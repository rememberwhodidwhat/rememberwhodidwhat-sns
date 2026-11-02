#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "atproto",
# ]
# ///
"""events.json の事件を Bluesky へ1件ずつ個別に投稿する。

使い方:
    uv run post_bluesky.py today                  今日（JST）の月日に一致する事件を投稿する
    uv run post_bluesky.py new <比較元のコミット>  比較元の events.json になかった slug の事件を投稿する

today モードでは、date が YYYY-MM（日が不明）の事件はその月の1日、YYYY（月日が不明）の事件は1月1日に投稿する。

events.json は RememberWhoDidWhat リポジトリの
`uv run build/rememberwhodidwhat-sns.py <このリポジトリのディレクトリ>` で直接書き出し、手動で commit・push する。

環境変数:
    BLUESKY_HANDLE        投稿アカウントのハンドル（例: example.bsky.social）
    BLUESKY_APP_PASSWORD  Bluesky の App Password（本パスワードは使わない）
"""

import argparse
import os
import sys
from datetime import datetime

from atproto import Client, client_utils

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

# Bluesky の投稿文字数上限（grapheme 単位）。日本語・ASCII のみなら len() で近似できる
MAX_POST_LENGTH = 300


def add_hashtags(tb: client_utils.TextBuilder, event: dict, length: int) -> None:
    """事件の人物・団体をハッシュタグとして末尾に追記する。投稿文字数上限を超えるものは省略する。"""
    for separator, tag in fit_hashtags(event_hashtags(event), length, MAX_POST_LENGTH):
        tb.text(separator)
        tb.tag(f"#{tag}", tag)


def build_post(event: dict, headline: str) -> client_utils.TextBuilder:
    """見出し文＋事件ページの URL＋ハッシュタグの投稿を組み立てる。"""
    url = event_url(event)
    tb = client_utils.TextBuilder()
    tb.text(f"{headline}\n")
    tb.link(url, url)
    add_hashtags(tb, event, len(tb.build_text()))
    return tb


def build_today_post(event: dict, today: datetime) -> client_utils.TextBuilder:
    return build_post(event, today_headline(event, today))


def build_new_post(event: dict) -> client_utils.TextBuilder:
    return build_post(event, new_headline(event))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="events.json の事件を Bluesky に投稿する")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("today", help="今日（JST）の月日に一致する事件を投稿する")
    new = sub.add_parser("new", help="比較元になかった slug の事件を投稿する")
    new.add_argument("base_ref", help="比較元のコミット")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("BLUESKY_HANDLE / BLUESKY_APP_PASSWORD が未設定です", file=sys.stderr)
        sys.exit(1)

    if args.mode == "today":
        today = datetime.now(JST)
        events = load_todays_events(today)
        if not events:
            print(f"{today.month}月{today.day}日に該当する事件はありません")
            return
        posts = [(e["slug"], build_today_post(e, today)) for e in events]
    else:
        events = load_new_events(args.base_ref)
        if not events:
            print("新規追加された事件はありません")
            return
        posts = [(e["slug"], build_new_post(e)) for e in events]

    client = Client()
    client.login(handle, app_password)

    for slug, post in posts:
        client.send_post(post)
        print(f"投稿しました: {slug}")


if __name__ == "__main__":
    main()
