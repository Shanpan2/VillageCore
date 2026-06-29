"""Unit tests for Features/poker.py pure-logic helpers."""

from Features.poker import (
    HAND_NAMES,
    bet_line,
    build_deck,
    card_label,
    card_sort_key,
    encode_card,
    evaluate_hand,
    hand_name,
    lobby_text,
    normalize_poker_state,
    rank_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_card(suit: str, rank: int) -> dict:
    return {"suit": suit, "rank": rank}


def make_hand(*specs: tuple[str, int]) -> list[dict]:
    return [make_card(s, r) for s, r in specs]


# ---------------------------------------------------------------------------
# rank_label / card_label / encode_card / card_sort_key
# ---------------------------------------------------------------------------

class TestCardUtilities:
    def test_rank_label_number(self):
        assert rank_label(5) == "5"

    def test_rank_label_face(self):
        assert rank_label(11) == "J"
        assert rank_label(12) == "Q"
        assert rank_label(13) == "K"
        assert rank_label(14) == "A"

    def test_card_label(self):
        assert card_label(make_card("S", 14)) == "♠A"
        assert card_label(make_card("H", 2)) == "♥2"

    def test_encode_card(self):
        assert encode_card(make_card("D", 10)) == "D10"

    def test_card_sort_key(self):
        cards = [make_card("H", 3), make_card("S", 14), make_card("D", 3)]
        sorted_cards = sorted(cards, key=card_sort_key)
        assert sorted_cards[0]["rank"] <= sorted_cards[-1]["rank"]


# ---------------------------------------------------------------------------
# build_deck
# ---------------------------------------------------------------------------

class TestBuildDeck:
    def test_deck_size(self):
        assert len(build_deck()) == 52

    def test_unique_cards(self):
        deck = build_deck()
        combos = [(c["suit"], c["rank"]) for c in deck]
        assert len(set(combos)) == 52


# ---------------------------------------------------------------------------
# evaluate_hand
# ---------------------------------------------------------------------------

class TestEvaluateHand:
    def test_high_card(self):
        hand = make_hand(("S", 2), ("H", 5), ("D", 8), ("C", 10), ("S", 13))
        score, tiebreakers = evaluate_hand(hand)
        assert score == 0

    def test_one_pair(self):
        hand = make_hand(("S", 5), ("H", 5), ("D", 8), ("C", 10), ("S", 13))
        score, _ = evaluate_hand(hand)
        assert score == 1

    def test_two_pair(self):
        hand = make_hand(("S", 5), ("H", 5), ("D", 10), ("C", 10), ("S", 13))
        score, _ = evaluate_hand(hand)
        assert score == 2

    def test_three_of_a_kind(self):
        hand = make_hand(("S", 7), ("H", 7), ("D", 7), ("C", 10), ("S", 13))
        score, _ = evaluate_hand(hand)
        assert score == 3

    def test_straight(self):
        hand = make_hand(("S", 5), ("H", 6), ("D", 7), ("C", 8), ("S", 9))
        score, _ = evaluate_hand(hand)
        assert score == 4

    def test_wheel_straight(self):
        hand = make_hand(("S", 14), ("H", 2), ("D", 3), ("C", 4), ("S", 5))
        score, tiebreakers = evaluate_hand(hand)
        assert score == 4
        assert tiebreakers == [5]

    def test_flush(self):
        hand = make_hand(("S", 2), ("S", 5), ("S", 8), ("S", 10), ("S", 13))
        score, _ = evaluate_hand(hand)
        assert score == 5

    def test_full_house(self):
        hand = make_hand(("S", 7), ("H", 7), ("D", 7), ("C", 10), ("S", 10))
        score, _ = evaluate_hand(hand)
        assert score == 6

    def test_four_of_a_kind(self):
        hand = make_hand(("S", 9), ("H", 9), ("D", 9), ("C", 9), ("S", 13))
        score, _ = evaluate_hand(hand)
        assert score == 7

    def test_straight_flush(self):
        hand = make_hand(("H", 5), ("H", 6), ("H", 7), ("H", 8), ("H", 9))
        score, _ = evaluate_hand(hand)
        assert score == 8

    def test_hand_ranking_order(self):
        high = make_hand(("S", 2), ("H", 5), ("D", 8), ("C", 10), ("S", 13))
        pair = make_hand(("S", 5), ("H", 5), ("D", 8), ("C", 10), ("S", 13))
        flush = make_hand(("S", 2), ("S", 5), ("S", 8), ("S", 10), ("S", 13))
        sf = make_hand(("H", 5), ("H", 6), ("H", 7), ("H", 8), ("H", 9))
        scores = [evaluate_hand(h) for h in [high, pair, flush, sf]]
        assert scores[0] < scores[1] < scores[2] < scores[3]


# ---------------------------------------------------------------------------
# hand_name
# ---------------------------------------------------------------------------

class TestHandName:
    def test_all_names_covered(self):
        for code, name in HAND_NAMES.items():
            assert isinstance(name, str)

    def test_straight_flush_name(self):
        hand = make_hand(("H", 5), ("H", 6), ("H", 7), ("H", 8), ("H", 9))
        assert hand_name(hand) == "ストレートフラッシュ"

    def test_high_card_name(self):
        hand = make_hand(("S", 2), ("H", 5), ("D", 8), ("C", 10), ("S", 13))
        assert hand_name(hand) == "ハイカード"


# ---------------------------------------------------------------------------
# bet_line / lobby_text
# ---------------------------------------------------------------------------

class TestBetLine:
    def test_no_bet(self):
        state = {"bet": 0, "pot": 0, "players": [1, 2]}
        assert "なし" in bet_line(state)

    def test_with_bet(self):
        state = {"bet": 10, "pot": 20, "players": [1, 2]}
        result = bet_line(state)
        assert "10" in result
        assert "20" in result


class TestLobbyText:
    def test_empty_players(self):
        state = {"players": [], "bet": 0, "pot": 0}
        text = lobby_text(state)
        assert "なし" in text

    def test_with_players(self):
        state = {"players": [111, 222], "bet": 0, "pot": 0}
        text = lobby_text(state)
        assert "<@111>" in text
        assert "<@222>" in text


# ---------------------------------------------------------------------------
# normalize_poker_state
# ---------------------------------------------------------------------------

class TestNormalizePokerState:
    def test_converts_string_ids(self):
        state = {"players": ["1", "2"], "turn_index": "0", "exchanged": []}
        result = normalize_poker_state(state)
        assert result["players"] == [1, 2]
        assert result["turn_index"] == 0

    def test_wraps_turn_index(self):
        state = {"players": [1, 2, 3], "turn_index": 5, "exchanged": []}
        result = normalize_poker_state(state)
        assert result["turn_index"] == 2
