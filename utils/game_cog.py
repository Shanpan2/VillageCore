"""Shared base Cog for game features.

Every game Cog (UNO, Sevens, Daifugo, Poker, Ito, Codenames, Werewolf,
Othello, Gomoku) duplicated the same pattern:

    class GameCog(commands.Cog):
        def __init__(self, bot):
            self.bot = bot
            self._restore_task = None

        async def cog_load(self):
            self._restore_task = asyncio.create_task(self._restore_saved_games())

        async def cog_unload(self):
            if self._restore_task:
                self._restore_task.cancel()

        async def _restore_saved_games(self):
            await self.bot.wait_until_ready()
            for guild in self.bot.guilds:
                await load_games_for_guild(self.bot, guild)

This module provides a reusable base class.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import discord
from discord.ext import commands


class BaseGameCog(commands.Cog):
    """Base Cog that auto-restores persisted games on load.

    Subclasses must set ``_load_guild`` to an ``async (bot, guild)``
    callable (typically the game module's ``load_*_games_for_guild``).
    """

    _load_guild: Callable[[commands.Bot, discord.Guild], Awaitable[None]]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restore_task: asyncio.Task[None] | None = None

    async def cog_load(self) -> None:
        self._restore_task = asyncio.create_task(self._restore_saved_games())

    async def cog_unload(self) -> None:
        if self._restore_task:
            self._restore_task.cancel()

    async def _restore_saved_games(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._load_guild(self.bot, guild)
