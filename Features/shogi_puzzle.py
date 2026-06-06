import json
import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

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
PUZZLE_FILE = Path("assets/shogi/shogi_puzzles.json")
EXTRA_PUZZLE_FILES = [
    Path("assets/shogi/shogi_puzzles_yaneura.json"),
]

LEVELS = {
    "easy": {"label": "初級", "reward": 2, "description": "1手詰め中心。まずは気軽に。"},
    "normal": {"label": "中級", "reward": 5, "description": "3手詰め中心。相手の応手を読んで進めます。"},
    "hard": {"label": "上級", "reward": 8, "description": "5手詰め中心。数手先まで読む腕試し向け。"},
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
            (5, 2): ("gote", "S"),
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
    candidates = [puzzle for puzzle in load_puzzles() if puzzle["level"] == level]
    if not candidates:
        candidates = [puzzle for puzzle in PUZZLES if puzzle["level"] == level]
    return random.choice(candidates)


def load_puzzle_file(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    puzzles = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not all(item.get(key) for key in ("id", "level", "title", "sfen", "answer")):
            continue
        puzzle = {
            "id": str(item["id"]),
            "level": str(item["level"]),
            "title": str(item["title"]),
            "side": str(item.get("side", "先手")),
            "sfen": str(item["sfen"]),
            "answer": str(item["answer"]),
            "answer_text": str(item.get("answer_text") or item["answer"]),
            "mate_moves": int(item.get("mate_moves") or 1),
            "explanation": str(item.get("explanation", "解説はまだ登録されていません。")),
            "source": str(item.get("source", "unknown")),
            "license": str(item.get("license", "unknown")),
        }
        if isinstance(item.get("solution"), list):
            puzzle["solution"] = [str(move) for move in item["solution"] if move]
        if isinstance(item.get("acceptable_answers"), list):
            puzzle["acceptable_answers"] = [str(move) for move in item["acceptable_answers"] if move]
        if isinstance(item.get("options"), list):
            puzzle["options"] = item["options"]
        puzzles.append(puzzle)
    return puzzles


def load_puzzles() -> list[dict]:
    puzzles = load_puzzle_file(PUZZLE_FILE)
    for path in EXTRA_PUZZLE_FILES:
        puzzles.extend(load_puzzle_file(path))
    return puzzles or PUZZLES


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


def runtime_puzzle(puzzle: dict) -> dict:
    state = deepcopy(puzzle)
    state["_initial_sfen"] = state.get("sfen", "")
    state["_progress"] = 0
    if "solution" not in state:
        state["solution"] = [state["answer"]]
    if not state.get("mate_moves"):
        state["mate_moves"] = len(state["solution"])
    return state


def solution_moves(puzzle: dict) -> list[str]:
    moves = puzzle.get("solution")
    if isinstance(moves, list) and moves:
        return [str(move) for move in moves]
    return [str(puzzle.get("answer", ""))]


def current_solution_move(puzzle: dict) -> str | None:
    moves = solution_moves(puzzle)
    progress = int(puzzle.get("_progress", 0) or 0)
    if progress >= len(moves):
        return None
    return moves[progress]


def current_acceptable_moves(puzzle: dict) -> list[str]:
    expected = current_solution_move(puzzle) or puzzle.get("answer", "")
    progress = int(puzzle.get("_progress", 0) or 0)
    dynamic = puzzle.get("_acceptable_moves_by_progress", {}).get(str(progress))
    if isinstance(dynamic, list) and dynamic:
        return [str(move) for move in dynamic if move]
    if progress == 0 and isinstance(puzzle.get("acceptable_answers"), list):
        moves = [str(move) for move in puzzle["acceptable_answers"] if move]
        if expected and expected not in moves:
            moves.insert(0, expected)
        return moves
    return [expected] if expected else []


def correct_text_for_current(puzzle: dict) -> str:
    moves = current_acceptable_moves(puzzle)
    if len(moves) <= 1:
        return move_label(puzzle, moves[0]) if moves else answer_text(puzzle)
    return " / ".join(move_label(puzzle, move) for move in moves[:4])


def push_solution_move(puzzle: dict, move_value: str) -> tuple[bool, str]:
    if shogi is None:
        if len(solution_moves(puzzle)) <= 1:
            puzzle["_progress"] = int(puzzle.get("_progress", 0) or 0) + 1
            return True, ""
        return False, "将棋判定ライブラリが未導入のため、複数手の問題を進められません。"
    try:
        board = shogi.Board(puzzle_sfen(puzzle))
        move = shogi.Move.from_usi(move_value)
    except Exception as exc:
        return False, f"局面または手の解析に失敗しました: {exc}"
    if not any(move == legal_move for legal_move in board.legal_moves):
        return False, "手順内の手が現在の局面では合法手ではありません。問題データを確認してください。"
    board.push(move)
    puzzle["sfen"] = board.sfen()
    puzzle["_progress"] = int(puzzle.get("_progress", 0) or 0) + 1
    return True, ""


def forced_reply_mate_continuation(puzzle: dict, move_value: str) -> tuple[str, list[str]] | None:
    if shogi is None:
        return None
    progress = int(puzzle.get("_progress", 0) or 0)
    remaining = len(solution_moves(puzzle)) - progress
    if remaining != 3:
        return None
    try:
        board = shogi.Board(puzzle_sfen(puzzle))
        move = shogi.Move.from_usi(move_value)
    except Exception:
        return None
    if not any(move == legal_move for legal_move in board.legal_moves):
        return None
    board.push(move)
    if not board.is_check() or board.is_checkmate():
        return None
    replies = list(board.legal_moves)
    if len(replies) != 1:
        return None
    board.push(replies[0])
    final_moves = []
    for final_move in board.legal_moves:
        candidate = shogi.Board(board.sfen())
        candidate.push(final_move)
        if candidate.is_checkmate():
            final_moves.append(final_move.usi())
    return (replies[0].usi(), final_moves) if final_moves else None


def solution_progress_text(puzzle: dict) -> str:
    moves = solution_moves(puzzle)
    user_turn = int(puzzle.get("_progress", 0) or 0) // 2 + 1
    total_user_turns = (len(moves) + 1) // 2
    return f"{user_turn}/{total_user_turns}手目"


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
            token = char
            if char == "+" and index + 1 < len(row):
                token = row[index:index + 2]
                index += 2
            else:
                index += 1
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


def puzzle_pieces(puzzle: dict) -> dict[tuple[int, int], tuple[str, str]]:
    if "pieces" in puzzle:
        return puzzle["pieces"]
    return pieces_from_sfen(puzzle["sfen"])


def puzzle_hands(puzzle: dict) -> dict[str, list[str]]:
    if "hands" in puzzle:
        return puzzle["hands"]
    return hands_from_sfen(puzzle["sfen"])


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
    return f"{square[0]}筋{RANK_TO_JA.get(square[1], square[1])}段"


def piece_at_usi_square(puzzle: dict, square: str) -> str:
    if len(square) != 2:
        return ""
    file_num = int(square[0])
    rank = "abcdefghi".index(square[1]) + 1
    item = puzzle_pieces(puzzle).get((file_num, rank))
    if not item:
        return ""
    return piece_text(item[1])


def move_source_key(move_value: str) -> str:
    return move_value[:2] if "*" not in move_value[:2] else move_value[:2]


def move_destination_key(move_value: str) -> str:
    return move_value[2:4] if "*" in move_value[:2] else move_value[2:4]


def gote_king_square(puzzle: dict) -> str | None:
    for (file_num, rank), (owner, piece) in puzzle_pieces(puzzle).items():
        if owner == "gote" and piece == "K":
            return f"{file_num}{'abcdefghi'[rank - 1]}"
    return None


def move_targets_gote_king(puzzle: dict, move_value: str) -> bool:
    king_square = gote_king_square(puzzle)
    return bool(king_square and move_destination_key(move_value) == king_square)


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
        return [move for move in fallback_move_values(puzzle) if not move_targets_gote_king(puzzle, move)]
    try:
        board = shogi.Board(puzzle_sfen(puzzle))
        return sorted({move.usi() for move in board.legal_moves if not move_targets_gote_king(puzzle, move.usi())})
    except Exception:
        return [move for move in fallback_move_values(puzzle) if not move_targets_gote_king(puzzle, move)]


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


def destination_options(puzzle: dict, source: str, page: int = 0) -> list[discord.SelectOption]:
    moves = [move for move in legal_move_values(puzzle) if move_source_key(move) == source]
    options = []
    start = max(page, 0) * 25
    for move in moves[start:start + 25]:
        options.append(
            discord.SelectOption(
                label=move_label(puzzle, move)[:100],
                value=move,
                description="この手で回答する",
            )
        )
    return options


def destination_page_count(puzzle: dict, source: str) -> int:
    moves = [move for move in legal_move_values(puzzle) if move_source_key(move) == source]
    return max((len(moves) - 1) // 25 + 1, 1)


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
    if puzzle.get("sfen"):
        return puzzle["sfen"]
    rows = []
    for rank in range(1, 10):
        empty = 0
        row_parts = []
        for file_num in range(9, 0, -1):
            item = puzzle_pieces(puzzle).get((file_num, rank))
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
    return f"{'/'.join(rows)} b {sfen_hands(puzzle_hands(puzzle))} 1"


def analyze_move(puzzle: dict, move_value: str) -> tuple[bool | None, bool | None, str]:
    if move_targets_gote_king(puzzle, move_value):
        return False, False, "王を取る手は詰将棋の回答として扱いません。王を逃げられない状態にする手を選んでください。"
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
    owner_font = load_font(12, bold=True)

    draw.text((34, 22), f"詰将棋 - {puzzle['title']}", fill=(255, 255, 255), font=title_font)
    draw.text((board_left + board_size + 36, 84), f"手番: {puzzle['side']}", fill=(255, 245, 210), font=small_font)
    draw.rounded_rectangle((board_left + board_size + 36, 38, board_left + board_size + 100, 64), radius=8, fill=(56, 126, 214))
    draw.text((board_left + board_size + 44, 41), "先手", fill=(255, 255, 255), font=small_font)
    draw.rounded_rectangle((board_left + board_size + 112, 38, board_left + board_size + 176, 64), radius=8, fill=(218, 82, 82))
    draw.text((board_left + board_size + 120, 41), "後手", fill=(255, 255, 255), font=small_font)
    draw.text((board_left + board_size + 36, 122), "持ち駒", fill=(255, 255, 255), font=small_font)
    hand = puzzle_hands(puzzle).get("sente", [])
    hand_text = " ".join(piece_text(piece) for piece in hand) if hand else "なし"
    draw.text((board_left + board_size + 36, 154), hand_text, fill=(255, 245, 210), font=small_font)
    draw.text((board_left + board_size + 36, 216), "上の数字が筋、", fill=(220, 236, 222), font=small_font)
    draw.text((board_left + board_size + 36, 246), "左の漢数字が段です。", fill=(220, 236, 222), font=small_font)

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
        rank_label = RANK_TO_JA["abcdefghi"[rank - 1]]
        draw.text((board_left - 28, y), rank_label, fill=(235, 235, 220), font=coord_font)

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

    for (file_num, rank), (owner, piece) in puzzle_pieces(puzzle).items():
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
        owner_color = (56, 126, 214) if owner == "sente" else (218, 82, 82)
        owner_label = "先" if owner == "sente" else "後"
        if owner == "gote":
            points = [(px, y + 56 - (py - y)) for px, py in points]
        draw.polygon(points, fill=fill, outline=outline)
        draw.line(points + [points[0]], fill=owner_color, width=3)
        draw.rounded_rectangle((x + 2, y + 2, x + 20, y + 20), radius=5, fill=owner_color)
        draw.text((x + 5, y + 3), owner_label, fill=(255, 255, 255), font=owner_font)
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
                f"移動元: **{move_source_label(view.puzzle, source)}** ({solution_progress_text(view.puzzle)})\n"
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
    def __init__(self, puzzle: dict, owner_id: int, source: str, page: int = 0):
        super().__init__(timeout=600)
        self.puzzle = puzzle
        self.owner_id = owner_id
        self.source = source
        page_count = destination_page_count(puzzle, source)
        page = max(0, min(page, page_count - 1))
        self.add_item(ShogiDestinationSelect(puzzle, source, page))
        if page_count > 1:
            self.add_item(ShogiPuzzleDestinationPageButton(puzzle, owner_id, source, page - 1, "Prev", page <= 0))
            self.add_item(ShogiPuzzleDestinationPageButton(puzzle, owner_id, source, page + 1, "Next", page >= page_count - 1))
        self.add_item(ShogiBackButton())


class ShogiDestinationSelect(discord.ui.Select):
    def __init__(self, puzzle: dict, source: str, page: int = 0):
        options = destination_options(puzzle, source, page)
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
        expected = current_solution_move(puzzle) or puzzle["answer"]
        correct = selected in current_acceptable_moves(puzzle)
        correct_text = correct_text_for_current(puzzle)
        selected_text = move_label(puzzle, selected)
        legal, mate, analysis_text = analyze_move(puzzle, selected)

        if not correct:
            alternate = forced_reply_mate_continuation(puzzle, selected)
            if alternate:
                reply, final_moves = alternate
                reply_label = move_label(puzzle, reply)
                ok, error = push_solution_move(puzzle, selected)
                if not ok:
                    await interaction.response.send_message(error or "盤面の更新に失敗しました。", ephemeral=True)
                    return
                ok, error = push_solution_move(puzzle, reply)
                if not ok:
                    await interaction.response.send_message(error or "応手の更新に失敗しました。", ephemeral=True)
                    return
                acceptable = puzzle.setdefault("_acceptable_moves_by_progress", {})
                acceptable[str(int(puzzle.get("_progress", 0) or 0))] = final_moves
                await interaction.response.edit_message(
                    content=(
                        f"別解候補として進めます。 **{selected_text}**\n"
                        f"応手: **{reply_label}**\n\n"
                        f"次の一手を選んでください。({solution_progress_text(puzzle)})"
                    ),
                    attachments=[render_puzzle_image(puzzle)],
                    view=ShogiPuzzleSourceView(puzzle, view.owner_id),
                )
                return
            for item in view.children:
                item.disabled = True
            result = f"惜しいです。選んだ手は **{selected_text}** です。\nこの局面の正解は **{correct_text}** です。"
            if analysis_text:
                result += f"\n\n判定: {analysis_text}"
            if legal and mate:
                result += "\n選んだ手も詰み判定になりました。問題側の正解候補を見直す必要があります。"
            if len(solution_moves(puzzle)) <= 1:
                result += f"\n\n解説: {puzzle['explanation']}"
            else:
                result += "\n\n複数手詰めの途中なので、解説は最後まで進んだ時に表示します。"
            await interaction.response.edit_message(content=result, view=view)
            return

        ok, error = push_solution_move(puzzle, selected)
        if not ok:
            for item in view.children:
                item.disabled = True
            await interaction.response.edit_message(content=f"正解手でしたが、局面更新に失敗しました。\n{error}", view=view)
            return

        moves = solution_moves(puzzle)
        if int(puzzle.get("_progress", 0) or 0) >= len(moves):
            for item in view.children:
                item.disabled = True
            _, reward_text = await grant_reward(interaction, puzzle["level"])
            result = f"正解です！ **{selected_text}**\n{reward_text}"
            if analysis_text:
                result += f"\n\n判定: {analysis_text}"
            result += f"\n\n解説: {puzzle['explanation']}"
            await interaction.response.edit_message(
                content=result,
                attachments=[render_puzzle_image(puzzle)],
                view=view,
            )
            return

        reply = current_solution_move(puzzle)
        reply_label = move_label(puzzle, reply) if reply else ""
        if reply:
            ok, error = push_solution_move(puzzle, reply)
            if not ok:
                for item in view.children:
                    item.disabled = True
                await interaction.response.edit_message(content=f"正解手でしたが、応手の局面更新に失敗しました。\n{error}", view=view)
                return

        if int(puzzle.get("_progress", 0) or 0) >= len(moves):
            for item in view.children:
                item.disabled = True
            _, reward_text = await grant_reward(interaction, puzzle["level"])
            result = f"正解です！ **{selected_text}**\n{reward_text}\n\n解説: {puzzle['explanation']}"
            await interaction.response.edit_message(content=result, attachments=[render_puzzle_image(puzzle)], view=view)
            return

        await interaction.response.edit_message(
            content=(
                f"正解です。**{selected_text}**\n"
                f"応手: **{reply_label}**\n\n"
                f"次の一手を選んでください。({solution_progress_text(puzzle)})"
            ),
            attachments=[render_puzzle_image(puzzle)],
            view=ShogiPuzzleSourceView(puzzle, view.owner_id),
        )


class ShogiPuzzleDestinationPageButton(discord.ui.Button):
    def __init__(self, puzzle: dict, owner_id: int, source: str, page: int, label: str, disabled: bool):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled, row=1)
        self.puzzle = puzzle
        self.owner_id = owner_id
        self.source = source
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return
        hints = destination_squares_for_source(self.puzzle, self.source)
        await interaction.response.edit_message(
            content=(
                f"移動元: **{move_source_label(self.puzzle, self.source)}** ({solution_progress_text(self.puzzle)})\n"
                "青いマスが移動できる候補です。移動先を選んでください。"
            ),
            attachments=[
                render_puzzle_image(
                    self.puzzle,
                    selected_source=self.source,
                    destination_hints=hints,
                )
            ],
            view=ShogiPuzzleDestinationView(self.puzzle, self.owner_id, self.source, self.page),
        )


class ShogiBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="移動元を選び直す", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: ShogiPuzzleDestinationView = self.view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=f"動かす駒を選んでください。({solution_progress_text(view.puzzle)})",
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
        puzzle = runtime_puzzle(puzzle_for_level(self.level))
        level = LEVELS[self.level]
        content = (
            f"**詰将棋: {level['label']}**\n"
            f"{level['description']}\n"
            f"問題: **{puzzle.get('mate_moves', 1)}手詰め**\n"
            "動かす駒と移動先を選んでください。3手/5手詰めは、相手の応手をBotが自動で進めます。\n"
            "座標は「数字=筋、漢数字=段」です。例: 5二 は5筋二段です。\n"
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
                "表示された盤面で、相手玉を詰ます手順を選びます。\n"
                "まず動かす駒を選び、次に移動先を選んで回答します。\n"
                "3手/5手詰めでは、相手の応手はBotが自動で進め、次の一手を続けて選べます。\n"
                "座標は、横が数字の筋、縦が漢数字の段です。例: 5二 は5筋二段です。\n"
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
    embed.add_field(name="中級", value="3手詰め中心 / 5コイン", inline=True)
    embed.add_field(name="上級", value="5手詰め中心 / 8コイン", inline=True)
    embed.add_field(
        name="将棋判定",
        value="OK: python-shogi 有効" if shogi is not None else "NG: python-shogi 未導入",
        inline=False,
    )
    return embed


class ShogiPuzzle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ShogiPuzzle(bot))
