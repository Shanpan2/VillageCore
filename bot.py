import os
import sys
import discord
from discord.ext import commands
import asyncio
from aiohttp import web

from bot_instance import bot
from database.config_db import db_init

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
COMMANDS_SYNCED = False
PERSISTENT_VIEWS_REGISTERED = False


# ==========================
# Cog ロード
# ==========================
async def load_cogs():
    cogs = [
        # cogs/
        "cogs.clean",
        "cogs.reminder",
        "cogs.vote",
        "cogs.janken",
        "cogs.welcome",
        "cogs.music",
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


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)

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
