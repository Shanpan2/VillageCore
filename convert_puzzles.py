import shogi
import json
import random
from pathlib import Path

# 設定
INPUT_FILES = {
    "normal": Path("mate3.sfen"),   # 3手詰め → 中級
    "hard":   Path("mate5.sfen"),   # 5手詰め → 上級
}
OUTPUT_FILE = Path("assets/shogi/shogi_puzzles_yaneura.json")
SAMPLE_SIZE = 100  # 各難易度から何問取り込むか

def solve_mate(sfen: str, max_moves: int) -> list[str] | None:
    """python-shogiで詰み手順を取得する。取れなければNoneを返す。"""
    try:
        board = shogi.Board(sfen)
    except Exception:
        return None

    def dfs(board, depth, moves):
        if depth == 0:
            return board.is_checkmate()
        for move in board.legal_moves:
            board.push(move)
            if depth == 1:
                if board.is_checkmate():
                    board.pop()
                    moves.append(move.usi())
                    return True
                board.pop()
            else:
                # 相手番(逃げ手)は合法手を全部試す
                escaped = False
                for reply in board.legal_moves:
                    board.push(reply)
                    result_moves = []
                    if dfs(board, depth - 2, result_moves):
                        board.pop()
                        board.pop()
                        moves.append(move.usi())
                        moves.append(reply.usi())
                        moves.extend(result_moves)
                        return True
                    board.pop()
                    escaped = True
                board.pop()
        return False

    solution = []
    if dfs(board, max_moves, solution):
        return solution
    return None


def convert(level: str, sfen_path: Path, mate_moves: int, sample_size: int) -> list[dict]:
    if not sfen_path.exists():
        print(f"ファイルが見つかりません: {sfen_path}")
        return []

    lines = sfen_path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in lines if line.strip()]
    sample = random.sample(lines, min(sample_size * 5, len(lines)))  # 多めに取って後でフィルタ

    puzzles = []
    checked = 0

    for i, raw_sfen in enumerate(sample):
        if len(puzzles) >= sample_size:
            break

        # "sfen " prefixがあれば除去
        sfen = raw_sfen.removeprefix("sfen ").strip()

        # 先手番のみ使う（"b"が手番）
        parts = sfen.split()
        if len(parts) < 2 or parts[1] != "b":
            continue

        solution = solve_mate(sfen, mate_moves)
        if not solution or len(solution) != mate_moves:
            continue

        checked += 1
        puzzle_id = f"yaneura_{level}_{len(puzzles) + 1:03d}"
        answer = solution[0]

        puzzle = {
            "id": puzzle_id,
            "level": level,
            "title": f"やねうら王 {mate_moves}手詰め {len(puzzles) + 1:03d}",
            "side": "先手",
            "sfen": sfen,
            "answer": answer,
            "answer_text": answer,
            "solution": solution,
            "mate_moves": mate_moves,
            "explanation": f"{mate_moves}手詰めです。",
            "source": "yaneuraou_2020",
            "license": "no_copyright_claimed",
        }
        puzzles.append(puzzle)

        if len(puzzles) % 10 == 0:
            print(f"  {level}: {len(puzzles)}問取得済み (確認済み: {i+1}問中)")

    return puzzles


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_puzzles = []
    for level, (sfen_path, mate_moves) in {
        "normal": (INPUT_FILES["normal"], 3),
        "hard":   (INPUT_FILES["hard"],   5),
    }.items():
        print(f"\n{level} ({mate_moves}手詰め) を処理中...")
        puzzles = convert(level, sfen_path, mate_moves, SAMPLE_SIZE)
        print(f"  → {len(puzzles)}問取得")
        all_puzzles.extend(puzzles)

    OUTPUT_FILE.write_text(
        json.dumps(all_puzzles, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n完了: 合計{len(all_puzzles)}問を {OUTPUT_FILE} に保存しました。")


if __name__ == "__main__":
    main()