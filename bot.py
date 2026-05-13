from discord.ext import commands
from bot_instance import bot  # あなたの bot インスタンス

# ③ cogs の読み込み ← ここに入れる
bot.load_extension("cogs.clean")
bot.load_extension("cogs.reminder")
bot.load_extension("cogs.vote")
bot.load_extension("cogs.janken")
bot.load_extension("cogs.ai")  # AI応答を作るなら
bot.load_extension("cogs.music")
bot.load_extension("cogs.welcome")


# ====== Features ======
from features.ticket import setup_ticket_system
from features.role_panel import setup_role_panel
from features.attendance import setup_attendance
from features.othello import setup_othello
from features.dice import setup_dice
from features.omikuji import setup_omikuji
from features.meigen import setup_meigen

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


# ====== Persistent Views ======
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

bot.run(TOKEN)

