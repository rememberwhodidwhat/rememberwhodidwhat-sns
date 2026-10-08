#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "atproto",
# ]
# ///
"""events.json から今日（JST）の月日に一致する事件を抽出し、Bluesky へ1件ずつ個別に投稿する。

events.json は RememberWhoDidWhat リポジトリの
`uv run build/rememberwhodidwhat-sns.py <このリポジトリのディレクトリ>` で直接書き出し、手動で commit・push する。

環境変数:
    BLUESKY_HANDLE        投稿アカウントのハンドル（例: example.bsky.social）
    BLUESKY_APP_PASSWORD  Bluesky の App Password（本パスワードは使わない）
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from atproto import Client, client_utils

SITE_URL = "https://rememberwhodidwhat.github.io"
EVENTS_FILE = Path(__file__).parent / "events.json"
JST = ZoneInfo("Asia/Tokyo")


def load_todays_events(today: datetime) -> list[dict]:
    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    matches = [
        e for e in events
        if int(e["date"][5:7]) == today.month and int(e["date"][8:10]) == today.day
    ]
    return sorted(matches, key=lambda e: e["date"])


def build_post(event: dict, today: datetime) -> client_utils.TextBuilder:
    years_ago = today.year - int(event["date"][:4])
    url = f"{SITE_URL}/case/{event['slug']}/"
    tb = client_utils.TextBuilder()
    if years_ago <= 0:
        tb.text(f"今日は「{event['title']}」の日\n")
    else:
        tb.text(f"{years_ago}年前の今日、{event['title']}\n")
    tb.link(url, url)
    return tb


def main() -> None:
    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("BLUESKY_HANDLE / BLUESKY_APP_PASSWORD が未設定です", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(JST)
    todays_events = load_todays_events(today)
    if not todays_events:
        print(f"{today.month}月{today.day}日に該当する事件はありません")
        return

    client = Client()
    client.login(handle, app_password)

    for event in todays_events:
        post = build_post(event, today)
        client.send_post(post)
        print(f"投稿しました: {event['slug']}")


if __name__ == "__main__":
    main()
