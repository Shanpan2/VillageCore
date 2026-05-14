# features/dice.py

import discord
from discord.ext import commands
import re
import random


def setup_dice(bot: commands.Bot):

    @bot.event
    async def on_message(message: discord.Message):

        # bot 自身には反応しない
        if message.author.bot:
            return

        # XdY 形式を検出（例：2d6, 1d100, d20）
        match = re.fullmatch(r"(\d*)d(\d+)", message.content.lower())
        if not match:
            return

        # X（回数）
        times = int(match.group(1)) if match.group(1) else 1
        # Y（面数）
        sides = int(match.group(2))

        # 制限
        if times < 1 or times > 50:
            await message.reply("❌ 回数は 1〜50 の範囲で指定してください。")
            return

        if sides < 2 or sides > 1000:
            await message.reply("❌ 面数は 2〜1000 の範囲で指定してください。")
            return

        # ダイスロール
        rolls = [random.randint(1, sides) for _ in range(times)]
        total = sum(rolls)

        # 結果メッセージ
        result_text = " + ".join(map(str, rolls))

        embed = discord.Embed(
            title="🎲 ダイスロール",
            description=f"**{times}d{sides}** の結果：\n{result_text} = **{total}**",
            color=0x3498db
        )

        await message.reply(embed=embed)
