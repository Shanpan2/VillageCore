import discord
from discord.ext import commands
from discord import app_commands

from views.attendance_views import AttendanceView
from utils.checks import check_admin
from database.config_db import db_get_all_config


class Attendance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="attend_setup", description="【管理者】出席パネルを設置します")
    async def attend_setup(self, interaction: discord.Interaction):
        if not await check_admin(interaction):
            return

        embed = discord.Embed(
            title="📝 出席管理",
            description="ボタンを押して出席状況を登録してください。",
            color=0x2ECC71,
        )
        await interaction.response.send_message(
            embed=embed,
            view=AttendanceView(),
            ephemeral=True,
        )

    @app_commands.command(name="attend_list", description="【管理者】出席状況を一覧表示します")
    async def attend_list(self, interaction: discord.Interaction):
        if not await check_admin(interaction):
            return

        all_data = await db_get_all_config()

        lines = []
        for key, value in all_data.items():
            if key.startswith("attendance_"):
                user_id = key.replace("attendance_", "")
                if user_id.isdigit():
                    lines.append(f"<@{user_id}>：{value}")

        if not lines:
            await interaction.response.send_message(
                "📭 出席データはまだありません。", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📝 出席一覧",
            description="\n".join(lines),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Attendance(bot))
