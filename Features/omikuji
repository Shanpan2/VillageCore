# features/omikuji.py

import discord
from discord.ext import commands
from discord import app_commands
import random


def setup_omikuji(bot: commands.Bot):

    @bot.tree.command(name="omikuji", description="おみくじを引きます")
    async def omikuji(interaction: discord.Interaction):

        fortunes = [
            ("🌟 大吉", "最高の運勢！今日は何をしても上手くいくかも。"),
            ("✨ 中吉", "良いことが起こりそうな予感。"),
            ("😊 小吉", "ちょっと良いことがあるかも。"),
            ("🙂 吉", "平和な一日になりそう。"),
            ("😌 末吉", "焦らずゆっくり進めると吉。"),
            ("⚠️ 凶", "注意が必要。落ち着いて行動しよう。"),
            ("💀 大凶", "今日は慎重に。無理は禁物。")
        ]

        result, message = random.choice(fortunes)

        embed = discord.Embed(
            title="🎴 おみくじ",
            description=f"**{result}**\n{message}",
            color=0xe67e22
        )

        await interaction.response.send_message(embed=embed)
