import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="remind")
    async def remind(self, ctx, time_str: str, *, message: str):
        """
        リマインダー:
        /remind 18:30 宿題しろ
        /remind 2026-05-14 18:30 会議
        /remind 10m 水飲め
        """

        # -------------------------
        # ① 相対時間（10m, 2h, 30s）
        # -------------------------
        if any(x in time_str for x in ["s", "m", "h"]):
            seconds = self.parse_relative(time_str)
            if seconds <= 0:
                await ctx.send("❌ 時間指定が正しくありません。")
                return

            await ctx.send(f"⏰ {time_str} 後にリマインドします。")
            await asyncio.sleep(seconds)

            await ctx.send(f"🔔 リマインダー: {ctx.author.mention} {message}")
            return

        # -------------------------
        # ② 絶対時間（18:30）
        # -------------------------
        if ":" in time_str and "-" not in time_str:
            now = datetime.now()
            hour, minute = map(int, time_str.split(":"))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # すでに過ぎていたら明日
            if target < now:
                target += timedelta(days=1)

            seconds = (target - now).total_seconds()

            await ctx.send(f"⏰ {target.strftime('%Y-%m-%d %H:%M')} にリマインドします。")
            await asyncio.sleep(seconds)

            await ctx.send(f"🔔 リマインダー: {ctx.author.mention} {message}")
            return

        # -------------------------
        # ③ 日付＋時間（2026-05-14 18:30）
        # -------------------------
        try:
            target = datetime.strptime(time_str, "%Y-%m-%d")
            # 時間がない場合は 00:00
            target = target.replace(hour=0, minute=0, second=0)
        except:
            try:
                target = datetime.strptime(time_str, "%Y-%m-%d_%H:%M")
            except:
                try:
                    target = datetime.strptime(time_str, "%Y-%m-%d-%H:%M")
                except:
                    await ctx.send("❌ 時間形式が正しくありません。")
                    return

        now = datetime.now()
        seconds = (target - now).total_seconds()

        if seconds <= 0:
            await ctx.send("❌ 過去の時間は指定できません。")
            return

        await ctx.send(f"⏰ {target.strftime('%Y-%m-%d %H:%M')} にリマインドします。")
        await asyncio.sleep(seconds)

        await ctx.send(f"🔔 リマインダー: {ctx.author.mention} {message}")

    # -------------------------
    # 相対時間の解析（10m → 600秒）
    # -------------------------
    def parse_relative(self, t: str):
        sec = 0
        num = ""
        for c in t:
            if c.isdigit():
                num += c
            else:
                if c == "s":
                    sec += int(num)
                elif c == "m":
                    sec += int(num) * 60
                elif c == "h":
                    sec += int(num) * 3600
                num = ""
        return sec


async def setup(bot):
    await bot.add_cog(Reminder(bot))


