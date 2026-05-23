# VillageCore

VillageCore は、Discord サーバー運営をまとめて支援する多機能 Bot です。

音楽、チケット、役職パネル、出席管理、投票、YouTube 通知、AI 応答、ミニゲーム、検索、ログ、管理パネルなどをまとめて扱えます。

English README: [README_EN.md](README_EN.md)

## リンク

- Bot 招待: https://discord.com/oauth2/authorize?client_id=1501521359963033741&permissions=1119110818992&integration_type=0&scope=bot+applications.commands
- ヘルプサイト: https://worker-production-9aed.up.railway.app/help

## 主な機能

- `/game`: UNO、7並べ、大富豪、ポーカーをボタンで操作
- `/music`: 音楽再生、停止、スキップ、キュー確認などをボタンで操作
- `/youtube`: YouTube 通知の設定と確認
- `/attendance`: 出席管理、ポイント一覧、警告確認
- `/admin`: 設定確認、権限診断、ログ設定、メンテナンス
- `/quick`: 日常用のショートカット
- チケット、役職パネル、投票、誕生日通知、NGワード、検索、AI 応答など

## セットアップ

このリポジトリには、Token、API Key、Cookie、データベースURLなどの秘密情報は含めていません。

必要な設定値は、Railway などのデプロイ先の Variables / Secrets に登録してください。公開 README には具体的な環境変数一覧や実値は記載していません。

## 起動

```bash
pip install -r requirements.txt
python bot.py
```

Docker / Railway でのデプロイにも対応しています。

## 注意

以下のようなファイルや値は公開しないでください。

- `.env`
- `cookies.txt`
- `config.json`
- `*.db`
- `*.sqlite`
- `ticket_logs/`
- Discord Bot Token
- API Key
- Database URL
- YouTube Cookie

もし秘密情報を誤って commit / push した場合は、該当する Token、API Key、Cookie を再発行してください。
