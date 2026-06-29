"""Unit tests for Features/omikuji.py pure-logic helpers."""

from Features.omikuji import (
    FORTUNES,
    LUCKY_COLORS,
    LUCKY_ITEMS,
    OMIKUJI_STREAK_TITLES,
    choose_fortune,
    omikuji_last_key,
    omikuji_streak_key,
)


# ---------------------------------------------------------------------------
# FORTUNES constant
# ---------------------------------------------------------------------------

class TestFortunes:
    def test_not_empty(self):
        assert len(FORTUNES) > 0

    def test_weights_positive(self):
        for f in FORTUNES:
            assert f["weight"] > 0

    def test_coins_non_negative(self):
        for f in FORTUNES:
            assert f["coins"] >= 0

    def test_all_have_required_keys(self):
        for f in FORTUNES:
            assert "name" in f
            assert "message" in f
            assert "weight" in f
            assert "coins" in f
            assert "color" in f

    def test_weights_sum(self):
        total = sum(f["weight"] for f in FORTUNES)
        assert total == 100


# ---------------------------------------------------------------------------
# choose_fortune
# ---------------------------------------------------------------------------

class TestChooseFortune:
    def test_returns_valid_fortune(self):
        result = choose_fortune()
        assert result in FORTUNES

    def test_multiple_calls(self):
        results = {choose_fortune()["name"] for _ in range(200)}
        assert len(results) >= 2


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_omikuji_last_key(self):
        assert omikuji_last_key(1, 2) == "omikuji_last_1_2"

    def test_omikuji_streak_key(self):
        assert omikuji_streak_key(1, 2) == "omikuji_streak:1:2"


# ---------------------------------------------------------------------------
# LUCKY_* constants
# ---------------------------------------------------------------------------

class TestLuckyConstants:
    def test_colors_not_empty(self):
        assert len(LUCKY_COLORS) >= 5

    def test_items_not_empty(self):
        assert len(LUCKY_ITEMS) >= 10

    def test_unique_colors(self):
        assert len(set(LUCKY_COLORS)) == len(LUCKY_COLORS)


# ---------------------------------------------------------------------------
# OMIKUJI_STREAK_TITLES
# ---------------------------------------------------------------------------

class TestStreakTitles:
    def test_ascending_days(self):
        days = [d for d, _ in OMIKUJI_STREAK_TITLES]
        assert days == sorted(days)

    def test_all_have_title(self):
        for _, title in OMIKUJI_STREAK_TITLES:
            assert isinstance(title, str)
            assert len(title) > 0
