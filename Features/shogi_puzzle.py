import random
from datetime import datetime, timedelta, timezone
from io import BytesIO

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from cogs.community import apply_coin_rewards, coin_key
from database.config_db import db_get, db_set

try:
    import shogi
except ModuleNotFoundError:
    shogi = None


JST = timezone(timedelta(hours=9))

LEVELS = {
    "easy": {"label": "初級", "reward": 2, "description": "1手詰め中心。まずは気軽に。"},
    "normal": {"label": "中級", "reward": 5, "description": "少し読む問題。慣れてきた人向け。"},
    "hard": {"label": "上級", "reward": 8, "description": "読みが必要な問題。腕試し向け。"},
}

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

PUZZLES = [
    {
        "id": "easy_001",
        "level": "easy",
        "title": "初級 1手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (5, 3): ("sente", "R"),
            (4, 2): ("sente", "G"),
            (6, 2): ("sente", "G"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": [], "gote": []},
        "answer": "5c5b+",
        "answer_text": "飛 5三→5二成",
        "options": [
            {"label": "飛 5三→5二成", "value": "5c5b+"},
            {"label": "金 4二→4一", "value": "4b4a"},
            {"label": "金 6二→6一", "value": "6b6a"},
            {"label": "飛 5三→5一成", "value": "5c5a+"},
        ],
        "explanation": "飛車を5三から5二へ成って、玉の逃げ道をふさぐ形です。",
    },
    {
        "id": "easy_002",
        "level": "easy",
        "title": "初級 1手詰め",
        "side": "先手",
        "pieces": {
            (4, 1): ("gote", "K"),
            (4, 3): ("sente", "G"),
            (5, 2): ("sente", "R"),
            (3, 2): ("sente", "S"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": [], "gote": []},
        "answer": "4c4b",
        "answer_text": "金 4三→4二",
        "options": [
            {"label": "金 4三→4二", "value": "4c4b"},
            {"label": "飛 5二→5一成", "value": "5b5a+"},
            {"label": "銀 3二→3一成", "value": "3b3a+"},
            {"label": "金 4三→4一", "value": "4c4a"},
        ],
        "explanation": "玉の正面に金を寄せて逃げ道を消す基本形です。飛車成は強い王手に見えますが、この問題では金で密着する手を正解にしています。",
    },
    {
        "id": "normal_001",
        "level": "normal",
        "title": "中級 3手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (4, 1): ("gote", "G"),
            (6, 1): ("gote", "G"),
            (5, 3): ("sente", "R"),
            (4, 3): ("sente", "B"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": ["G"], "gote": []},
        "answer": "G*5b",
        "answer_text": "金打 5二",
        "options": [
            {"label": "金打 5二", "value": "G*5b"},
            {"label": "飛 5三→5一成", "value": "5c5a+"},
            {"label": "角 4三→4二成", "value": "4c4b+"},
            {"label": "金打 6二", "value": "G*6b"},
        ],
        "explanation": "持ち駒の金で玉を押さえるのが急所です。飛車や角を先に動かすと逃げ道が残ります。",
    },
    {
        "id": "normal_002",
        "level": "normal",
        "title": "中級 3手詰め",
        "side": "先手",
        "pieces": {
            (3, 1): ("gote", "K"),
            (2, 1): ("gote", "G"),
            (4, 1): ("gote", "S"),
            (3, 3): ("sente", "B"),
            (5, 3): ("sente", "R"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": ["G"], "gote": []},
        "answer": "G*3b",
        "answer_text": "金打 3二",
        "options": [
            {"label": "金打 3二", "value": "G*3b"},
            {"label": "角 3三→2二成", "value": "3c2b+"},
            {"label": "飛 5三→5一成", "value": "5c5a+"},
            {"label": "金打 4二", "value": "G*4b"},
        ],
        "explanation": "3二金で玉の正面を押さえるのが詰み筋です。大駒の王手より金の密着が強い場面です。",
    },
    {
        "id": "hard_001",
        "level": "hard",
        "title": "上級 5手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (4, 1): ("gote", "G"),
            (6, 1): ("gote", "S"),
            (5, 4): ("sente", "R"),
            (3, 3): ("sente", "B"),
            (6, 3): ("sente", "S"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": ["G", "G"], "gote": []},
        "answer": "G*5b",
        "answer_text": "金打 5二",
        "options": [
            {"label": "金打 5二", "value": "G*5b"},
            {"label": "金打 4二", "value": "G*4b"},
            {"label": "飛 5四→5一成", "value": "5d5a+"},
            {"label": "銀 6三→6二成", "value": "6c6b+"},
        ],
        "explanation": "初手は5二金。玉を狭くしてから大駒を使うのがポイントです。",
    },
    {
        "id": "hard_002",
        "level": "hard",
        "title": "上級 5手詰め",
        "side": "先手",
        "pieces": {
            (7, 1): ("gote", "K"),
            (6, 1): ("gote", "G"),
            (8, 1): ("gote", "G"),
            (7, 4): ("sente", "R"),
            (5, 3): ("sente", "B"),
            (8, 3): ("sente", "S"),
            (9, 9): ("sente", "K"),
        },
        "hands": {"sente": ["G", "S"], "gote": []},
        "answer": "G*7b",
        "answer_text": "金打 7二",
        "options": [
            {"label": "金打 7二", "value": "G*7b"},
            {"label": "銀 8三→7二成", "value": "8c7b+"},
            {"label": "飛 7四→7一成", "value": "7d7a+"},
            {"label": "金打 8二", "value": "G*8b"},
        ],
        "explanation": "金を玉の頭に打つことで逃げ道を消します。派手な大駒より、金の打ち込みが急所です。",
    },
]


def shogi_daily_key(guild_id: int, user_id: int, level: str) -> str:
    return f"shogi_puzzle_daily:{guild_id}:{user_id}:{level}"


def jst_today() -> str:
    return datetime.now(JST).date().isoformat()


def puzzle_for_level(level: str) -> dict:
    candidates = [puzzle for puzzle in PUZZLES if puzzle["level"] == level]
    return random.choice(candidates)


def load_font(size: int, bold: bool = False):
    names = [
        "meiryo.ttc",
        "YuGothB.ttc" if bold else "YuGothM.ttc",
        "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
        "NotoSansJP-Bold.otf" if bold else "NotoSansJP-Regular.otf",
        "ipaexg.ttf",
        "ipag.ttf",
        "TakaoGothic.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def piece_text(piece: str) -> str:
    return PIECES.get(piece, piece)


def piece_short(piece: str) -> str:
    return {
        "K": "K",
        "R": "R",
        "B": "B",
        "G": "G",
        "S": "S",
        "N": "N",
        "L": "L",
        "P": "P",
        "+R": "+R",
        "+B": "+B",
        "+S": "+S",
        "+N": "+N",
        "+L": "+L",
        "+P": "+P",
    }.get(piece, piece)


def option_label(option: dict | str) -> str:
    return option.get("label", "") if isinstance(option, dict) else str(option)


def option_value(option: dict | str) -> str:
    return option.get("value", option.get("label", "")) if isinstance(option, dict) else str(option)


def answer_text(puzzle: dict) -> str:
    return puzzle.get("answer_text") or next(
        (option_label(option) for option in puzzle.get("options", []) if option_value(option) == puzzle.get("answer")),
        str(puzzle.get("answer", "")),
    )


RANK_TO_JA = {
    "a": "一",
    "b": "二",
    "c": "三",
    "d": "四",
    "e": "五",
    "f": "六",
    "g": "七",
    "h": "八",
    "i": "九",
}

USI_PIECE_TO_TEXT = {
    "R": "飛",
    "B": "角",
    "G": "金",
    "S": "銀",
    "N": "桂",
    "L": "香",
    "P": "歩",
}


def square_label(square: str) -> str:
    if len(square) != 2:
        return square
    return f"{square[0]}{RANK_TO_JA.get(square[1], square[1])}"


def piece_at_usi_square(puzzle: dict, square: str) -> str:
    if len(square) != 2:
        return ""
    file_num = int(square[0])
    rank = "abcdefghi".index(square[1]) + 1
    item = puzzle["pieces"].get((file_num, rank))
    if not item:
        return ""
    return piece_text(item[1])


def move_source_key(move_value: str) -> str:
    return move_value[:2] if "*" not in move_value[:2] else move_value[:2]


def move_destination_key(move_value: str) -> str:
    return move_value[2:4] if "*" in move_value[:2] else move_value[2:4]


def usi_square_to_coord(square: str) -> tuple[int, int] | None:
    if len(square) != 2 or not square[0].isdigit() or square[1] not in "abcdefghi":
        return None
    return int(square[0]), "abcdefghi".index(square[1]) + 1


def move_source_label(puzzle: dict, source: str) -> str:
    if "*" in source:
        return f"持ち駒 {USI_PIECE_TO_TEXT.get(source[0], source[0])}"
    piece = piece_at_usi_square(puzzle, source)
    prefix = f"{piece} " if piece else ""
    return f"{prefix}{square_label(source)}"


def move_label(puzzle: dict, move_value: str) -> str:
    if "*" in move_value[:2]:
        piece = USI_PIECE_TO_TEXT.get(move_value[0], move_value[0])
        return f"{piece}打 {square_label(move_value[2:4])}"
    source = move_value[:2]
    destination = move_value[2:4]
    piece = piece_at_usi_square(puzzle, source)
    promote = "成" if move_value.endswith("+") else ""
    prefix = f"{piece} " if piece else ""
    return f"{prefix}{square_label(source)}→{square_label(destination)}{promote}"


def fallback_move_values(puzzle: dict) -> list[str]:
    return [option_value(option) for option in puzzle.get("options", [])]


def legal_move_values(puzzle: dict) -> list[str]:
    if shogi is None:
        return fallback_move_values(puzzle)
    try:
        board = shogi.Board(puzzle_sfen(puzzle))
        return sorted({move.usi() for move in board.legal_moves})
    except Exception:
        return fallback_move_values(puzzle)


def source_options(puzzle: dict) -> list[discord.SelectOption]:
    moves = legal_move_values(puzzle)
    seen = set()
    options = []
    for move in moves:
        source = move_source_key(move)
        if source in seen:
            continue
        seen.add(source)
        options.append(
            discord.SelectOption(
                label=move_source_label(puzzle, source)[:100],
                value=source,
                description="この駒を動かす候補を見る",
            )
        )
    return options[:25]


def destination_options(puzzle: dict, source: str) -> list[discord.SelectOption]:
    moves = [move for move in legal_move_values(puzzle) if move_source_key(move) == source]
    options = []
    for move in moves[:25]:
        options.append(
            discord.SelectOption(
                label=move_label(puzzle, move)[:100],
                value=move,
                description="この手で回答する",
            )
        )
    return options


def destination_squares_for_source(puzzle: dict, source: str) -> set[tuple[int, int]]:
    squares = set()
    for move in legal_move_values(puzzle):
        if move_source_key(move) != source:
            continue
        coord = usi_square_to_coord(move_destination_key(move))
        if coord:
            squares.add(coord)
    return squares


def sfen_piece(owner: str, piece: str) -> str:
    text = piece
    promoted = text.startswith("+")
    if promoted:
        text = text[1:]
    text = text.upper() if owner == "sente" else text.lower()
    return f"+{text}" if promoted else text


def sfen_hands(hands: dict) -> str:
    order = ["R", "B", "G", "S", "N", "L", "P"]
    parts = []
    for owner, symbols in (("sente", order), ("gote", [item.lower() for item in order])):
        pieces = hands.get(owner, [])
        normalized = [piece.upper().replace("+", "") for piece in pieces]
        for symbol in symbols:
            count = normalized.count(symbol.upper())
            if count:
                parts.append((str(count) if count > 1 else "") + symbol)
    return "".join(parts) or "-"


def puzzle_sfen(puzzle: dict) -> str:
    rows = []
    for rank in range(1, 10):
        empty = 0
        row_parts = []
        for file_num in range(9, 0, -1):
            item = puzzle["pieces"].get((file_num, rank))
            if not item:
                empty += 1
                continue
            if empty:
                row_parts.append(str(empty))
                empty = 0
            owner, piece = item
            row_parts.append(sfen_piece(owner, piece))
        if empty:
            row_parts.append(str(empty))
        rows.append("".join(row_parts))
    return f"{'/'.join(rows)} b {sfen_hands(puzzle.get('hands', {}))} 1"


def analyze_move(puzzle: dict, move_value: str) -> tuple[bool | None, bool | None, str]:
    if shogi is None:
        return None, None, ""
    try:
        board = shogi.Board(puzzle_sfen(puzzle))
        move = shogi.Move.from_usi(move_value)
    except Exception as exc:
        return False, False, f"局面または手の解析に失敗しました: {exc}"
    legal = any(move == legal_move for legal_move in board.legal_moves)
    if not legal:
        return False, False, "この手は現在の局面では合法手ではありません。"
    try:
        board.push(move)
        mate = board.is_checkmate()
    except Exception as exc:
        return True, False, f"詰み判定に失敗しました: {exc}"
    return True, mate, "合法手です。" + ("詰みになっています。" if mate else "ただし詰みではありません。")


def render_puzzle_image(
    puzzle: dict,
    *,
    selected_source: str | None = None,
    destination_hints: set[tuple[int, int]] | None = None,
) -> discord.File:
    cell = 70
    board_left = 56
    board_top = 72
    board_size = cell * 9
    width = board_left + board_size + 250
    height = board_top + board_size + 72
    image = Image.new("RGB", (width, height), (47, 68, 57))
    draw = ImageDraw.Draw(image)

    title_font = load_font(28, bold=True)
    small_font = load_font(18)
    coord_font = load_font(16, bold=True)
    piece_font = load_font(28, bold=True)
    piece_short_font = load_font(13, bold=True)

    draw.text((34, 22), f"詰将棋 - {puzzle['title']}", fill=(255, 255, 255), font=title_font)
    draw.text((board_left + board_size + 36, 84), f"手番: {puzzle['side']}", fill=(255, 245, 210), font=small_font)
    draw.text((board_left + board_size + 36, 122), "持ち駒", fill=(255, 255, 255), font=small_font)
    hand = puzzle.get("hands", {}).get("sente", [])
    hand_text = " ".join(piece_text(piece) for piece in hand) if hand else "なし"
    draw.text((board_left + board_size + 36, 154), hand_text, fill=(255, 245, 210), font=small_font)
    draw.text((board_left + board_size + 36, 216), "動かす駒と移動先を", fill=(220, 236, 222), font=small_font)
    draw.text((board_left + board_size + 36, 246), "選んでください。", fill=(220, 236, 222), font=small_font)

    draw.rectangle(
        (board_left, board_top, board_left + board_size, board_top + board_size),
        fill=(226, 174, 96),
        outline=(64, 42, 24),
        width=3,
    )
    for index in range(10):
        x = board_left + index * cell
        y = board_top + index * cell
        draw.line((x, board_top, x, board_top + board_size), fill=(80, 52, 28), width=1)
        draw.line((board_left, y, board_left + board_size, y), fill=(80, 52, 28), width=1)

    for file_num in range(9, 0, -1):
        col = 9 - file_num
        x = board_left + col * cell + 28
        draw.text((x, board_top - 25), str(file_num), fill=(235, 235, 220), font=coord_font)
    for rank in range(1, 10):
        y = board_top + (rank - 1) * cell + 24
        draw.text((board_left - 28, y), str(rank), fill=(235, 235, 220), font=coord_font)

    destination_hints = destination_hints or set()
    source_coord = usi_square_to_coord(selected_source) if selected_source and "*" not in selected_source else None
    for file_num, rank in destination_hints:
        col = 9 - file_num
        row = rank - 1
        x = board_left + col * cell
        y = board_top + row * cell
        draw.rounded_rectangle(
            (x + 7, y + 7, x + cell - 7, y + cell - 7),
            radius=12,
            fill=(69, 130, 214),
            outline=(230, 245, 255),
            width=3,
        )
    if source_coord:
        file_num, rank = source_coord
        col = 9 - file_num
        row = rank - 1
        x = board_left + col * cell
        y = board_top + row * cell
        draw.rounded_rectangle(
            (x + 4, y + 4, x + cell - 4, y + cell - 4),
            radius=12,
            outline=(255, 214, 84),
            width=5,
        )

    for (file_num, rank), (owner, piece) in puzzle["pieces"].items():
        col = 9 - file_num
        row = rank - 1
        x = board_left + col * cell + 8
        y = board_top + row * cell + 8
        fill = (250, 222, 151) if owner == "sente" else (238, 196, 118)
        outline = (82, 54, 26)
        points = [
            (x + 27, y),
            (x + 54, y + 14),
            (x + 48, y + 56),
            (x + 6, y + 56),
            (x, y + 14),
        ]
        if owner == "gote":
            points = [(px, y + 56 - (py - y)) for px, py in points]
        draw.polygon(points, fill=fill, outline=outline)
        label = piece_text(piece)
        bbox = draw.textbbox((0, 0), label, font=piece_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x + 27 - tw / 2, y + 25 - th / 2), label, fill=(34, 28, 22), font=piece_font)
        short = piece_short(piece)
        bbox = draw.textbbox((0, 0), short, font=piece_short_font)
        sw = bbox[2] - bbox[0]
        draw.text((x + 27 - sw / 2, y + 41), short, fill=(82, 54, 26), font=piece_short_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="shogi_puzzle.png")


async def grant_reward(interaction: discord.Interaction, level: str) -> tuple[int, str]:
    if not interaction.guild_id:
        return 0, ""
    today = jst_today()
    daily_key = shogi_daily_key(interaction.guild_id, interaction.user.id, level)
    if await db_get(daily_key) == today:
        return 0, "このレベルの今日の報酬は受け取り済みです。"

    reward = LEVELS[level]["reward"]
    key = coin_key(interaction.guild_id, interaction.user.id)
    current = int(await db_get(key) or "0")
    new_balance = current + reward
    await db_set(key, str(new_balance))
    await db_set(daily_key, today)
    rewards = await apply_coin_rewards(interaction.guild, interaction.user, new_balance)
    reward_text = f"{reward}コイン獲得しました。現在 **{new_balance}** コインです。"
    if rewards:
        reward_text += "\n" + "\n".join(f"🎖 {message}" for message in rewards)
    return reward, reward_text


class ShogiPuzzleSourceView(discord.ui.View):
    def __init__(self, puzzle: dict, owner_id: int):
        super().__init__(timeout=600)
        self.puzzle = puzzle
        self.owner_id = owner_id
        self.add_item(ShogiSourceSelect(puzzle))


class ShogiSourceSelect(discord.ui.Select):
    def __init__(self, puzzle: dict):
        options = source_options(puzzle)
        if not options:
            options = [discord.SelectOption(label="候補なし", value="none", description="合法手候補を作成できませんでした。")]
        super().__init__(
            placeholder="動かす駒を選んでください",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view: ShogiPuzzleSourceView = self.view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return
        source = self.values[0]
        if source == "none":
            await interaction.response.send_message("回答候補を作成できませんでした。", ephemeral=True)
            return
        hints = destination_squares_for_source(view.puzzle, source)
        await interaction.response.edit_message(
            content=(
                f"移動元: **{move_source_label(view.puzzle, source)}**\n"
                "青いマスが移動できる候補です。移動先を選んでください。"
            ),
            attachments=[
                render_puzzle_image(
                    view.puzzle,
                    selected_source=source,
                    destination_hints=hints,
                )
            ],
            view=ShogiPuzzleDestinationView(view.puzzle, view.owner_id, source),
        )


class ShogiPuzzleDestinationView(discord.ui.View):
    def __init__(self, puzzle: dict, owner_id: int, source: str):
        super().__init__(timeout=600)
        self.puzzle = puzzle
        self.owner_id = owner_id
        self.source = source
        self.add_item(ShogiDestinationSelect(puzzle, source))
        self.add_item(ShogiBackButton())


class ShogiDestinationSelect(discord.ui.Select):
    def __init__(self, puzzle: dict, source: str):
        options = destination_options(puzzle, source)
        if not options:
            options = [discord.SelectOption(label="候補なし", value="none", description="この駒の移動先候補がありません。")]
        super().__init__(
            placeholder="移動先を選んで回答してください",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        view: ShogiPuzzleDestinationView = self.view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return
        selected = self.values[0]
        if selected == "none":
            await interaction.response.send_message("この駒の移動先候補がありません。", ephemeral=True)
            return

        puzzle = view.puzzle
        correct = selected == puzzle["answer"]
        correct_text = answer_text(puzzle)
        selected_text = move_label(puzzle, selected)
        legal, mate, analysis_text = analyze_move(puzzle, selected)
        for item in view.children:
            item.disabled = True

        if correct:
            _, reward_text = await grant_reward(interaction, puzzle["level"])
            result = f"正解です！ **{correct_text}**\n{reward_text}"
        else:
            result = f"惜しいです。選んだ手は **{selected_text}** です。\n正解は **{correct_text}** です。"
        if analysis_text:
            result += f"\n\n判定: {analysis_text}"
        if legal and mate and not correct:
            result += "\n選んだ手も詰み判定になりました。問題側の正解候補を見直す必要があります。"
        result += f"\n\n解説: {puzzle['explanation']}"
        await interaction.response.edit_message(content=result, view=view)


class ShogiBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="移動元を選び直す", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: ShogiPuzzleDestinationView = self.view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="動かす駒を選んでください。",
            attachments=[render_puzzle_image(view.puzzle)],
            view=ShogiPuzzleSourceView(view.puzzle, view.owner_id),
        )


class ShogiPuzzleLevelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShogiPuzzleLevelButton("初級", "easy", discord.ButtonStyle.success, 0))
        self.add_item(ShogiPuzzleLevelButton("中級", "normal", discord.ButtonStyle.primary, 0))
        self.add_item(ShogiPuzzleLevelButton("上級", "hard", discord.ButtonStyle.danger, 0))
        self.add_item(ShogiPuzzleRulesButton())


class ShogiPuzzleLevelButton(discord.ui.Button):
    def __init__(self, label: str, level: str, style: discord.ButtonStyle, row: int):
        super().__init__(
            label=label,
            style=style,
            row=row,
            custom_id=f"shogi_puzzle_level_{level}",
        )
        self.level = level

    async def callback(self, interaction: discord.Interaction):
        puzzle = puzzle_for_level(self.level)
        level = LEVELS[self.level]
        content = (
            f"**詰将棋: {level['label']}**\n"
            f"{level['description']}\n"
            "動かす駒と移動先を選んでください。\n"
            f"正解すると **{level['reward']}コイン** 獲得できます。同じレベルの報酬は1日1回までです。"
        )
        if shogi is None:
            content += "\n\n※ 将棋判定ライブラリが未導入のため、候補手の正誤だけで判定します。"
        await interaction.response.send_message(
            content,
            file=render_puzzle_image(puzzle),
            view=ShogiPuzzleSourceView(puzzle, interaction.user.id),
        )


class ShogiPuzzleRulesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ルール",
            style=discord.ButtonStyle.secondary,
            row=1,
            custom_id="shogi_puzzle_rules",
        )

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="詰将棋の遊び方",
            description=(
                "表示された盤面で、相手玉を詰ます最初の一手を選びます。\n"
                "まず動かす駒を選び、次に移動先を選んで回答します。\n"
                "初級は1手詰め中心、中級と上級は読みが必要な問題です。\n"
                "正解するとコインがもらえますが、同じレベルの報酬は1日1回までです。\n\n"
                "報酬: 初級2 / 中級5 / 上級8 コイン"
            ),
            color=0xD6A24A,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def shogi_puzzle_embed() -> discord.Embed:
    embed = discord.Embed(
        title="詰将棋",
        description=(
            "レベルを選んで詰将棋に挑戦できます。\n"
            "正解するとコイン報酬があります。報酬は同じレベルにつき1日1回までです。"
        ),
        color=0xD6A24A,
    )
    embed.add_field(name="初級", value="1手詰め中心 / 2コイン", inline=True)
    embed.add_field(name="中級", value="少し読む問題 / 5コイン", inline=True)
    embed.add_field(name="上級", value="腕試し / 8コイン", inline=True)
    return embed


class ShogiPuzzle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ShogiPuzzle(bot))
