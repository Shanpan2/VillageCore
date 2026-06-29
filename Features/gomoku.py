import asyncio
import io
import json
import random

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from database.config_db import db_get, db_set


gomoku_games: dict[str, dict] = {}

BOARD_SIZE = 15
AI_PLAYER_ID = 0
AI_DIFFICULTIES = {
    "easy": {"label": "初級", "mistake": 0.45, "profit": 0.20},
    "normal": {"label": "中級", "mistake": 0.18, "profit": 0.50},
    "hard": {"label": "上級", "mistake": 0.04, "profit": 1.00},
}
RANDOMIZER = random.SystemRandom()


def coin_key(guild_id: int, user_id: int) -> str:
    return f"community_coin:{guild_id}:{user_id}"


def gomoku_index_key(guild_id: int) -> str:
    return f"gomoku_games_index:{guild_id}"


def gomoku_game_key(guild_id: int, game_id: str) -> str:
    return f"gomoku_game:{guild_id}:{game_id}"


async def get_coin_balance(guild_id: int, user_id: int) -> int:
    return int(await db_get(coin_key(guild_id, user_id)) or "0")


async def set_coin_balance(guild_id: int, user_id: int, amount: int):
    await db_set(coin_key(guild_id, user_id), str(max(0, amount)))


async def save_gomoku_game(guild_id: int | None, game_id: str, game: dict):
    if not guild_id:
        return
    game["guild_id"] = guild_id
    await db_set(gomoku_game_key(guild_id, game_id), json.dumps(game, ensure_ascii=False))
    try:
        index = json.loads(await db_get(gomoku_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(gomoku_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_gomoku_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(gomoku_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(gomoku_index_key(guild_id), json.dumps(index, ensure_ascii=False))
    await db_set(gomoku_game_key(guild_id, game_id), "")


async def load_gomoku_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(gomoku_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []
    active = []
    for game_id in index:
        raw = await db_get(gomoku_game_key(guild.id, game_id))
        if not raw:
            continue
        try:
            game = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(game.get("board"), list) and not game.get("finished") and game.get("message_id"):
            gomoku_games[game_id] = game
            bot.add_view(GomokuView(game_id, show_join=game.get("white_id") is None))
            active.append(game_id)
    if active != index:
        await db_set(gomoku_index_key(guild.id), json.dumps(active, ensure_ascii=False))


async def cleanup_stale_gomoku_game(interaction: discord.Interaction, game_id: str) -> bool:
    game = gomoku_games.get(game_id)
    if not game:
        return True

    guild_id = interaction.guild_id or game.get("guild_id")
    message_id = game.get("message_id")
    if not message_id:
        await delete_gomoku_game(guild_id, game_id)
        gomoku_games.pop(game_id, None)
        return True

    channel = interaction.channel
    if not channel or not hasattr(channel, "fetch_message"):
        return False
    try:
        await channel.fetch_message(int(message_id))
        return False
    except discord.NotFound:
        await delete_gomoku_game(guild_id, game_id)
        gomoku_games.pop(game_id, None)
        return True
    except (discord.Forbidden, discord.HTTPException, ValueError):
        return False


def new_board() -> list[list[int]]:
    return [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def opponent(color: int) -> int:
    return 2 if color == 1 else 1


def color_name(color: int) -> str:
    return "黒" if color == 1 else "白"


def player_name(game: dict, color: int | None) -> str:
    if color is None:
        return "引き分け"
    user_id = game.get("black_id") if color == 1 else game.get("white_id")
    return "AI" if user_id == AI_PLAYER_ID else f"<@{user_id}>"


def is_full(board: list[list[int]]) -> bool:
    return all(cell for row in board for cell in row)


def check_winner(board: list[list[int]]) -> int | None:
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            color = board[y][x]
            if not color:
                continue
            for dx, dy in directions:
                count = 1
                nx, ny = x + dx, y + dy
                while 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE and board[ny][nx] == color:
                    count += 1
                    if count >= 5:
                        return color
                    nx += dx
                    ny += dy
    return None


def candidate_moves(board: list[list[int]]) -> list[tuple[int, int]]:
    stones = [(x, y) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE) if board[y][x]]
    if not stones:
        mid = BOARD_SIZE // 2
        return [(mid, mid)]
    candidates = set()
    for sx, sy in stones:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                x, y = sx + dx, sy + dy
                if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and board[y][x] == 0:
                    candidates.add((x, y))
    return sorted(candidates)


def longest_line_score(board: list[list[int]], x: int, y: int, color: int) -> int:
    score = 0
    for dx, dy in [(1, 0), (0, 1), (1, 1), (1, -1)]:
        count = 1
        open_ends = 0
        for sign in (1, -1):
            nx, ny = x + dx * sign, y + dy * sign
            while 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE and board[ny][nx] == color:
                count += 1
                nx += dx * sign
                ny += dy * sign
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE and board[ny][nx] == 0:
                open_ends += 1
        score = max(score, count * count * 10 + open_ends * 8)
    return score


def move_score(board: list[list[int]], x: int, y: int, color: int) -> int:
    if board[y][x]:
        return -1
    board[y][x] = color
    if check_winner(board) == color:
        board[y][x] = 0
        return 1_000_000
    attack = longest_line_score(board, x, y, color)
    board[y][x] = 0

    enemy = opponent(color)
    board[y][x] = enemy
    block = 900_000 if check_winner(board) == enemy else longest_line_score(board, x, y, enemy)
    board[y][x] = 0

    center = BOARD_SIZE // 2
    center_bonus = max(0, 20 - abs(x - center) - abs(y - center))
    return attack * 3 + block * 4 + center_bonus


def choose_ai_move(board: list[list[int]], ai_color: int, difficulty: str) -> tuple[int, int] | None:
    moves = candidate_moves(board)
    if not moves:
        return None
    config = AI_DIFFICULTIES.get(difficulty, AI_DIFFICULTIES["normal"])
    if config["mistake"] and random.random() < config["mistake"]:
        return random.choice(moves)
    scored = [(move_score(board, x, y, ai_color), x, y) for x, y in moves]
    scored.sort(reverse=True)
    if difficulty == "easy" and len(scored) > 3:
        return random.choice(scored[:5])[1:]
    if difficulty == "normal" and len(scored) > 1:
        return random.choice(scored[:2])[1:]
    return scored[0][1], scored[0][2]


def resolve_first_choice(first: str) -> tuple[str, bool]:
    if first in {"black", "white"}:
        return first, False
    return RANDOMIZER.choice(["black", "white"]), True


async def settle_ai_coins(game: dict, guild_id: int | None, winner_color: int | None) -> str:
    bet = int(game.get("bet", 0) or 0)
    if game.get("coin_settled") or not guild_id or bet <= 0:
        return ""
    game["coin_settled"] = True
    human_id = int(game.get("human_id"))
    human_color = int(game.get("human_color"))
    balance = await get_coin_balance(guild_id, human_id)
    if winner_color is None:
        await set_coin_balance(guild_id, human_id, balance + bet)
        return f"\n引き分けのため **{bet}** コインを返却しました。"
    if winner_color == human_color:
        rate = AI_DIFFICULTIES.get(game.get("difficulty"), AI_DIFFICULTIES["normal"])["profit"]
        payout = bet + max(1, int(bet * rate))
        await set_coin_balance(guild_id, human_id, balance + payout)
        return f"\n勝利報酬として **{payout}** コインを受け取りました。"
    return f"\n敗北したため **{bet}** コインを失いました。"


def game_status_text(game: dict, prefix: str = "") -> str:
    diff = game.get("difficulty")
    diff_text = f"\n難易度: **{AI_DIFFICULTIES[diff]['label']}**" if diff in AI_DIFFICULTIES else ""
    bet_text = f"\n賭けコイン: **{game.get('bet', 0)}**" if game.get("bet", 0) else ""
    white = player_name(game, 2) if game.get("white_id") is not None else "未参加"
    return (
        f"{prefix + chr(10) if prefix else ''}"
        f"黒: {player_name(game, 1)}\n"
        f"白: {white}\n"
        f"現在: **{color_name(game['turn'])}番**{diff_text}{bet_text}\n"
        "行と列を選んで「置く」を押してください。"
    )


def render_gomoku_image(board: list[list[int]], selected: tuple[int, int] | None = None) -> discord.File:
    cell = 42
    margin = 42
    size = margin * 2 + cell * (BOARD_SIZE - 1)
    image = Image.new("RGB", (size, size), (224, 177, 105))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()

    line_color = (93, 58, 25)
    for i in range(BOARD_SIZE):
        p = margin + i * cell
        draw.line([(margin, p), (size - margin, p)], fill=line_color, width=2)
        draw.line([(p, margin), (p, size - margin)], fill=line_color, width=2)
        label = chr(65 + i)
        draw.text((p - 5, 12), label, fill=(50, 35, 20), font=font)
        draw.text((12, p - 8), str(i + 1), fill=(50, 35, 20), font=font)

    for hx, hy in [(3, 3), (11, 3), (7, 7), (3, 11), (11, 11)]:
        cx, cy = margin + hx * cell, margin + hy * cell
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(70, 45, 25))

    if selected:
        sx, sy = selected
        cx, cy = margin + sx * cell, margin + sy * cell
        draw.rectangle([cx - 18, cy - 18, cx + 18, cy + 18], outline=(30, 120, 220), width=4)

    for y, row in enumerate(board):
        for x, stone in enumerate(row):
            if not stone:
                continue
            cx, cy = margin + x * cell, margin + y * cell
            color = (25, 25, 25) if stone == 1 else (245, 245, 245)
            outline = (245, 245, 245) if stone == 1 else (30, 30, 30)
            draw.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=color, outline=outline, width=2)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="gomoku.png")


async def run_ai_turn(game: dict) -> str:
    if not game.get("ai") or game.get("turn") != game.get("ai_color"):
        return ""
    move = choose_ai_move(game["board"], int(game["ai_color"]), game.get("difficulty", "normal"))
    if move is None:
        return ""
    x, y = move
    game["board"][y][x] = int(game["ai_color"])
    game["turn"] = opponent(int(game["ai_color"]))
    return f"AIが **{chr(65 + x)}{y + 1}** に置きました。"


async def finish_gomoku_game(interaction: discord.Interaction, game_id: str, winner_color: int | None, prefix: str = ""):
    game = gomoku_games.get(game_id)
    if not game:
        return
    guild_id = interaction.guild_id or game.get("guild_id")
    game["finished"] = True
    coin_text = await settle_ai_coins(game, guild_id, winner_color)
    await delete_gomoku_game(guild_id, game_id)
    gomoku_games.pop(game_id, None)

    title = "五目並べ 終了"
    winner = player_name(game, winner_color)
    embed = discord.Embed(
        title=title,
        description=f"{prefix + chr(10) if prefix else ''}勝者: **{winner}**{coin_text}",
        color=0xD6A84F,
    )
    file = render_gomoku_image(game["board"])
    try:
        await interaction.message.edit(embed=embed, attachments=[file], view=None)
    except discord.HTTPException:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.response.send_message(embed=embed, file=file)


async def send_gomoku_state(interaction: discord.Interaction, game_id: str, prefix: str = "", initial: bool = False):
    game = gomoku_games.get(game_id)
    if not game:
        return
    winner = check_winner(game["board"])
    if winner or is_full(game["board"]):
        await finish_gomoku_game(interaction, game_id, winner, prefix)
        return
    await save_gomoku_game(interaction.guild_id or game.get("guild_id"), game_id, game)
    embed = discord.Embed(title="五目並べ", description=game_status_text(game, prefix), color=0xD6A84F)
    file = render_gomoku_image(game["board"])
    view = GomokuView(game_id, show_join=game.get("white_id") is None)
    if initial:
        if interaction.response.is_done():
            message = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, file=file, view=view)
            message = await interaction.original_response()
        game["message_id"] = message.id
        await save_gomoku_game(interaction.guild_id or game.get("guild_id"), game_id, game)
    else:
        await interaction.message.edit(embed=embed, attachments=[file], view=view)


async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = True, thinking: bool = False) -> bool:
    if interaction.response.is_done():
        return True
    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False


