# rememberwhodidwhat-sns

[RememberWhoDidWhat](https://rememberwhodidwhat.github.io) の「今日は何の日？」を毎日 Bluesky と Twitter に自動投稿する。

## 仕組み

- `events.json` — 公開対象の事件から `date` / `slug` / `title` / `people` / `organizations` のみを抽出したデータ。
  `people` / `organizations` はサイトにページがある人物・団体名で、投稿末尾にハッシュタグとして付ける
  （括弧書き・空白は除き、文字数の上限を超える分は省略する）。
  `date` は判明している精度のまま `YYYY-MM-DD` / `YYYY-MM` / `YYYY` で記録する。
  RememberWhoDidWhat リポジトリ（private）で `uv run build/rememberwhodidwhat-sns.py <このリポジトリのディレクトリ>` を実行して
  このリポジトリの `events.json` に直接書き出し、手動で commit・push する。
- `.github/workflows/post_today_bluesky.yml` / `post_today_twitter.yml` — 毎日 12:00 JST に
  `post_bluesky.py today` / `post_twitter.py today` を実行する GitHub Actions ワークフロー（`workflow_dispatch` で手動実行も可能）。
- `.github/workflows/post_new_bluesky.yml` / `post_new_twitter.yml` — `main` への push で `events.json` が変更されたときに、
  push 前のコミットを比較元として `post_bluesky.py new` / `post_twitter.py new` を実行する。
- Bluesky と Twitter はワークフローを分けているので、片方の投稿が失敗してももう片方には影響しない。
- `post_bluesky.py` / `post_twitter.py` — それぞれ Bluesky / Twitter に投稿するスクリプト。どちらも次の2モードを持つ。
  - `today` — `events.json` から今日（JST）の月日に一致する事件を投稿する。
    日が不明な事件（`YYYY-MM`）はその月の1日、月日が不明な事件（`YYYY`）は1月1日に投稿する。
  - `new <比較元のコミット>` — 比較元の `events.json` と比べ、新規追加された slug の事件を投稿する。
- `post_bluesky.py` — [atproto](https://pypi.org/project/atproto/) 経由で Bluesky に1件ずつ個別投稿する
  （複数該当時はスレッドにせず順次投稿）。
- `post_twitter.py` — [Buffer](https://buffer.com) の GraphQL API 経由で Twitter に投稿する
  （Twitter API は従量課金のため使わない）。標準ライブラリのみで動く。

  投稿文の上限は twitter-text v3 の重み付き文字数で 280（日本語は1文字 2、URL は一律 23）。
  対象の件数によって投稿のしかたを変える（しきい値は `post_twitter.py` の `SUMMARY_THRESHOLD`）。
  - **10件以下**: Bluesky と同じ形式（本文＋事件ページの URL＋ハッシュタグ）で1件ずつ投稿する。
    上限を超える分はハッシュタグを末尾から省き、それでも超える場合はタイトルを「…」で切り詰める。
    連続投稿がスパムと判定されにくいよう、投稿の間に 60 秒ずつ待つ（`POST_INTERVAL_SECONDS`）。
  - **11件以上**: 見出し（「今日（1月31日）の出来事（全63件）」「【新規追加】46件」）、入るだけのタイトルの箇条書き（日付順）、
    「ほか M件」、サイトの URL からなるまとめ投稿を1件だけ投稿する。

  Buffer の Free プランの上限は 24時間あたり 100 リクエスト、15分あたり 100 リクエスト。
- `common.py` — 日付の解析・整形、ハッシュタグの整形、事件の抽出、見出し文の生成など、各スクリプトの共通処理。

## セットアップ

1. Bluesky で投稿用アカウントの [App Password](https://bsky.app/settings/app-passwords) を発行する（本パスワードは使わない）。
2. Buffer に投稿先の Twitter アカウントをチャンネルとして接続し、API キーを発行して、そのチャンネルの ID を控える。
3. このリポジトリの Settings → Secrets and variables → Actions に以下を登録する。
   - `BLUESKY_HANDLE`（例: `example.bsky.social`）
   - `BLUESKY_APP_PASSWORD`
   - `BUFFER_API_KEY` — Buffer の API キー
   - `BUFFER_CHANNEL_ID` — 投稿先の Twitter チャンネルの ID
4. `events.json` を最新化する場合は RememberWhoDidWhat 側で以下を実行し、このリポジトリで commit・push する。

   ```sh
   uv run build/rememberwhodidwhat-sns.py ~/Git/rememberwhodidwhat-sns
   ```

## 手動実行

Actions タブから `Post today's events to Bluesky` / `Post today's events to Twitter` ワークフローを
`workflow_dispatch` で実行する。Twitter だけ動作確認したい場合は後者だけを実行すればよい。
