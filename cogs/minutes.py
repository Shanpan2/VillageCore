import asyncio
import io
import json
import os
from collections import Counter
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_set

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    genai = None
    types = None


MAX_MINUTES_MESSAGES = int(os.getenv("MINUTES_MAX_MESSAGES", "500"))
MAX_MINUTES_CHARS = int(os.getenv("MINUTES_MAX_CHARS", "12000"))


def minutes_session_key(guild_id: int, channel_id: int) -> str:
    return f"minutes_session:{guild_id}:{channel_id}"


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_from_raw(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and data.get("started_at") else None


def can_manage_minutes(interaction: discord.Interaction, session: dict | None = None) -> bool:
    if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_messages:
        return True
    if session and int(session.get("started_by", 0)) == interaction.user.id:
        return True
    return False


def split_text(text: str, limit: int = 1900) -> list[str]:
    chunks = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
                current = ""
        current = f"{current}\n{line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


class Minutes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.client = genai.Client(api_key=self.api_key) if genai and self.api_key else None

    async def get_session(self, guild_id: int, channel_id: int) -> dict | None:
        return session_from_raw(await db_get(minutes_session_key(guild_id, channel_id)))

    async def set_session(self, guild_id: int, channel_id: int, session: dict | None):
        value = json.dumps(session, ensure_ascii=False) if session else ""
        await db_set(minutes_session_key(guild_id, channel_id), value)

    async def collect_messages(self, channel: discord.TextChannel, started_at: datetime) -> list[discord.Message]:
        messages = []
        async for message in channel.history(
            limit=MAX_MINUTES_MESSAGES,
            after=started_at,
            oldest_first=True,
        ):
            if message.author.bot:
                continue
            if not message.content and not message.attachments:
                continue
            messages.append(message)
        return messages

    def build_source_text(self, messages: list[discord.Message]) -> tuple[str, Counter]:
        lines = []
        participants: Counter[str] = Counter()
        total_chars = 0
        for message in messages:
            name = getattr(message.author, "display_name", message.author.name)
            participants[name] += 1
            content = (message.content or "").replace("\n", " ").strip()
            if message.attachments:
                files = ", ".join(attachment.filename for attachment in message.attachments[:3])
                content = f"{content} [添付: {files}]".strip()
            line = f"[{message.created_at.astimezone(timezone.utc).strftime('%H:%M')}] {name}: {content}"
            if total_chars + len(line) > MAX_MINUTES_CHARS:
                break
            lines.append(line)
            total_chars += len(line)
        return "\n".join(lines), participants

    def fallback_summary(self, title: str, source: str, participants: Counter, message_count: int) -> str:
        participant_text = ", ".join(f"{name}({count})" for name, count in participants.most_common(12)) or "なし"
        excerpt = "\n".join(source.splitlines()[-20:])
        return (
            f"**議事録: {title}**\n"
            f"参加者: {participant_text}\n"
            f"記録メッセージ数: {message_count}\n\n"
            "**AI要約は利用できなかったため、直近ログを整理して出力します。**\n"
            "重要な結論・TODOは必要に応じて手動で追記してください。\n\n"
            "```text\n"
            f"{excerpt[:1400]}\n"
            "```"
        )

    def summarize_sync(self, title: str, source: str, participants: Counter, message_count: int) -> str:
        if not self.client or not types:
            return self.fallback_summary(title, source, participants, message_count)

        participant_text = ", ".join(f"{name}({count})" for name, count in participants.most_common(20))
        prompt = (
            "次のDiscordテキストチャンネルの会話ログを、日本語の議事録として整理してください。\n"
            "出力は短く見やすくしてください。\n\n"
            f"議題: {title}\n"
            f"参加者と発言数: {participant_text}\n"
            f"メッセージ数: {message_count}\n\n"
            "必要な構成:\n"
            "1. 要約\n"
            "2. 決まったこと\n"
            "3. 未決定・確認が必要なこと\n"
            "4. TODO（担当者が分かる場合は名前つき）\n"
            "5. 重要な発言メモ\n\n"
            "会話ログ:\n"
            f"{source}"
        )
        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1200,
        )
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        text = (getattr(response, "text", None) or "").strip()
        return text or self.fallback_summary(title, source, participants, message_count)

    async def summarize(self, title: str, source: str, participants: Counter, message_count: int) -> str:
        try:
            return await asyncio.to_thread(self.summarize_sync, title, source, participants, message_count)
        except Exception as e:
            print(f"[minutes summary error] {type(e).__name__}: {e}", flush=True)
            return self.fallback_summary(title, source, participants, message_count)

    @app_commands.command(name="minutes_start", description="このチャンネルで議事録の記録を開始します")
    @app_commands.describe(title="議題や話し合いの名前")
    async def minutes_start(self, interaction: discord.Interaction, title: str = "話し合い"):
        if not interaction.guild_id or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return

        existing = await self.get_session(interaction.guild_id, interaction.channel_id)
        if existing:
            await interaction.response.send_message(
                "このチャンネルではすでに議事録を記録中です。終了する場合は `/minutes_stop` を使ってください。",
                ephemeral=True,
            )
            return

        session = {
            "title": title.strip()[:100] or "話し合い",
            "started_by": interaction.user.id,
            "started_at": utc_now().isoformat(),
        }
        await self.set_session(interaction.guild_id, interaction.channel_id, session)
        await interaction.response.send_message(
            f"議事録を開始しました。\n議題: **{session['title']}**\n終了するときは `/minutes_stop` を実行してください。"
        )

    @app_commands.command(name="minutes_status", description="このチャンネルの議事録状態を確認します")
    async def minutes_status(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        session = await self.get_session(interaction.guild_id, interaction.channel_id)
        if not session:
            await interaction.response.send_message("このチャンネルでは議事録を記録していません。", ephemeral=True)
            return
        started_at = parse_utc(session.get("started_at"))
        started = started_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if started_at else "不明"
        await interaction.response.send_message(
            f"議事録を記録中です。\n議題: **{session.get('title', '話し合い')}**\n開始: `{started}`",
            ephemeral=True,
        )

    @app_commands.command(name="minutes_stop", description="議事録を終了し、自動で要約を出力します")
    async def minutes_stop(self, interaction: discord.Interaction):
        if not interaction.guild_id or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return
        session = await self.get_session(interaction.guild_id, interaction.channel_id)
        if not session:
            await interaction.response.send_message("このチャンネルでは議事録を記録していません。", ephemeral=True)
            return
        if not can_manage_minutes(interaction, session):
            await interaction.response.send_message("議事録を終了できるのは、開始した人かメッセージ管理権限を持つ人だけです。", ephemeral=True)
            return

        started_at = parse_utc(session.get("started_at"))
        if not started_at:
            await self.set_session(interaction.guild_id, interaction.channel_id, None)
            await interaction.response.send_message("開始時刻が壊れていたため、議事録をリセットしました。", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        messages = await self.collect_messages(interaction.channel, started_at)
        await self.set_session(interaction.guild_id, interaction.channel_id, None)

        if not messages:
            await interaction.followup.send("議事録を終了しました。記録対象の発言はありませんでした。")
            return

        title = session.get("title", "話し合い")
        source, participants = self.build_source_text(messages)
        summary = await self.summarize(title, source, participants, len(messages))
        header = f"**議事録を終了しました: {title}**\n記録メッセージ数: **{len(messages)}**\n\n"
        output = header + summary
        if len(output) <= 1900:
            await interaction.followup.send(output)
            return

        data = output.encode("utf-8")
        await interaction.followup.send(
            "議事録を終了しました。長くなったためテキストファイルで出力します。",
            file=discord.File(io.BytesIO(data), filename="minutes_summary.txt"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Minutes(bot))
