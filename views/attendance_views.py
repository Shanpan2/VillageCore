# views/attendance_views.py

import discord
from database.config_db import db_set


# ============================================================
# 📝 出席管理ボタン
# ============================================================

class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 出席", style=discord.ButtonStyle.success, custom_id="attend_present")
    async def attend_present(self, inter: discord.Interaction, button: discord.ui.Button):
        await save_attendance(inter, "出席")

    @discord.ui.button(label="🟡 遅刻", style=discord.ButtonStyle.secondary, custom_id="attend_late")
    async def attend_late(self, inter: discord.Interaction, button: discord.ui.Button):
        await save_attendance(inter, "遅刻")

    @discord.ui.button(label="🔴 欠席", style=discord.ButtonStyle.danger, custom_id="attend_absent")
    async def attend_absent(self, inter: discord.Interaction, button: discord.ui.Button):
        await save_attendance(inter, "欠席")


async def save_attendance(inter: discord.Interaction, status: str):
    key = f"attendance_{inter.user.id}"
    await db_set(key, status)

    await inter.response.send_message(
        f"📝 {inter.user.mention} の出席状況を **{status}** に更新しました。",
        ephemeral=True,
    )
