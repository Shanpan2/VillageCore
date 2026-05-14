import os
import discord
from discord.ext import commands
import asyncio

from bot_instance import bot
from database.config_db import db_init

TOKEN = os.getenv("DISCORD_TOKEN")  # ← ここで環境変数から読む

async def load_cogs():
    await bot.load_extension("cogs.clean")
    await bot.load_extension("cogs.reminder")
    await bot.load_extension("cogs.vote")
    await bot.load_extension("cogs.janken")
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.welcome")

from views.ticket_views import TicketButtonView
from views.role_panel_views import RolePanelView
from views.attendance_views import AttendanceView
from views.othello_views import OthelloView
from views.uno_views import UnoHandView, WildColorSelectView, UnoDeclareView

@bot.event
async def on_ready():
    bot.add_view(TicketButtonView(bot))
    bot.add_view(RolePanelView(0))
    bot.add_view(AttendanceView())

    # Slash Command を Discord に同期
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands")

    print("Bot is ready")


async def main():
    await db_init()
    await load_cogs()

    if TOKEN is None:
        print("❌ DISCORD_TOKEN が設定されていません")
        return

    await bot.start(TOKEN)

asyncio.run(main())


