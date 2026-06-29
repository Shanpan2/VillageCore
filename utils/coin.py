"""Shared coin-balance helpers.

``coin_key``, ``get_coin_balance`` and ``set_coin_balance`` were duplicated
across ``cogs/community.py``, ``Features/poker.py``, ``Features/othello.py``
and ``Features/gomoku.py``.  This module provides the single source of truth.
"""

from __future__ import annotations

from database.config_db import db_get, db_set


def coin_key(guild_id: int, user_id: int) -> str:
    return f"community_coin:{guild_id}:{user_id}"


async def get_coin_balance(guild_id: int, user_id: int) -> int:
    return int(await db_get(coin_key(guild_id, user_id)) or "0")


async def set_coin_balance(guild_id: int, user_id: int, amount: int) -> None:
    await db_set(coin_key(guild_id, user_id), str(max(0, amount)))
