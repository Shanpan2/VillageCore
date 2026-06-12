from __future__ import annotations

import ast
import random
import sys
from pathlib import Path


SOURCE = Path("role_guesser/bot.py")
NAMES = {
    "Role",
    "parse_bool",
    "normalize_mod_name",
    "load_roles",
    "team_questions_to_skip",
    "team_answer_matches",
    "priority_bonus",
    "answer_match_count",
    "best_question",
    "GuessSession",
    "primary_team",
    "should_delay_final_result",
    "nearby_candidates_for_more_questions",
    "expand_final_candidates_if_needed",
    "feature_signature",
    "single_group_roles",
}
ASSIGNS = {
    "DATA_PATH",
    "MOD_ALIASES",
    "FEATURE_QUESTIONS",
    "QUESTION_PRIORITY_BONUS",
    "TEAM_QUESTION_KEYS",
    "TEAM_YES_FEATURE_SKIP",
    "MIN_FINAL_ANSWERED_QUESTIONS",
    "MIN_FINAL_POSITIVE_ANSWERS",
    "sessions",
}


def load_namespace() -> dict[str, object]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in ASSIGNS
            for target in node.targets
        ):
            keep.append(node)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in ASSIGNS
        ):
            keep.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in NAMES:
            keep.append(node)

    module = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"__file__": str(SOURCE.resolve())}
    exec(compile(module, "role_guesser_sim", "exec"), namespace)
    return namespace


def main() -> None:
    namespace = load_namespace()
    roles = namespace["load_roles"]()
    selected_mod = sys.argv[1] if len(sys.argv) > 1 else None
    if selected_mod:
        roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
    original_best_question = namespace["best_question"]
    cache = {}

    def cached_best_question(candidates, asked):
        key = (
            tuple(sorted(role.name for role in candidates)),
            tuple(sorted(asked)),
        )
        if key not in cache:
            cache[key] = original_best_question(candidates, asked)
        return cache[key]

    namespace["best_question"] = cached_best_question
    namespace["expand_final_candidates_if_needed"].__globals__["best_question"] = cached_best_question
    namespace["GuessSession"].next_question.__globals__["best_question"] = cached_best_question
    random.seed(1)

    def truth(role, key):
        if key.startswith("guess:"):
            return key.removeprefix("guess:") == role.name
        return role.features.get(key)

    def resolved(session):
        namespace["expand_final_candidates_if_needed"](session)
        final_allowed = not namespace["should_delay_final_result"](session)
        if final_allowed and namespace["single_group_roles"](session.candidates):
            return True, True
        if final_allowed and len(session.candidates) == 1:
            return True, True
        if cached_best_question(session.candidates, session.asked) is None:
            return True, False
        return False, False

    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    rows = []
    for role in roles:
        pool = [candidate for candidate in namespace["load_roles"]() if candidate.mod == role.mod]
        session = namespace["GuessSession"](0, pool, role.mod)
        finished = False
        exact_result = False
        for _ in range(max_steps):
            finished, exact_result = resolved(session)
            if finished:
                break
            question = session.next_question()
            if not question:
                finished = True
                exact_result = False
                break
            session.apply_answer(truth(role, question))
            session.current_question = None
        hit = any(candidate.name == role.name for candidate in session.candidates)
        rows.append(
            (
                session.answered_question_count,
                session.positive_answer_count,
                len(session.candidates),
                hit,
                finished,
                exact_result,
                role.mod,
                role.name,
                role.display_name,
            )
        )

    minimum = namespace["MIN_FINAL_ANSWERED_QUESTIONS"]
    fast = [row for row in rows if row[5] and row[0] < minimum]
    misses = [row for row in rows if not row[3]]
    print(f"mod {selected_mod or 'ALL'}")
    print(f"roles {len(rows)}")
    print(f"max_steps {max_steps}")
    print(
        "questions",
        f"min={min(row[0] for row in rows)}",
        f"avg={sum(row[0] for row in rows) / len(rows):.2f}",
        f"max={max(row[0] for row in rows)}",
    )
    print(f"fast_final_like {len(fast)}")
    print(f"misses {len(misses)}")
    for row in sorted(fast)[:40]:
        print("FAST", row)
    for row in misses[:40]:
        print("MISS", row)


if __name__ == "__main__":
    main()
