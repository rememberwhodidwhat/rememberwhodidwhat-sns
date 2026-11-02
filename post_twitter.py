#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""events.json の事件を Buffer の GraphQL API 経由で Twitter へ投稿する。

使い方:
    uv run post_twitter.py today                  今日（JST）の月日に一致する事件を投稿する
    uv run post_twitter.py new <比較元のコミット>  比較元の events.json になかった slug の事件を投稿する

対象が SUMMARY_THRESHOLD 件以下なら Bluesky と同じ形式（本文＋事件ページの URL＋ハッシュタグ）で1件ずつ、
それより多ければタイトルを箇条書きにしたまとめ投稿を1件だけ投稿する。

環境変数:
    BUFFER_API_KEY     Buffer の API キー
    BUFFER_CHANNEL_ID  投稿先の Twitter チャンネルの ID
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime

from common import (
    JST,
    SITE_URL,
    event_hashtags,
    event_url,
    fit_hashtags,
    load_new_events,
    load_todays_events,
    new_headline,
    today_headline,
)

# Twitter の投稿文字数上限（twitter-text v3 の重み付き文字数）
MAX_POST_LENGTH = 280
# URL は長さによらずこの重みで数える（t.co 短縮後の長さ）
URL_WEIGHT = 23
# 重み 1 で数える文字の範囲（twitter-text v3 の既定設定）。それ以外は重み 2
LIGHT_RANGES = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))
URL_PATTERN = re.compile(r"https?://\S+")
# 対象がこの件数を超えたら、1件ずつではなくまとめ投稿を1件だけ出す
SUMMARY_THRESHOLD = 10
ELLIPSIS = "…"

BUFFER_API_URL = "https://api.buffer.com"
CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id status } }
    ... on MutationError { message }
  }
}
"""


def char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in LIGHT_RANGES) else 2


def weighted_length(text: str) -> int:
    """twitter-text v3 の重み付けで文字数を数える。http(s) で始まる URL は一律 URL_WEIGHT とする。

    スキームなしのドメイン（example.com など）の自動リンクは考慮しない（events.json には現れない）。
    """
    text = unicodedata.normalize("NFC", text)
    length = 0
    pos = 0
    for m in URL_PATTERN.finditer(text):
        length += sum(char_weight(c) for c in text[pos : m.start()]) + URL_WEIGHT
        pos = m.end()
    return length + sum(char_weight(c) for c in text[pos:])


def truncate_to_fit(title: str, render: Callable[[str], str]) -> str:
    """render(title) が上限に収まるよう、タイトルを末尾から削って「…」を付ける。"""
    if weighted_length(render(title)) <= MAX_POST_LENGTH:
        return title
    for end in range(len(title) - 1, -1, -1):
        shortened = title[:end] + ELLIPSIS
        if weighted_length(render(shortened)) <= MAX_POST_LENGTH:
            return shortened
    return ELLIPSIS


def build_single_post(event: dict, headline: Callable[[str], str]) -> str:
    """Bluesky と同じ形式の投稿文。headline はタイトルを受け取り見出し文を返す。

    上限を超える場合はハッシュタグを末尾から省き、それでも超える場合はタイトルを「…」で切り詰める。
    """
    url = event_url(event)
    title = truncate_to_fit(event["title"], lambda t: f"{headline(t)}\n{url}")
    text = f"{headline(title)}\n{url}"
    for separator, tag in fit_hashtags(event_hashtags(event), weighted_length(text), MAX_POST_LENGTH, weighted_length):
        text += f"{separator}#{tag}"
    return text


def build_summary_post(heading: str, events: list[dict]) -> str:
    """見出し＋タイトルの箇条書き（日付順に入るだけ）＋「ほか M件」＋サイトの URL のまとめ投稿。"""
    lines = [heading]
    for i, event in enumerate(events):
        rest = len(events) - i - 1
        candidate = lines + [f"・{event['title']}"]
        footer = ([f"ほか {rest}件"] if rest else []) + [SITE_URL]
        if weighted_length("\n".join(candidate + footer)) > MAX_POST_LENGTH:
            break
        lines = candidate
    rest = len(events) - (len(lines) - 1)
    footer = ([f"ほか {rest}件"] if rest else []) + [SITE_URL]
    return "\n".join(lines + footer)


def build_posts(events: list[dict], headline: Callable[[dict, str], str], heading: str) -> list[tuple[str, str]]:
    """投稿する (ラベル, 投稿文) の一覧。件数が SUMMARY_THRESHOLD を超えたらまとめ投稿1件にする。"""
    if len(events) > SUMMARY_THRESHOLD:
        return [(f"まとめ（{len(events)}件）", build_summary_post(heading, events))]
    return [(e["slug"], build_single_post(e, lambda t, e=e: headline(e, t))) for e in events]


def build_today_posts(events: list[dict], today: datetime) -> list[tuple[str, str]]:
    heading = f"今日（{today.month}月{today.day}日）の出来事（全{len(events)}件）"
    return build_posts(events, lambda e, t: today_headline(e, today, t), heading)


def build_new_posts(events: list[dict]) -> list[tuple[str, str]]:
    return build_posts(events, lambda e, t: new_headline(e, t), f"【新規追加】{len(events)}件")


class BufferError(Exception):
    pass


def post_to_buffer(text: str, api_key: str, channel_id: str) -> str:
    """Buffer に即時投稿し、投稿 ID を返す。失敗時は BufferError を送出する。

    Buffer はエラー時も HTTP 200 を返すため、errors 配列と MutationError の message で判定する。
    """
    body = json.dumps(
        {
            "query": CREATE_POST_MUTATION,
            "variables": {
                "input": {
                    "text": text,
                    "channelId": channel_id,
                    "schedulingType": "automatic",
                    "mode": "shareNow",
                }
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        BUFFER_API_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BufferError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise BufferError(str(e)) from e

    if payload.get("errors"):
        raise BufferError("; ".join(err.get("message", str(err)) for err in payload["errors"]))
    result = (payload.get("data") or {}).get("createPost") or {}
    if "message" in result:
        raise BufferError(result["message"])
    post = result.get("post")
    if not post:
        raise BufferError(f"想定外の応答: {payload}")
    return f"{post.get('id')} ({post.get('status')})"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="events.json の事件を Buffer 経由で Twitter に投稿する")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("today", help="今日（JST）の月日に一致する事件を投稿する")
    new = sub.add_parser("new", help="比較元になかった slug の事件を投稿する")
    new.add_argument("base_ref", help="比較元のコミット")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = os.environ.get("BUFFER_API_KEY")
    channel_id = os.environ.get("BUFFER_CHANNEL_ID")
    if not api_key or not channel_id:
        print("BUFFER_API_KEY / BUFFER_CHANNEL_ID が未設定です", file=sys.stderr)
        sys.exit(1)

    if args.mode == "today":
        today = datetime.now(JST)
        events = load_todays_events(today)
        if not events:
            print(f"{today.month}月{today.day}日に該当する事件はありません")
            return
        posts = build_today_posts(events, today)
    else:
        events = load_new_events(args.base_ref)
        if not events:
            print("新規追加された事件はありません")
            return
        posts = build_new_posts(events)

    failed = 0
    for label, text in posts:
        try:
            post_id = post_to_buffer(text, api_key, channel_id)
            print(f"投稿しました: {label} → {post_id}")
        except Exception as e:  # 1件の失敗で残りを止めない
            failed += 1
            print(f"投稿に失敗しました: {label}: {type(e).__name__}: {e}", file=sys.stderr)

    if failed:
        print(f"{len(posts)} 件中 {failed} 件の投稿に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
