# Features/othello.py

import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image
from views.othello_views import OthelloView

othello_games = {}

class Othello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ★ ここに guilds() を追加する（ギルドIDはあなたのID）
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


async def handle_othello_move(inter, game_id, x, y):
    game = othello_games.get(game_id)
    if not game:
        await inter.response.send_message("❌ このゲームは存在しません。", ephemeral=True)
        return

    board = game["board"]
    turn = game["turn"]

    if board[y][x] != 0:
        await inter.response.send_message("❌ そこには置けません。", ephemeral=True)
        return

    flipped = get_flipped(board, x, y, turn)
    if not flipped:
        await inter.response.send_message("❌ そこには置けません。", ephemeral=True)
        return

    board[y][x] = turn
    for fx, fy in flipped:
        board[fy][fx] = turn

    turn = 2 if turn == 1 else 1
    game["turn"] = turn

    img = generate_othello_image(board)
    file = discord.File(img, filename="othello.png")

    embed = discord.Embed(
        title="🎮 オセロ",
        description=f"{'黒' if turn == 1 else '白'}番です。",
        color=0x2ECC71,
    )

    await inter.response.edit_message(
        embed=embed,
        attachments=[file],
        view=OthelloView(game_id)
    )


def get_flipped(board, x, y, turn):
    enemy = 2 if turn == 1 else 1
    flipped = []
    directions = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]

    for dx, dy in directions:
        temp = []
        cx, cy = x + dx, y + dy
        while 0 <= cx < 8 and 0 <= cy < 8:
            if board[cy][cx] == enemy:
                temp.append((cx, cy))
            elif board[cy][cx] == turn:
                flipped.extend(temp)
                break
            else:
                break
            cx += dx
            cy += dy

    return flipped


def generate_othello_image(board):
    cell_size = 60
    img = Image.new("RGB", (cell_size * 8, cell_size * 8), (0, 128, 0))

    black = Image.open("assets/othello/black.png").resize((cell_size, cell_size))
    white = Image.open("assets/othello/white.png").resize((cell_size, cell_size))

    for y in range(8):
        for x in range(8):
            if board[y][x] == 1:
                img.paste(black, (x * cell_size, y * cell_size))
            elif board[y][x] == 2:
                img.paste(white, (x * cell_size, y * cell_size))

    path = "othello_temp.png"
    img.save(path)
    return path


async def setup(bot):
    await bot.add_cog(Othello(bot))