class GomokuRowSelect(discord.ui.Select):
    def __init__(self, game_id: str):
        super().__init__(
            placeholder="行を選択",
            options=[discord.SelectOption(label=str(i + 1), value=str(i)) for i in range(BOARD_SIZE)],
            custom_id=f"gomoku_row_{game_id}",
            row=0,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.response.send_message("ゲームが見つかりません。", ephemeral=True)
            return
        if not game.get("ai") and game.get("white_id") is None:
            await interaction.response.send_message("相手が参加するまで選択できません。", ephemeral=True)
            return
        if not is_turn_user(game, interaction.user.id):
            await interaction.response.send_message("今はあなたの番ではありません。", ephemeral=True)
            return
        self.view.selected_y = int(self.values[0])
        await interaction.response.send_message(f"行: {self.view.selected_y + 1}", ephemeral=True)


class GomokuColSelect(discord.ui.Select):
    def __init__(self, game_id: str):
        super().__init__(
            placeholder="列を選択",
            options=[discord.SelectOption(label=chr(65 + i), value=str(i)) for i in range(BOARD_SIZE)],
            custom_id=f"gomoku_col_{game_id}",
            row=1,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.response.send_message("ゲームが見つかりません。", ephemeral=True)
            return
        if not game.get("ai") and game.get("white_id") is None:
            await interaction.response.send_message("相手が参加するまで選択できません。", ephemeral=True)
            return
        if not is_turn_user(game, interaction.user.id):
            await interaction.response.send_message("今はあなたの番ではありません。", ephemeral=True)
            return
        self.view.selected_x = int(self.values[0])
        await interaction.response.send_message(f"列: {chr(65 + self.view.selected_x)}", ephemeral=True)


def is_turn_user(game: dict, user_id: int) -> bool:
    allowed = game.get("black_id") if game.get("turn") == 1 else game.get("white_id")
    return allowed == user_id


class GomokuPlaceButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="置く", style=discord.ButtonStyle.success, custom_id=f"gomoku_place_{game_id}", row=2)
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True, thinking=True):
            return
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.followup.send("ゲームが見つかりません。", ephemeral=True)
            return
        if not game.get("ai") and game.get("white_id") is None:
            await interaction.followup.send("相手が参加するまで開始できません。", ephemeral=True)
            return
        if not is_turn_user(game, interaction.user.id):
            await interaction.followup.send("今はあなたの番ではありません。", ephemeral=True)
            return
        x = getattr(self.view, "selected_x", None)
        y = getattr(self.view, "selected_y", None)
        if x is None or y is None:
            await interaction.followup.send("行と列を両方選んでください。", ephemeral=True)
            return
        if game["board"][y][x] != 0:
            await interaction.followup.send("その場所にはすでに石があります。", ephemeral=True)
            return

        color = int(game["turn"])
        game["board"][y][x] = color
        prefix = f"{interaction.user.mention} が **{chr(65 + x)}{y + 1}** に置きました。"
        if check_winner(game["board"]):
            await finish_gomoku_game(interaction, self.game_id, color, prefix)
            return
        if is_full(game["board"]):
            await finish_gomoku_game(interaction, self.game_id, None, prefix)
            return

        game["turn"] = opponent(color)
        ai_note = await run_ai_turn(game)
        if ai_note:
            prefix += "\n" + ai_note
            winner = check_winner(game["board"])
            if winner or is_full(game["board"]):
                await finish_gomoku_game(interaction, self.game_id, winner, prefix)
                return
        await send_gomoku_state(interaction, self.game_id, prefix)


class GomokuJoinButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="参加する", style=discord.ButtonStyle.primary, custom_id=f"gomoku_join_{game_id}", row=2)
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True, thinking=True):
            return
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.followup.send("ゲームが見つかりません。", ephemeral=True)
            return
        if game.get("white_id") is not None:
            await interaction.followup.send("すでに参加者がいます。", ephemeral=True)
            return
        if interaction.user.id == game.get("black_id"):
            await interaction.followup.send("作成者は後手に参加できません。", ephemeral=True)
            return
        game["white_id"] = interaction.user.id
        game["started"] = True
        await send_gomoku_state(interaction, self.game_id, f"{interaction.user.mention} が白番で参加しました。")
        await interaction.followup.send("参加しました。", ephemeral=True)


class GomokuSurrenderButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="降参", style=discord.ButtonStyle.danger, custom_id=f"gomoku_surrender_{game_id}", row=2)
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True, thinking=True):
            return
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.followup.send("ゲームが見つかりません。", ephemeral=True)
            return
        user_id = interaction.user.id
        if user_id not in (game.get("black_id"), game.get("white_id")):
            await interaction.followup.send("参加者のみ降参できます。", ephemeral=True)
            return
        winner = 2 if user_id == game.get("black_id") else 1
        await finish_gomoku_game(interaction, self.game_id, winner, f"{interaction.user.mention} が降参しました。")


class GomokuCancelButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="募集を中止", style=discord.ButtonStyle.danger, custom_id=f"gomoku_cancel_{game_id}", row=2)
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True, thinking=True):
            return
        game = gomoku_games.get(self.game_id)
        if not game:
            await interaction.followup.send("ゲームが見つかりません。", ephemeral=True)
            return
        if game.get("white_id") is not None:
            await interaction.followup.send("対戦開始後は「降参」を使ってください。", ephemeral=True)
            return
        is_creator = interaction.user.id == game.get("creator_id") or interaction.user.id == game.get("black_id")
        is_admin = bool(getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.manage_guild)
        if not is_creator and not is_admin:
            await interaction.followup.send("募集を中止できるのは作成者または管理者だけです。", ephemeral=True)
            return
        guild_id = interaction.guild_id or game.get("guild_id")
        await delete_gomoku_game(guild_id, self.game_id)
        gomoku_games.pop(self.game_id, None)
        try:
            await interaction.message.edit(
                embed=discord.Embed(
                    title="五目並べ 募集中止",
                    description=f"{interaction.user.mention} が五目並べ募集を中止しました。",
                    color=0x95A5A6,
                ),
                attachments=[],
                view=None,
            )
        except discord.HTTPException as e:
            print(f"[Gomoku] cancel message edit failed: {type(e).__name__}: {e}", flush=True)
        await interaction.followup.send("五目並べ募集を中止しました。", ephemeral=True)


