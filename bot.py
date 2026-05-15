import os
import discord
from discord.ext import commands
import asyncio
from aiohttp import web

from bot_instance import bot
from database.config_db import db_init

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1405716361933754408
PORT = int(os.getenv("PORT", "8000"))


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
        # Features/
        "Features.attendance",
        "Features.dice",
        "Features.meigen",
        "Features.omikuji",
        "Features.othello",
        "Features.role_panel",
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
    from views.ticket_views import TicketButtonView
    from views.role_panel_views import RolePanelView
    # ★ AttendanceView は attendance.py に統合したため削除
    bot.add_view(TicketButtonView(bot))
    bot.add_view(RolePanelView(0))


# ==========================
# on_ready
# ==========================
@bot.event
async def on_ready():
    try:
        register_persistent_views()
    except Exception as e:
        print(f"⚠️ register_persistent_views エラー: {e}")

    guild = discord.Object(id=GUILD_ID)

    # ギルドコマンドを同期（即時反映）
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)

    print(f"✅ Bot ready: {bot.user} ({bot.user.id})")
    print(f"🔄 Synced {len(synced)} slash commands to guild {GUILD_ID}")


async def handle_ping(request):
    return web.Response(text="OK")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"🌐 Health server running on port {PORT}")


# ==========================
# エントリポイント
# ==========================
async def main():
    print("🚀 Starting bot process")

    if TOKEN is None:
        print("❌ DISCORD_TOKEN が設定されていません")
        return

    await db_init()
    await load_cogs()

    print(f"🌐 Starting health server on port {PORT}")
    asyncio.create_task(start_health_server())

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {type(e).__name__}: {e}")
        raise


asyncio.run(main())
