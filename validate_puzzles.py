import argparse
import json
from pathlib import Path

try:
    import shogi
except ModuleNotFoundError:
    shogi = None


PUZZLE_FILE = Path("assets/shogi/shogi_puzzles.json")


def as_list(value, fallback):
    if isinstance(value, list) and value:
        return [str(item) for item in value if item]
    return fallback


def validate(puzzles: list[dict]) -> tuple[int, list[str]]:
    ok = 0
    ng: list[str] = []

    for puzzle in puzzles:
        pid = puzzle.get("id", "???")
        sfen = str(puzzle.get("sfen", ""))
        answer = str(puzzle.get("answer", ""))
        mate_moves = int(puzzle.get("mate_moves") or 1)
        solution = as_list(puzzle.get("solution"), [answer])
        acceptable = as_list(puzzle.get("acceptable_answers"), [answer])

        try:
            board = shogi.Board(sfen)
        except Exception as exc:
            ng.append(f"[{pid}] SFEN読み込み失敗: {exc}")
            continue

        legal_moves = set(board.legal_moves)
        for move_usi in acceptable:
            try:
                move = shogi.Move.from_usi(move_usi)
            except Exception as exc:
                ng.append(f"[{pid}] 手の解析失敗 ({move_usi}): {exc}")
                continue
            if move not in legal_moves:
                ng.append(f"[{pid}] 非合法手: {move_usi}")

        if mate_moves == 1:
            mate_ok = True
            for move_usi in acceptable:
                try:
                    candidate = shogi.Board(sfen)
                    candidate.push(shogi.Move.from_usi(move_usi))
                    if not candidate.is_checkmate():
                        ng.append(f"[{pid}] 1手後に詰みになっていない: {move_usi}")
                        mate_ok = False
                except Exception as exc:
                    ng.append(f"[{pid}] 詰み確認失敗 ({move_usi}): {exc}")
                    mate_ok = False
            if mate_ok:
                ok += 1
            continue

        try:
            candidate = shogi.Board(sfen)
            for index, move_usi in enumerate(solution, start=1):
                move = shogi.Move.from_usi(move_usi)
                if move not in candidate.legal_moves:
                    ng.append(f"[{pid}] 手順{index}手目が非合法手: {move_usi}")
                    break
                candidate.push(move)
            else:
                if candidate.is_checkmate():
                    ok += 1
                else:
                    ng.append(f"[{pid}] 手順終了後に詰みになっていない: {solution}")
        except Exception as exc:
            ng.append(f"[{pid}] 手順確認失敗: {exc}")

    return ok, ng


def mate_moves_after(board: "shogi.Board") -> list[str]:
    moves = []
    for move in board.legal_moves:
        candidate = shogi.Board(board.sfen())
        candidate.push(move)
        if candidate.is_checkmate():
            moves.append(move.usi())
    return moves


def forced_reply_continuations(board: "shogi.Board") -> list[tuple[str, list[str]]]:
    continuations = []
    replies = list(board.legal_moves)
    if len(replies) != 1:
        return continuations
    reply = replies[0]
    after_reply = shogi.Board(board.sfen())
    after_reply.push(reply)
    final_moves = mate_moves_after(after_reply)
    if final_moves:
        continuations.append((reply.usi(), final_moves))
    return continuations


def find_alternates(puzzles: list[dict]) -> list[str]:
    messages: list[str] = []
    for puzzle in puzzles:
        pid = puzzle.get("id", "???")
        sfen = str(puzzle.get("sfen", ""))
        answer = str(puzzle.get("answer", ""))
        mate_moves = int(puzzle.get("mate_moves") or 1)
        solution = as_list(puzzle.get("solution"), [answer])
        acceptable = set(as_list(puzzle.get("acceptable_answers"), [answer]))

        try:
            board = shogi.Board(sfen)
        except Exception as exc:
            messages.append(f"[{pid}] 別解検出をスキップ: SFEN読み込み失敗: {exc}")
            continue

        if mate_moves == 1:
            mates = set(mate_moves_after(board))
            extra = sorted(mates - acceptable)
            if extra:
                messages.append(f"[{pid}] 1手詰めの未登録別解: {', '.join(extra)}")
            continue

        if len(solution) >= 3:
            first_answer = solution[0]
            alternates = []
            for move in board.legal_moves:
                move_usi = move.usi()
                if move_usi == first_answer:
                    continue
                candidate = shogi.Board(sfen)
                candidate.push(move)
                if not candidate.is_check():
                    continue
                for reply, final_moves in forced_reply_continuations(candidate):
                    alternates.append(f"{move_usi} / {reply} / {', '.join(final_moves)}")
            if alternates:
                messages.append(f"[{pid}] 3手詰め相当の別解候補: " + " ; ".join(alternates))

    return messages


def main() -> int:
    if shogi is None:
        print("python-shogi がローカル環境に入っていません。")
        print("次のどちらかでインストールしてから再実行してください。")
        print("  py -m pip install python-shogi")
        print("  python -m pip install python-shogi")
        return 2

    parser = argparse.ArgumentParser(description="Validate shogi puzzle JSON files.")
    parser.add_argument("--file", type=Path, default=PUZZLE_FILE, help="Puzzle JSON file to validate.")
    args = parser.parse_args()

    puzzles = json.loads(args.file.read_text(encoding="utf-8"))
    ok, ng = validate(puzzles)
    print(f"\n対象: {args.file}")
    print(f"結果: {ok}問OK / {len(ng)}件NG\n")
    for message in ng:
        print("NG:", message)

    alternates = find_alternates(puzzles)
    print(f"\n別解チェック: {len(alternates)}件\n")
    for message in alternates:
        print("ALT:", message)
    return 1 if ng else 0


if __name__ == "__main__":
    raise SystemExit(main())
