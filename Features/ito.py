import random

import discord
from discord import app_commands
from discord.ext import commands

from utils.game_persistence import (
    save_game as _save_game,
    delete_game as _delete_game,
    load_games_for_guild,
    get_game_state,
)
from utils.game_cog import BaseGameCog


ito_games: dict[str, dict] = {}

_PREFIX = "ito"

DEFAULT_TOPICS = [
    "強そうなもの",
    "うれしいこと",
    "怖いもの",
    "人気がありそうなもの",
    "朝ごはんに合いそうなもの",
    "テンションが上がるもの",
    "一緒に旅したいもの",
    "学校にあったら便利なもの",
]


async def save_ito_game(guild_id: int | None, game_id: str, state: dict | None = None):
    await _save_game(_PREFIX, ito_games, guild_id, game_id, state)


async def delete_ito_game(guild_id: int | None, game_id: str):
    await _delete_game(_PREFIX, guild_id, game_id)


def _restore_ito_view(bot: commands.Bot, game_id: str, state: dict) -> None:
    if state.get("phase") == "lobby":
        bot.add_view(ItoLobbyView(game_id))


async def load_ito_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    await load_games_for_guild(
        _PREFIX, ito_games, bot, guild,
        restore_view=_restore_ito_view,
    )


def normalize_ito_state(state: dict) -> dict:
    state["players"] = [int(uid) for uid in state.get("players", [])]
    state["creator_id"] = int(state.get("creator_id", 0) or 0)
    if state.get("channel_id"):
        state["channel_id"] = int(state["channel_id"])
    return state


async def get_ito_game_state(bot: commands.Bot, game_id: str, guild_id: int | None = None) -> dict | None:
    return await get_game_state(
        _PREFIX, ito_games, bot, game_id, guild_id,
        normalize=normalize_ito_state,
    )


def mention(user_id: int | str) -> str:
    return f"<@{int(user_id)}>"


def lobby_text(state: dict) -> str:
    players = " / ".join(mention(uid) for uid in state.get("players", [])) or "まだいません"
    return (
        "**Ito募集**\n"
        f"お題: **{state.get('topic', 'ランダム')}**\n"
        f"参加者: {players}\n\n"
        "開始後、各プレイヤーに1から100の数字をDMで送ります。"
    )


def clue_text(state: dict) -> str:
    lines = []
    for index, uid in enumerate(state.get("players", []), start=1):
        clue = state.get("clues", {}).get(str(uid), "未提出")
        lines.append(f"{index}. {mention(uid)}: {clue}")
    return (
        f"**Ito進行中**\n"
        f"お題: **{state.get('topic')}**\n\n"
        + "\n".join(lines)
        + "\n\n全員が例えを出したら、作成者が `/ito action:順番提出 text:1,3,2` のように小さい順で提出してください。"
    )


class ItoLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel", "rules"), self.children):
            child.custom_id = f"ito_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = ito_games.get(self.game_id)
        if not state or state.get("phase") != "lobby":
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        if len(state["players"]) >= 12:
            await interaction.response.send_message("参加上限は12人です。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_ito_game(interaction.guild_id, self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = ito_games.get(self.game_id)
        if not state or state.get("phase") != "lobby":
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        state["players"] = [uid for uid in state["players"] if uid != interaction.user.id]
        await save_ito_game(interaction.guild_id, self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await begin_ito(interaction, self.game_id, edit_message=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = ito_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("中止できるのは作成者または管理者です。", ephemeral=True)
            return
        await delete_ito_game(interaction.guild_id, self.game_id)
        ito_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="Itoの募集を中止しました。", view=None)

    @discord.ui.button(label="ルール", style=discord.ButtonStyle.secondary, row=1)
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Ito のルール",
            description=(
                "各プレイヤーに1から100の数字がDMで配られます。\n"
                "数字を直接言わず、お題に沿った例えで自分の数字の大きさを表現します。\n"
                "全員の例えを見て、数字が小さい順になるように並べられたら成功です。\n\n"
                "例え提出: `/ito action:例え提出 text:ここに例え`\n"
                "順番提出: `/ito action:順番提出 text:1,3,2`"
            ),
            color=0xF1C40F,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def begin_ito(interaction: discord.Interaction, game_id: str, edit_message: bool = False):
    state = await get_ito_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("Ito募集がありません。", ephemeral=True)
        return
    if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("開始できるのは作成者または管理者です。", ephemeral=True)
        return
    if len(state.get("players", [])) < 2:
        await interaction.response.send_message("Itoは2人以上で開始できます。", ephemeral=True)
        return
    numbers = random.sample(range(1, 101), len(state["players"]))
    state["phase"] = "playing"
    state["numbers"] = {str(uid): number for uid, number in zip(state["players"], numbers)}
    state["clues"] = {}
    await save_ito_game(interaction.guild_id, game_id, state)
    for uid, number in state["numbers"].items():
        member = interaction.guild.get_member(int(uid)) or await interaction.client.fetch_user(int(uid))
        try:
            await member.send(f"Itoのお題は **{state['topic']}** です。あなたの数字は **{number}** です。数字を直接言わずに例えてください。")
        except discord.HTTPException:
            pass
    content = clue_text(state)
    if edit_message:
        await interaction.response.edit_message(content=content, view=None)
    else:
        await interaction.response.send_message(content)
    await interaction.followup.send("数字をDMに送りました。DMが届かない場合は管理者に確認してください。", ephemeral=True)


class Ito(BaseGameCog):
    _load_guild = staticmethod(load_ito_games_for_guild)

    @app_commands.command(name="ito", description="Itoを遊びます")
    @app_commands.describe(action="操作", text="お題、例え、順番提出に使います")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="募集", value="start"),
            app_commands.Choice(name="参加", value="join"),
            app_commands.Choice(name="抜ける", value="leave"),
            app_commands.Choice(name="開始", value="begin"),
            app_commands.Choice(name="例え提出", value="clue"),
            app_commands.Choice(name="順番提出", value="order"),
            app_commands.Choice(name="状況", value="status"),
            app_commands.Choice(name="終了", value="end"),
        ]
    )
    async def ito(self, interaction: discord.Interaction, action: app_commands.Choice[str], text: str | None = None):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return
        game_id = str(interaction.channel_id)
        state = await get_ito_game_state(self.bot, game_id, interaction.guild_id)

        if action.value == "start":
            if state and state.get("phase") != "ended":
                await interaction.response.send_message("このチャンネルではすでにItoがあります。", ephemeral=True)
                return
            topic = (text or "").strip() or random.choice(DEFAULT_TOPICS)
            state = {
                "guild_id": interaction.guild_id,
                "channel_id": interaction.channel_id,
                "creator_id": interaction.user.id,
                "phase": "lobby",
                "topic": topic,
                "players": [interaction.user.id],
                "numbers": {},
                "clues": {},
            }
            ito_games[game_id] = state
            await save_ito_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state), view=ItoLobbyView(game_id))
            return

        if not state:
            await interaction.response.send_message("このチャンネルにItoはありません。", ephemeral=True)
            return

        if action.value == "join":
            if state.get("phase") != "lobby":
                await interaction.response.send_message("開始後は参加できません。", ephemeral=True)
                return
            if interaction.user.id not in state["players"]:
                state["players"].append(interaction.user.id)
                await save_ito_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state))
            return

        if action.value == "leave":
            if state.get("phase") != "lobby":
                await interaction.response.send_message("開始後は抜けられません。", ephemeral=True)
                return
            state["players"] = [uid for uid in state["players"] if uid != interaction.user.id]
            await save_ito_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state))
            return

        if action.value == "begin":
            await begin_ito(interaction, game_id)
            return

        if action.value == "clue":
            if state.get("phase") != "playing":
                await interaction.response.send_message("開始後に例えを提出できます。", ephemeral=True)
                return
            if interaction.user.id not in state["players"]:
                await interaction.response.send_message("参加者のみ提出できます。", ephemeral=True)
                return
            clue = (text or "").strip()
            if not clue:
                await interaction.response.send_message("例えを `text` に入力してください。", ephemeral=True)
                return
            state.setdefault("clues", {})[str(interaction.user.id)] = clue[:80]
            await save_ito_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(clue_text(state))
            return

        if action.value == "order":
            if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("順番提出できるのは作成者または管理者です。", ephemeral=True)
                return
            raw_order = [part.strip() for part in (text or "").replace("，", ",").split(",") if part.strip()]
            try:
                order_indexes = [int(part) for part in raw_order]
            except ValueError:
                await interaction.response.send_message("順番は `1,3,2` のように番号で入力してください。", ephemeral=True)
                return
            players = state.get("players", [])
            if sorted(order_indexes) != list(range(1, len(players) + 1)):
                await interaction.response.send_message("参加者番号を重複なく全員分入力してください。", ephemeral=True)
                return
            submitted = [players[index - 1] for index in order_indexes]
            answer = sorted(players, key=lambda uid: state["numbers"][str(uid)])
            ok = submitted == answer
            answer_lines = [
                f"{i}. {mention(uid)}: {state['numbers'][str(uid)]} / {state.get('clues', {}).get(str(uid), '未提出')}"
                for i, uid in enumerate(answer, start=1)
            ]
            await delete_ito_game(interaction.guild_id, game_id)
            ito_games.pop(game_id, None)
            await interaction.response.send_message(
                ("成功です！" if ok else "惜しいです。")
                + "\n\n**正解順**\n"
                + "\n".join(answer_lines)
            )
            return

        if action.value == "status":
            await interaction.response.send_message(clue_text(state) if state.get("phase") == "playing" else lobby_text(state), ephemeral=True)
            return

        if action.value == "end":
            if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("終了できるのは作成者または管理者です。", ephemeral=True)
                return
            await delete_ito_game(interaction.guild_id, game_id)
            ito_games.pop(game_id, None)
            await interaction.response.send_message("Itoを終了しました。")


async def setup(bot):
    await bot.add_cog(Ito(bot))
