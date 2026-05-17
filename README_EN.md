# VillageCore

VillageCore is a multi-purpose Discord server management bot.

It includes music playback, tickets, role panels, attendance tracking, polls, YouTube notifications, AI replies, mini games, search, server logs, diagnostics, and backup tools.

Japanese README: [README.md](README.md)

## Features

- Music playback
- AI mention/reply responses
- Ticket creation, reopen, transcript export, archive channel, and channel deletion
- Multi-role role panels
- Attendance points and history
- Polls
- YouTube hashtag notifications with multiple keyword support
- DuckDuckGo search command
- Server logs
- NG word moderation
- Bot diagnostics and permission checks
- Backup export/import
- Birthday notifications
- Setup guide for new servers
- UNO, Sevens, Daifugo, Othello, Janken, Omikuji, and Dice

## Environment Variables

Required:

```env
DISCORD_TOKEN=your_discord_bot_token
DATABASE_URL=your_postgresql_url
GEMINI_API_KEY=your_gemini_api_key
YOUTUBE_API_KEY=your_youtube_data_api_key
```

Optional:

```env
YOUTUBE_NOTIFY_CHANNEL_ID=channel_id
YOUTUBE_NOTIFY_KEYWORD=#your-hashtag
YOUTUBE_CHECK_INTERVAL_MINUTES=10
PORT=8000
DASHBOARD_TOKEN=your_dashboard_password
```

## First Setup

After starting the bot, run these commands in Discord:

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

## Backup

Export all DB-backed settings and records:

```text
/backup_export
```

Restore from a backup JSON:

```text
/backup_import
```

Some restored settings are cached while the bot is running, so restart the bot after importing a backup.

## Web Dashboard

Set `DASHBOARD_TOKEN` to enable the read-only web dashboard.

```text
https://your-app-url/dashboard?token=your_dashboard_password
```

It shows bot status, DB status, environment-variable presence, guild count, and slash-command count.

## Security

Do not publish these files:

- `.env`
- `cookies.txt`
- `config.db`
- `attendance_backup.json`
- `ticket_logs/`

YouTube `cookies.txt` can contain private account data. Keep it out of public repositories.

If secrets were ever committed or pushed, regenerate the affected tokens, API keys, and cookies.

## Run

```bash
pip install -r requirements.txt
python bot.py
```

Docker deployment is supported with the included `Dockerfile`.
