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


def role_panel_payload(
    guild_id: int | None,
    channel_id: int | None,
    message_id: int,
    roles: list[discord.Role],
) -> str:
    return json.dumps(
        {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "role_ids": [role.id for role in roles],
            "role_names": {role.id: role.name for role in roles},
        },
        ensure_ascii=False,
    )


def role_names(roles: list[discord.Role]) -> dict[int, str]:
    return {role.id: role.name for role in roles}


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
            view=RolePanelView(role_ids, role_names(roles)),
        )
        message = await interaction.original_response()
        await db_set(
            role_panel_key(message.id),
            role_panel_payload(interaction.guild_id, interaction.channel_id, message.id, roles),
        )

    @app_commands.command(name="role_panel_migrate", description="【管理者】アップデート前の役職パネルを新形式へ変換します")
    @app_commands.describe(
        message_id="変換したい古い役職パネルのメッセージID",
        role1="そのパネルで付与したいロール 1",
        role2="そのパネルで付与したいロール 2",
        role3="そのパネルで付与したいロール 3",
        role4="そのパネルで付与したいロール 4",
        role5="そのパネルで付与したいロール 5",
    )
    @app_commands.default_permissions(administrator=True)
    async def role_panel_migrate(
        self,
        interaction: discord.Interaction,
        message_id: str,
        role1: discord.Role,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
        role4: discord.Role | None = None,
        role5: discord.Role | None = None,
    ):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("テキストチャンネルで実行してください。", ephemeral=True)
            return

        try:
            target_message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("メッセージIDは数字で入力してください。", ephemeral=True)
            return

        roles = collect_roles(role1, role2, role3, role4, role5)
        role_ids = [role.id for role in roles]

        try:
            message = await interaction.channel.fetch_message(target_message_id)
        except discord.NotFound:
            await interaction.response.send_message(
                "指定したメッセージがこのチャンネルに見つかりませんでした。",
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "Botにメッセージ履歴を読む権限がありません。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0] if message.embeds else discord.Embed(title="役職パネル", color=0x3498DB)
        embed.clear_fields()
        embed.add_field(
            name="設定ロール",
            value="\n".join(role.mention for role in roles),
            inline=False,
        )
        embed.set_footer(text="アップデート後の複数ロール対応パネルへ変換済みです。")

        await message.edit(embed=embed, view=RolePanelView(role_ids, role_names(roles)))
        await db_set(
            role_panel_key(message.id),
            role_panel_payload(interaction.guild_id, interaction.channel_id, message.id, roles),
        )
        await interaction.response.send_message(
            f"役職パネルを変換しました: {message.jump_url}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RolePanel(bot))
