import io
import random
import traceback
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw
from utils.game_persistence import (
    save_game as _save_game,
    delete_game as _delete_game,
    load_games_for_guild,
)
from utils.game_cog import BaseGameCog
from utils.coin import get_coin_balance, set_coin_balance
from views.othello_views import OthelloView

othello_games = {}

AI_PLAYER_ID = 0
AI_DIFFICULTIES = {
    "easy": {"label": "易", "depth": 1, "mistake": 0.45, "profit": 0.10},
    "normal": {"label": "普通", "depth": 2, "mistake": 0.20, "profit": 0.30},
    "hard": {"label": "難", "depth": 3, "mistake": 0.08, "profit": 0.70},
    "master": {"label": "達人", "depth": 4, "mistake": 0.0, "profit": 1.00},
}
CORNER_SCORE = 120
EDGE_SCORE = 18
MOBILITY_SCORE = 8


_PREFIX = "othello"
_EXCLUDE_KEYS = frozenset({"message_id", "channel_id"})


async def save_othello_game(guild_id: int | None, game_id: str, game: dict):
    await _save_game(
        _PREFIX, othello_games, guild_id, game_id, game,
        exclude_keys=_EXCLUDE_KEYS,
    )


async def delete_othello_game(guild_id: int | None, game_id: str):
    await _delete_game(_PREFIX, guild_id, game_id)


def _validate_othello(state: dict) -> bool:
    board = state.get("board")
    return isinstance(board, list) and len(board) == 8


def _restore_othello_view(bot: commands.Bot, game_id: str, state: dict) -> None:
    valid_moves = get_valid_moves(state["board"], int(state.get("turn", 1)))
    bot.add_view(OthelloView(game_id, valid_moves, show_join=(state.get("white_id") is None)))


async def load_othello_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    await load_games_for_guild(
        _PREFIX, othello_games, bot, guild,
        validate=_validate_othello,
        restore_view=_restore_othello_view,
    )

class Othello(BaseGameCog):
    _load_guild = staticmethod(load_othello_games_for_guild)

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
                "creator_id": interaction.user.id,
                "guild_id": interaction.guild_id,
            }
            await save_othello_game(interaction.guild_id, game_id, othello_games[game_id])

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

    @app_commands.command(name="othello_ai", description="AIとオセロで対戦します")
    @app_commands.describe(
        first="先攻/後攻を選びます",
        difficulty="AIの難易度",
        bet="賭けるコイン数。0で賭けなし",
    )
    @app_commands.choices(
        first=[
            app_commands.Choice(name="先攻（黒）", value="black"),
            app_commands.Choice(name="後攻（白）", value="white"),
            app_commands.Choice(name="ランダム", value="random"),
        ],
        difficulty=[
            app_commands.Choice(name="易", value="easy"),
            app_commands.Choice(name="普通", value="normal"),
            app_commands.Choice(name="難", value="hard"),
            app_commands.Choice(name="達人", value="master"),
        ],
    )
    async def othello_ai(
        self,
        interaction: discord.Interaction,
        first: app_commands.Choice[str],
        difficulty: app_commands.Choice[str],
        bet: int = 0,
    ):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if bet < 0:
            await interaction.response.send_message("賭けるコイン数は0以上にしてください。", ephemeral=True)
            return
        if bet > 0:
            balance = await get_coin_balance(interaction.guild_id, interaction.user.id)
            if balance < bet:
                await interaction.response.send_message(f"コインが足りません。現在の所持コインは **{balance}** です。", ephemeral=True)
                return
            await set_coin_balance(interaction.guild_id, interaction.user.id, balance - bet)
        await interaction.response.defer()

        player_first = first.value
        if player_first == "random":
            player_first = random.choice(["black", "white"])

        human_color = 1 if player_first == "black" else 2
        ai_color = 2 if human_color == 1 else 1
        game_id = str(interaction.id)

        board = new_board()
        othello_games[game_id] = {
            "board": board,
            "turn": 1,
            "black_id": interaction.user.id if human_color == 1 else AI_PLAYER_ID,
            "white_id": interaction.user.id if human_color == 2 else AI_PLAYER_ID,
            "creator_id": interaction.user.id,
            "guild_id": interaction.guild_id,
            "ai": True,
            "human_id": interaction.user.id,
            "human_color": human_color,
            "ai_color": ai_color,
            "difficulty": difficulty.value,
            "bet": bet,
            "coin_settled": False,
        }

        prefix = f"AI対戦を開始しました。難易度: **{AI_DIFFICULTIES[difficulty.value]['label']}**"
        if bet > 0:
            prefix += f"\n賭けコイン: **{bet}**"
        prefix = await run_ai_turns(othello_games[game_id], prefix)
        await send_othello_state(interaction, game_id, prefix, initial=True)


