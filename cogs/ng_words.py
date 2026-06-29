import json

import discord
from discord import app_commands
from discord.ext import commands

from cogs.server_logs import log_channel_key
from database.config_db import db_get, db_set


def ng_words_key(guild_id: int) -> str:
    return f"ng_words:{guild_id}"


def normalize_word(word: str) -> str:
    return word.strip().lower()


class NgWords(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def load_words(self, guild_id: int) -> list[str]:
        raw = await db_get(ng_words_key(guild_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    async def save_words(self, guild_id: int, words: list[str]):
        cleaned = []
        seen = set()
        for word in words:
            normalized = normalize_word(word)
            if not normalized or normalized in seen:
                continue
            cleaned.append(normalized)
            seen.add(normalized)
        await db_set(ng_words_key(guild_id), json.dumps(cleaned[:200], ensure_ascii=False))

    async def send_moderation_log(self, message: discord.Message, matched: str):
        if not message.guild:
            return
        raw = await db_get(log_channel_key(message.guild.id))
        if not raw:
            return
        channel = message.guild.get_channel(int(raw))
        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(title="NGワード検知", color=0xE74C3C)
        embed.add_field(name="投稿者", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="チャンネル", value=message.channel.mention, inline=True)
        embed.add_field(name="検知ワード", value=f"`{matched}`", inline=True)
        embed.add_field(name="内容", value=(message.content or "なし")[:1000], inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"[NGWords] moderation log send failed: {type(e).__name__}: {e}", flush=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if isinstance(message.author, discord.Member):
            perms = message.author.guild_permissions
            if perms.administrator or perms.manage_messages:
                return

        words = await self.load_words(message.guild.id)
        if not words or not message.content:
            return

        lowered = message.content.lower()
        matched = next((word for word in words if word in lowered), None)
        if not matched:
            return

        try:
            await message.delete()
        except discord.HTTPException as e:
            print(f"[NGWords] message delete failed: {type(e).__name__}: {e}", flush=True)

        try:
            await message.channel.send(
                f"{message.author.mention} NGワードが含まれていたため削除しました。",
                delete_after=8,
            )
        except discord.HTTPException as e:
            print(f"[NGWords] notification send failed: {type(e).__name__}: {e}", flush=True)

        await self.send_moderation_log(message, matched)

    @app_commands.command(name="ng_word_add", description="【管理者】NGワードを追加します")
    @app_commands.describe(word="追加するNGワード")
    @app_commands.default_permissions(manage_messages=True)
    async def add_word(self, interaction: discord.Interaction, word: str):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        normalized = normalize_word(word)
        if not normalized:
            await interaction.response.send_message("ワードを入力してください。", ephemeral=True)
            return
        words = await self.load_words(interaction.guild_id)
        if normalized not in words:
            words.append(normalized)
            await self.save_words(interaction.guild_id, words)
        await interaction.response.send_message(f"NGワードを追加しました: `{normalized}`", ephemeral=True)

    @app_commands.command(name="ng_word_remove", description="【管理者】NGワードを削除します")
    @app_commands.describe(word="削除するNGワード")
    @app_commands.default_permissions(manage_messages=True)
    async def remove_word(self, interaction: discord.Interaction, word: str):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        normalized = normalize_word(word)
        words = await self.load_words(interaction.guild_id)
        if normalized in words:
            words.remove(normalized)
            await self.save_words(interaction.guild_id, words)
            await interaction.response.send_message(f"NGワードを削除しました: `{normalized}`", ephemeral=True)
            return
        await interaction.response.send_message("そのNGワードは登録されていません。", ephemeral=True)

    @app_commands.command(name="ng_word_list", description="登録済みNGワードを表示します")
    @app_commands.default_permissions(manage_messages=True)
    async def list_words(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        words = await self.load_words(interaction.guild_id)
        if not words:
            await interaction.response.send_message("NGワードは登録されていません。", ephemeral=True)
            return
        text = "\n".join(f"- `{word}`" for word in words[:100])
        await interaction.response.send_message(f"登録済みNGワード:\n{text}", ephemeral=True)

    @app_commands.command(name="ng_word_clear", description="【管理者】NGワードを全削除します")
    @app_commands.default_permissions(administrator=True)
    async def clear_words(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await self.save_words(interaction.guild_id, [])
        await interaction.response.send_message("NGワードを全削除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(NgWords(bot))
