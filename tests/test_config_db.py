"""Unit tests for database/config_db.py using SQLite backend."""

import os
import pytest
import asyncio

# Force SQLite mode for testing
os.environ.pop("DATABASE_URL", None)
os.environ["DATABASE_PATH"] = ":memory:"

from database.config_db import db_get, db_init, db_set, use_postgres


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestUsePostgres:
    def test_returns_false_without_url(self):
        assert use_postgres() is False


class TestDbSetGet:
    def test_round_trip(self):
        # Use a file-backed DB because :memory: creates a fresh DB per connection
        db_path = "/tmp/test_config_db.sqlite3"
        os.environ["DATABASE_PATH"] = db_path
        try:
            run(db_init())
            run(db_set("test_key", "test_value"))
            result = run(db_get("test_key"))
            assert result == "test_value"
        finally:
            os.environ["DATABASE_PATH"] = ":memory:"
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_get_missing_key(self):
        db_path = "/tmp/test_config_db2.sqlite3"
        os.environ["DATABASE_PATH"] = db_path
        try:
            run(db_init())
            result = run(db_get("nonexistent"))
            assert result is None
        finally:
            os.environ["DATABASE_PATH"] = ":memory:"
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_overwrite(self):
        db_path = "/tmp/test_config_db3.sqlite3"
        os.environ["DATABASE_PATH"] = db_path
        try:
            run(db_init())
            run(db_set("key", "v1"))
            run(db_set("key", "v2"))
            assert run(db_get("key")) == "v2"
        finally:
            os.environ["DATABASE_PATH"] = ":memory:"
            if os.path.exists(db_path):
                os.remove(db_path)
