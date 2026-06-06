import argparse
import json
import random
from functools import lru_cache
from pathlib import Path

import shogi


DEFAULT_INPUTS = {
    "normal": ("mate3.sfen", 3),
    "hard": ("mate5.sfen", 5),
}
OUTPUT_FILE = Path("assets/shogi/shogi_puzzles_yaneura.json")


def normalize_sfen(line: str) -> str:
    line = line.strip()
    if line.startswith("sfen "):
        line = line[5:].strip()
    return line


def is_supported_sfen(sfen: str, allow_white: bool) -> bool:
    parts = sfen.split()
    if len(parts) < 4:
        return False
    return allow_white or parts[1] == "b"


def mate_search_pv(sfen: str, depth: int) -> list[str] | None:
    @lru_cache(maxsize=200_000)
    def can_mate(cached_sfen: str, remaining: int) -> tuple[bool, tuple[str, ...]]:
        board = shogi.Board(cached_sfen)
        if remaining <= 0:
            return board.is_checkmate(), ()

        for attack in board.legal_moves:
            after_attack = shogi.Board(cached_sfen)
            after_attack.push(attack)

            if remaining == 1:
                if after_attack.is_checkmate():
                    return True, (attack.usi(),)
                continue

            replies = list(after_attack.legal_moves)
            if not replies:
                continue

            chosen_line: tuple[str, ...] | None = None
            all_replies_mated = True
            for reply in replies:
                after_reply = shogi.Board(after_attack.sfen())
                after_reply.push(reply)
                ok, tail = can_mate(after_reply.sfen(), remaining - 2)
                if not ok:
                    all_replies_mated = False
                    break
                if chosen_line is None:
                    chosen_line = (attack.usi(), reply.usi(), *tail)

            if all_replies_mated and chosen_line:
                return True, chosen_line

        return False, ()

    ok, pv = can_mate(sfen, depth)
    return list(pv) if ok and len(pv) == depth else None


def convert_file(level: str, input_path: Path, mate_moves: int, sample_size: int, allow_white: bool) -> list[dict]:
    if not input_path.exists():
        print(f"missing: {input_path}")
        return []

    lines = [normalize_sfen(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    sfens = [line for line in lines if line and is_supported_sfen(line, allow_white)]
    random.shuffle(sfens)

    puzzles = []
    checked = 0
    for sfen in sfens:
        if len(puzzles) >= sample_size:
            break
        checked += 1
        try:
            solution = mate_search_pv(sfen, mate_moves)
        except Exception:
            continue
        if not solution:
            continue

        index = len(puzzles) + 1
        puzzles.append(
            {
                "id": f"yaneura_{level}_{index:03d}",
                "level": level,
                "title": f"やねうら王 {mate_moves}手詰め {index:03d}",
                "side": "先手" if sfen.split()[1] == "b" else "後手",
                "sfen": sfen,
                "answer": solution[0],
                "answer_text": solution[0],
                "solution": solution,
                "mate_moves": mate_moves,
                "explanation": f"{mate_moves}手詰めです。手順: {' -> '.join(solution)}",
                "source": "yaneuraou_2020_mate_sfen",
                "license": "no_copyright_claimed_by_author",
            }
        )
        if len(puzzles) % 10 == 0:
            print(f"{level}: {len(puzzles)} puzzles collected / {checked} checked")

    return puzzles


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert YaneuraOu mate SFEN files into VillageCore puzzle JSON.")
    parser.add_argument("--sample-size", type=int, default=50, help="Number of puzzles per level.")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    parser.add_argument("--allow-white", action="store_true", help="Also import positions where side to move is white/gote.")
    args = parser.parse_args()

    all_puzzles = []
    for level, (filename, mate_moves) in DEFAULT_INPUTS.items():
        print(f"converting {filename} as {level} ({mate_moves} moves)")
        all_puzzles.extend(convert_file(level, Path(filename), mate_moves, args.sample_size, args.allow_white))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(all_puzzles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(all_puzzles)} puzzles to {args.output}")
    return 0 if all_puzzles else 1


if __name__ == "__main__":
    raise SystemExit(main())
