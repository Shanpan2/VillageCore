import discord
from discord.ext import commands
import re
import random


class Dice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        match = re.fullmatch(r"(\d*)d(\d+)", message.content.lower())
        if not match:
            return

        times = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))

        if times < 1 or times > 50:
            await message.reply("❌ 回数は 1〜50 の範囲で指定してください。")
            return

        if sides < 2 or sides > 1000:
            await message.reply("❌ 面数は 2〜1000 の範囲で指定してください。")
            return

        rolls = [random.randint(1, sides) for _ in range(times)]
        total = sum(rolls)
        result_text = " + ".join(map(str, rolls))

        embed = discord.Embed(
            title="🎲 ダイスロール",
            description=f"**{times}d{sides}** の結果：\n{result_text} = **{total}**",
            color=0x3498DB,
        )
        await message.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))
