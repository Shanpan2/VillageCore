from __future__ import annotations

import asyncio
import json
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from database.config_db import db_get, db_set


PREFIX = "投票-"
DB_KEY = "active_votes"


async def load_votes() -> dict:
    raw = await db_get(DB_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


async def save_votes(data: dict):
    await db_set(DB_KEY, json.dumps(data, ensure_ascii=False))


class VoteButton(Button):
    def __init__(self, option: str, index: int, vote_view: "VoteView"):
        super().__init__(
            label=option[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"vote_button:{vote_view.message_id}:{index}",
        )
        self.option = option
        self.vote_view = vote_view

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(user, discord.Member):
            await interaction.response.send_message("❌ サーバー内で実行してください。", ephemeral=True)
            return

        option = self.option
        role_name = f"{PREFIX}{option}"
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            role = await guild.create_role(name=role_name)

        votes_for_option = self.vote_view.votes.setdefault(option, set())
        if user.id in votes_for_option:
            votes_for_option.discard(user.id)
            try:
                await user.remove_roles(role)
            except discord.HTTPException:
                pass
            msg_text = f"↩️ **{option}** の投票を取り消しました。"
        else:
            votes_for_option.add(user.id)
            try:
                await user.add_roles(role)
            except discord.HTTPException:
                pass
            msg_text = f"🗳️ **{option}** に投票しました。"

        await self.vote_view.cog.persist_vote(self.vote_view)
        await self.vote_view.update_message(interaction.message)
        await interaction.response.send_message(msg_text, ephemeral=True)


class VoteView(View):
    def __init__(
        self,
        options: list[str],
        message_id: int,
        cog: "Vote",
        votes: dict[str, set[int]] | None = None,
    ):
        super().__init__(timeout=None)
        self.options = options
        self.message_id = message_id
        self.cog = cog
        self.votes: dict[str, set[int]] = votes or {opt: set() for opt in options}

        for index, opt in enumerate(options):
            self.add_item(VoteButton(opt, index, self))

    def build_description(self) -> str:
        return "\n".join(f"{opt}: **{len(self.votes.get(opt, set()))}票**" for opt in self.options)

    async def update_message(self, message: discord.Message | None):
        if message is None or not message.embeds:
            return
        embed = message.embeds[0]
        embed.description = self.build_description()
        await message.edit(embed=embed, view=self)


class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_votes: dict[int, dict] = {}
        self.auto_end_tasks: dict[int, asyncio.Task] = {}
        self.restore_task: asyncio.Task | None = None

    async def cog_load(self):
        self.restore_task = asyncio.create_task(self.restore_votes_after_ready())

    def cog_unload(self):
        if self.restore_task and not self.restore_task.done():
            self.restore_task.cancel()
        for task in self.auto_end_tasks.values():
            task.cancel()

    async def restore_votes_after_ready(self):
        await self.bot.wait_until_ready()
        await self.restore_votes()

    async def restore_votes(self):
        data = await load_votes()
        changed = False
        now = int(time.time())

        for message_id_str, vote_data in list(data.items()):
            try:
                message_id = int(message_id_str)
                channel_id = int(vote_data["channel_id"])
            except Exception:
                data.pop(message_id_str, None)
                changed = True
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue

            try:
                message = await channel.fetch_message(message_id)
            except Exception:
                data.pop(message_id_str, None)
                changed = True
                continue

            options = vote_data.get("options", [])
            votes = {
                opt: {int(uid) for uid in vote_data.get("votes", {}).get(opt, [])}
                for opt in options
            }
            view = VoteView(options, message_id, self, votes=votes)
            self.bot.add_view(view, message_id=message_id)
            self.active_votes[message_id] = {
                **vote_data,
                "view": view,
            }
            await view.update_message(message)

            end_at = vote_data.get("end_at")
            if end_at:
                remaining = int(end_at) - now
                if remaining <= 0:
                    guild = self.bot.get_guild(int(vote_data["guild_id"]))
                    if guild:
                        await self._end_vote(guild, channel, message_id)
                    data.pop(message_id_str, None)
                else:
                    self.auto_end_tasks[message_id] = asyncio.create_task(
                        self._auto_end(int(vote_data["guild_id"]), channel_id, message_id, remaining)
                    )

        if changed:
            await save_votes(data)

    async def persist_vote(self, view: VoteView):
        data = await load_votes()
        current = data.get(str(view.message_id), {})
        current["votes"] = {
            opt: [str(uid) for uid in view.votes.get(opt, set())]
            for opt in view.options
        }
        data[str(view.message_id)] = current
        await save_votes(data)

    @app_commands.command(name="vote", description="投票を開始します")
    @app_commands.describe(
        question="投票のタイトル・質問",
        options="選択肢をスペース区切りで入力 例: りんご バナナ みかん",
        duration="自動終了までの時間 例: 30s / 5m / 1h",
    )
    async def vote(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        duration: str | None = None,
    ):
        opts = options.split()
        if len(opts) < 2:
            await interaction.response.send_message(
                "❌ 選択肢は2つ以上、スペース区切りで入力してください。",
                ephemeral=True,
            )
            return

        seconds = self._parse_duration(duration) if duration else None
        embed = discord.Embed(
            title=f"🗳️ 投票: {question}",
            description="\n".join(f"{opt}: **0票**" for opt in opts),
            color=0x00FFCC,
        )
        if seconds:
            embed.set_footer(text=f"⏰ {duration} 後に自動終了")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        view = VoteView(opts, msg.id, self)
        await msg.edit(view=view)

        end_at = int(time.time()) + seconds if seconds else None
        data = await load_votes()
        data[str(msg.id)] = {
            "guild_id": str(interaction.guild_id),
            "channel_id": str(interaction.channel_id),
            "question": question,
            "options": opts,
            "votes": {opt: [] for opt in opts},
            "end_at": end_at,
        }
        await save_votes(data)

        self.active_votes[msg.id] = {
            **data[str(msg.id)],
            "view": view,
        }
        self.bot.add_view(view, message_id=msg.id)

        if seconds:
            self.auto_end_tasks[msg.id] = asyncio.create_task(
                self._auto_end(interaction.guild_id, interaction.channel_id, msg.id, seconds)
            )

    @app_commands.command(name="vote_end", description="投票を手動で終了します")
    @app_commands.describe(message_id="終了させたい投票メッセージのID")
    @app_commands.default_permissions(manage_roles=True)
    async def vote_end(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                "❌ メッセージIDは数字で入力してください。",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        result = await self._end_vote(interaction.guild, interaction.channel, mid)
        await interaction.followup.send(result, ephemeral=True)

    async def _auto_end(self, guild_id: int, channel_id: int, message_id: int, seconds: int):
        await asyncio.sleep(seconds)
        guild = self.bot.get_guild(guild_id)
        channel = self.bot.get_channel(channel_id)
        if guild and channel:
            await self._end_vote(guild, channel, message_id)

    async def _end_vote(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: int,
    ) -> str:
        data = await load_votes()
        vote_data = self.active_votes.pop(message_id, None)
        persisted = data.pop(str(message_id), None)
        if not vote_data and not persisted:
            return "❌ その投票は見つかりません。すでに終了済みかもしれません。"

        view: VoteView | None = vote_data.get("view") if vote_data else None
        options = (vote_data or persisted)["options"]
        votes = view.votes if view else {
            opt: {int(uid) for uid in persisted.get("votes", {}).get(opt, [])}
            for opt in options
        }
        results = {opt: len(votes.get(opt, set())) for opt in options}

        task = self.auto_end_tasks.pop(message_id, None)
        if task and not task.done():
            task.cancel()

        deleted = []
        for opt in options:
            role = discord.utils.get(guild.roles, name=f"{PREFIX}{opt}")
            if role:
                try:
                    await role.delete()
                    deleted.append(role.name)
                except discord.HTTPException:
                    pass

        try:
            msg = await channel.fetch_message(message_id)
            if msg.embeds:
                embed = msg.embeds[0]
                embed.title = embed.title.replace("🗳️", "📊") + "（終了）"
                embed.description = "\n".join(f"{opt}: **{results[opt]}票**" for opt in options)
                embed.color = 0xFF5555
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        result_lines = "\n".join(f"**{opt}** → {results[opt]}票" for opt in options)
        deleted_text = f"\n🗑️ 削除されたロール: {', '.join(deleted)}" if deleted else ""
        await channel.send(f"📊 **投票結果**\n{result_lines}{deleted_text}")

        await save_votes(data)
        return "✅ 投票を終了しました。"

    @staticmethod
    def _parse_duration(t: str) -> int | None:
        sec = 0
        num = ""
        found = False
        for c in t:
            if c.isdigit():
                num += c
            elif c in ("s", "m", "h") and num:
                found = True
                if c == "s":
                    sec += int(num)
                elif c == "m":
                    sec += int(num) * 60
                elif c == "h":
                    sec += int(num) * 3600
                num = ""
        return sec if found else None


async def setup(bot: commands.Bot):
    await bot.add_cog(Vote(bot))
