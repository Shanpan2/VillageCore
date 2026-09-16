import json

import discord
from discord import app_commands
from discord.ext import commands

from cogs.server_logs import send_server_log
from database.config_db import db_get, db_set


def coin_role_shop_key(guild_id: int) -> str:
    return f"community_coin_role_shop:{guild_id}"


async def load_coin_role_shop(guild_id: int) -> dict:
    raw = await db_get(coin_role_shop_key(guild_id))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


async def save_coin_role_shop(guild_id: int, shop: dict):
    await db_set(coin_role_shop_key(guild_id), json.dumps(shop, ensure_ascii=False))


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

    @app_commands.command(name="role_remove", description="【管理者】メンバーからロールを解除します")
    @app_commands.describe(member="解除するメンバー", role="解除するロール", reason="理由（任意）")
    @app_commands.default_permissions(manage_roles=True)
    async def role_remove(
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

    @commands.command(name="role_remove")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def role_remove_prefix(
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

    @app_commands.command(name="role_create", description="【管理者】新しいロールを作成します")
    @app_commands.describe(
        name="作成するロール名",
        color_hex="色（例: FF0000、省略可）",
        coin_exchange="コインショップで交換可能にするか",
        coin_cost="交換に必要なコイン数",
        sell_enabled="購入後に売却可能にするか",
    )
    @app_commands.default_permissions(manage_roles=True)
    async def role_create(
        self,
        interaction: discord.Interaction,
        name: str,
        color_hex: str | None = None,
        coin_exchange: bool = False,
        coin_cost: int = 0,
        sell_enabled: bool = True,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("「ロールの管理」権限が必要です。", ephemeral=True)
            return
        role_name = name.strip()
        if not role_name or len(role_name) > 100:
            await interaction.response.send_message("ロール名は1～100文字で指定してください。", ephemeral=True)
            return
        if discord.utils.get(interaction.guild.roles, name=role_name):
            await interaction.response.send_message("同名のロールがすでに存在します。", ephemeral=True)
            return
        if coin_exchange and coin_cost <= 0:
            await interaction.response.send_message("コイン交換を有効にする場合は価格を1以上にしてください。", ephemeral=True)
            return
        color = discord.Color.default()
        if color_hex:
            try:
                color = discord.Color(int(color_hex.strip().lstrip("#"), 16))
            except ValueError:
                await interaction.response.send_message("色は `FF0000` のような16進数で指定してください。", ephemeral=True)
                return
        try:
            role = await interaction.guild.create_role(
                name=role_name,
                color=color,
                reason=f"/role_create by {interaction.user} ({interaction.user.id})",
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            await interaction.response.send_message(f"ロールを作成できませんでした: {exc}", ephemeral=True)
            return
        if coin_exchange:
            shop = await load_coin_role_shop(interaction.guild.id)
            shop[str(role.id)] = {
                "role_id": role.id,
                "cost": coin_cost,
                "name": role.name,
                "sell_enabled": sell_enabled,
            }
            await save_coin_role_shop(interaction.guild.id, shop)
        embed = discord.Embed(title="ロール作成", color=role.color, timestamp=discord.utils.utcnow())
        embed.add_field(name="ロール", value=f"{role.mention} (`{role.id}`)", inline=False)
        embed.add_field(name="実行者", value=f"{safe_name(interaction.user)} (`{interaction.user.id}`)", inline=False)
        embed.add_field(
            name="コイン交換",
            value=f"{coin_cost}コイン / {'売却可' if sell_enabled else '売却不可'}" if coin_exchange else "無効",
            inline=False,
        )
        await send_server_log(self.bot, interaction.guild, embed, "role_channel")
        await interaction.response.send_message(f"{role.mention} を作成しました。", ephemeral=True)

    @app_commands.command(name="role_delete", description="【管理者】ロールそのものを削除します")
    @app_commands.describe(role="削除するロール", reason="理由（任意）")
    @app_commands.default_permissions(manage_roles=True)
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role, reason: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("「ロールの管理」権限が必要です。", ephemeral=True)
            return
        if role == interaction.guild.default_role or role.managed:
            await interaction.response.send_message("このロールは削除できません。", ephemeral=True)
            return
        me = interaction.guild.me
        if not me or role >= me.top_role or (interaction.user != interaction.guild.owner and role >= interaction.user.top_role):
            await interaction.response.send_message("ロール順位のため削除できません。", ephemeral=True)
            return
        role_name, role_id = role.name, role.id
        try:
            await role.delete(reason=f"{reason or '指定なし'} / 実行者: {interaction.user} ({interaction.user.id})")
        except (discord.Forbidden, discord.HTTPException) as exc:
            await interaction.response.send_message(f"ロールを削除できませんでした: {exc}", ephemeral=True)
            return
        shop = await load_coin_role_shop(interaction.guild.id)
        if shop.pop(str(role_id), None) is not None:
            await save_coin_role_shop(interaction.guild.id, shop)
        embed = discord.Embed(title="ロール削除", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="ロール", value=f"{role_name} (`{role_id}`)", inline=False)
        embed.add_field(name="実行者", value=f"{safe_name(interaction.user)} (`{interaction.user.id}`)", inline=False)
        if reason:
            embed.add_field(name="理由", value=reason[:1000], inline=False)
        await send_server_log(self.bot, interaction.guild, embed, "role_channel")
        await interaction.response.send_message(f"ロール「{role_name}」を削除しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleAdmin(bot))
