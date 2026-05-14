import discord
from discord import app_commands
from discord.ext import commands
from views.role_panel_views import RolePanelView


class RolePanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="role_panel_setup", description="【管理者】ロールパネルを設置します")
    @app_commands.describe(
        role="付与したいロール",
        title="パネルのタイトル",
        description="パネルの説明文",
    )
    @app_commands.default_permissions(administrator=True)
    async def role_panel_setup(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        title: str = "ロールパネル",
        description: str = "ボタンを押すとロールを付与 / 削除できます。",
    ):
        embed = discord.Embed(
            title=title,
            description=description,
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, view=RolePanelView(role.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(RolePanel(bot))
