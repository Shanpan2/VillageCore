"""Unit tests for Features/codenames.py pure-logic helpers."""

from Features.codenames import (
    WORDS,
    board_lines,
    board_text,
    codenames_game_key,
    codenames_index_key,
    key_text,
    lobby_text,
    mention,
    team_members,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sample_board() -> list[dict]:
    board = []
    teams = ["red"] * 9 + ["blue"] * 8 + ["neutral"] * 7 + ["assassin"]
    for i in range(25):
        board.append({"word": WORDS[i], "team": teams[i], "revealed": False})
    return board


def sample_state(**overrides) -> dict:
    base = {
        "teams": {"red": [1, 2], "blue": [3, 4]},
        "spymasters": {"red": 1, "blue": 3},
        "board": sample_board(),
        "turn": "red",
        "clue": None,
        "guesses_left": 0,
        "phase": "play",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# mention
# ---------------------------------------------------------------------------

class TestMention:
    def test_int(self):
        assert mention(42) == "<@42>"

    def test_string(self):
        assert mention("42") == "<@42>"


# ---------------------------------------------------------------------------
# team_members
# ---------------------------------------------------------------------------

class TestTeamMembers:
    def test_with_spymaster(self):
        state = sample_state()
        result = team_members(state, "red")
        assert "<@1>" in result
        assert "<@2>" in result
        assert "スパイマスター" in result

    def test_empty_team(self):
        state = sample_state(teams={"red": [], "blue": []}, spymasters={})
        result = team_members(state, "red")
        assert "なし" in result


# ---------------------------------------------------------------------------
# lobby_text
# ---------------------------------------------------------------------------

class TestLobbyText:
    def test_contains_teams(self):
        state = sample_state()
        text = lobby_text(state)
        assert "赤チーム" in text
        assert "青チーム" in text

    def test_empty_lobby(self):
        state = sample_state(teams={"red": [], "blue": []}, spymasters={})
        text = lobby_text(state)
        assert "なし" in text


# ---------------------------------------------------------------------------
# board_lines
# ---------------------------------------------------------------------------

class TestBoardLines:
    def test_five_rows(self):
        state = sample_state()
        lines = board_lines(state)
        assert len(lines) == 5

    def test_hidden_by_default(self):
        state = sample_state()
        lines = board_lines(state)
        for line in lines:
            assert "[R]" not in line
            assert "[B]" not in line

    def test_revealed_shows_mark(self):
        state = sample_state()
        state["board"][0]["revealed"] = True
        lines = board_lines(state)
        assert "[R]" in lines[0]

    def test_reveal_all(self):
        state = sample_state()
        lines = board_lines(state, reveal_all=True)
        full = "\n".join(lines)
        assert "[R]" in full
        assert "[B]" in full


# ---------------------------------------------------------------------------
# board_text
# ---------------------------------------------------------------------------

class TestBoardText:
    def test_basic(self):
        state = sample_state()
        text = board_text(state)
        assert "赤チーム" in text
        assert "コードネーム盤面" in text

    def test_with_clue(self):
        state = sample_state(clue={"word": "テスト", "count": 3}, guesses_left=2)
        text = board_text(state)
        assert "テスト" in text
        assert "3" in text


# ---------------------------------------------------------------------------
# key_text
# ---------------------------------------------------------------------------

class TestKeyText:
    def test_reveals_all(self):
        state = sample_state()
        text = key_text(state)
        assert "スパイマスター" in text
        assert "[R]" in text
        assert "[X]" in text


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_codenames_index_key(self):
        assert codenames_index_key(5) == "codenames_games_index:5"

    def test_codenames_game_key(self):
        assert codenames_game_key(5, "x") == "codenames_game:5:x"


# ---------------------------------------------------------------------------
# WORDS constant
# ---------------------------------------------------------------------------

class TestWords:
    def test_at_least_25(self):
        assert len(WORDS) >= 25

    def test_unique(self):
        assert len(set(WORDS)) == len(WORDS)
