import os
import discord
from discord.ext import commands
import asyncio

from bot_instance import bot
from database.config_db import db_init

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1405716361933754408


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
            # ファイルが存在しない・構文エラーなどはスキップして続行
            print(f"  ⚠️  skipped: {cog} → {e}")


# ==========================
# 永続 View の登録
# ==========================
def register_persistent_views():
    from views.ticket_views import TicketButtonView
    from views.role_panel_views import RolePanelView
    from views.attendance_views import AttendanceView

    bot.add_view(TicketButtonView(bot))
    bot.add_view(RolePanelView(0))
    bot.add_view(AttendanceView())


# ==========================
# on_ready
# ==========================
@bot.event
async def on_ready():
    register_persistent_views()

    guild = discord.Object(id=GUILD_ID)

    # ギルドコマンドを同期（即時反映）
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)

    print(f"✅ Bot ready: {bot.user} ({bot.user.id})")
    print(f"🔄 Synced {len(synced)} slash commands to guild {GUILD_ID}")


# ==========================
# エントリポイント
# ==========================
async def main():
    if TOKEN is None:
        print("❌ DISCORD_TOKEN が設定されていません")
        return

    await db_init()
    await load_cogs()
    await bot.start(TOKEN)


asyncio.run(main())
