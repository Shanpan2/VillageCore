import os
import sys
import discord
from discord.ext import commands
import asyncio
from html import escape
from aiohttp import web

from bot_instance import bot
from database.config_db import db_get_all_config, db_init, use_postgres

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
LEGACY_GUILD_ID = os.getenv("LEGACY_GUILD_ID", "1405716361933754408")
PORT = int(os.getenv("PORT", "8000"))
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN")
COMMANDS_SYNCED = False
PERSISTENT_VIEWS_REGISTERED = False


# ==========================
# Cog ロード
# ==========================
async def load_cogs():
    cogs = [
        # cogs/
        "cogs.backup",
        "cogs.birthday",
        "cogs.clean",
        "cogs.reminder",
        "cogs.bot_status",
        "cogs.permission_check",
        "cogs.server_logs",
        "cogs.setup_guide",
        "cogs.vote",
        "cogs.janken",
        "cogs.welcome",
        "cogs.music",
        "cogs.ng_words",
        "cogs.ai_chat",
        "cogs.help",
        # Features/
        "Features.attendance",
        "Features.dice",
        "Features.google_search",
        "Features.omikuji",
        "Features.othello",
        "Features.role_panel",
        "Features.sevens",
        "Features.ticket",
        "Features.uno",
        "Features.youtube_notify",
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"  ✅ loaded: {cog}")
        except Exception as e:
            print(f"  ⚠️  skipped: {cog} → {e}")


# ==========================
# 永続 View の登録
# ==========================
def register_persistent_views():
    from views.ticket_views import ClosedTicketView, TicketButtonView, TicketControlView
    from views.role_panel_views import LegacyRolePanelView, RolePanelView
    # ★ AttendanceView は attendance.py に統合したため削除
    bot.add_view(TicketButtonView(bot))
    bot.add_view(TicketControlView())
    bot.add_view(ClosedTicketView())
    bot.add_view(RolePanelView())
    bot.add_view(LegacyRolePanelView())


async def clear_global_commands():
    try:
        print("🔄 Clearing global slash commands so only guild commands remain...", flush=True)
        bot.tree.clear_commands(guild=None)
        cleared_global = await bot.tree.sync(guild=None)
        print(f"🔄 Global slash commands after cleanup: {len(cleared_global)}", flush=True)
    except Exception as e:
        print(f"⚠️ Global slash command cleanup failed: {type(e).__name__}: {e}", flush=True)


async def clear_legacy_guild_commands():
    if not LEGACY_GUILD_ID:
        return
    try:
        guild = discord.Object(id=int(LEGACY_GUILD_ID))
        print(f"🔄 Clearing legacy guild slash commands: {LEGACY_GUILD_ID}", flush=True)
        bot.tree.clear_commands(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔄 Legacy guild slash commands after cleanup: {len(synced)}", flush=True)
    except Exception as e:
        print(f"⚠️ Legacy guild command cleanup failed: {type(e).__name__}: {e}", flush=True)


# ==========================
# on_ready
# ==========================
@bot.event
async def on_ready():
    global COMMANDS_SYNCED, PERSISTENT_VIEWS_REGISTERED

    try:
        if not PERSISTENT_VIEWS_REGISTERED:
            register_persistent_views()
            PERSISTENT_VIEWS_REGISTERED = True
    except Exception as e:
        print(f"⚠️ register_persistent_views エラー: {e}")

    if COMMANDS_SYNCED:
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        return

    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        # Keep slash commands guild-scoped so Discord does not show global + guild duplicates.
        bot.tree.clear_commands(guild=guild)
        print("🔄 Copying slash commands to target guild...", flush=True)
        bot.tree.copy_global_to(guild=guild)

        print("🔄 Syncing current guild slash commands...", flush=True)
        synced = await bot.tree.sync(guild=guild)
        asyncio.create_task(clear_global_commands())
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(synced)} slash commands to guild {GUILD_ID}", flush=True)
    else:
        synced = await bot.tree.sync()
        asyncio.create_task(clear_legacy_guild_commands())
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(synced)} global slash commands", flush=True)


