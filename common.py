"""Bluesky / Twitter 投稿スクリプトの共通処理（外部依存なし）。

日付の解析・整形、ハッシュタグの整形、今日の事件・新規事件の抽出、見出し文の生成を行う。
"""

import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


def event_url(event: dict) -> str:
    return f"{SITE_URL}/case/{event['slug']}/"


def load_events() -> list[dict]:
    return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))


def load_todays_events(today: datetime) -> list[dict]:
    """今日の月日に一致する事件を日付順に返す。日が不明なら月の1日、月日が不明なら1月1日として扱う。"""
    matches = []
    for e in load_events():
        _, month, day = parse_date(e["date"])
        if (month or 1) == today.month and (day or 1) == today.day:
            matches.append(e)
    return sorted(matches, key=lambda e: e["date"])


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
    """base_ref 時点の events.json になかった slug の事件を日付順に返す。"""
    old_slugs = load_old_slugs(base_ref)
    matches = [e for e in load_events() if e["slug"] not in old_slugs]
    return sorted(matches, key=lambda e: e["date"])


def hashtag(name: str) -> str:
    """人物・団体名をハッシュタグ用に整形する（「X (Twitter)」→「X」のように括弧書きと空白を除く）。"""
    return re.sub(r"\s+", "", re.sub(r"\s*[(（][^)）]*[)）]", "", name))


def event_hashtags(event: dict) -> list[str]:
    """事件の人物・団体を、重複を除いたハッシュタグ名（# なし）の一覧にする。"""
    return list(dict.fromkeys(hashtag(n) for n in event.get("people", []) + event.get("organizations", [])))


def fit_hashtags(
    tags: list[str], length: int, max_length: int, measure: Callable[[str], int] = len
) -> list[tuple[str, str]]:
    """本文の長さ length に続けて入るハッシュタグを先頭から選び、(区切り文字, タグ名) の一覧で返す。

    最初のタグの前は改行、以降は空白で区切る。上限を超えるタグは飛ばす（後続の短いタグは入れば入れる）。
    """
    result = []
    separator = "\n"
    for tag in tags:
        if not tag:
            continue
        added = measure(separator) + measure(f"#{tag}")
        if length + added > max_length:
            continue
        result.append((separator, tag))
        length += added
        separator = " "
    return result


def today_headline(event: dict, today: datetime, title: str | None = None) -> str:
    """「N年前の今日、…」などの見出し文（末尾の改行なし）。title を渡すと事件タイトルの代わりに使う。"""
    title = event["title"] if title is None else title
    year, month, day = parse_date(event["date"])
    years_ago = today.year - year
    if day is not None:
        if years_ago <= 0:
            return f"今日は「{title}」の日"
        return f"{years_ago}年前の今日、{title}"
    # 日付が不明な事件は月の1日（月も不明なら1月1日）に「○年前の○月」「○年前」として投稿する
    when = "今年" if years_ago <= 0 else f"{years_ago}年前"
    if month is not None:
        when += f"の{month}月"
    return f"{when}、{title}"


def new_headline(event: dict, title: str | None = None) -> str:
    """「【新規追加】YYYY年M月D日、…」の見出し文（末尾の改行なし）。"""
    title = event["title"] if title is None else title
    return f"【新規追加】{format_date(event['date'])}、{title}"
