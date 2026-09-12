import discord
from discord import app_commands
from discord.ext import commands

from cogs.server_logs import send_server_log


def safe_name(value: discord.Member | discord.User | discord.Role) -> str:
    return discord.utils.escape_markdown(str(value))


def validate_role_operation(
    guild: discord.Guild,
    actor: discord.Member,
    member: discord.Member,
    role: discord.Role,
) -> str | None:
    bot_member = guild.me
    if role == guild.default_role:
        return "@everyone は操作できません。"
    if role.managed:
        return "Bot連携などで自動管理されているロールは操作できません。"
    if not bot_member or not bot_member.guild_permissions.manage_roles:
        return "Botに「ロールの管理」権限がありません。"
    if role >= bot_member.top_role:
        return "対象ロールをBotの最上位ロールより下に移動してください。"
    if member == guild.owner:
        return "サーバー所有者のロールはこのコマンドでは変更できません。"
    if member.top_role >= bot_member.top_role:
        return "対象メンバーの最上位ロールがBot以上のため操作できません。"
    if actor != guild.owner:
        if role >= actor.top_role:
            return "自分と同じか、自分より上位のロールは操作できません。"
        if member.top_role >= actor.top_role and member != actor:
            return "自分と同じか、自分より上位のメンバーは操作できません。"
    return None


class RoleAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def change_role(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        member: discord.Member,
        role: discord.Role,
        *,
        give: bool,
        reason: str | None,
    ) -> tuple[bool, str]:
        error = validate_role_operation(guild, actor, member, role)
        if error:
            return False, error

        action = "付与" if give else "解除"
        if give and role in member.roles:
            return False, f"{safe_name(member)} さんはすでに @{safe_name(role)} を持っています。"
        if not give and role not in member.roles:
            return False, f"{safe_name(member)} さんは @{safe_name(role)} を持っていません。"

        audit_reason = f"{action} by {actor} ({actor.id})"
        if reason:
            audit_reason += f": {reason[:300]}"
        try:
            if give:
                await member.add_roles(role, reason=audit_reason)
            else:
                await member.remove_roles(role, reason=audit_reason)
        except discord.Forbidden:
            return False, "Discordの権限またはロール順位により操作できませんでした。"
        except discord.HTTPException as exc:
            return False, f"ロールの{action}中にDiscord APIエラーが発生しました: {exc}"

        embed = discord.Embed(
            title=f"メンバーロール{action}",
            color=0x2ECC71 if give else 0xE67E22,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="対象メンバー", value=f"{safe_name(member)} (`{member.id}`)", inline=False)
        embed.add_field(name="ロール", value=f"@{safe_name(role)} (`{role.id}`)", inline=False)
        embed.add_field(name="実行者", value=f"{safe_name(actor)} (`{actor.id}`)", inline=False)
        if reason:
            embed.add_field(name="理由", value=reason[:1000], inline=False)
        await send_server_log(self.bot, guild, embed, "role_channel")

        return True, f"{safe_name(member)} さんへ @{safe_name(role)} を{action}しました。"

    @app_commands.command(name="role_give", description="【管理者】メンバーへロールを付与します")
    @app_commands.describe(member="付与するメンバー", role="付与するロール", reason="理由（任意）")
    @app_commands.default_permissions(manage_roles=True)
    async def role_give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("「ロールの管理」権限が必要です。", ephemeral=True)
            return
        ok, message = await self.change_role(
            interaction.guild, interaction.user, member, role, give=True, reason=reason
        )
        await interaction.response.send_message(
            message,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="role_delete", description="【管理者】メンバーからロールを解除します")
    @app_commands.describe(member="解除するメンバー", role="解除するロール", reason="理由（任意）")
    @app_commands.default_permissions(manage_roles=True)
    async def role_delete(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("「ロールの管理」権限が必要です。", ephemeral=True)
            return
        ok, message = await self.change_role(
            interaction.guild, interaction.user, member, role, give=False, reason=reason
        )
        await interaction.response.send_message(
            message,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="role_give")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def role_give_prefix(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        reason: str | None = None,
    ):
        ok, message = await self.change_role(ctx.guild, ctx.author, member, role, give=True, reason=reason)
        await ctx.reply(
            message,
            mention_author=False,
            delete_after=60 if not ok else None,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="role_delete")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def role_delete_prefix(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        reason: str | None = None,
    ):
        ok, message = await self.change_role(ctx.guild, ctx.author, member, role, give=False, reason=reason)
        await ctx.reply(
            message,
            mention_author=False,
            delete_after=60 if not ok else None,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleAdmin(bot))
