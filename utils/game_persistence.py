"""Shared persistence helpers for all game features.

Every game module (UNO, Sevens, Daifugo, Poker, Ito, Codenames, Werewolf,
Othello, Gomoku) duplicated the same save / delete / load-index / get-state
boilerplate.  This module extracts the common logic so each game only needs
to supply its ``prefix`` string, the in-memory ``games`` dict, and
(optionally) a ``normalize`` callback.
"""

from __future__ import annotations

import json
from typing import Callable

import discord
from discord.ext import commands

from database.config_db import db_get, db_set


def _index_key(prefix: str, guild_id: int) -> str:
    return f"{prefix}_games_index:{guild_id}"


def _game_key(prefix: str, guild_id: int, game_id: str) -> str:
    return f"{prefix}_game:{guild_id}:{game_id}"


async def save_game(
    prefix: str,
    games: dict[str, dict],
    guild_id: int | None,
    game_id: str,
    state: dict | None = None,
    *,
    exclude_keys: frozenset[str] = frozenset(),
    max_index: int = 100,
) -> None:
    """Persist *state* (or the in-memory entry) to the database and update
    the guild's game index.

    ``exclude_keys`` – keys stripped before serialisation (e.g. transient
    channel/message references that should not be persisted).
    """
    if not guild_id:
        return
    state = state or games.get(game_id)
    if not state:
        return
    state["guild_id"] = guild_id

    data = {k: v for k, v in state.items() if k not in exclude_keys} if exclude_keys else state
    await db_set(_game_key(prefix, guild_id, game_id), json.dumps(data, ensure_ascii=False))

    try:
        index: list[str] = json.loads(await db_get(_index_key(prefix, guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(_index_key(prefix, guild_id), json.dumps(index[-max_index:], ensure_ascii=False))


async def delete_game(
    prefix: str,
    guild_id: int | None,
    game_id: str,
    *,
    clear_value: bool = False,
) -> None:
    """Remove *game_id* from the guild index.

    When ``clear_value`` is True the stored game data is also blanked (used by
    gomoku).
    """
    if not guild_id:
        return
    try:
        index: list[str] = json.loads(await db_get(_index_key(prefix, guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(_index_key(prefix, guild_id), json.dumps(index, ensure_ascii=False))
    if clear_value:
        await db_set(_game_key(prefix, guild_id, game_id), "")


async def load_games_for_guild(
    prefix: str,
    games: dict[str, dict],
    bot: commands.Bot,
    guild: discord.Guild,
    *,
    validate: Callable[[dict], bool] | None = None,
    restore_view: Callable[[commands.Bot, str, dict], None] | None = None,
) -> None:
    """Reload every persisted game for *guild* into *games*.

    ``validate`` – return False to skip an entry (default: check for
    ``state.get("players")`` being truthy).
    ``restore_view`` – called with ``(bot, game_id, state)`` so the caller
    can re-register persistent views.
    """
    try:
        index: list[str] = json.loads(await db_get(_index_key(prefix, guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []

    changed = False
    for game_id in index:
        raw = await db_get(_game_key(prefix, guild.id, game_id))
        if not raw:
            changed = True
            continue
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            changed = True
            continue
        if validate is not None:
            if not validate(state):
                changed = True
                continue
        elif not isinstance(state, dict) or not state.get("players"):
            changed = True
            continue
        games[game_id] = state
        if restore_view is not None:
            restore_view(bot, game_id, state)

    if changed:
        active = [gid for gid in index if gid in games]
        await db_set(_index_key(prefix, guild.id), json.dumps(active, ensure_ascii=False))


async def get_game_state(
    prefix: str,
    games: dict[str, dict],
    bot: commands.Bot,
    game_id: str,
    guild_id: int | None = None,
    *,
    normalize: Callable[[dict], dict] | None = None,
) -> dict | None:
    """Return the in-memory state for *game_id*, falling back to a DB lookup
    across all known guilds.  If ``normalize`` is given it is applied before
    returning."""
    state = games.get(game_id)
    if state:
        if normalize:
            state = normalize(state)
        games[game_id] = state
        return state

    guild_ids: list[int] = []
    if guild_id:
        guild_ids.append(int(guild_id))
    guild_ids.extend(g.id for g in getattr(bot, "guilds", []) if g.id not in guild_ids)

    for target_guild_id in guild_ids:
        raw = await db_get(_game_key(prefix, target_guild_id, game_id))
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if normalize:
            state = normalize(state)
        if not state.get("players"):
            continue
        state["guild_id"] = target_guild_id
        games[game_id] = state
        return state
    return None
