# VillageCore

VillageCore は、Discord サーバー運営をまとめて支援する多機能 Bot です。

音楽、チケット、役職パネル、出席管理、投票、YouTube 通知、AI 応答、ミニゲーム、検索、ログ、管理パネルなどをまとめて扱えます。

English README: [README_EN.md](README_EN.md)

## Roles Guesser
Among Usの役職アキネーター・クイズ:Roles Guesser Botは[こちら](https://github.com/Shanpan2/VillageCore/blob/main/role_guesser/README.md)から

## リンク

- Bot 招待: https://discord.com/oauth2/authorize?client_id=1501521359963033741&permissions=1119110818992&integration_type=0&scope=bot+applications.commands
- ヘルプサイト: https://shanpan2.github.io/VillageCore/

## 主な機能

- `/game`: UNO、7並べ、大富豪、ポーカー、オセロ、Ito、コードネーム、人狼をボタンで操作
- `/music`: 音楽再生、停止、スキップ、キュー確認などをボタンで操作
- `/youtube`: YouTube 通知の設定と状態確認
- `/attendance`: 出席管理、ポイント一覧、警告確認
- `/admin`: 設定確認、権限診断、ログ設定、メンテナンス
- `/quick`: 日常用のショートカット
- チケット、役職パネル、投票、誕生日通知、NGワード、検索、AI 応答など

## ゲーム

ゲームは `/game` から選ぶのがおすすめです。募集作成、参加、抜ける、開始、中止、ルール確認をボタンで操作できます。

- Ito は主催者がお題を入力できます。空欄で作成した場合はランダムお題になります。
- コードネームは赤/青チーム参加とスパイマスター設定をパネルで行えます。
- 人狼は募集、参加、抜ける、開始、中止、ルール確認をパネルで行えます。夜行動と投票は対象指定が必要なため `/werewolf` を使います。
- 作成済みのゲーム状態はデータベースに保存され、再デプロイ後も続きから確認できます。

## セットアップ

このリポジトリには、Token、API Key、Cookie、データベースURLなどの秘密情報は含めていません。

必要な設定値は、Railway などのデプロイ先の Variables / Secrets に登録してください。

音楽再生でYouTube Cookieが必要な場合は、ファイルを配置するより `YTDLP_COOKIES_TEXT` に cookies.txt の内容を登録する運用を推奨します。Botは通常動画をCookieなしで取得し、必要な時だけCookieありで再試行します。

開発・運用時のセキュリティ注意は [SECURITY.md](SECURITY.md) を確認してください。

## 起動

```bash
pip install -r requirements.txt
python bot.py
```

Docker / Railway でのデプロイにも対応しています。
