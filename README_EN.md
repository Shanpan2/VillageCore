# VillageCore

VillageCore is a multi-purpose Discord bot for community and server management.

It includes music controls, tickets, role panels, attendance tracking, polls, YouTube notifications, AI replies, mini games, search, logs, and admin panels.

Japanese README: [README.md](README.md)

## Links

- Bot Invite: https://discord.com/oauth2/authorize?client_id=1501521359963033741&permissions=1119110818992&integration_type=0&scope=bot+applications.commands
- Help Site: https://worker-production-9aed.up.railway.app/help

## Features

- `/game`: button-based game panel for UNO, Sevens, Daifugo, and Poker
- `/music`: button-based music controls
- `/youtube`: YouTube notification settings and status
- `/attendance`: attendance tracking and warning checks
- `/admin`: settings, permission checks, logs, and maintenance tools
- `/quick`: daily shortcuts
- Tickets, role panels, polls, birthdays, NG words, search, and AI replies

## Setup

This repository does not include secrets such as tokens, API keys, cookies, or database URLs.

Set required values in your deployment provider's Variables / Secrets page, such as Railway. Detailed environment variable names and real values are intentionally not listed in this public README.

## Run

```bash
pip install -r requirements.txt
python bot.py
```

Docker / Railway deployment is supported.

## Security

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

If secrets were ever committed or pushed, regenerate the affected tokens, API keys, and cookies.
