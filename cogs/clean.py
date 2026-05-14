import discord
from discord.ext import commands
from discord import app_commands

class Clean(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="clean", description="指定した数のメッセージを削除します")
    @app_commands.describe(amount="削除するメッセージ数")
    async def clean(self, interaction: discord.Interaction, amount: int):
        """Slash Command 版 clean"""
        # 権限チェック
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ メッセージ管理権限が必要です。", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ 1以上の数字を指定してください。", ephemeral=True)
            return

        # コマンドの応答（遅延応答）
        await interaction.response.defer(ephemeral=True)

        deleted = await interaction.channel.purge(limit=amount)

        await interaction.followup.send(
            f"🧹 {len(deleted)} 件のメッセージを削除しました。",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Clean(bot))
