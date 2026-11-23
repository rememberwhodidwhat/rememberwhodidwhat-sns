#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""events.json の事件を Mastodon へ1件ずつ個別に投稿する。

使い方:
    uv run post_mastodon.py today                  今日（JST）の月日に一致する事件を投稿する
    uv run post_mastodon.py new <比較元のコミット>  比較元の events.json になかった slug の事件を投稿する

投稿形式は Bluesky と同じ（見出し文＋事件ページの URL＋ハッシュタグ）。標準ライブラリのみで動く。

環境変数:
    MASTODON_BASE_URL      インスタンスの URL（例: https://mstdn.jp）
    MASTODON_ACCESS_TOKEN  write:statuses スコープを持つアクセストークン
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from common import (
    JST,
    event_hashtags,
    event_url,
    fit_hashtags,
    load_new_events,
    load_todays_events,
    new_headline,
    today_headline,
)

# 投稿文字数上限（mstdn.jp の /api/v2/instance の configuration.statuses.max_characters）
MAX_POST_LENGTH = 500
# URL は長さによらずこの文字数で数える（configuration.statuses.characters_reserved_per_url）
URL_LENGTH = 23
URL_PATTERN = re.compile(r"https?://\S+")
VISIBILITY = "public"
LANGUAGE = "ja"


def post_length(text: str) -> int:
    """Mastodon の数え方で文字数を数える（http(s) の URL は一律 URL_LENGTH）。"""
    return len(URL_PATTERN.sub("x" * URL_LENGTH, text))


def build_post(event: dict, headline: str) -> str:
    """見出し文＋事件ページの URL＋ハッシュタグの投稿文を組み立てる。"""
    text = f"{headline}\n{event_url(event)}"
    for separator, tag in fit_hashtags(event_hashtags(event), post_length(text), MAX_POST_LENGTH, post_length):
        text += f"{separator}#{tag}"
    return text


def build_today_post(event: dict, today: datetime) -> str:
    return build_post(event, today_headline(event, today))


def build_new_post(event: dict) -> str:
    return build_post(event, new_headline(event))


class MastodonError(Exception):
    pass


def post_to_mastodon(text: str, base_url: str, access_token: str, idempotency_key: str) -> str:
    """投稿して投稿の URL を返す。失敗時は MastodonError を送出する。

    Idempotency-Key により、同じキーでの再送は1時間以内なら重複投稿にならない。
    """
    body = urllib.parse.urlencode({"status": text, "visibility": VISIBILITY, "language": LANGUAGE}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/statuses",
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise MastodonError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise MastodonError(str(e)) from e
    return payload.get("url") or payload.get("id") or str(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="events.json の事件を Mastodon に投稿する")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("today", help="今日（JST）の月日に一致する事件を投稿する")
    new = sub.add_parser("new", help="比較元になかった slug の事件を投稿する")
    new.add_argument("base_ref", help="比較元のコミット")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    base_url = os.environ.get("MASTODON_BASE_URL")
    access_token = os.environ.get("MASTODON_ACCESS_TOKEN")
    if not base_url or not access_token:
        print("MASTODON_BASE_URL / MASTODON_ACCESS_TOKEN が未設定です", file=sys.stderr)
        sys.exit(1)

    if args.mode == "today":
        today = datetime.now(JST)
        events = load_todays_events(today)
        if not events:
            print(f"{today.month}月{today.day}日に該当する事件はありません")
            return
        key_prefix = f"today:{today:%Y-%m-%d}"
        posts = [(e["slug"], build_today_post(e, today)) for e in events]
    else:
        events = load_new_events(args.base_ref)
        if not events:
            print("新規追加された事件はありません")
            return
        key_prefix = f"new:{args.base_ref}"
        posts = [(e["slug"], build_new_post(e)) for e in events]

    failed = 0
    for slug, text in posts:
        key = hashlib.sha256(f"{key_prefix}:{slug}".encode("utf-8")).hexdigest()
        try:
            url = post_to_mastodon(text, base_url, access_token, key)
            print(f"投稿しました: {slug} → {url}")
        except Exception as e:  # 1件の失敗で残りを止めない
            failed += 1
            print(f"投稿に失敗しました: {slug}: {type(e).__name__}: {e}", file=sys.stderr)

    if failed:
        print(f"{len(posts)} 件中 {failed} 件の投稿に失敗しました", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