async def handle_ping(request):
    return web.Response(text="OK")


def dashboard_auth_ok(request: web.Request) -> bool:
    return bool(DASHBOARD_TOKEN and request.query.get("token") == DASHBOARD_TOKEN)


async def handle_dashboard(request: web.Request):
    if not DASHBOARD_TOKEN:
        return web.Response(
            text=(
                "<h1>VillageCore Dashboard</h1>"
                "<p>Dashboard is disabled. Set <code>DASHBOARD_TOKEN</code> to enable it.</p>"
            ),
            content_type="text/html",
        )

    if not dashboard_auth_ok(request):
        return web.Response(status=401, text="Unauthorized")

    try:
        config = await db_get_all_config()
        db_status = "OK"
    except Exception as e:
        config = {}
        db_status = f"NG: {type(e).__name__}"

    command_count = len([c for c in bot.tree.walk_commands() if c.parent is None])
    guild_rows = "".join(
        f"<tr><td>{escape(guild.name)}</td><td>{guild.id}</td><td>{guild.member_count or '-'}</td></tr>"
        for guild in bot.guilds
    )
    env_rows = "".join(
        f"<tr><td>{name}</td><td>{'OK' if os.getenv(name) else 'Not set'}</td></tr>"
        for name in ("DISCORD_TOKEN", "DATABASE_URL", "GEMINI_API_KEY", "YOUTUBE_API_KEY")
    )

    html = f"""
    <!doctype html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>VillageCore Dashboard</title>
      <style>
        body {{ font-family: system-ui, sans-serif; margin: 32px; background: #f6f7f9; color: #20242a; }}
        main {{ max-width: 960px; margin: auto; }}
        section {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; margin: 16px 0; }}
        h1, h2 {{ margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; border-bottom: 1px solid #edf0f2; padding: 8px; }}
        .ok {{ color: #16794c; font-weight: 700; }}
      </style>
    </head>
    <body>
      <main>
        <h1>VillageCore Dashboard</h1>
        <section>
          <h2>Status</h2>
          <p>Bot: <span class="ok">{escape(str(bot.user)) if bot.user else "Starting"}</span></p>
          <p>DB: {escape("PostgreSQL" if use_postgres() else "SQLite")} / {escape(db_status)}</p>
          <p>Guilds: {len(bot.guilds)}</p>
          <p>Slash commands: {command_count}</p>
          <p>Stored config keys: {len(config)}</p>
        </section>
        <section>
          <h2>Environment</h2>
          <table><tbody>{env_rows}</tbody></table>
        </section>
        <section>
          <h2>Guilds</h2>
          <table>
            <thead><tr><th>Name</th><th>ID</th><th>Members</th></tr></thead>
            <tbody>{guild_rows or "<tr><td colspan='3'>No guilds</td></tr>"}</tbody>
          </table>
        </section>
      </main>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/dashboard", handle_dashboard)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"🌐 Health server running on port {PORT}", flush=True)


# ==========================
# エントリポイント
# ==========================
async def main():
    print("🚀 Starting bot process", flush=True)
    print(f"🔑 DISCORD_TOKEN set: {TOKEN is not None}", flush=True)
    print(f"🌐 PORT={PORT}", flush=True)
    print(f"🛡️ GUILD_ID={GUILD_ID or '(global sync)'}", flush=True)

    if TOKEN is None:
        print("❌ DISCORD_TOKEN が設定されていません", flush=True)
        return

    await db_init()
    await load_cogs()

    print(f"🌐 Starting health server on port {PORT}", flush=True)
    asyncio.create_task(start_health_server())

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {type(e).__name__}: {e}", flush=True)
        raise


asyncio.run(main())
