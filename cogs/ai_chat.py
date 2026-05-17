import asyncio
import json
import os
import re
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


MENTION_RE = re.compile(r"<@!?\d+>")
MAX_HISTORY_TURNS = 10


def sanitize_error_text(text: str, api_key: str | None = None) -> str:
    if api_key:
        text = text.replace(api_key, "***")
    return text[:700]


def user_friendly_ai_error(error: Exception, api_key: str | None = None) -> str:
    detail = sanitize_error_text(str(error), api_key)
    status = getattr(error, "code", None) or getattr(error, "status_code", None)

    if status in (401, 403):
        reason = "APIキー、Gemini APIの有効化、またはプロジェクト権限を確認してください。"
    elif status == 404:
        reason = "指定しているGeminiモデル名が使えない可能性があります。`GEMINI_MODEL` を確認してください。"
    elif status == 429:
        reason = "Gemini APIの利用制限、短時間の呼び出し過多、または無料枠上限の可能性があります。"
    elif status and 400 <= int(status) < 500:
        reason = "Gemini APIへのリクエスト内容、キー、モデル、利用制限のいずれかで拒否されています。"
    elif status and int(status) >= 500:
        reason = "Gemini API側の一時的な障害、または通信失敗の可能性があります。"
    else:
        reason = "Gemini APIへの接続または応答生成で失敗しています。Railwayログの詳細も確認してください。"

    if detail:
        return f"{reason}\n詳細: `{detail}`"
    return reason


def memory_key(guild_id: int | None, user_id: int) -> str:
    scope = guild_id if guild_id is not None else "dm"
    return f"ai_memory:{scope}:{user_id}"


def split_discord_message(text: str, limit: int = 1900) -> list[str]:
    chunks = []
    current = ""
    for line in text.splitlines() or [text]:
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
        current = f"{current}\n{line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=self.api_key) if genai and self.api_key else None

    async def cog_load(self):
        if not self.client:
            print("AI chat disabled: GEMINI_API_KEY or GOOGLE_API_KEY is not set.", flush=True)

    async def load_memory(self, guild_id: int | None, user_id: int) -> list[dict]:
        raw = await db_get(memory_key(guild_id, user_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    async def save_memory(self, guild_id: int | None, user_id: int, history: list[dict]):
        await db_set(memory_key(guild_id, user_id), json.dumps(history[-MAX_HISTORY_TURNS:], ensure_ascii=False))

    def build_prompt(self, message: discord.Message, question: str, history: list[dict]) -> str:
        display_name = getattr(message.author, "display_name", message.author.name)
        guild_name = message.guild.name if message.guild else "DM"
        history_lines = []
        for item in history[-MAX_HISTORY_TURNS:]:
            user_text = item.get("user", "")
            assistant_text = item.get("assistant", "")
            if user_text:
                history_lines.append(f"User: {user_text}")
            if assistant_text:
                history_lines.append(f"Assistant: {assistant_text}")

        history_text = "\n".join(history_lines) if history_lines else "No previous conversation."
        return (
            f"Discord server: {guild_name}\n"
            f"User: {display_name}\n\n"
            f"Recent conversation with this user:\n{history_text}\n\n"
            f"Current question:\n{question}"
        )

    def generate_reply(self, prompt: str) -> str:
        if not self.client:
            return "AI応答が未設定です。環境変数 `GEMINI_API_KEY` を設定してください。"

        config = types.GenerateContentConfig(
            system_instruction=(
                "あなたはDiscordサーバー内で動く親切な日本語アシスタントです。"
                "会話履歴を参考にしつつ、簡潔で自然に答えてください。"
                "不確かなことは断定せず、確認が必要だと伝えてください。"
            ),
            temperature=0.7,
            max_output_tokens=1000,
        )
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        return (getattr(response, "text", None) or "").strip() or "すみません、うまく回答を生成できませんでした。"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user:
            return

        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = False
        if message.reference:
            replied_message = message.reference.resolved
            if not isinstance(replied_message, discord.Message) and message.reference.message_id:
                try:
                    replied_message = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    replied_message = None
            if isinstance(replied_message, discord.Message):
                is_reply_to_bot = replied_message.author.id == self.bot.user.id

        if not is_mentioned and not is_reply_to_bot:
            return

        question = MENTION_RE.sub("", message.content).strip()
        if not question:
            await message.reply("質問内容も一緒に送ってください。例: `@Bot 今日の予定を整理して`")
            return

        async with message.channel.typing():
            try:
                history = await self.load_memory(message.guild.id if message.guild else None, message.author.id)
                prompt = self.build_prompt(message, question, history)
                reply = await asyncio.to_thread(self.generate_reply, prompt)
                history.append(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "user": question[:1000],
                        "assistant": reply[:1500],
                    }
                )
                await self.save_memory(message.guild.id if message.guild else None, message.author.id, history)
            except Exception as e:
                detail = sanitize_error_text(str(e), self.api_key)
                print(f"[ai_chat error] {type(e).__name__}: {detail}", flush=True)
                await message.reply(f"AI応答中にエラーが発生しました: {type(e).__name__}\n{user_friendly_ai_error(e, self.api_key)}")
                return

        chunks = split_discord_message(reply)
        if chunks:
            await message.reply(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)

    @app_commands.command(name="ai_memory_clear", description="自分のAI会話履歴を削除します")
    async def ai_memory_clear(self, interaction: discord.Interaction):
        await db_set(memory_key(interaction.guild_id, interaction.user.id), "[]")
        await interaction.response.send_message("AI会話履歴を削除しました。", ephemeral=True)

    @app_commands.command(name="ai_memory_status", description="自分のAI会話履歴の保存件数を表示します")
    async def ai_memory_status(self, interaction: discord.Interaction):
        history = await self.load_memory(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"保存されている会話履歴: {len(history)}件", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
