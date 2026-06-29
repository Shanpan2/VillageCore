"""Unit tests for Features/daifugo.py pure-logic helpers."""

from Features.daifugo import (
    DEFAULT_RULES,
    active_players,
    apply_capital_fall,
    beats,
    build_deck,
    can_play,
    card_label,
    clear_field,
    decode_group,
    encode_group,
    group_info,
    group_label,
    legal_groups,
    normalize_daifugo_state,
    rank_label,
    rules_text,
    sequence_groups,
    suit_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_card(suit: str, rank: int) -> dict:
    return {"suit": suit, "rank": rank}


def make_state(**overrides) -> dict:
    base = {
        "players": [1, 2, 3],
        "turn_index": 0,
        "hands": {},
        "finished": [],
        "fallen": [],
        "last_play": None,
        "last_info": None,
        "last_player": None,
        "passed": [],
        "locked_suits": None,
        "revolution": False,
        "rules": dict(DEFAULT_RULES),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# rank_label / card_label / group_label
# ---------------------------------------------------------------------------

class TestCardLabels:
    def test_rank_label_number(self):
        assert rank_label(5) == "5"

    def test_rank_label_face(self):
        assert rank_label(11) == "J"
        assert rank_label(14) == "A"
        assert rank_label(15) == "2"
        assert rank_label(16) == "JOKER"

    def test_card_label_normal(self):
        assert card_label(make_card("S", 3)) == "♠3"

    def test_card_label_joker(self):
        assert card_label(make_card("J", 16)) == "JOKER"

    def test_group_label(self):
        cards = [make_card("S", 3), make_card("H", 3)]
        assert group_label(cards) == "♠3 ♥3"


# ---------------------------------------------------------------------------
# build_deck
# ---------------------------------------------------------------------------

class TestBuildDeck:
    def test_size(self):
        deck = build_deck()
        assert len(deck) == 53  # 52 + joker

    def test_contains_joker(self):
        deck = build_deck()
        jokers = [c for c in deck if c["rank"] == 16]
        assert len(jokers) == 1

    def test_unique_non_joker(self):
        deck = build_deck()
        non_joker = [(c["suit"], c["rank"]) for c in deck if c["rank"] != 16]
        assert len(set(non_joker)) == 52


# ---------------------------------------------------------------------------
# encode_group / decode_group
# ---------------------------------------------------------------------------

class TestEncodeDecodeGroup:
    def test_round_trip(self):
        hand = [make_card("S", 3), make_card("H", 5), make_card("D", 10)]
        group = [hand[0], hand[2]]
        encoded = encode_group(group)
        decoded = decode_group(encoded, hand)
        assert len(decoded) == 2
        assert decoded[0] == hand[0]
        assert decoded[1] == hand[2]


# ---------------------------------------------------------------------------
# suit_key
# ---------------------------------------------------------------------------

class TestSuitKey:
    def test_single_card(self):
        assert suit_key([make_card("H", 5)]) == ("H",)

    def test_multiple_sorted(self):
        cards = [make_card("H", 5), make_card("C", 5)]
        assert suit_key(cards) == ("C", "H")


# ---------------------------------------------------------------------------
# beats
# ---------------------------------------------------------------------------

class TestBeats:
    def test_higher_beats_lower_normal(self):
        assert beats(10, 5, False) is True

    def test_lower_does_not_beat_higher_normal(self):
        assert beats(5, 10, False) is False

    def test_revolution_reverses(self):
        assert beats(5, 10, True) is True
        assert beats(10, 5, True) is False

    def test_joker_beats_all(self):
        assert beats(16, 15, False) is True

    def test_nothing_beats_joker(self):
        assert beats(14, 16, False) is False

    def test_joker_vs_joker(self):
        assert beats(16, 16, False) is False

    def test_beats_empty_field(self):
        assert beats(3, 0, False) is True


# ---------------------------------------------------------------------------
# group_info
# ---------------------------------------------------------------------------

class TestGroupInfo:
    def test_single_card(self):
        info = group_info([make_card("S", 5)])
        assert info["type"] == "single"
        assert info["count"] == 1
        assert info["rank"] == 5

    def test_pair(self):
        cards = [make_card("S", 7), make_card("H", 7)]
        info = group_info(cards)
        assert info["type"] == "set"
        assert info["count"] == 2

    def test_triple(self):
        cards = [make_card("S", 7), make_card("H", 7), make_card("D", 7)]
        info = group_info(cards)
        assert info["type"] == "set"
        assert info["count"] == 3

    def test_sequence(self):
        cards = [make_card("S", 5), make_card("S", 6), make_card("S", 7)]
        info = group_info(cards)
        assert info["type"] == "sequence"
        assert info["count"] == 3
        assert info["rank"] == 7

    def test_empty(self):
        assert group_info([]) is None

    def test_joker_invalid_group(self):
        cards = [make_card("S", 5), make_card("J", 16)]
        assert group_info(cards) is None

    def test_mixed_ranks_not_sequence(self):
        cards = [make_card("S", 5), make_card("S", 7), make_card("S", 9)]
        assert group_info(cards) is None

    def test_mixed_suit_not_sequence(self):
        cards = [make_card("S", 5), make_card("H", 6), make_card("D", 7)]
        assert group_info(cards) is None


# ---------------------------------------------------------------------------
# can_play
# ---------------------------------------------------------------------------

class TestCanPlay:
    def test_first_play(self):
        state = make_state()
        cards = [make_card("S", 5)]
        assert can_play(cards, state) is True

    def test_must_match_type_and_count(self):
        state = make_state(
            last_info={"type": "single", "count": 1, "rank": 5, "suits": ("S",)},
        )
        pair = [make_card("S", 7), make_card("H", 7)]
        assert can_play(pair, state) is False

    def test_must_beat_last_rank(self):
        state = make_state(
            last_info={"type": "single", "count": 1, "rank": 10, "suits": ("S",)},
        )
        assert can_play([make_card("H", 5)], state) is False
        assert can_play([make_card("H", 12)], state) is True

    def test_suit_lock(self):
        state = make_state(
            last_info={"type": "single", "count": 1, "rank": 5, "suits": ("S",)},
            locked_suits=["S"],
        )
        assert can_play([make_card("S", 10)], state) is True
        assert can_play([make_card("H", 10)], state) is False


# ---------------------------------------------------------------------------
# sequence_groups
# ---------------------------------------------------------------------------

class TestSequenceGroups:
    def test_finds_sequences(self):
        hand = [make_card("S", r) for r in [3, 4, 5, 6, 10]]
        groups = sequence_groups(hand)
        assert len(groups) >= 1
        lengths = [len(g) for g in groups]
        assert 3 in lengths

    def test_no_sequences(self):
        hand = [make_card("S", 3), make_card("H", 7), make_card("D", 12)]
        assert sequence_groups(hand) == []

    def test_ignores_joker(self):
        hand = [make_card("S", 3), make_card("S", 4), make_card("J", 16)]
        assert sequence_groups(hand) == []


# ---------------------------------------------------------------------------
# legal_groups
# ---------------------------------------------------------------------------

class TestLegalGroups:
    def test_initial_turn(self):
        hand = [make_card("S", 5), make_card("H", 10), make_card("J", 16)]
        state = make_state()
        groups = legal_groups(hand, state)
        assert len(groups) >= 3

    def test_respects_suit_lock(self):
        hand = [make_card("S", 10), make_card("H", 12)]
        state = make_state(
            last_info={"type": "single", "count": 1, "rank": 5, "suits": ("S",)},
            locked_suits=["S"],
        )
        groups = legal_groups(hand, state)
        values = [g[0]["suit"] for g in groups if len(g) == 1]
        assert all(s == "S" for s in values)


# ---------------------------------------------------------------------------
# active_players / clear_field
# ---------------------------------------------------------------------------

class TestActivePlayers:
    def test_excludes_finished(self):
        state = make_state(finished=["2"])
        assert active_players(state) == [1, 3]

    def test_excludes_fallen(self):
        state = make_state(fallen=["3"])
        assert active_players(state) == [1, 2]


class TestClearField:
    def test_resets_all_fields(self):
        state = make_state(
            last_play=[make_card("S", 5)],
            last_info={"type": "single"},
            last_player=1,
            passed=[2],
            locked_suits=["S"],
        )
        clear_field(state)
        assert state["last_play"] is None
        assert state["last_info"] is None
        assert state["last_player"] is None
        assert state["passed"] == []
        assert state["locked_suits"] is None


# ---------------------------------------------------------------------------
# rules_text
# ---------------------------------------------------------------------------

class TestRulesText:
    def test_default_rules(self):
        state = make_state()
        text = rules_text(state)
        assert "革命" in text
        assert "8切り" in text

    def test_no_rules(self):
        state = make_state(rules={})
        assert rules_text(state) == "追加ルールなし"


# ---------------------------------------------------------------------------
# apply_capital_fall
# ---------------------------------------------------------------------------

class TestApplyCapitalFall:
    def test_no_previous(self):
        state = make_state()
        assert apply_capital_fall(state, 1) == ""

    def test_same_winner(self):
        state = make_state(previous_daifugo_id=1)
        assert apply_capital_fall(state, 1) == ""

    def test_previous_falls(self):
        state = make_state(previous_daifugo_id=2)
        result = apply_capital_fall(state, 1)
        assert "都落ち" in result
        assert "2" in state.get("fallen", [])

    def test_disabled_rule(self):
        rules = dict(DEFAULT_RULES)
        rules["capital_fall"] = False
        state = make_state(rules=rules, previous_daifugo_id=2)
        assert apply_capital_fall(state, 1) == ""

    def test_already_finished(self):
        state = make_state(previous_daifugo_id=2, finished=["2"])
        assert apply_capital_fall(state, 1) == ""


# ---------------------------------------------------------------------------
# normalize_daifugo_state
# ---------------------------------------------------------------------------

class TestNormalizeDaifugoState:
    def test_converts_string_ids(self):
        state = {"players": ["1", "2"], "turn_index": "1"}
        result = normalize_daifugo_state(state)
        assert result["players"] == [1, 2]
        assert result["turn_index"] == 1

    def test_wraps_turn_index(self):
        state = {"players": [1, 2], "turn_index": 5}
        result = normalize_daifugo_state(state)
        assert result["turn_index"] == 1
