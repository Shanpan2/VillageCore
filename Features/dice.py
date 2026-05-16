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

        # CCB check pattern: "CCB<=<number>"
        ccb_match = re.fullmatch(r"ccb<=(\d+)", message.content.lower())
        if ccb_match:
            await self._handle_ccb_check(message, int(ccb_match.group(1)))
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

    async def _handle_ccb_check(self, message: discord.Message, difficulty: int):
        """CCB (Custom Check Box) システム: CCB<=<number> 形式
        - 1d100 をロール
        - ロール値 ≤ 難易度値で成功
        - 1-5: クリティカル成功
        - 96-100: ファンブル失敗
        """
        roll = random.randint(1, 100)
        
        # 難易度の妥当性チェック
        if difficulty < 1 or difficulty > 100:
            await message.reply("❌ CCB の難易度は 1〜100 の範囲で指定してください。")
            return
        
        # 結果の判定
        title = "🎲 CCB 判定"
        desc = f"**難易度: {difficulty}** に対して 1d100 をロール\n"
        desc += f"**結果: {roll}**\n\n"
        
        color = 0x3498DB
        
        if roll <= 5:
            desc += f"🌟 **クリティカル成功！** ({roll} ≦ 5)\n最高の成功です！"
            color = 0xFFD700
        elif roll >= 96:
            desc += f"💀 **ファンブル！** ({roll} ≧ 96)\n最悪の失敗…"
            color = 0xFF0000
        elif roll <= difficulty:
            desc += f"✅ **成功！** ({roll} ≦ {difficulty})"
            color = 0x2ECC71
        else:
            desc += f"❌ **失敗** ({roll} > {difficulty})"
            color = 0x95A5A6
        
        embed = discord.Embed(
            title=title,
            description=desc,
            color=color,
        )
        await message.reply(embed=embed)
