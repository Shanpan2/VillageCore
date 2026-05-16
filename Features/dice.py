import discord
from discord.ext import commands
import re
import random


# 1d100 専用の判定閾値
CRITICAL_MAX = 5    # 1〜5: クリティカル
FUMBLE_MIN = 96     # 96〜100: ファンブル


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

        # 1d100 のみクリティカル/ファンブル判定
        special = None
        color = 0x3498DB

        if times == 1 and sides == 100:
            value = rolls[0]
            if value <= CRITICAL_MAX:
                special = f"🌟 **クリティカル！** ({value} ≦ {CRITICAL_MAX})\n最高の成功！"
                color = 0xFFD700
            elif value >= FUMBLE_MIN:
                special = f"💀 **ファンブル！** ({value} ≧ {FUMBLE_MIN})\n最悪の失敗…"
                color = 0xFF0000
            elif value <= 50:
                special = f"✅ **成功** ({value})"
                color = 0x2ECC71
            else:
                special = f"❌ **失敗** ({value})"
                color = 0x95A5A6

        desc = f"**{times}d{sides}** の結果：\n{result_text} = **{total}**"
        if special:
            desc += f"\n\n{special}"

        embed = discord.Embed(
            title="🎲 ダイスロール",
            description=desc,
            color=color,
        )
        await message.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))
