import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime

from database.config_db import db_get, db_set


class Omikuji(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="omikuji", description="おみくじを引きます")
    async def omikuji(self, interaction: discord.Interaction):
        today = datetime.date.today().isoformat()
        key = f"omikuji_last_{interaction.guild.id}_{interaction.user.id}"
        last_draw = await db_get(key)

        if last_draw == today:
            await interaction.response.send_message(
                "❌ 今日はすでにおみくじを引いています。明日になったらまた引いてください。",
                ephemeral=True,
            )
            return

        fortunes = [
            ("🌟 大吉", "最高の運勢！今日は何をしても上手くいくかも。"),
            ("✨ 中吉", "良いことが起こりそうな予感。"),
            ("😊 小吉", "ちょっと良いことがあるかも。"),
            ("🙂 吉", "平和な一日になりそう。"),
            ("😌 末吉", "焦らずゆっくり進めると吉。"),
            ("⚠️ 凶", "注意が必要。落ち着いて行動しよう。"),
            ("💀 大凶", "今日は慎重に。無理は禁物。"),
        ]

        result, message = random.choice(fortunes)
        await db_set(key, today)

        embed = discord.Embed(
            title="🎴 おみくじ",
            description=f"**{result}**\n{message}",
            color=0xE67E22,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Omikuji(bot))
