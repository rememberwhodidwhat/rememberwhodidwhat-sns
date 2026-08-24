# rememberwhodidwhat-sns

[RememberWhoDidWhat](https://rememberwhodidwhat.github.io) の「今日は何の日？」を毎日 Bluesky に自動投稿する。

## 仕組み

- `events.json` — 公開対象の事件から `date` / `slug` / `title` のみを抽出したデータ。
  RememberWhoDidWhat リポジトリ（private）で `uv run build/generate_metadata_case.py <出力先>` を実行して生成し、
  このリポジトリに手動でコピー・commit・push する。
- `.github/workflows/post.yml` — 毎日 08:00 JST に `post_today.py` を実行する GitHub Actions ワークフロー
  （`workflow_dispatch` で手動実行も可能）。
- `post_today.py` — `events.json` から今日（JST）の月日に一致する事件を抽出し、[atproto](https://pypi.org/project/atproto/)
  経由で Bluesky に1件ずつ個別投稿する（複数該当時はスレッドにせず順次投稿）。

## セットアップ

1. Bluesky で投稿用アカウントの [App Password](https://bsky.app/settings/app-passwords) を発行する（本パスワードは使わない）。
2. このリポジトリの Settings → Secrets and variables → Actions に以下を登録する。
   - `BLUESKY_HANDLE`（例: `example.bsky.social`）
   - `BLUESKY_APP_PASSWORD`
3. `events.json` を最新化する場合は RememberWhoDidWhat 側で以下を実行し、出力ファイルをこのリポジトリにコピーして push する。

   ```sh
   uv run build/generate_metadata_case.py <出力先ファイル>
   ```

## 手動実行

Actions タブから `Post today's events to Bluesky` ワークフローを `workflow_dispatch` で実行する。
