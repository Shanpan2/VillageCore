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
    async def othello(self, interaction: discord.Interaction):
        print(f"[Othello] command invoked by {interaction.user} ({interaction.user.id}), interaction {interaction.id}")
        try:
            game_id = str(interaction.id)

            board = [[0] * 8 for _ in range(8)]
            board[3][3] = 2
            board[4][4] = 2
            board[3][4] = 1
            board[4][3] = 1

            othello_games[game_id] = {
                "board": board,
                "turn": 1,
                "black_id": interaction.user.id,
                "white_id": None,
            }

            valid_moves = get_valid_moves(board, 1)
            img = generate_othello_image(board, valid_moves)
            file = discord.File(img, filename="othello.png")

            embed = discord.Embed(
                title="🎮 オセロ開始！",
                description=(
                    f"黒番（先手）：<@{interaction.user.id}>\n"
                    "白番（後手）：まだ参加していません。\n"
                    "置ける場所を選択してください。"
                ),
                color=0x2ECC71,
            )
            await interaction.response.send_message(
                embed=embed,
                file=file,
                view=OthelloView(game_id, valid_moves, show_join=True),
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


def get_valid_moves(board, turn):
    moves = []
    for y in range(8):
        for x in range(8):
            if board[y][x] != 0:
                continue
            if get_flipped(board, x, y, turn):
                moves.append((x, y))
    return moves


def generate_othello_image(board, valid_moves=None):
    board_size = 640
    cell_size = board_size // 8
    line_color = (20, 40, 20)
    board_color = (46, 110, 69)
    border_color = (15, 30, 15)

    board_img = Image.new("RGBA", (board_size, board_size), board_color)
    draw = ImageDraw.Draw(board_img)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None

    # グリッド線
    for i in range(9):
        pos = i * cell_size
        draw.line([(pos, 0), (pos, board_size)], fill=line_color, width=3)
        draw.line([(0, pos), (board_size, pos)], fill=line_color, width=3)

    # 置ける場所のヒントを描画
    if valid_moves:
        for x, y in valid_moves:
            px = x * cell_size
            py = y * cell_size
            center_x = px + cell_size // 2
            center_y = py + cell_size // 2
            hint_radius = int(cell_size * 0.26)
            draw.ellipse(
                [center_x-hint_radius, center_y-hint_radius, center_x+hint_radius, center_y+hint_radius],
                fill=(250, 220, 100, 120),
                outline=(250, 220, 100),
                width=4,
            )
            draw.ellipse(
                [center_x-hint_radius+8, center_y-hint_radius+8, center_x+hint_radius-8, center_y+hint_radius-8],
                outline=(250, 220, 100),
                width=2,
            )

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

    # ラベルを描画（A-H と 1-8）
    for x in range(8):
        label = chr(65 + x)
        lx = x * cell_size + cell_size // 2
        # 上に描画
        draw.text((lx - 6, 2), label, fill=(255, 255, 255), font=font)
        # 下にも描画
        draw.text((lx - 6, board_size - 14), label, fill=(255, 255, 255), font=font)

    for y in range(8):
        label = str(y + 1)
        ly = y * cell_size + cell_size // 2
        # 左に描画
        draw.text((2, ly - 6), label, fill=(255, 255, 255), font=font)
        # 右にも描画
        draw.text((board_size - 12, ly - 6), label, fill=(255, 255, 255), font=font)

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
        black_id = game["black_id"]
        white_id = game["white_id"]

        if turn == 1 and interaction.user.id != black_id:
            await interaction.followup.send(
                f"❌ 黒番のプレイヤーは <@{black_id}> です。黒番の方のみ操作できます。",
                ephemeral=True,
            )
            return

        if turn == 2:
            if white_id is None:
                if interaction.user.id == black_id:
                    await interaction.followup.send(
                        "❌ 先手と同じ人は後手を担当できません。別のユーザーが後手になります。",
                        ephemeral=True,
                    )
                    return
                game["white_id"] = interaction.user.id
                white_id = interaction.user.id
            elif interaction.user.id != white_id:
                await interaction.followup.send(
                    f"❌ 白番のプレイヤーは <@{white_id}> です。白番の方のみ操作できます。",
                    ephemeral=True,
                )
                return

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

        valid_moves = get_valid_moves(board, game["turn"])
        if not valid_moves:
            next_turn = 2 if game["turn"] == 1 else 1
            other_moves = get_valid_moves(board, next_turn)
            if other_moves:
                game["turn"] = next_turn
                valid_moves = other_moves
                status_text = "置ける場所がないためターンをスキップしました。"
            else:
                black_count = sum(cell == 1 for row in board for cell in row)
                white_count = sum(cell == 2 for row in board for cell in row)
                if black_count > white_count:
                    winner = "黒"
                elif white_count > black_count:
                    winner = "白"
                else:
                    winner = "引き分け"
                img = generate_othello_image(board, [])
                file = discord.File(img, filename="othello.png")
                try:
                    await interaction.message.edit(
                        embed=discord.Embed(
                            title="🎮 オセロ 終了",
                            description=(
                                f"ゲーム終了！\n"
                                f"黒 {black_count} - 白 {white_count} で {winner} の勝利です。"
                            ),
                            color=0x2ECC71,
                        ),
                        attachments=[file],
                        view=None,
                    )
                except Exception:
                    # 編集できなければフォローアップで送る
                    await interaction.followup.send(
                        f"ゲーム終了！ 黒 {black_count} - 白 {white_count} で {winner} の勝利です。",
                        ephemeral=False,
                    )
                return
        else:
            status_text = "置ける場所を選択してください。"

        img = generate_othello_image(board, valid_moves)
        file = discord.File(img, filename="othello.png")

        player_text = (
            f"黒: <@{game['black_id']}>\n"
            f"白: <@{game['white_id']}>\n"
            if game["white_id"]
            else f"黒: <@{game['black_id']}>\n白: まだ参加していません。\n"
        )

        embed = discord.Embed(
            title="🎮 オセロ",
            description=(
                f"{player_text}"
                f"{'黒' if game['turn'] == 1 else '白'}番です。\n"
                f"{status_text}"
            ),
            color=0x2ECC71,
        )
        try:
            await interaction.message.edit(
                embed=embed,
                attachments=[file],
                view=OthelloView(game_id, valid_moves, show_join=(game.get("white_id") is None)),
            )
        except Exception:
            # 編集に失敗したらフォローアップで代替表示
            await interaction.followup.send(embed=embed, attachments=[file], ephemeral=False)
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

