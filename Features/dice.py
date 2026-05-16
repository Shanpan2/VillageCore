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

        # CCB check pattern: CCB<=数字 / CCB>=数字 / CCB<数字 / CCB>数字
        content = message.content.lower().strip()
        ccb_match = re.fullmatch(r"ccb\s*(<=|>=|<|>)\s*(\d+)", content)
        if ccb_match:
            comparator = ccb_match.group(1)
            difficulty = int(ccb_match.group(2))
            await self._handle_ccb_check(message, comparator, difficulty)
            return

        match = re.fullmatch(r"(\d*)d(\d+)", content)
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

    async def _handle_ccb_check(self, message: discord.Message, comparator: str, difficulty: int):
        """CCB (Custom Check Box) システム: CCB<= / CCB>= / CCB< / CCB> 形式"""
        roll = random.randint(1, 100)

        if difficulty < 1 or difficulty > 100:
            await message.reply("❌ CCB の難易度は 1〜100 の範囲で指定してください。")
            return

        result = f"**難易度: CCB{comparator}{difficulty}** に対して 1d100 をロール\n"
        result += f"**結果: {roll}**\n\n"
        color = 0x3498DB

        if roll <= CRITICAL_MAX:
            result += f"🌟 **クリティカル成功！** ({roll} ≦ {CRITICAL_MAX})\n最高の成功です！"
            color = 0xFFD700
        elif roll >= FUMBLE_MIN:
            result += f"💀 **ファンブル！** ({roll} ≧ {FUMBLE_MIN})\n最悪の失敗…"
            color = 0xFF0000
        else:
            if comparator == "<=":
                success = roll <= difficulty
                comparison = f"{roll} ≦ {difficulty}"
            elif comparator == "<":
                success = roll < difficulty
                comparison = f"{roll} < {difficulty}"
            elif comparator == ">=":
                success = roll >= difficulty
                comparison = f"{roll} ≧ {difficulty}"
            else:
                success = roll > difficulty
                comparison = f"{roll} > {difficulty}"

            if success:
                result += f"✅ **成功！** ({comparison})"
                color = 0x2ECC71
            else:
                result += f"❌ **失敗** ({comparison})"
                color = 0x95A5A6

        embed = discord.Embed(
            title="🎲 CCB 判定",
            description=result,
            color=color,
        )
        await message.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))
