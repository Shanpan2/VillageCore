import io
import traceback
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw
from views.othello_views import OthelloView

othello_games = {}

class Othello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="othello", description="オセロゲームを開始します")
    @app_commands.guilds(discord.Object(id=1405716361933754408))
    async def othello(self, interaction: discord.Interaction):
        print(f"[Othello] command invoked by {interaction.user} ({interaction.user.id}), interaction {interaction.id}")
        try:
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
        except Exception as e:
            print(f"[Othello] command error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(
                    "❌ オセロの開始中にエラーが発生しました。",
                    ephemeral=True,
                )
            except Exception:
                pass
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
    board_size = 640
    cell_size = board_size // 8
    line_color = (20, 40, 20)
    board_color = (46, 110, 69)
    border_color = (15, 30, 15)

    board_img = Image.new("RGBA", (board_size, board_size), board_color)
    draw = Image.Draw.Draw(board_img)

    # グリッド線
    for i in range(9):
        pos = i * cell_size
        draw.line([(pos, 0), (pos, board_size)], fill=line_color, width=3)
        draw.line([(0, pos), (board_size, pos)], fill=line_color, width=3)

    # 盤面の隅を少し強調
    inset = cell_size // 6
    for x in range(2, 6, 2):
        for y in range(2, 6, 2):
            cx = x * cell_size + cell_size // 2
            cy = y * cell_size + cell_size // 2
            r = cell_size // 12
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(200, 200, 120))

    # 石を描画
    for y in range(8):
        for x in range(8):
            cell = board[y][x]
            if cell == 0:
                continue

            px = x * cell_size
            py = y * cell_size
            radius = int(cell_size * 0.38)
            center_x = px + cell_size // 2
            center_y = py + cell_size // 2
            disc_color = (0, 0, 0) if cell == 1 else (255, 255, 255)
            outline_color = (240, 240, 240) if cell == 1 else (40, 40, 40)

            draw.ellipse(
                [center_x-radius, center_y-radius, center_x+radius, center_y+radius],
                fill=disc_color,
                outline=outline_color,
                width=4,
            )

    buffer = io.BytesIO()
    board_img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def handle_othello_move(interaction, game_id, x, y):
    print(f"[Othello] move requested game_id={game_id} x={x} y={y}")
    try:
        game = othello_games.get(game_id)
        if not game:
            await interaction.followup.send("❌ ゲームデータが見つかりません。", ephemeral=True)
            return

        board = game["board"]
        turn = game["turn"]

        # すでに置かれている
        if board[y][x] != 0:
            await interaction.followup.send("❌ そこには置けません。", ephemeral=True)
            return

        flipped = get_flipped(board, x, y, turn)
        if not flipped:
            await interaction.followup.send("❌ そこには置けません。", ephemeral=True)
            return

        # 石を置く
        board[y][x] = turn
        for fx, fy in flipped:
            board[fy][fx] = turn

        # ターン交代
        game["turn"] = 2 if turn == 1 else 1

        # 画像生成
        img = generate_othello_image(board)
        file = discord.File(img, filename="othello.png")

        embed = discord.Embed(
            title="🎮 オセロ",
            description=f"{'黒' if game['turn'] == 1 else '白'}番です。",
            color=0x2ECC71,
        )

        await interaction.response.edit_message(embed=embed, attachments=[file], view=OthelloView(game_id))
    except Exception as e:
        print(f"[Othello] move error: {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            await interaction.followup.send(
                "❌ オセロの処理中にエラーが発生しました。",
                ephemeral=True,
            )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Othello(bot))

