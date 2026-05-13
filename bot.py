import discord
from discord.ext import commands
import asyncio

from bot_instance import bot  # bot インスタンス

# ====== Cogs の読み込み ======
async def load_cogs():
    await bot.load_extension("cogs.clean")
    await bot.load_extension("cogs.reminder")
    await bot.load_extension("cogs.vote")
    await bot.load_extension("cogs.janken")
    await bot.load_extension("cogs.ai")
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.welcome")

# ====== Features ======
from Features.ticket import setup_ticket_system
from Features.role_panel import setup_role_panel
from Features.attendance import setup_attendance
from Features.othello import setup_othello
from Features.dice import setup_dice
from Features.omikuji import setup_omikuji
from Features.meigen import setup_meigen

# ====== Views ======
from views.ticket_views import TicketButtonView
from views.role_panel_views import RolePanelView
from views.attendance_views import AttendanceView
from views.othello_views import OthelloView
from views.uno_views import UnoHandView, WildColorSelectView, UnoDeclareView

# ====== Setup Features ======
def setup_features():
    setup_meigen(bot)
    setup_dice(bot)
    setup_omikuji(bot)
    setup_othello(bot)
    setup_attendance(bot)
    setup_ticket_system(bot)
    setup_role_panel(bot)

setup_features()

# ====== Bot Ready ======
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

# ====== メイン処理 ======
async def main():
    async with bot:
        await load_cogs()
        await bot.start("YOUR_TOKEN_HERE")

asyncio.run(main())