class GomokuView(discord.ui.View):
    def __init__(self, game_id: str, show_join: bool = False):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.selected_x: int | None = None
        self.selected_y: int | None = None
        if show_join:
            self.add_item(GomokuJoinButton(game_id))
            self.add_item(GomokuCancelButton(game_id))
        else:
            self.add_item(GomokuRowSelect(game_id))
            self.add_item(GomokuColSelect(game_id))
            self.add_item(GomokuPlaceButton(game_id))
            self.add_item(GomokuSurrenderButton(game_id))


class GomokuLobbyCleanupView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=300)
        self.add_item(GomokuCancelButton(game_id))


def gomoku_mode_embed() -> discord.Embed:
    return discord.Embed(
        title="五目並べ パネル",
        description=(
            "対人戦かAI戦を選んでください。\n"
            "AI戦は初級・中級・上級を選べます。コイン賭けは `/gomoku_ai` から指定できます。"
        ),
        color=0xD6A84F,
    )


class GomokuModeButton(discord.ui.Button):
    def __init__(self, label: str, mode: str, difficulty: str | None = None, row: int = 0):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary if mode == "pvp" else discord.ButtonStyle.success,
            custom_id=f"game_gomoku_mode_{mode}_{difficulty or 'pvp'}",
            row=row,
        )
        self.mode = mode
        self.difficulty = difficulty

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Gomoku")
        if not cog:
            await interaction.response.send_message("五目並べは現在利用できません。", ephemeral=True)
            return
        if self.mode == "pvp":
            await cog.start_pvp(interaction)
            return
        await interaction.response.send_message(
            embed=gomoku_first_embed(self.difficulty or "normal"),
            view=GomokuFirstView(self.difficulty or "normal"),
            ephemeral=True,
        )


class GomokuModeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(GomokuModeButton("対人作成", "pvp", row=0))
        self.add_item(GomokuModeButton("AI: 初級", "ai", "easy", row=0))
        self.add_item(GomokuModeButton("AI: 中級", "ai", "normal", row=0))
        self.add_item(GomokuModeButton("AI: 上級", "ai", "hard", row=1))
        self.add_item(GomokuRulesButton(row=1))


class GomokuRulesButton(discord.ui.Button):
    def __init__(self, row: int = 1):
        super().__init__(label="ルール", style=discord.ButtonStyle.secondary, custom_id="game_gomoku_rules", row=row)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="五目並べのルール",
            description=(
                "黒と白が交互に石を置き、先に縦・横・斜めのどれかで **5個連続** に並べた人が勝ちです。\n\n"
                "**操作方法**\n"
                "行と列を選んでから「置く」を押します。すでに石がある場所には置けません。\n\n"
                "**対人戦**\n"
                "作成者が黒番、参加者が白番です。参加者が入るまで石は置けません。\n\n"
                "**AI戦**\n"
                "初級・中級・上級を選び、先手/後手/ランダムを選んで開始します。"
            ),
            color=0xD6A84F,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def gomoku_first_embed(difficulty: str) -> discord.Embed:
    label = AI_DIFFICULTIES.get(difficulty, AI_DIFFICULTIES["normal"])["label"]
    return discord.Embed(
        title="五目並べ AI対戦",
        description=f"難易度: **{label}**\n先手・後手・ランダムを選んでください。",
        color=0xD6A84F,
    )


class GomokuFirstButton(discord.ui.Button):
    def __init__(self, label: str, difficulty: str, first: str, row: int = 0):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"game_gomoku_first_{difficulty}_{first}",
            row=row,
        )
        self.difficulty = difficulty
        self.first = first

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Gomoku")
        if not cog:
            await interaction.response.send_message("五目並べは現在利用できません。", ephemeral=True)
            return
        await cog.start_ai(interaction, self.difficulty, 0, self.first)


class GomokuFirstView(discord.ui.View):
    def __init__(self, difficulty: str):
        super().__init__(timeout=None)
        self.add_item(GomokuFirstButton("先手（黒）", difficulty, "black", row=0))
        self.add_item(GomokuFirstButton("後手（白）", difficulty, "white", row=0))
        self.add_item(GomokuFirstButton("ランダム", difficulty, "random", row=0))


