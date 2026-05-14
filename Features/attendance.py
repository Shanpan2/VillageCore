import discord
from discord import app_commands
from discord.ext import commands

from views.attendance_views import AttendanceView
from utils.checks import check_admin
from database.config_db import db_get_all_config


def setup_attendance(bot: commands.Bot):

    @bot.tree.command(name="attend_setup", description="【管理者】出席パネルを設置します")
    async def attend_setup(interaction: discord.Interaction):

        if not await check_admin(interaction):
            return

        embed = discord.Embed(
            title="📝 出席管理",
            description="ボタンを押して出席状況を登録してください。",
            color=0x2ecc71
        )

        await interaction.response.send_message(
            embed=embed,
            view=AttendanceView(),
            ephemeral=True  # 管理者向けなので非公開推奨
        )

    @bot.tree.command(name="attend_list", description="【管理者】出席状況を一覧表示します")
    async def attend_list(interaction: discord.Interaction):

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
            await interaction.response.send_message("📭 出席データはまだありません。", ephemeral=True)
            return

        text = "\n".join(lines)

        embed = discord.Embed(
            title="📝 出席一覧",
            description=text,
            color=0x3498db
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


