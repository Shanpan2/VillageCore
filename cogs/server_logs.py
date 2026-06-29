import json
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_set


def log_channel_key(guild_id: int) -> str:
    return f"server_log_channel:{guild_id}"


def log_settings_key(guild_id: int) -> str:
    return f"server_log_settings:{guild_id}"


LOG_CATEGORIES = {
    "message": "メッセージ編集/削除",
    "command_delete": "コマンド削除",
    "member": "参加/退出",
    "moderation": "Kick/BAN",
    "voice_join_leave": "VC入室/退出/移動",
    "voice_state": "VCミュート等",
    "role_channel": "ロール/チャンネル",
}
DEFAULT_LOG_SETTINGS = {key: True for key in LOG_CATEGORIES}
COMMAND_DELETED_MESSAGE_IDS: set[int] = set()


def mark_command_deleted_messages(messages: list[discord.Message]):
    COMMAND_DELETED_MESSAGE_IDS.update(message.id for message in messages)


def unmark_command_deleted_messages(messages: list[discord.Message]):
    for message in messages:
        COMMAND_DELETED_MESSAGE_IDS.discard(message.id)


async def load_log_settings(guild_id: int) -> dict[str, bool]:
    raw = await db_get(log_settings_key(guild_id))
    if not raw:
        return DEFAULT_LOG_SETTINGS.copy()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_LOG_SETTINGS.copy()
    settings = DEFAULT_LOG_SETTINGS.copy()
    if isinstance(data, dict):
        for key in settings:
            if key in data:
                settings[key] = bool(data[key])
        if "voice" in data:
            settings["voice_join_leave"] = bool(data["voice"])
            settings["voice_state"] = bool(data["voice"])
    return settings


async def save_log_settings(guild_id: int, settings: dict[str, bool]):
    normalized = {key: bool(settings.get(key, True)) for key in LOG_CATEGORIES}
    await db_set(log_settings_key(guild_id), json.dumps(normalized, ensure_ascii=False))


async def is_log_enabled(guild_id: int, category: str | None) -> bool:
    if category is None:
        return True
    settings = await load_log_settings(guild_id)
    return settings.get(category, True)


async def send_server_log(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed, category: str | None = None):
    if not await is_log_enabled(guild.id, category):
        return
    raw = await db_get(log_channel_key(guild.id))
    if not raw:
        return
    try:
        channel_id = int(raw)
    except (TypeError, ValueError):
        return
    channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[ServerLog] failed to send log to channel {channel_id}: {type(e).__name__}: {e}", flush=True)


def log_settings_embed(settings: dict[str, bool]) -> discord.Embed:
    embed = discord.Embed(
        title="ログ種別設定",
        description="有効にするログ種別を選択してください。チェックを外した種類はサーバーログに送信されません。",
        color=0x3498DB,
    )
    for key, label in LOG_CATEGORIES.items():
        embed.add_field(name=label, value="ON" if settings.get(key, True) else "OFF", inline=True)
    return embed


def message_matches_log_search(message: discord.Message, keyword: str) -> bool:
    needle = keyword.lower()
    parts = [message.content or ""]
    for embed in message.embeds:
        parts.append(embed.title or "")
        parts.append(embed.description or "")
        for field in embed.fields:
            parts.append(field.name)
            parts.append(field.value)
    return needle in "\n".join(parts).lower()


def describe_log_message(message: discord.Message) -> str:
    title = "ログ"
    detail = message.content or ""
    if message.embeds:
        embed = message.embeds[0]
        title = embed.title or title
        if embed.description:
            detail = embed.description
        elif embed.fields:
            field = embed.fields[0]
            detail = f"{field.name}: {field.value}"
    detail = detail.replace("\n", " ").strip() or "内容なし"
    timestamp = message.created_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] [{title}] {detail[:140]}\n{message.jump_url}"


