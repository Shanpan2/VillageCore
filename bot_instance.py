import discord
from discord.ext import commands

intents = discord.Intents.all()

# prefix は "/" にしてはいけない
bot = commands.Bot(command_prefix="!", intents=intents)

