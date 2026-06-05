import asyncio
import json
from io import BytesIO

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from database.config_db import db_get, db_set

try:
    import shogi
except ModuleNotFoundError:
    shogi = None


shogi_games: dict[str, dict] = {}

PIECES = {
    "K": "玉",
    "R": "飛",
    "B": "角",
    "G": "金",
    "S": "銀",
    "N": "桂",
    "L": "香",
    "P": "歩",
    "+R": "龍",
    "+B": "馬",
    "+S": "成銀",
    "+N": "成桂",
    "+L": "成香",
    "+P": "と",
}
USI_PIECE_TO_TEXT = {"R": "飛", "B": "角", "G": "金", "S": "銀", "N": "桂", "L": "香", "P": "歩"}
RANK_TO_JA = {"a": "一", "b": "二", "c": "三", "d": "四", "e": "五", "f": "六", "g": "七", "h": "八", "i": "九"}


def shogi_index_key(guild_id: int) -> str:
    return f"shogi_games_index:{guild_id}"


def shogi_game_key(guild_id: int, game_id: str) -> str:
    return f"shogi_game:{guild_id}:{game_id}"


async def save_shogi_game(guild_id: int | None, game_id: str, state: dict | None = None):
    if not guild_id:
        return
    state = state or shogi_games.get(game_id)
    if not state:
        return
    state["guild_id"] = guild_id
    await db_set(shogi_game_key(guild_id, game_id), json.dumps(state, ensure_ascii=False))
    try:
        index = json.loads(await db_get(shogi_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
    await db_set(shogi_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_shogi_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(shogi_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(shogi_index_key(guild_id), json.dumps(index, ensure_ascii=False))
    await db_set(shogi_game_key(guild_id, game_id), "")


async def load_shogi_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(shogi_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []
    active = []
    for game_id in index:
        raw = await db_get(shogi_game_key(guild.id, game_id))
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            continue
        players = state.get("players") or []
        if not players:
            continue
        state["players"] = [int(uid) for uid in players]
        state["creator_id"] = int(state.get("creator_id", state["players"][0]) or state["players"][0])
        shogi_games[game_id] = state
        active.append(game_id)
        bot.add_view(ShogiMoveView(game_id) if state.get("started") else ShogiLobbyView(game_id))
    await db_set(shogi_index_key(guild.id), json.dumps(active, ensure_ascii=False))


def load_font(size: int, bold: bool = False):
    names = [
        "meiryo.ttc",
        "YuGothB.ttc" if bold else "YuGothM.ttc",
        "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
        "NotoSansJP-Bold.otf" if bold else "NotoSansJP-Regular.otf",
        "ipaexg.ttf",
        "ipag.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def parse_sfen_piece(token: str) -> tuple[str, str]:
    promoted = token.startswith("+")
    if promoted:
        token = token[1:]
    owner = "sente" if token.isupper() else "gote"
    piece = token.upper()
    return owner, f"+{piece}" if promoted else piece


def pieces_from_sfen(sfen: str) -> dict[tuple[int, int], tuple[str, str]]:
    board_part = sfen.split()[0]
    pieces = {}
    for rank_index, row in enumerate(board_part.split("/"), start=1):
        file_num = 9
        index = 0
        while index < len(row):
            char = row[index]
            if char.isdigit():
                file_num -= int(char)
                index += 1
                continue
            token = row[index:index + 2] if char == "+" and index + 1 < len(row) else char
            index += len(token)
            pieces[(file_num, rank_index)] = parse_sfen_piece(token)
            file_num -= 1
    return pieces


def hands_from_sfen(sfen: str) -> dict[str, list[str]]:
    parts = sfen.split()
    if len(parts) < 3 or parts[2] == "-":
        return {"sente": [], "gote": []}
    hands = {"sente": [], "gote": []}
    count_text = ""
    for char in parts[2]:
        if char.isdigit():
            count_text += char
            continue
        count = int(count_text or "1")
        count_text = ""
        owner = "sente" if char.isupper() else "gote"
        hands[owner].extend([char.upper()] * count)
    return hands


def piece_text(piece: str) -> str:
    return PIECES.get(piece, piece)


def square_label(square: str) -> str:
    if len(square) != 2:
        return square
    return f"{square[0]}{RANK_TO_JA.get(square[1], square[1])}"


def usi_square_to_coord(square: str) -> tuple[int, int] | None:
    if len(square) != 2 or not square[0].isdigit() or square[1] not in "abcdefghi":
        return None
    return int(square[0]), "abcdefghi".index(square[1]) + 1


def move_source_key(move_value: str) -> str:
    return move_value[:2]


def move_destination_key(move_value: str) -> str:
    return move_value[2:4]


def board_from_state(state: dict):
    if shogi is None:
        return None
    try:
        return shogi.Board(state.get("sfen") or shogi.Board().sfen())
    except Exception:
        return shogi.Board()


def legal_moves(state: dict) -> list[str]:
    board = board_from_state(state)
    if not board:
        return []
    return sorted({move.usi() for move in board.legal_moves})


def current_player_id(state: dict) -> int | None:
    players = state.get("players") or []
    if len(players) < 2:
        return players[0] if players else None
    board = board_from_state(state)
    if board and shogi is not None:
        return players[0] if board.turn == shogi.BLACK else players[1]
    return players[0]


def current_side_label(state: dict) -> str:
    board = board_from_state(state)
    if board and shogi is not None:
        return "先手" if board.turn == shogi.BLACK else "後手"
    return "先手"


def piece_at_square(sfen: str, square: str) -> str:
    coord = usi_square_to_coord(square)
    if not coord:
        return ""
    item = pieces_from_sfen(sfen).get(coord)
    return piece_text(item[1]) if item else ""


def move_source_label(sfen: str, source: str) -> str:
    if "*" in source:
        return f"持ち駒 {USI_PIECE_TO_TEXT.get(source[0], source[0])}"
    piece = piece_at_square(sfen, source)
    return f"{piece} {square_label(source)}" if piece else square_label(source)


def move_label(sfen: str, move_value: str) -> str:
    if "*" in move_value[:2]:
        piece = USI_PIECE_TO_TEXT.get(move_value[0], move_value[0])
        return f"{piece}打 {square_label(move_value[2:4])}"
    source = move_value[:2]
    destination = move_value[2:4]
    promote = "成" if move_value.endswith("+") else ""
    piece = piece_at_square(sfen, source)
    prefix = f"{piece} " if piece else ""
    return f"{prefix}{square_label(source)}→{square_label(destination)}{promote}"


def status_text(state: dict, prefix: str = "") -> str:
    players = state.get("players") or []
    sente = f"<@{players[0]}>" if len(players) >= 1 else "未定"
    gote = f"<@{players[1]}>" if len(players) >= 2 else "未定"
    current = current_player_id(state)
    lines = ["**将棋 対局中**", f"先手: {sente}", f"後手: {gote}"]
    if current:
        lines.append(f"手番: **{current_side_label(state)}** <@{current}>")
    board = board_from_state(state)
    if board and getattr(board, "is_check", lambda: False)():
        lines.append("王手がかかっています。")
    if prefix:
        lines.insert(0, prefix)
    return "\n".join(lines)


def render_board_file(state: dict, selected_source: str | None = None, hints: set[tuple[int, int]] | None = None) -> discord.File:
    sfen = state.get("sfen") or (shogi.Board().sfen() if shogi else "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1")
    pieces = pieces_from_sfen(sfen)
    hands = hands_from_sfen(sfen)
    cell = 66
    left, top = 60, 78
    board_size = cell * 9
    width = left + board_size + 280
    height = top + board_size + 70
    image = Image.new("RGB", (width, height), (42, 66, 54))
    draw = ImageDraw.Draw(image)
    title_font = load_font(28, True)
    small_font = load_font(18)
    coord_font = load_font(16, True)
    piece_font = load_font(25, True)
    owner_font = load_font(12, True)

    draw.text((34, 24), "将棋", fill=(255, 255, 255), font=title_font)
    draw.rectangle((left, top, left + board_size, top + board_size), fill=(226, 174, 96), outline=(64, 42, 24), width=3)
    for index in range(10):
        x = left + index * cell
        y = top + index * cell
        draw.line((x, top, x, top + board_size), fill=(80, 52, 28), width=1)
        draw.line((left, y, left + board_size, y), fill=(80, 52, 28), width=1)

    for file_num in range(9, 0, -1):
        col = 9 - file_num
        draw.text((left + col * cell + 26, top - 25), str(file_num), fill=(235, 235, 220), font=coord_font)
    for rank in range(1, 10):
        draw.text((left - 30, top + (rank - 1) * cell + 23), str(rank), fill=(235, 235, 220), font=coord_font)

    hints = hints or set()
    source_coord = usi_square_to_coord(selected_source) if selected_source and "*" not in selected_source else None
    for file_num, rank in hints:
        col, row = 9 - file_num, rank - 1
        x, y = left + col * cell, top + row * cell
        draw.rounded_rectangle((x + 7, y + 7, x + cell - 7, y + cell - 7), radius=11, fill=(69, 130, 214), outline=(230, 245, 255), width=3)
    if source_coord:
        file_num, rank = source_coord
        col, row = 9 - file_num, rank - 1
        x, y = left + col * cell, top + row * cell
        draw.rounded_rectangle((x + 4, y + 4, x + cell - 4, y + cell - 4), radius=11, outline=(255, 214, 84), width=5)

    for (file_num, rank), (owner, piece) in pieces.items():
        col, row = 9 - file_num, rank - 1
        x, y = left + col * cell + 7, top + row * cell + 6
        points = [(x + 26, y), (x + 52, y + 14), (x + 47, y + 55), (x + 5, y + 55), (x, y + 14)]
        owner_color = (56, 126, 214) if owner == "sente" else (218, 82, 82)
        owner_label = "先" if owner == "sente" else "後"
        if owner == "gote":
            points = [(px, y + 55 - (py - y)) for px, py in points]
        draw.polygon(points, fill=(250, 222, 151), outline=(82, 54, 26))
        draw.line(points + [points[0]], fill=owner_color, width=3)
        draw.rounded_rectangle((x + 2, y + 2, x + 20, y + 20), radius=5, fill=owner_color)
        draw.text((x + 5, y + 3), owner_label, fill=(255, 255, 255), font=owner_font)
        label = piece_text(piece)
        bbox = draw.textbbox((0, 0), label, font=piece_font)
        draw.text((x + 26 - (bbox[2] - bbox[0]) / 2, y + 28 - (bbox[3] - bbox[1]) / 2), label, fill=(34, 28, 22), font=piece_font)

    side_x = left + board_size + 34
    draw.rounded_rectangle((side_x, top - 34, side_x + 64, top - 8), radius=8, fill=(56, 126, 214))
    draw.text((side_x + 8, top - 31), "先手", fill=(255, 255, 255), font=small_font)
    draw.rounded_rectangle((side_x + 76, top - 34, side_x + 140, top - 8), radius=8, fill=(218, 82, 82))
    draw.text((side_x + 84, top - 31), "後手", fill=(255, 255, 255), font=small_font)
    draw.text((side_x, top + 8), "持ち駒", fill=(255, 255, 255), font=small_font)
    sente = " ".join(piece_text(piece) for piece in hands["sente"]) or "なし"
    gote = " ".join(piece_text(piece) for piece in hands["gote"]) or "なし"
    draw.text((side_x, top + 44), f"先手: {sente}", fill=(255, 245, 210), font=small_font)
    draw.text((side_x, top + 76), f"後手: {gote}", fill=(255, 245, 210), font=small_font)
    draw.text((side_x, top + 138), "駒を選ぶと", fill=(220, 236, 222), font=small_font)
    draw.text((side_x, top + 166), "移動候補を表示します。", fill=(220, 236, 222), font=small_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="shogi_board.png")


def lobby_text(state: dict) -> str:
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", [])) or "なし"
    return f"**将棋 募集中**\n参加者: {players}\n\n2人で開始できます。先手は作成者、後手は2人目の参加者です。"


class ShogiLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel", "rules"), self.children):
            child.custom_id = f"shogi_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = shogi_games.get(self.game_id)
        if not state or state.get("started"):
            await interaction.response.send_message("この募集には参加できません。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        if len(state["players"]) >= 2:
            await interaction.response.send_message("将棋は2人までです。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = shogi_games.get(self.game_id)
        if not state or state.get("started"):
            await interaction.response.send_message("開始後は抜けられません。投了を使ってください。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("参加していません。", ephemeral=True)
            return
        state["players"] = [uid for uid in state["players"] if uid != interaction.user.id]
        if not state["players"]:
            await delete_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            shogi_games.pop(self.game_id, None)
            await interaction.response.edit_message(content="将棋の募集を終了しました。", view=None)
            return
        state["creator_id"] = state["players"][0]
        await save_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_shogi_game(interaction, self.game_id)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = shogi_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("募集がありません。", ephemeral=True)
            return
        if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("中止できるのは作成者または管理者です。", ephemeral=True)
            return
        await delete_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        shogi_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="将棋の募集を中止しました。", view=None)

    @discord.ui.button(label="ルール", style=discord.ButtonStyle.secondary, row=1)
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "仮版の本将棋です。2人で対局し、手番の人だけが駒と移動先を選べます。"
            "現在は千日手、持将棋、時間制限は未対応です。",
            ephemeral=True,
        )


class ShogiMoveView(discord.ui.View):
    def __init__(self, game_id: str, source: str | None = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        state = shogi_games.get(game_id)
        if not state:
            return
        if source:
            self.add_item(ShogiDestinationSelect(game_id, source))
            self.add_item(ShogiBackButton(game_id))
        else:
            self.add_item(ShogiSourceSelect(game_id))
        self.add_item(ShogiResignButton(game_id))


class ShogiSourceSelect(discord.ui.Select):
    def __init__(self, game_id: str):
        state = shogi_games.get(game_id, {})
        moves = legal_moves(state)
        seen = set()
        options = []
        for move in moves:
            source = move_source_key(move)
            if source in seen:
                continue
            seen.add(source)
            options.append(discord.SelectOption(label=move_source_label(state.get("sfen", ""), source)[:100], value=source))
        options = options[:25] or [discord.SelectOption(label="候補なし", value="none")]
        super().__init__(placeholder="動かす駒を選んでください", options=options, custom_id=f"shogi_source_{game_id}")
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        state = shogi_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("対局が見つかりません。", ephemeral=True)
            return
        if interaction.user.id != current_player_id(state):
            await interaction.response.send_message("あなたの手番ではありません。", ephemeral=True)
            return
        source = self.values[0]
        if source == "none":
            await interaction.response.send_message("指せる手がありません。", ephemeral=True)
            return
        hints = {usi_square_to_coord(move_destination_key(move)) for move in legal_moves(state) if move_source_key(move) == source}
        hints = {coord for coord in hints if coord}
        await interaction.response.edit_message(
            content=f"移動元: **{move_source_label(state['sfen'], source)}**\n移動先を選んでください。",
            attachments=[render_board_file(state, selected_source=source, hints=hints)],
            view=ShogiMoveView(self.game_id, source),
        )


class ShogiDestinationSelect(discord.ui.Select):
    def __init__(self, game_id: str, source: str):
        state = shogi_games.get(game_id, {})
        moves = [move for move in legal_moves(state) if move_source_key(move) == source]
        options = [discord.SelectOption(label=move_label(state.get("sfen", ""), move)[:100], value=move) for move in moves[:25]]
        options = options or [discord.SelectOption(label="候補なし", value="none")]
        super().__init__(placeholder="移動先を選んでください", options=options, custom_id=f"shogi_dest_{game_id}_{source}")
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        state = shogi_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("対局が見つかりません。", ephemeral=True)
            return
        if interaction.user.id != current_player_id(state):
            await interaction.response.send_message("あなたの手番ではありません。", ephemeral=True)
            return
        move_value = self.values[0]
        if move_value == "none":
            await interaction.response.send_message("移動先候補がありません。", ephemeral=True)
            return
        board = board_from_state(state)
        if not board or shogi is None:
            await interaction.response.send_message("将棋ライブラリを読み込めませんでした。", ephemeral=True)
            return
        move = shogi.Move.from_usi(move_value)
        if not any(move == legal for legal in board.legal_moves):
            await interaction.response.send_message("その手は指せません。", ephemeral=True)
            return
        label = move_label(state["sfen"], move_value)
        board.push(move)
        state["sfen"] = board.sfen()
        await save_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        if board.is_checkmate():
            winner = interaction.user.mention
            await delete_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            shogi_games.pop(self.game_id, None)
            await interaction.response.edit_message(
                content=f"**詰みです。{winner} の勝ちです。**\n最後の手: {label}",
                attachments=[render_board_file(state)],
                view=None,
            )
            return
        await interaction.response.edit_message(
            content=status_text(state, f"{interaction.user.mention} が **{label}** を指しました。"),
            attachments=[render_board_file(state)],
            view=ShogiMoveView(self.game_id),
        )


class ShogiBackButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="駒選択に戻る", style=discord.ButtonStyle.secondary, custom_id=f"shogi_back_{game_id}")
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        state = shogi_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("対局が見つかりません。", ephemeral=True)
            return
        await interaction.response.edit_message(content=status_text(state), attachments=[render_board_file(state)], view=ShogiMoveView(self.game_id))


class ShogiResignButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(label="投了", style=discord.ButtonStyle.danger, row=1, custom_id=f"shogi_resign_{game_id}")
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        state = shogi_games.get(self.game_id)
        if not state or interaction.user.id not in state.get("players", []):
            await interaction.response.send_message("対局参加者のみ投了できます。", ephemeral=True)
            return
        winner_id = next((uid for uid in state["players"] if uid != interaction.user.id), None)
        await delete_shogi_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        shogi_games.pop(self.game_id, None)
        await interaction.response.edit_message(content=f"<@{interaction.user.id}> が投了しました。<@{winner_id}> の勝ちです。", view=None)


async def create_shogi_lobby(interaction: discord.Interaction):
    game_id = str(interaction.channel_id)
    if shogi is None:
        await interaction.response.send_message("将棋ライブラリが未導入のため、将棋は利用できません。`python-shogi` を入れてください。", ephemeral=True)
        return
    if game_id in shogi_games:
        await interaction.response.send_message("このチャンネルにはすでに将棋の募集または対局があります。", ephemeral=True)
        return
    state = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "creator_id": interaction.user.id,
        "players": [interaction.user.id],
        "started": False,
        "sfen": "",
    }
    shogi_games[game_id] = state
    await save_shogi_game(interaction.guild_id, game_id, state)
    await interaction.response.send_message(lobby_text(state), view=ShogiLobbyView(game_id))


async def start_shogi_game(interaction: discord.Interaction, game_id: str):
    state = shogi_games.get(game_id)
    if not state:
        await interaction.response.send_message("将棋の募集がありません。", ephemeral=True)
        return
    if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("開始できるのは作成者または管理者です。", ephemeral=True)
        return
    if len(state.get("players", [])) < 2:
        await interaction.response.send_message("2人必要です。", ephemeral=True)
        return
    state["started"] = True
    state["sfen"] = shogi.Board().sfen()
    await save_shogi_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    await interaction.response.edit_message(content=status_text(state, "将棋を開始しました。"), attachments=[render_board_file(state)], view=ShogiMoveView(game_id))


def shogi_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="将棋",
        description="2人用の本将棋です。現在は仮版のため、千日手・持将棋・時間制限は未対応です。",
        color=0xB8860B,
    )


class ShogiPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShogiCreateButton())
        self.add_item(ShogiRulesButton())


class ShogiCreateButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="募集作成", style=discord.ButtonStyle.primary, custom_id="shogi_panel_create")

    async def callback(self, interaction: discord.Interaction):
        await create_shogi_lobby(interaction)


class ShogiRulesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="ルール", style=discord.ButtonStyle.secondary, custom_id="shogi_panel_rules")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "王将を詰ませた側の勝ちです。自分の手番で駒を選び、表示された移動先から指し手を選んでください。"
            "持ち駒の打ちも選択肢に出ます。",
            ephemeral=True,
        )


class Shogi(commands.Cog):
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
            await load_shogi_games_for_guild(self.bot, guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shogi(bot))
