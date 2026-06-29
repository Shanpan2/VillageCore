"""Unit tests for Features/sevens.py pure-logic helpers."""

from Features.sevens import (
    SUITS,
    active_players,
    build_deck,
    card_label,
    card_value,
    lobby_text,
    normalize_sevens_state,
    parse_card,
    playable_cards,
    rank_label,
    status_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_card(suit: str, rank: int) -> tuple[str, int]:
    return (suit, rank)


def default_board() -> dict[str, list[int]]:
    return {suit: [7] for suit in SUITS}


# ---------------------------------------------------------------------------
# rank_label
# ---------------------------------------------------------------------------

class TestRankLabel:
    def test_number(self):
        assert rank_label(5) == "5"

    def test_ace(self):
        assert rank_label(1) == "A"

    def test_jack(self):
        assert rank_label(11) == "J"

    def test_queen(self):
        assert rank_label(12) == "Q"

    def test_king(self):
        assert rank_label(13) == "K"


# ---------------------------------------------------------------------------
# card_label / card_value / parse_card
# ---------------------------------------------------------------------------

class TestCardConversions:
    def test_card_label(self):
        assert card_label(("S", 1)) == "♠A"
        assert card_label(("H", 7)) == "♥7"

    def test_card_value(self):
        assert card_value(("S", 5)) == "spade_5"
        assert card_value(("H", 13)) == "heart_13"

    def test_parse_card(self):
        assert parse_card("spade_5") == ("S", 5)
        assert parse_card("heart_13") == ("H", 13)

    def test_round_trip(self):
        card = ("D", 10)
        assert parse_card(card_value(card)) == card


# ---------------------------------------------------------------------------
# build_deck
# ---------------------------------------------------------------------------

class TestBuildDeck:
    def test_size(self):
        assert len(build_deck()) == 52

    def test_unique(self):
        deck = build_deck()
        assert len(set(deck)) == 52

    def test_contains_all_suits(self):
        deck = build_deck()
        suits = {card[0] for card in deck}
        assert suits == set(SUITS)


# ---------------------------------------------------------------------------
# playable_cards
# ---------------------------------------------------------------------------

class TestPlayableCards:
    def test_seven_always_playable(self):
        board = {suit: [] for suit in SUITS}
        hand = [("S", 7)]
        result = playable_cards(hand, board)
        assert ("S", 7) in result

    def test_adjacent_below(self):
        board = default_board()
        hand = [("S", 6), ("S", 3)]
        result = playable_cards(hand, board)
        assert ("S", 6) in result
        assert ("S", 3) not in result

    def test_adjacent_above(self):
        board = default_board()
        hand = [("S", 8), ("S", 12)]
        result = playable_cards(hand, board)
        assert ("S", 8) in result
        assert ("S", 12) not in result

    def test_already_placed(self):
        board = {suit: [7] for suit in SUITS}
        board["S"].append(6)
        hand = [("S", 6)]
        result = playable_cards(hand, board)
        assert result == []

    def test_empty_hand(self):
        assert playable_cards([], default_board()) == []

    def test_chain(self):
        board = {suit: [7] for suit in SUITS}
        board["H"] = [5, 6, 7]
        hand = [("H", 4), ("H", 8)]
        result = playable_cards(hand, board)
        assert ("H", 4) in result
        assert ("H", 8) in result


# ---------------------------------------------------------------------------
# active_players
# ---------------------------------------------------------------------------

class TestActivePlayers:
    def test_all_active(self):
        state = {"players": [1, 2, 3], "finished": {}}
        assert active_players(state) == [1, 2, 3]

    def test_excludes_finished(self):
        state = {"players": [1, 2, 3], "finished": {"2": 1}}
        assert active_players(state) == [1, 3]


# ---------------------------------------------------------------------------
# lobby_text
# ---------------------------------------------------------------------------

class TestLobbyText:
    def test_no_players(self):
        state = {"players": []}
        text = lobby_text(state)
        assert "なし" in text

    def test_with_players(self):
        state = {"players": [100, 200]}
        text = lobby_text(state)
        assert "<@100>" in text
        assert "<@200>" in text


# ---------------------------------------------------------------------------
# normalize_sevens_state
# ---------------------------------------------------------------------------

class TestNormalizeSevensState:
    def test_converts_string_ids(self):
        state = {"players": ["1", "2"], "turn_index": "1"}
        result = normalize_sevens_state(state)
        assert result["players"] == [1, 2]
        assert result["turn_index"] == 1

    def test_wraps_turn_index(self):
        state = {"players": [1, 2], "turn_index": 5}
        result = normalize_sevens_state(state)
        assert result["turn_index"] == 1

    def test_empty_players(self):
        state = {"players": [], "turn_index": 0}
        result = normalize_sevens_state(state)
        assert result["turn_index"] == 0


# ---------------------------------------------------------------------------
# status_text
# ---------------------------------------------------------------------------

class TestStatusText:
    def test_contains_turn_info(self):
        state = {
            "players": [1, 2],
            "turn_index": 0,
            "finished": {},
            "hands": {"1": [("S", 3)], "2": [("H", 5)]},
            "passes": {"1": 0, "2": 1},
        }
        text = status_text(state)
        assert "<@1>" in text
        assert "7並べ" in text

    def test_prefix(self):
        state = {
            "players": [1],
            "turn_index": 0,
            "finished": {},
            "hands": {"1": []},
            "passes": {},
        }
        text = status_text(state, prefix="テスト")
        assert text.startswith("テスト")
