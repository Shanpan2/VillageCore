# features/role_panel.py

import discord
from discord import app_commands
from discord.ext import commands
from views.role_panel_views import RolePanelView


# ============================================================
# 🔐 管理者チェック（core.utils 不要）
# ============================================================

async def check_admin(interaction: discord.Interaction) -> bool:
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ このコマンドは管理者のみ使用できます。",
            ephemeral=True
        )
        return False
    return True


# ============================================================
# 🎛️ ロールパネル（分割構成用）
# ============================================================

def setup_role_panel(bot: commands.Bot):

    @bot.tree.command(name="role_panel_setup", description="【管理者】ロールパネルを設置します")
    @app_commands.describe(
        role="付与したいロール",
        title="パネルのタイトル",
        description="パネルの説明文"
    )
    async def role_panel_setup(
        interaction: discord.Interaction,
        role: discord.Role,
        title: str = "ロールパネル",
        description: str = "ボタンを押すとロールを付与 / 削除できます。"
    ):
        if not await check_admin(interaction):
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x3498db
        )

        view = RolePanelView(role.id)

        await interaction.response.send_message(embed=embed, view=view)

