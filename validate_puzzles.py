import json
from pathlib import Path

import shogi


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


def main() -> int:
    puzzles = json.loads(PUZZLE_FILE.read_text(encoding="utf-8"))
    ok, ng = validate(puzzles)
    print(f"\n結果: {ok}問OK / {len(ng)}件NG\n")
    for message in ng:
        print("NG:", message)
    return 1 if ng else 0


if __name__ == "__main__":
    raise SystemExit(main())
