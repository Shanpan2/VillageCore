import discord
from discord import app_commands
from discord.ext import commands


class PermissionCheck(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="permission_check", description="Botがロール付与やチャンネル操作できるか確認します")
    @app_commands.default_permissions(administrator=True)
    async def permission_check(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild or not guild.me:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        me = guild.me
        channel_perms = interaction.channel.permissions_for(me)
        manageable_roles = []
        blocked_roles = []

        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default() or role.managed:
                continue
            if role < me.top_role or me.guild_permissions.administrator:
                manageable_roles.append(role.name)
            else:
                blocked_roles.append(role.name)

        embed = discord.Embed(title="権限チェック", color=0x3498DB)
        embed.add_field(name="Bot最上位ロール", value=me.top_role.mention, inline=False)
        embed.add_field(
            name="基本権限",
            value="\n".join(
                [
                    f"{'OK' if me.guild_permissions.manage_roles else 'NG'} ロール管理",
                    f"{'OK' if me.guild_permissions.manage_channels else 'NG'} チャンネル管理",
                    f"{'OK' if channel_perms.send_messages else 'NG'} このチャンネルに送信",
                    f"{'OK' if channel_perms.attach_files else 'NG'} ファイル添付",
                    f"{'OK' if channel_perms.read_message_history else 'NG'} 履歴閲覧",
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name="付与できない可能性が高いロール",
            value="\n".join(blocked_roles[:20]) if blocked_roles else "なし",
            inline=False,
        )
        embed.set_footer(text=f"付与可能ロール数: {len(manageable_roles)} / ブロック対象: {len(blocked_roles)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PermissionCheck(bot))
