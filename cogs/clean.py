import discord
from discord.ext import commands

class Clean(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clean")
    @commands.has_permissions(manage_messages=True)
    async def clean(self, ctx, amount: int):
        """指定した数のメッセージを削除します"""
        if amount <= 0:
            await ctx.send("❌ 1以上の数字を指定してください。", delete_after=5)
            return

        deleted = await ctx.channel.purge(limit=amount + 1)

        await ctx.send(
            f"🧹 {len(deleted) - 1} 件のメッセージを削除しました。",
            delete_after=5
        )

async def setup(bot):   # ← ★ここが重要（async）
    await bot.add_cog(Clean(bot))


