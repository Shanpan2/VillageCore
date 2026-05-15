import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image
from views.othello_views import OthelloView

othello_games = {}

class Othello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # ★ Slash コマンドを tree に登録（これが無いと実行されない）
        self.bot.tree.add_command(self.othello)

    @app_commands.command(name="othello", description="オセロゲームを開始します")
    @app_commands.guilds(discord.Object(id=1405716361933754408))
    async def othello(self, interaction: discord.Interaction):
        game_id = str(interaction.id)

        board = [[0] * 8 for _ in range(8)]
        board[3][3] = 2
        board[4][4] = 2
        board[3][4] = 1
        board[4][3] = 1

        othello_games[game_id] = {"board": board, "turn": 1}

        img = generate_othello_image(board)
        file = discord.File(img, filename="othello.png")

        embed = discord.Embed(
            title="🎮 オセロ開始！",
            description="黒番（先手）です。",
            color=0x2ECC71,
        )
        await interaction.response.send_message(
            embed=embed, file=file, view=OthelloView(game_id)
        )


async def setup(bot):
    await bot.add_cog(Othello(bot))
