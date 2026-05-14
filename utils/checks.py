# utils/checks.py

import discord

async def check_admin(interaction: discord.Interaction) -> bool:
    """管理者権限を持っているか確認"""
    if interaction.user.guild_permissions.administrator:
        return True

    await interaction.response.send_message(
        "❌ このコマンドは管理者のみ使用できます。",
        ephemeral=True
    )
    return False
