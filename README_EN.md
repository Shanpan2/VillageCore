# VillageCore

VillageCore is a multi-purpose Discord bot for community and server management.

It includes music controls, tickets, role panels, attendance tracking, polls, YouTube notifications, AI replies, mini games, search, logs, and admin panels.

Japanese README: [README.md](README.md)

## Links

- Bot Invite: https://discord.com/oauth2/authorize?client_id=1501521359963033741&permissions=1119110818992&integration_type=0&scope=bot+applications.commands
- Help Site: https://shanpan2.github.io/VillageCore/

## Features

- `/game`: button-based game panel for UNO, Sevens, Daifugo, Poker, Othello, Ito, Codenames, and Werewolf
- `/music`: button-based music controls
- `/youtube`: YouTube notification settings and status
- `/attendance`: attendance tracking and warning checks
- `/admin`: settings, permission checks, logs, and maintenance tools
- `/quick`: daily shortcuts
- Tickets, role panels, polls, birthdays, NG words, search, and AI replies

## Games

Use `/game` as the main entry point. It supports lobby creation, joining, leaving, starting, canceling, and rule checks through buttons.

- Ito lets the host enter a custom topic. If left blank, a random topic is used.
- Codenames supports red/blue team joining and spymaster selection from the panel.
- Werewolf supports lobby creation, joining, leaving, starting, canceling, and rule checks from the panel. Night actions and votes still use `/werewolf` because they require a target member.
- Created game state is stored in the database and can survive redeploys.

## Setup

This repository does not include secrets such as tokens, API keys, cookies, or database URLs.

Set required values in your deployment provider's Variables / Secrets page, such as Railway.

For YouTube music cookies, prefer storing the cookies.txt content in `YTDLP_COOKIES_TEXT` instead of committing or deploying a cookie file. The bot first tries normal playback without cookies and only retries with cookies when needed.

For development and operational security notes, see [SECURITY.md](SECURITY.md).

## Run

```bash
pip install -r requirements.txt
python bot.py
```

Docker / Railway deployment is supported.