def new_board() -> list[list[int]]:
    board = [[0] * 8 for _ in range(8)]
    board[3][3] = 2
    board[4][4] = 2
    board[3][4] = 1
    board[4][3] = 1
    return board
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


def clone_board(board):
    return [row.copy() for row in board]


def apply_move(board, x, y, turn):
    flipped = get_flipped(board, x, y, turn)
    if not flipped:
        return False
    board[y][x] = turn
    for fx, fy in flipped:
        board[fy][fx] = turn
    return True


def opponent(turn: int) -> int:
    return 2 if turn == 1 else 1


def evaluate_board(board, ai_color: int) -> int:
    human_color = opponent(ai_color)
    ai_count = sum(cell == ai_color for row in board for cell in row)
    human_count = sum(cell == human_color for row in board for cell in row)
    score = (ai_count - human_count) * 3

    for x, y in [(0, 0), (7, 0), (0, 7), (7, 7)]:
        if board[y][x] == ai_color:
            score += CORNER_SCORE
        elif board[y][x] == human_color:
            score -= CORNER_SCORE

    for i in range(8):
        for x, y in [(i, 0), (i, 7), (0, i), (7, i)]:
            if board[y][x] == ai_color:
                score += EDGE_SCORE
            elif board[y][x] == human_color:
                score -= EDGE_SCORE

    score += (len(get_valid_moves(board, ai_color)) - len(get_valid_moves(board, human_color))) * MOBILITY_SCORE
    return score


def minimax(board, turn: int, ai_color: int, depth: int, maximizing: bool) -> int:
    moves = get_valid_moves(board, turn)
    if depth <= 0 or not moves:
        return evaluate_board(board, ai_color)

    values = []
    for x, y in moves:
        next_board = clone_board(board)
        apply_move(next_board, x, y, turn)
        values.append(minimax(next_board, opponent(turn), ai_color, depth - 1, not maximizing))
    return max(values) if maximizing else min(values)


def choose_ai_move(board, ai_color: int, difficulty: str) -> tuple[int, int] | None:
    moves = get_valid_moves(board, ai_color)
    if not moves:
        return None
    config = AI_DIFFICULTIES.get(difficulty, AI_DIFFICULTIES["normal"])
    if config["mistake"] and random.random() < config["mistake"]:
        return random.choice(moves)

    depth = config["depth"]
    scored = []
    for x, y in moves:
        next_board = clone_board(board)
        apply_move(next_board, x, y, ai_color)
        score = minimax(next_board, opponent(ai_color), ai_color, depth - 1, False)
        scored.append((score, x, y))
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2]


async def settle_ai_coins(game: dict, guild_id: int | None, winner_color: int | None) -> str:
    bet = int(game.get("bet", 0) or 0)
    if game.get("coin_settled") or not guild_id or bet <= 0:
        return ""
    game["coin_settled"] = True

    human_id = game.get("human_id")
    human_color = game.get("human_color")
    balance = await get_coin_balance(guild_id, human_id)
    if winner_color is None:
        await set_coin_balance(guild_id, human_id, balance + bet)
        return f"引き分けのため **{bet}** コインを返却しました。"
    if winner_color == human_color:
        profit_rate = AI_DIFFICULTIES.get(game.get("difficulty"), AI_DIFFICULTIES["normal"])["profit"]
        payout = bet + max(1, int(bet * profit_rate))
        await set_coin_balance(guild_id, human_id, balance + payout)
        return f"勝利報酬として **{payout}** コインを受け取りました。"
    return f"敗北したため **{bet}** コインを失いました。"


def player_line(game: dict) -> str:
    black = "AI" if game.get("black_id") == AI_PLAYER_ID else f"<@{game.get('black_id')}>"
    white_id = game.get("white_id")
    white = "AI" if white_id == AI_PLAYER_ID else (f"<@{white_id}>" if white_id else "まだ参加していません。")
    return f"黒: {black}\n白: {white}\n"


def player_name(game: dict, color: int | None) -> str:
    if color is None:
        return "引き分け"
    user_id = game.get("black_id") if color == 1 else game.get("white_id")
    return "AI" if user_id == AI_PLAYER_ID else f"<@{user_id}>"


