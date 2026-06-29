"""Shared lobby-view base class for card games (UNO, Sevens, Daifugo, Poker).

Each of these games had an almost identical ``*LobbyView`` with join / leave /
begin / cancel buttons differing only in:

* the game name shown in messages
* the in-memory ``games`` dict
* the ``save_game`` / ``delete_game`` / ``start_game`` coroutines
* the ``lobby_text`` formatter

This base class captures the shared logic.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import discord


class GameLobbyView(discord.ui.View):
    """Reusable four-button lobby (参加 / 抜ける / 開始 / 中止).

    Subclass parameters (set as *class* attributes or pass to ``__init__``):

    * ``game_name``    – human label, e.g. ``"UNO"``
    * ``lobby_prefix`` – custom_id prefix, e.g. ``"uno_lobby"``
    * ``games``        – the module-level ``dict[str, dict]`` of live games
    * ``save``         – ``async (guild_id, game_id, state) -> None``
    * ``delete``       – ``async (guild_id, game_id) -> None``
    * ``start``        – ``async (interaction, game_id) -> None``
    * ``lobby_text``   – ``(state) -> str``
    * ``started_key``  – state key indicating the game has started
                         (``"hands"`` for UNO, ``"started"`` for others)
    * ``begin_cmd``    – slash-command hint shown on error,
                         e.g. ``"/uno_begin"``
    """

    game_name: str
    lobby_prefix: str
    games: dict[str, dict]
    save: Callable[..., Awaitable[None]]
    delete: Callable[..., Awaitable[None]]
    start: Callable[..., Awaitable[None]]
    lobby_text: Callable[[dict], str]
    started_key: str = "started"
    begin_cmd: str = ""

    def __init__(self, game_id: str, **kwargs: Any):
        super().__init__(timeout=None)
        self.game_id = game_id
        for key, value in kwargs.items():
            setattr(self, key, value)
        for action, child in zip(("join", "leave", "begin", "cancel"), self.children):
            child.custom_id = f"{self.lobby_prefix}_{action}_{game_id}"

    def _is_started(self, state: dict) -> bool:
        return bool(state.get(self.started_key))

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        state = self.games.get(self.game_id)
        if not state:
            await interaction.response.send_message(
                f"この{self.game_name}募集は終了しています。", ephemeral=True,
            )
            return
        if self._is_started(state):
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await self.save(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=self.lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        state = self.games.get(self.game_id)
        if not state:
            await interaction.response.send_message(
                f"この{self.game_name}募集は終了しています。", ephemeral=True,
            )
            return
        if self._is_started(state):
            await interaction.response.send_message(
                "すでに開始しています。開始後は抜けられません。", ephemeral=True,
            )
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"].remove(interaction.user.id)
        if not state["players"]:
            await self.delete(interaction.guild_id or state.get("guild_id"), self.game_id)
            self.games.pop(self.game_id, None)
            await interaction.response.edit_message(
                content=f"参加者がいなくなったため、{self.game_name}募集を終了しました。",
                view=None,
            )
            return
        if state.get("creator_id") == interaction.user.id:
            state["creator_id"] = state["players"][0]
        await self.save(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=self.lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await self.start(interaction, self.game_id)
            state = self.games.get(self.game_id)
            if state and self._is_started(state) and interaction.message:
                try:
                    await interaction.message.edit(
                        content=self.lobby_text(state) + "\n\n開始済みです。", view=None,
                    )
                except discord.HTTPException:
                    pass
        except Exception as e:
            print(f"[{type(self).__name__}.begin] error: {type(e).__name__}: {e}", flush=True)
            hint = f"`{self.begin_cmd}` でもう一度試してください。" if self.begin_cmd else "もう一度試してください。"
            msg = f"開始処理中にエラーが発生しました。{hint}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        state = self.games.get(self.game_id)
        if not state:
            await interaction.response.send_message(
                f"この{self.game_name}募集はありません。", ephemeral=True,
            )
            return
        is_creator = interaction.user.id == state.get("creator_id")
        is_admin = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
        if not is_creator and not is_admin:
            await interaction.response.send_message(
                "中止できるのは作成者または管理者だけです。", ephemeral=True,
            )
            return
        await self.delete(interaction.guild_id or state.get("guild_id"), self.game_id)
        self.games.pop(self.game_id, None)
        await interaction.response.edit_message(
            content=f"{self.game_name}募集を中止しました。", view=None,
        )
