import json

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_set
from views.role_panel_views import RolePanelView, role_panel_key


def collect_roles(*roles: discord.Role | None) -> list[discord.Role]:
    result = []
    seen = set()
    for role in roles:
        if role is None or role.id in seen:
            continue
        result.append(role)
        seen.add(role.id)
    return result


class RolePanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="role_panel_setup", description="【管理者】複数ロール対応の役職パネルを設置します")
    @app_commands.describe(
        role1="設定するロール 1",
        role2="設定するロール 2",
        role3="設定するロール 3",
        role4="設定するロール 4",
        role5="設定するロール 5",
        title="パネルのタイトル",
        description="パネルの説明文",
    )
    @app_commands.default_permissions(administrator=True)
    async def role_panel_setup(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
        role4: discord.Role | None = None,
        role5: discord.Role | None = None,
        title: str = "役職パネル",
        description: str = "メニューからロールを選ぶと、付与/解除できます。",
    ):
        roles = collect_roles(role1, role2, role3, role4, role5)
        role_ids = [role.id for role in roles]
        role_names = {role.id: role.name for role in roles}

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x3498DB,
        )
        embed.add_field(
            name="設定ロール",
            value="\n".join(role.mention for role in roles),
            inline=False,
        )
        embed.set_footer(text="一度に複数選択できます。すでに持っているロールは解除されます。")

        await interaction.response.send_message(
            embed=embed,
            view=RolePanelView(role_ids, role_names),
        )
        message = await interaction.original_response()
        await db_set(
            role_panel_key(message.id),
            json.dumps(
                {
                    "guild_id": interaction.guild_id,
                    "channel_id": interaction.channel_id,
                    "message_id": message.id,
                    "role_ids": role_ids,
                    "role_names": role_names,
                },
                ensure_ascii=False,
            ),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RolePanel(bot))
