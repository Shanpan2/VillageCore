# Security

このファイルは、VillageCore を開発・運用する人向けのセキュリティメモです。

## 公開しないもの

以下のファイルや値は、GitHub や公開チャンネルに載せないでください。

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

## 秘密情報の扱い

Token、API Key、Cookie、Database URL などは、Railway などのデプロイ先の Variables / Secrets に登録してください。

README、ソースコード、Issue、Pull Request、Discord の公開チャンネルには実値を書かないでください。

## 漏えいした場合

秘密情報を誤って commit / push した場合は、削除だけでは不十分です。

該当する Token、API Key、Cookie を再発行してください。

特に Discord Bot Token が漏れた場合は、Discord Developer Portal で Token を再生成し、デプロイ先の環境変数も更新してください。

---

# Security Policy

This file is a security note for VillageCore developers and operators.

## Do Not Publish

Do not publish files or values such as:

- `.env`
- `cookies.txt`
- `config.json`
- `*.db`
- `*.sqlite`
- `ticket_logs/`
- Discord Bot Token
- API keys
- Database URL
- YouTube cookies

## Handling Secrets

Store tokens, API keys, cookies, and database URLs in your deployment provider's Variables / Secrets page, such as Railway.

Do not write real secret values in README files, source code, issues, pull requests, or public Discord channels.

## If Secrets Are Leaked

Deleting leaked secrets from the repository is not enough.

Regenerate the affected tokens, API keys, and cookies.

If a Discord Bot Token is leaked, reset it in the Discord Developer Portal and update the deployment environment variable.
