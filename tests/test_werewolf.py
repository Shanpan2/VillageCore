"""Unit tests for Features/werewolf.py pure-logic helpers."""

from Features.werewolf import (
    ROLE_LABELS,
    alive_ids,
    assign_roles,
    lobby_text,
    mention,
    role_of,
    status_text,
    werewolf_game_key,
    werewolf_index_key,
)


# ---------------------------------------------------------------------------
# mention
# ---------------------------------------------------------------------------

class TestMention:
    def test_int(self):
        assert mention(42) == "<@42>"

    def test_string(self):
        assert mention("42") == "<@42>"


# ---------------------------------------------------------------------------
# alive_ids
# ---------------------------------------------------------------------------

class TestAliveIds:
    def test_returns_ints(self):
        state = {"alive": [1, 2, 3]}
        assert alive_ids(state) == [1, 2, 3]

    def test_converts_strings(self):
        state = {"alive": ["1", "2"]}
        assert alive_ids(state) == [1, 2]

    def test_empty(self):
        state = {"alive": []}
        assert alive_ids(state) == []


# ---------------------------------------------------------------------------
# role_of
# ---------------------------------------------------------------------------

class TestRoleOf:
    def test_found(self):
        state = {"roles": {"1": "werewolf", "2": "seer"}}
        assert role_of(state, 1) == "werewolf"
        assert role_of(state, "2") == "seer"

    def test_not_found(self):
        state = {"roles": {}}
        assert role_of(state, 99) is None


# ---------------------------------------------------------------------------
# assign_roles
# ---------------------------------------------------------------------------

class TestAssignRoles:
    def test_four_players(self):
        players = [1, 2, 3, 4]
        roles = assign_roles(players)
        assert len(roles) == 4
        counts = {}
        for role in roles.values():
            counts[role] = counts.get(role, 0) + 1
        assert counts.get("werewolf", 0) == 1
        assert counts.get("seer", 0) == 1
        assert "villager" in counts

    def test_five_players_has_knight(self):
        players = list(range(1, 6))
        roles = assign_roles(players)
        assert "knight" in roles.values()

    def test_eight_players_two_wolves(self):
        players = list(range(1, 9))
        roles = assign_roles(players)
        wolf_count = sum(1 for r in roles.values() if r == "werewolf")
        assert wolf_count == 2

    def test_all_roles_are_known(self):
        players = list(range(1, 10))
        roles = assign_roles(players)
        for role in roles.values():
            assert role in ROLE_LABELS


# ---------------------------------------------------------------------------
# lobby_text
# ---------------------------------------------------------------------------

class TestLobbyText:
    def test_empty(self):
        state = {"players": []}
        text = lobby_text(state)
        assert "まだいません" in text

    def test_with_players(self):
        state = {"players": [10, 20]}
        text = lobby_text(state)
        assert "<@10>" in text
        assert "2/12" in text


# ---------------------------------------------------------------------------
# status_text
# ---------------------------------------------------------------------------

class TestStatusText:
    def test_lobby_phase(self):
        state = {"phase": "lobby", "players": [1]}
        text = status_text(state)
        assert "人狼ゲーム募集" in text

    def test_night_phase(self):
        state = {"phase": "night", "day": 1, "alive": [1, 2, 3]}
        text = status_text(state)
        assert "夜" in text
        assert "1日目" in text

    def test_day_phase(self):
        state = {"phase": "day", "day": 2, "alive": [1, 2]}
        text = status_text(state)
        assert "昼" in text
        assert "投票" in text

    def test_end_phase(self):
        state = {"phase": "end", "day": 3, "alive": []}
        text = status_text(state)
        assert "終了" in text


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_werewolf_index_key(self):
        assert werewolf_index_key(5) == "werewolf_games_index:5"

    def test_werewolf_game_key(self):
        assert werewolf_game_key(5, "abc") == "werewolf_game:5:abc"
