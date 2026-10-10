#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "atproto",
# ]
# ///
"""events.json から今日（JST）の月日に一致する事件を抽出し、Bluesky へ1件ずつ個別に投稿する。

date が YYYY-MM（日が不明）の事件はその月の1日、YYYY（月日が不明）の事件は1月1日に投稿する。

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


def parse_date(date: str) -> tuple[int, int | None, int | None]:
    """YYYY-MM-DD / YYYY-MM / YYYY を (年, 月, 日) に分解する。不明な部分は None。"""
    parts = [int(x) for x in date.split("-")]
    return (parts[0], parts[1] if len(parts) > 1 else None, parts[2] if len(parts) > 2 else None)


def format_date(date: str) -> str:
    year, month, day = parse_date(date)
    if month is None:
        return f"{year}年"
    if day is None:
        return f"{year}年{month}月"
    return f"{year}年{month}月{day}日"


def load_todays_events(today: datetime) -> list[dict]:
    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    matches = []
    for e in events:
        _, month, day = parse_date(e["date"])
        if (month or 1) == today.month and (day or 1) == today.day:
            matches.append(e)
    return sorted(matches, key=lambda e: e["date"])


def build_post(event: dict, today: datetime) -> client_utils.TextBuilder:
    year, month, day = parse_date(event["date"])
    years_ago = today.year - year
    url = f"{SITE_URL}/case/{event['slug']}/"
    tb = client_utils.TextBuilder()
    if day is not None:
        if years_ago <= 0:
            tb.text(f"今日は「{event['title']}」の日\n")
        else:
            tb.text(f"{years_ago}年前の今日、{event['title']}\n")
    else:
        # 日付が不明な事件は月の1日（月も不明なら1月1日）に「○年前の○月」「○年前」として投稿する
        when = "今年" if years_ago <= 0 else f"{years_ago}年前"
        if month is not None:
            when += f"の{month}月"
        tb.text(f"{when}、{event['title']}\n")
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
