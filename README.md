# rememberwhodidwhat-sns

[RememberWhoDidWhat](https://rememberwhodidwhat.github.io) の「今日は何の日？」を毎日 Bluesky に自動投稿する。

## 仕組み

- `events.json` — 公開対象の事件から `date` / `slug` / `title` のみを抽出したデータ。
  RememberWhoDidWhat リポジトリ（private）で `uv run build/rememberwhodidwhat-sns.py <このリポジトリのディレクトリ>` を実行して
  このリポジトリの `events.json` に直接書き出し、手動で commit・push する。
- `.github/workflows/post.yml` — 毎日 08:00 JST に `post_today.py` を実行する GitHub Actions ワークフロー
  （`workflow_dispatch` で手動実行も可能）。
- `post_today.py` — `events.json` から今日（JST）の月日に一致する事件を抽出し、[atproto](https://pypi.org/project/atproto/)
  経由で Bluesky に1件ずつ個別投稿する（複数該当時はスレッドにせず順次投稿）。
- `.github/workflows/post_new.yml` — `main` への push で `events.json` が変更されたときに `post_new.py` を実行する。
- `post_new.py` — push 前のコミットの `events.json` と比較し、新規追加された slug の事件を Bluesky に1件ずつ投稿する。

## セットアップ

1. Bluesky で投稿用アカウントの [App Password](https://bsky.app/settings/app-passwords) を発行する（本パスワードは使わない）。
2. このリポジトリの Settings → Secrets and variables → Actions に以下を登録する。
   - `BLUESKY_HANDLE`（例: `example.bsky.social`）
   - `BLUESKY_APP_PASSWORD`
3. `events.json` を最新化する場合は RememberWhoDidWhat 側で以下を実行し、このリポジトリで commit・push する。

   ```sh
   uv run build/rememberwhodidwhat-sns.py ~/Git/rememberwhodidwhat-sns
   ```

## 手動実行

Actions タブから `Post today's events to Bluesky` ワークフローを `workflow_dispatch` で実行する。
