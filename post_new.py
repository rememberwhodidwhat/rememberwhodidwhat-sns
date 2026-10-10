#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "atproto",
# ]
# ///
"""指定コミット時点の events.json と現在の events.json を比較し、新規 slug の事件を Bluesky へ1件ずつ個別に投稿する。

使い方:
    uv run post_new.py <比較元のコミット>

環境変数:
    BLUESKY_HANDLE        投稿アカウントのハンドル（例: example.bsky.social）
    BLUESKY_APP_PASSWORD  Bluesky の App Password（本パスワードは使わない）
"""

import json
import os
import subprocess
import sys

from atproto import Client, client_utils

from post_today import EVENTS_FILE, SITE_URL, format_date


def load_old_slugs(base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:events.json"],
        cwd=EVENTS_FILE.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        # 比較元に events.json が存在しない場合、全件投稿を避けるため中断する
        print(f"{base_ref} の events.json を読めません: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return {e["slug"] for e in json.loads(result.stdout)}


def load_new_events(base_ref: str) -> list[dict]:
    old_slugs = load_old_slugs(base_ref)
    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    matches = [e for e in events if e["slug"] not in old_slugs]
    return sorted(matches, key=lambda e: e["date"])


def build_post(event: dict) -> client_utils.TextBuilder:
    url = f"{SITE_URL}/case/{event['slug']}/"
    tb = client_utils.TextBuilder()
    tb.text(f"【新規追加】{format_date(event['date'])}、{event['title']}\n")
    tb.link(url, url)
    return tb


def main() -> None:
    if len(sys.argv) != 2:
        print(f"使い方: {sys.argv[0]} <比較元のコミット>", file=sys.stderr)
        sys.exit(1)
    base_ref = sys.argv[1]

    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("BLUESKY_HANDLE / BLUESKY_APP_PASSWORD が未設定です", file=sys.stderr)
        sys.exit(1)

    new_events = load_new_events(base_ref)
    if not new_events:
        print("新規追加された事件はありません")
        return

    client = Client()
    client.login(handle, app_password)

    for event in new_events:
        post = build_post(event)
        client.send_post(post)
        print(f"投稿しました: {event['slug']}")


if __name__ == "__main__":
    main()
