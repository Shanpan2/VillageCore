import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image
from views.othello_views import OthelloView

othello_games = {}

class Othello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
    board_img = Image.open("assets/othello/board.png").convert("RGBA")

    cell_size = board_img.width // 8

    black = Image.open("assets/othello/black.png").convert("RGBA").resize((cell_size, cell_size))
    white = Image.open("assets/othello/white.png").convert("RGBA").resize((cell_size, cell_size))
    empty = Image.open("assets/othello/empty.png").convert("RGBA").resize((cell_size, cell_size))

    for y in range(8):
        for x in range(8):
            px = x * cell_size
            py = y * cell_size

            if board[y][x] == 1:
                board_img.paste(black, (px, py), black)
            elif board[y][x] == 2:
                board_img.paste(white, (px, py), white)
            else:
                # ★ empty は mask を使わない（透明でなくても動く）
                board_img.paste(empty, (px, py))

    path = "othello_temp.png"
    board_img.save(path)
    return path




async def setup(bot):
    await bot.add_cog(Othello(bot))

