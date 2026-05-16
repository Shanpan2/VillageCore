import asyncio
import os
import re

import discord
from discord.ext import commands

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    genai = None
    types = None


MENTION_RE = re.compile(r"<@!?\d+>")


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
            print(
                "⚠️ AI chat disabled: GEMINI_API_KEY or GOOGLE_API_KEY is not set.",
                flush=True,
            )

    def build_prompt(self, message: discord.Message, question: str) -> str:
        display_name = getattr(message.author, "display_name", message.author.name)
        guild_name = message.guild.name if message.guild else "DM"
        return (
            f"Discord server: {guild_name}\n"
            f"User: {display_name}\n"
            f"Question:\n{question}"
        )

    def generate_reply(self, prompt: str) -> str:
        if not self.client:
            return "AI応答が未設定です。環境変数 `GEMINI_API_KEY` を設定してください。"

        config = types.GenerateContentConfig(
            system_instruction=(
                "あなたはDiscordサーバー内で動く親切な日本語アシスタントです。"
                "回答は簡潔で自然に。必要なら箇条書きを使ってください。"
                "不確かなことは断定せず、確認が必要だと伝えてください。"
            ),
            temperature=0.7,
            max_output_tokens=1000,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return (getattr(response, "text", None) or "").strip() or "すみません、うまく回答を生成できませんでした。"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user:
            return

        if self.bot.user not in message.mentions:
            return

        question = MENTION_RE.sub("", message.content).strip()
        if not question:
            await message.reply("質問内容も一緒に送ってください。例: `@Bot 今日の予定を整理して`")
            return

        async with message.channel.typing():
            try:
                prompt = self.build_prompt(message, question)
                reply = await asyncio.to_thread(self.generate_reply, prompt)
            except Exception as e:
                print(f"[ai_chat error] {type(e).__name__}: {e}", flush=True)
                await message.reply(f"❌ AI応答中にエラーが発生しました: {type(e).__name__}")
                return

        chunks = split_discord_message(reply)
        if chunks:
            await message.reply(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
