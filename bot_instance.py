import discord
from discord.ext import commands

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=intents,
            application_id=1501521359963033741  # ← ここにあなたのアプリID
        )

bot = MyBot()


