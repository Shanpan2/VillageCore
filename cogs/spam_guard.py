import asyncio
import json
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from cogs.server_logs import send_server_log
from database.config_db import db_get, db_set


DEFAULT_SETTINGS = {
    "enabled": False,
    "delete_messages": True,
    "timeout_enabled": True,
    "dm_notify": True,
    "everyone_limit": 3,
    "repeat_limit": 5,
    "window_seconds": 30,
    "timeout_minutes": 10,
}


def spam_settings_key(guild_id: int) -> str:
    return f"spam_guard_settings:{guild_id}"


def normalize_content(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


class SpamGuard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._settings_cache: dict[int, dict] = {}
        self._events: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=30))
        self._locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._sanctioned_until: dict[tuple[int, int], float] = {}

    async def load_settings(self, guild_id: int) -> dict:
        cached = self._settings_cache.get(guild_id)
        if cached is not None:
            return cached.copy()
        settings = DEFAULT_SETTINGS.copy()
        raw = await db_get(spam_settings_key(guild_id))
        if raw:
            try:
                saved = json.loads(raw)
                if isinstance(saved, dict):
                    settings.update({key: saved[key] for key in settings if key in saved})
            except (json.JSONDecodeError, TypeError):
                pass
        self._settings_cache[guild_id] = settings
        return settings.copy()

    async def save_settings(self, guild_id: int, settings: dict):
        normalized = DEFAULT_SETTINGS.copy()
        normalized.update({key: settings[key] for key in normalized if key in settings})
        self._settings_cache[guild_id] = normalized
        await db_set(spam_settings_key(guild_id), json.dumps(normalized, ensure_ascii=False))

    @staticmethod
    def settings_embed(settings: dict) -> discord.Embed:
        embed = discord.Embed(
            title="スパム防止設定",
            description="管理者とメッセージ管理権限を持つメンバーは検出対象外です。",
            color=0x2ECC71 if settings["enabled"] else 0x95A5A6,
        )
        embed.add_field(name="機能", value="ON" if settings["enabled"] else "OFF", inline=True)
        embed.add_field(name="自動削除", value="ON" if settings["delete_messages"] else "OFF", inline=True)
        embed.add_field(name="タイムアウト", value="ON" if settings["timeout_enabled"] else "OFF", inline=True)
        embed.add_field(name="DM通知", value="ON" if settings["dm_notify"] else "OFF", inline=True)
        embed.add_field(
            name="検出条件",
            value=(
                f"{settings['window_seconds']}秒以内に\n"
                f"everyone/here: {settings['everyone_limit']}回\n"
                f"同一内容: {settings['repeat_limit']}回"
            ),
            inline=True,
        )
        embed.add_field(name="制限時間", value=f"{settings['timeout_minutes']}分", inline=True)
        return embed

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        permissions = message.author.guild_permissions
        if permissions.administrator or permissions.manage_messages:
            return

        settings = await self.load_settings(message.guild.id)
        if not settings["enabled"] or not message.content:
            return

        key = (message.guild.id, message.author.id)
        async with self._locks[key]:
            now = time.monotonic()
            events = self._events[key]
            window = int(settings["window_seconds"])
            while events and now - events[0][0] > window:
                events.popleft()

            signature = normalize_content(message.content)
            events.append((now, signature, message.mention_everyone, message))
            everyone_events = [event for event in events if event[2]]
            repeat_events = [event for event in events if signature and event[1] == signature]

            reason = None
            matched_events = []
            if message.mention_everyone and len(everyone_events) >= int(settings["everyone_limit"]):
                reason = f"{window}秒以内にeveryone/hereメンションを{len(everyone_events)}回送信"
                matched_events = everyone_events
            elif len(signature) >= 2 and len(repeat_events) >= int(settings["repeat_limit"]):
                reason = f"{window}秒以内に同じ内容を{len(repeat_events)}回送信"
                matched_events = repeat_events

            if not reason:
                return
            if self._sanctioned_until.get(key, 0) > now:
                if settings["delete_messages"]:
                    await self.delete_messages([message])
                return
            self._sanctioned_until[key] = now + window
            events.clear()

        deleted = 0
        if settings["delete_messages"]:
            deleted = await self.delete_messages([event[3] for event in matched_events])

        timeout_applied = False
        timeout_error = None
        if settings["timeout_enabled"]:
            me = message.guild.me
            if not me or not me.guild_permissions.moderate_members:
                timeout_error = "Botにタイムアウト権限がありません"
            elif message.author.top_role >= me.top_role:
                timeout_error = "対象メンバーのロールがBot以上です"
            else:
                try:
                    await message.author.timeout(
                        timedelta(minutes=int(settings["timeout_minutes"])),
                        reason=f"スパム自動検知: {reason}",
                    )
                    timeout_applied = True
                except (discord.Forbidden, discord.HTTPException) as exc:
                    timeout_error = str(exc)

        if settings["dm_notify"]:
            await self.notify_member(message, reason, deleted, timeout_applied, int(settings["timeout_minutes"]))
        await self.send_log(message, reason, deleted, timeout_applied, timeout_error)

    @staticmethod
    async def delete_messages(messages: list[discord.Message]) -> int:
        deleted = 0
        seen = set()
        for message in messages:
            if message.id in seen:
                continue
            seen.add(message.id)
            try:
                await message.delete()
                deleted += 1
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        return deleted

    @staticmethod
    async def notify_member(
        message: discord.Message,
        reason: str,
        deleted: int,
        timeout_applied: bool,
        timeout_minutes: int,
    ):
        lines = [f"サーバー「{message.guild.name}」でスパムを検知しました。", f"理由: {reason}"]
        if deleted:
            lines.append(f"削除されたメッセージ: {deleted}件")
        if timeout_applied:
            lines.append(f"タイムアウト: {timeout_minutes}分")
        try:
            await message.author.send("\n".join(lines))
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def send_log(
        self,
        message: discord.Message,
        reason: str,
        deleted: int,
        timeout_applied: bool,
        timeout_error: str | None,
    ):
        embed = discord.Embed(title="スパム自動検知", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="対象", value=f"{message.author} (`{message.author.id}`)", inline=False)
        embed.add_field(name="チャンネル", value=f"#{message.channel} (`{message.channel.id}`)", inline=False)
        embed.add_field(name="理由", value=reason, inline=False)
        embed.add_field(name="削除", value=f"{deleted}件", inline=True)
        timeout_value = "実施" if timeout_applied else (f"失敗: {timeout_error}" if timeout_error else "OFF")
        embed.add_field(name="タイムアウト", value=timeout_value[:1024], inline=True)
        embed.add_field(name="検出内容", value=(message.content or "なし")[:1000], inline=False)
        await send_server_log(self.bot, message.guild, embed, "moderation")

    @app_commands.command(name="spam_settings", description="【管理者】スパム防止機能を確認・設定します")
    @app_commands.describe(
        enabled="スパム防止機能のON/OFF",
        delete_messages="検出した連投メッセージを削除するか",
        timeout_enabled="検出したメンバーをタイムアウトするか",
        dm_notify="処分内容を本人へDMするか",
        everyone_limit="everyone/hereの検出回数（2～10回）",
        repeat_limit="同一内容の検出回数（2～15回）",
        window_seconds="監視する時間（5～300秒）",
        timeout_minutes="タイムアウト時間（1～40320分）",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def spam_settings(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        delete_messages: bool | None = None,
        timeout_enabled: bool | None = None,
        dm_notify: bool | None = None,
        everyone_limit: int | None = None,
        repeat_limit: int | None = None,
        window_seconds: int | None = None,
        timeout_minutes: int | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("「サーバーの管理」権限が必要です。", ephemeral=True)
            return

        ranges = {
            "everyone_limit": (everyone_limit, 2, 10),
            "repeat_limit": (repeat_limit, 2, 15),
            "window_seconds": (window_seconds, 5, 300),
            "timeout_minutes": (timeout_minutes, 1, 40320),
        }
        for label, (value, minimum, maximum) in ranges.items():
            if value is not None and not minimum <= value <= maximum:
                await interaction.response.send_message(
                    f"`{label}` は {minimum}～{maximum} の範囲で指定してください。",
                    ephemeral=True,
                )
                return

        settings = await self.load_settings(interaction.guild.id)
        updates = {
            "enabled": enabled,
            "delete_messages": delete_messages,
            "timeout_enabled": timeout_enabled,
            "dm_notify": dm_notify,
            "everyone_limit": everyone_limit,
            "repeat_limit": repeat_limit,
            "window_seconds": window_seconds,
            "timeout_minutes": timeout_minutes,
        }
        changed = False
        for key, value in updates.items():
            if value is not None:
                settings[key] = value
                changed = True
        if changed:
            await self.save_settings(interaction.guild.id, settings)
        await interaction.response.send_message(
            embed=self.settings_embed(settings),
            content="設定を保存しました。" if changed else None,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SpamGuard(bot))