class LogCategorySelect(discord.ui.Select):
    def __init__(self, settings: dict[str, bool]):
        options = [
            discord.SelectOption(label=label, value=key, default=settings.get(key, True))
            for key, label in LOG_CATEGORIES.items()
        ]
        super().__init__(
            placeholder="ONにするログ種別を選択",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id="server_log_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("サーバー管理権限が必要です。", ephemeral=True)
            return

        selected = set(self.values)
        settings = {key: key in selected for key in LOG_CATEGORIES}
        await save_log_settings(interaction.guild_id, settings)
        await interaction.response.edit_message(embed=log_settings_embed(settings), view=LogSettingsView(settings))


class LogSettingsView(discord.ui.View):
    def __init__(self, settings: dict[str, bool]):
        super().__init__(timeout=180)
        self.add_item(LogCategorySelect(settings))


class ServerLogs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        raw = await db_get(log_channel_key(guild.id))
        if not raw:
            return None
        channel = guild.get_channel(int(raw))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        await send_server_log(self.bot, guild, embed)

    @app_commands.command(name="server_log_channel", description="【管理者】サーバーログの送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def server_log_channel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await db_set(log_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"サーバーログ送信先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="log_panel", description="【管理者】サーバーログの種別ON/OFFを設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def log_panel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await load_log_settings(interaction.guild_id)
        await interaction.response.send_message(embed=log_settings_embed(settings), view=LogSettingsView(settings), ephemeral=True)

    @app_commands.command(name="log_search", description="【管理者】サーバーログチャンネル内を検索します")
    @app_commands.describe(keyword="検索したい文字", limit="確認するログ件数。最大300件です")
    @app_commands.default_permissions(manage_guild=True)
    async def log_search(self, interaction: discord.Interaction, keyword: str, limit: int = 100):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        channel = await self.get_log_channel(interaction.guild)
        if not channel:
            await interaction.response.send_message("先に `/server_log_channel` でログ送信先を設定してください。", ephemeral=True)
            return

        limit = max(1, min(limit, 300))
        keyword = keyword.strip()
        if not keyword:
            await interaction.response.send_message("検索文字を入力してください。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        results = []
        try:
            async for message in channel.history(limit=limit):
                if message_matches_log_search(message, keyword):
                    results.append(message)
                    if len(results) >= 10:
                        break
        except discord.Forbidden:
            await interaction.followup.send("Botにログチャンネルの履歴を読む権限がありません。", ephemeral=True)
            return

        if not results:
            await interaction.followup.send(f"`{keyword}` に一致するログは見つかりませんでした。", ephemeral=True)
            return

        embed = discord.Embed(title="ログ検索結果", color=0x3498DB)
        embed.description = f"検索: `{keyword}` / 確認: 最新 {limit}件 / 表示: {len(results)}件"
        for index, message in enumerate(results, start=1):
            embed.add_field(name=f"結果 {index}", value=describe_log_message(message)[:1024], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.id in COMMAND_DELETED_MESSAGE_IDS:
            COMMAND_DELETED_MESSAGE_IDS.discard(message.id)
            return
        embed = discord.Embed(title="メッセージ削除", color=0xE74C3C)
        embed.add_field(name="投稿者", value=f"{message.author.mention} ({message.author.id})", inline=False)
        embed.add_field(name="チャンネル", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="内容", value=message.content[:1000], inline=False)
        await send_server_log(self.bot, message.guild, embed, "message")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="メッセージ編集", color=0xF1C40F)
        embed.add_field(name="投稿者", value=f"{before.author.mention} ({before.author.id})", inline=False)
        embed.add_field(name="チャンネル", value=before.channel.mention, inline=True)
        embed.add_field(name="編集前", value=(before.content or "なし")[:800], inline=False)
        embed.add_field(name="編集後", value=(after.content or "なし")[:800], inline=False)
        await send_server_log(self.bot, before.guild, embed, "message")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title="メンバー参加", description=f"{member.mention} ({member.id})", color=0x2ECC71)
        await send_server_log(self.bot, member.guild, embed, "member")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        executor = None
        reason = None
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id and datetime.now(timezone.utc) - entry.created_at < timedelta(seconds=20):
                    executor = entry.user
                    reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if executor:
            embed = discord.Embed(title="メンバーKick", description=f"{member} ({member.id})", color=0xE74C3C)
            embed.add_field(name="実行者", value=f"{executor} ({executor.id})", inline=False)
            if reason:
                embed.add_field(name="理由", value=reason[:1000], inline=False)
            await send_server_log(self.bot, member.guild, embed, "moderation")
            return

        embed = discord.Embed(title="メンバー退出", description=f"{member} ({member.id})", color=0x95A5A6)
        await send_server_log(self.bot, member.guild, embed, "member")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        executor = None
        reason = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == user.id and datetime.now(timezone.utc) - entry.created_at < timedelta(seconds=20):
                    executor = entry.user
                    reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = discord.Embed(title="メンバーBAN", description=f"{user} ({user.id})", color=0xC0392B)
        if executor:
            embed.add_field(name="実行者", value=f"{executor} ({executor.id})", inline=False)
        if reason:
            embed.add_field(name="理由", value=reason[:1000], inline=False)
        await send_server_log(self.bot, guild, embed, "moderation")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="メンバーBAN解除", description=f"{user} ({user.id})", color=0x2ECC71)
        await send_server_log(self.bot, guild, embed, "moderation")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        before_channel = before.channel
        after_channel = after.channel
        if before_channel == after_channel:
            changes = []
            if before.self_mute != after.self_mute:
                changes.append("セルフミュートON" if after.self_mute else "セルフミュートOFF")
            if before.self_deaf != after.self_deaf:
                changes.append("セルフスピーカーミュートON" if after.self_deaf else "セルフスピーカーミュートOFF")
            if before.mute != after.mute:
                changes.append("サーバーミュートON" if after.mute else "サーバーミュートOFF")
            if before.deaf != after.deaf:
                changes.append("サーバースピーカーミュートON" if after.deaf else "サーバースピーカーミュートOFF")
            if not changes:
                return
            embed = discord.Embed(title="VC状態変更", color=0xF1C40F)
            embed.add_field(name="メンバー", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="チャンネル", value=after_channel.mention if after_channel else "不明", inline=True)
            embed.add_field(name="変更", value=", ".join(changes), inline=False)
            await send_server_log(self.bot, member.guild, embed, "voice_state")
            return

        if before_channel is None and after_channel is not None:
            title = "VC入室"
            color = 0x2ECC71
            detail = after_channel.mention
        elif before_channel is not None and after_channel is None:
            title = "VC退出"
            color = 0x95A5A6
            detail = before_channel.mention
        else:
            title = "VC移動"
            color = 0x3498DB
            detail = f"{before_channel.mention} → {after_channel.mention}"

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="メンバー", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="チャンネル", value=detail, inline=False)
        await send_server_log(self.bot, member.guild, embed, "voice_join_leave")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await send_server_log(self.bot, role.guild, discord.Embed(title="ロール作成", description=role.mention, color=0x3498DB), "role_channel")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await send_server_log(self.bot, role.guild, discord.Embed(title="ロール削除", description=role.name, color=0xE67E22), "role_channel")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await send_server_log(self.bot, channel.guild, discord.Embed(title="チャンネル作成", description=channel.mention, color=0x3498DB), "role_channel")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await send_server_log(self.bot, channel.guild, discord.Embed(title="チャンネル削除", description=channel.name, color=0xE67E22), "role_channel")


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogs(bot))
