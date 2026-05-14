import discord
from discord.ext import commands
import asyncio

from bot_instance import bot
from database.config_db import db_init

# ====== Cogs の読み込み ======
async def load_cogs():
    await bot.load_extension("cogs.clean")
    await bot.load_extension("cogs.reminder")
    await bot.load_extension("cogs.vote")
    await bot.load_extension("cogs.janken")
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.welcome")
    # AI を使うなら
    # await bot.load_extension("cogs.ai")

# ====== Views の読み込み ======
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
    bot.add_view(OthelloView("dummy"))
    bot.add_view(UnoHandView("dummy", 0, []))
    bot.add_view(WildColorSelectView("dummy", 0, "wild"))
    bot.add_view(UnoDeclareView("dummy", 0))

    print("Bot is ready")


# ====== 正しい main 関数 ======
async def main():
    await db_init()          # DB 初期化
    await load_cogs()        # Cogs 読み込み
    await bot.start("YOUR_TOKEN_HERE")  # Bot 起動


asyncio.run(main())

