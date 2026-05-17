# VillageCore

VillageCore は、Discordサーバー運営向けの多機能Botです。

音楽再生、チケット、役職パネル、出席管理、投票、YouTube通知、AI応答、ミニゲーム、検索、サーバーログ、診断、バックアップなどをまとめて扱えます。

English README: [README_EN.md](README_EN.md)

## 主な機能

- 音楽再生
- メンション/リプライによるAI応答
- チケット作成、再オープン、ログ保存、ログ送信先設定、チャンネル削除
- 複数ロール対応の役職パネル
- 出席ポイントと履歴管理
- 投票
- 複数ハッシュタグ対応のYouTube通知
- DuckDuckGo検索
- サーバーログ
- NGワード管理
- Bot診断、権限チェック
- バックアップ/復元
- 誕生日通知
- 初期設定ガイド
- UNO、7並べ、オセロ、じゃんけん、おみくじ、ダイス

## 必要な環境変数

```env
DISCORD_TOKEN=your_discord_bot_token
DATABASE_URL=your_postgresql_url
GEMINI_API_KEY=your_gemini_api_key
YOUTUBE_API_KEY=your_youtube_data_api_key
```

任意:

```env
YOUTUBE_NOTIFY_CHANNEL_ID=channel_id
YOUTUBE_NOTIFY_KEYWORD=#おちゃめ村
YOUTUBE_CHECK_INTERVAL_MINUTES=10
PORT=8000
DASHBOARD_TOKEN=your_dashboard_password
```

## 初期設定

Bot起動後、Discordサーバー内で以下を実行してください。

```text
/bot_status
/permission_check
/server_log_channel
/ng_word_add
/ticket_log_channel
/youtube_notify_channel
/youtube_notify_keywords
/backup_export
/birthday_channel
/setup_guide
```

## バックアップ

DBに保存している設定や記録をJSONで出力します。

```text
/backup_export
```

バックアップJSONから復元します。

```text
/backup_import
```

復元後、一部機能はBot再起動後に反映されます。

## Webダッシュボード

`DASHBOARD_TOKEN` を設定すると、読み取り専用の簡易ダッシュボードを利用できます。

```text
https://your-app-url/dashboard?token=your_dashboard_password
```

Bot状態、DB状態、環境変数の有無、参加サーバー数、登録コマンド数を確認できます。

## 注意

以下のファイルは公開しないでください。

- `.env`
- `cookies.txt`
- `config.db`
- `attendance_backup.json`
- `ticket_logs/`

YouTubeの `cookies.txt` には個人アカウント情報が含まれる可能性があります。公開リポジトリには含めないでください。

過去に秘密情報をコミットまたはpushした場合は、該当するトークン、APIキー、Cookieを再生成してください。

## 起動

```bash
pip install -r requirements.txt
python bot.py
```

Docker環境では同梱の `Dockerfile` を利用できます。
