"""Unit tests for Features/meigen.py pure-logic helpers."""

from Features.meigen import (
    MAX_MEIGEN_PER_USER,
    ensure_meigen_ids,
    meigen_key,
    meigen_quote_mode_key,
    sort_meigen_items,
)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_meigen_key(self):
        assert meigen_key(1, 2) == "meigen:1:2"

    def test_meigen_quote_mode_key(self):
        assert meigen_quote_mode_key(5) == "meigen_quote_mode:5"


# ---------------------------------------------------------------------------
# sort_meigen_items
# ---------------------------------------------------------------------------

class TestSortMeigenItems:
    def test_sorts_descending_by_date(self):
        items = [
            {"text": "a", "created_at": "2024-01-01 10:00"},
            {"text": "b", "created_at": "2024-06-15 12:00"},
            {"text": "c", "created_at": "2024-03-10 08:00"},
        ]
        result = sort_meigen_items(items)
        assert result[0]["text"] == "b"
        assert result[1]["text"] == "c"
        assert result[2]["text"] == "a"

    def test_empty(self):
        assert sort_meigen_items([]) == []

    def test_missing_date(self):
        items = [{"text": "a"}, {"text": "b", "created_at": "2024-01-01 10:00"}]
        result = sort_meigen_items(items)
        assert result[0]["text"] == "b"


# ---------------------------------------------------------------------------
# ensure_meigen_ids
# ---------------------------------------------------------------------------

class TestEnsureMeigenIds:
    def test_assigns_id_when_missing(self):
        items = [{"text": "hello"}]
        result, changed = ensure_meigen_ids(items, 1, 2)
        assert changed is True
        assert result[0]["id"]
        assert "1-2-" in result[0]["id"]

    def test_preserves_existing_id(self):
        items = [{"text": "hello", "id": "existing-123"}]
        result, changed = ensure_meigen_ids(items, 1, 2)
        assert changed is False
        assert result[0]["id"] == "existing-123"

    def test_mixed(self):
        items = [
            {"text": "a", "id": "keep-me"},
            {"text": "b"},
        ]
        result, changed = ensure_meigen_ids(items, 1, 2)
        assert changed is True
        assert result[0]["id"] == "keep-me"
        assert result[1]["id"]

    def test_non_dict_skipped(self):
        items = [{"text": "a"}, "not a dict"]
        result, changed = ensure_meigen_ids(items, 1, 2)
        assert changed is True


# ---------------------------------------------------------------------------
# MAX_MEIGEN_PER_USER
# ---------------------------------------------------------------------------

class TestMaxMeigen:
    def test_positive(self):
        assert MAX_MEIGEN_PER_USER > 0