class Gomoku(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restore_task = None

    async def cog_load(self):
        self._restore_task = asyncio.create_task(self._restore_saved_games())

    async def cog_unload(self):
        if self._restore_task:
            self._restore_task.cancel()

    async def _restore_saved_games(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await load_gomoku_games_for_guild(self.bot, guild)

    async def start_pvp(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        if game_id in gomoku_games:
            if await cleanup_stale_gomoku_game(interaction, game_id):
                return await self.start_pvp(interaction)
            game = gomoku_games[game_id]
            message_id = game.get("message_id") or "未保存"
            if not game.get("ai") and game.get("white_id") is None:
                await interaction.response.send_message(
                    f"このチャンネルには未開始の五目並べ募集があります。既存パネルの「参加する」または「募集を中止」を使ってください。\n対象メッセージID: `{message_id}`",
                    view=GomokuLobbyCleanupView(game_id),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(f"このチャンネルにはすでに進行中の五目並べがあります。\n対象メッセージID: `{message_id}`", ephemeral=True)
            return
        game = {
            "board": new_board(),
            "turn": 1,
            "black_id": interaction.user.id,
            "white_id": None,
            "creator_id": interaction.user.id,
            "guild_id": interaction.guild_id,
            "ai": False,
            "started": False,
        }
        gomoku_games[game_id] = game
        await save_gomoku_game(interaction.guild_id, game_id, game)
        embed = discord.Embed(title="五目並べ", description=game_status_text(game), color=0xD6A84F)
        await interaction.response.send_message(
            embed=embed,
            file=render_gomoku_image(game["board"]),
            view=GomokuView(game_id, show_join=True),
        )
        message = await interaction.original_response()
        game["message_id"] = message.id
        await save_gomoku_game(interaction.guild_id, game_id, game)

    async def start_ai(self, interaction: discord.Interaction, difficulty: str, bet: int = 0, first: str = "black"):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        game_id = str(interaction.channel_id)
        if game_id in gomoku_games:
            if await cleanup_stale_gomoku_game(interaction, game_id):
                return await self.start_ai(interaction, difficulty, bet, first)
            game = gomoku_games[game_id]
            message_id = game.get("message_id") or "未保存"
            if not game.get("ai") and game.get("white_id") is None:
                await interaction.response.send_message(
                    f"このチャンネルには未開始の五目並べ募集があります。既存募集を中止してからAI戦を開始してください。\n対象メッセージID: `{message_id}`",
                    view=GomokuLobbyCleanupView(game_id),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(f"このチャンネルにはすでに進行中の五目並べがあります。\n対象メッセージID: `{message_id}`", ephemeral=True)
            return
        if bet < 0:
            await interaction.response.send_message("賭けコインは0以上にしてください。", ephemeral=True)
            return
        if bet > 0:
            balance = await get_coin_balance(interaction.guild_id, interaction.user.id)
            if balance < bet:
                await interaction.response.send_message(f"コインが足りません。現在 **{balance}** コインです。", ephemeral=True)
                return
            await set_coin_balance(interaction.guild_id, interaction.user.id, balance - bet)
        await interaction.response.defer()

        player_first, was_random = resolve_first_choice(first)
        human_color = 1 if player_first == "black" else 2
        ai_color = opponent(human_color)
        game = {
            "board": new_board(),
            "turn": 1,
            "black_id": interaction.user.id if human_color == 1 else AI_PLAYER_ID,
            "white_id": interaction.user.id if human_color == 2 else AI_PLAYER_ID,
            "creator_id": interaction.user.id,
            "guild_id": interaction.guild_id,
            "ai": True,
            "started": True,
            "human_id": interaction.user.id,
            "human_color": human_color,
            "ai_color": ai_color,
            "difficulty": difficulty,
            "bet": bet,
            "coin_settled": False,
        }
        gomoku_games[game_id] = game
        first_text = "先手（黒）" if human_color == 1 else "後手（白）"
        prefix = f"AI対戦を開始しました。難易度: **{AI_DIFFICULTIES[difficulty]['label']}**\nあなたは **{first_text}** です。"
        if was_random:
            prefix += "\nランダム抽選で決定しました。"
        ai_note = await run_ai_turn(game)
        if ai_note:
            prefix += "\n" + ai_note
        await send_gomoku_state(interaction, game_id, prefix, initial=True)

    @app_commands.command(name="gomoku", description="五目並べの対人戦を開始します")
    async def gomoku(self, interaction: discord.Interaction):
        await self.start_pvp(interaction)

    @app_commands.command(name="gomoku_ai", description="AIと五目並べで対戦します")
    @app_commands.describe(difficulty="AIの難易度", bet="賭けるコイン数。0で賭けなし", first="先手/後手。未指定ならランダム")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="初級", value="easy"),
            app_commands.Choice(name="中級", value="normal"),
            app_commands.Choice(name="上級", value="hard"),
        ],
        first=[
            app_commands.Choice(name="先手（黒）", value="black"),
            app_commands.Choice(name="後手（白）", value="white"),
            app_commands.Choice(name="ランダム", value="random"),
        ],
    )
    async def gomoku_ai(
        self,
        interaction: discord.Interaction,
        difficulty: app_commands.Choice[str],
        bet: int = 0,
        first: app_commands.Choice[str] | None = None,
    ):
        await self.start_ai(interaction, difficulty.value, bet, first.value if first else "random")


async def setup(bot: commands.Bot):
    await bot.add_cog(Gomoku(bot))