async def run_ai_turns(game: dict, prefix: str = "") -> str:
    notes = [prefix] if prefix else []
    while game.get("ai") and game["turn"] == game.get("ai_color"):
        board = game["board"]
        ai_color = game["ai_color"]
        move = choose_ai_move(board, ai_color, game.get("difficulty", "normal"))
        if move is None:
            next_turn = opponent(ai_color)
            if get_valid_moves(board, next_turn):
                game["turn"] = next_turn
                notes.append("AIは置ける場所がないためパスしました。")
                break
            break
        x, y = move
        apply_move(board, x, y, ai_color)
        notes.append(f"AIが {chr(65 + x)}{y + 1} に置きました。")
        game["turn"] = opponent(ai_color)

        human_moves = get_valid_moves(board, game["turn"])
        if human_moves:
            break
        ai_moves = get_valid_moves(board, ai_color)
        if ai_moves:
            notes.append("あなたは置ける場所がないためパスしました。")
            game["turn"] = ai_color
            continue
        break
    return "\n".join(notes)


async def send_othello_state(interaction, game_id: str, prefix: str = "", initial: bool = False):
    game = othello_games.get(game_id)
    if not game:
        return
    board = game["board"]
    valid_moves = get_valid_moves(board, game["turn"])

    if not valid_moves:
        other = opponent(game["turn"])
        other_moves = get_valid_moves(board, other)
        if other_moves:
            game["turn"] = other
            valid_moves = other_moves
            prefix = (prefix + "\n" if prefix else "") + "置ける場所がないためターンをスキップしました。"
        else:
            await finish_othello_game(interaction, game_id, prefix)
            return

    img = generate_othello_image(board, valid_moves)
    file = discord.File(img, filename="othello.png")
    difficulty = game.get("difficulty")
    diff_text = f"\n難易度: **{AI_DIFFICULTIES[difficulty]['label']}**" if difficulty in AI_DIFFICULTIES else ""
    bet_text = f"\n賭けコイン: **{game.get('bet', 0)}**" if game.get("bet", 0) else ""
    embed = discord.Embed(
        title="🎮 オセロ",
        description=(
            f"{prefix + chr(10) if prefix else ''}"
            f"{player_line(game)}"
            f"{'黒' if game['turn'] == 1 else '白'}番です。"
            f"{diff_text}{bet_text}\n"
            "置ける場所を選択してください。"
        ),
        color=0x2ECC71,
    )
    view = OthelloView(game_id, valid_moves, show_join=(game.get("white_id") is None))
    await save_othello_game(getattr(interaction, "guild_id", None) or game.get("guild_id"), game_id, game)
    if initial:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, file=file, view=view)
        else:
            await interaction.response.send_message(embed=embed, file=file, view=view)
    else:
        await interaction.message.edit(embed=embed, attachments=[file], view=view)


async def finish_othello_game(interaction, game_id: str, prefix: str = ""):
    game = othello_games.get(game_id)
    if not game:
        return
    board = game["board"]
    black_count = sum(cell == 1 for row in board for cell in row)
    white_count = sum(cell == 2 for row in board for cell in row)
    winner_color = 1 if black_count > white_count else 2 if white_count > black_count else None
    winner = player_name(game, winner_color)
    coin_text = await settle_ai_coins(game, getattr(interaction, "guild_id", None), winner_color)
    await delete_othello_game(getattr(interaction, "guild_id", None) or game.get("guild_id"), game_id)
    othello_games.pop(game_id, None)

    img = generate_othello_image(board, [])
    file = discord.File(img, filename="othello.png")
    embed = discord.Embed(
        title="🎮 オセロ 終了",
        description=(
            f"{prefix + chr(10) if prefix else ''}"
            f"ゲーム終了！\n黒 {black_count} - 白 {white_count}\n"
            f"勝者: **{winner}**\n"
            f"{coin_text}"
        ),
        color=0x2ECC71,
    )
    try:
        await interaction.message.edit(embed=embed, attachments=[file], view=None)
    except Exception:
        if getattr(interaction, "response", None) and not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed, file=file)


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
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    except Exception:
        font = ImageFont.load_default()

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
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # 上に描画
        draw.text((lx - tw / 2, 4), label, fill=(255, 255, 255), font=font)
        # 下にも描画
        draw.text((lx - tw / 2, board_size - th - 4), label, fill=(255, 255, 255), font=font)

    for y in range(8):
        label = str(y + 1)
        ly = y * cell_size + cell_size // 2
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # 左に描画
        draw.text((4, ly - th / 2), label, fill=(255, 255, 255), font=font)
        # 右にも描画
        draw.text((board_size - tw - 4, ly - th / 2), label, fill=(255, 255, 255), font=font)

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

        apply_move(board, x, y, turn)
        game["turn"] = opponent(turn)

        prefix = f"<@{interaction.user.id}> が {chr(65 + x)}{y + 1} に置きました。"
        if game.get("ai"):
            prefix = await run_ai_turns(game, prefix)
        await send_othello_state(interaction, game_id, prefix)
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
