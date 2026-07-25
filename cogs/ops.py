import json
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_get_all_config, db_set

try:
    import shogi
except ModuleNotFoundError:
    shogi = None


JST = timezone(timedelta(hours=9))


def error_channel_key(guild_id: int) -> str:
    return f"ops_error_channel:{guild_id}"


def command_log_channel_key(guild_id: int) -> str:
    return f"ops_command_log_channel:{guild_id}"


def maintenance_key(guild_id: int) -> str:
    return f"ops_maintenance:{guild_id}"


def setup_done_key(guild_id: int) -> str:
    return f"ops_setup_done:{guild_id}"


def mention_channel(guild: discord.Guild, raw_id: str | int | None) -> str:
    if not raw_id:
        return "未設定"
    try:
        channel = guild.get_channel(int(raw_id))
    except (TypeError, ValueError):
        channel = None
    return channel.mention if channel else f"不明: `{raw_id}`"


def shogi_library_status() -> str:
    if shogi is None:
        return "NG: python-shogi 未導入"
    try:
        board = shogi.Board()
        return f"OK: python-shogi / `{board.sfen()}`"
    except Exception as exc:
        return f"NG: {type(exc).__name__}"


def read_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


class SetupGuideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="ログ/通知", style=discord.ButtonStyle.primary)
    async def logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "`/server_log_channel`\n"
            "`/ticket_log_channel`\n"
            "`/error_log_channel`\n"
            "`/command_log_channel`\n"
            "`/youtube_notify_channel`",
            ephemeral=True,
        )

    @discord.ui.button(label="コミュニティ", style=discord.ButtonStyle.success)
    async def community(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "`/report_channel`（Bot報告の控え先）\n"
            "`/rule_set`\n"
            "`/faq_set`\n"
            "`/role_panel_setup`",
            ephemeral=True,
        )

    @discord.ui.button(label="診断", style=discord.ButtonStyle.secondary)
    async def diagnostics(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "`/settings_status`\n"
            "`/permission_audit`",
            ephemeral=True,
        )


class Ops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.previous_interaction_check = None

    async def cog_load(self):
        self.previous_interaction_check = self.bot.tree.interaction_check

        async def maintenance_interaction_check(interaction: discord.Interaction) -> bool:
            if self.previous_interaction_check:
                ok = await self.previous_interaction_check(interaction)
                if not ok:
                    return False
            if not interaction.guild_id:
                return True
            command_name = interaction.command.name if interaction.command else ""
            if command_name in {"maintenance_off", "maintenance_on", "maintenance_status"}:
                return True
            if await db_get(maintenance_key(interaction.guild_id)) != "on":
                return True
            if interaction.user.guild_permissions.manage_guild:
                return True
            await interaction.response.send_message("現在メンテナンス中です。しばらく待ってから試してください。", ephemeral=True)
            return False

        self.bot.tree.interaction_check = maintenance_interaction_check

    def cog_unload(self):
        if self.previous_interaction_check:
            self.bot.tree.interaction_check = self.previous_interaction_check

    async def send_ops_log(self, guild_id: int | None, key_func, embed: discord.Embed):
        if not guild_id:
            return
        raw = await db_get(key_func(guild_id))
        if not raw:
            return
        channel = self.bot.get_channel(int(raw))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @app_commands.command(name="settings_status", description="主要なBot設定を一覧表示します")
    @app_commands.default_permissions(manage_guild=True)
    async def settings_status(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        guild_id = guild.id
        attendance = read_json(await db_get("attendance_data"), {})
        all_config = await db_get_all_config()
        role_panels = len([key for key in all_config if key.startswith("role_panel:")])
        faq_count = len(read_json(await db_get(f"community_faq_index:{guild_id}"), []))

        fields = {
            "サーバーログ": await db_get(f"server_log_channel:{guild_id}"),
            "チケットログ": await db_get(f"ticket_log_channel:{guild_id}"),
            "YouTube通知": await db_get(f"youtube_notify_channel_id:{guild_id}"),
            "出席通知": attendance.get("notify_channel_id"),
            "Bot報告控え": await db_get(f"community_report_channel:{guild_id}"),
            "エラー通知": await db_get(error_channel_key(guild_id)),
            "利用ログ": await db_get(command_log_channel_key(guild_id)),
            "Welcome": await db_get(f"welcome_channel_{guild_id}"),
        }
        embed = discord.Embed(title="設定一覧", color=0x00BFFF)
        for name, raw_id in fields.items():
            embed.add_field(name=name, value=mention_channel(guild, raw_id), inline=True)
        embed.add_field(name="役職パネル数", value=str(role_panels), inline=True)
        embed.add_field(name="FAQ数", value=str(faq_count), inline=True)
        embed.add_field(name="メンテナンス", value="ON" if await db_get(maintenance_key(guild_id)) == "on" else "OFF", inline=True)
        embed.add_field(name="自動Kick", value="ON" if await db_get(f"welcome_auto_kick_{guild_id}") == "on" else "OFF", inline=True)
        embed.add_field(name="将棋判定", value=shogi_library_status(), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="setup_wizard", description="導入時に必要な設定を案内します")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_wizard(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="初期設定ウィザード",
            description="導入直後に設定すると便利な項目です。下のボタンからカテゴリ別に確認できます。",
            color=0x2ECC71,
        )
        embed.add_field(name="まず確認", value="`/permission_audit` と `/settings_status`", inline=False)
        embed.add_field(name="最低限", value="ログ、チケットログ、通知先、通報先", inline=False)
        embed.add_field(name="参加制限", value="新規参加を止めたい時だけ `/auto_kick_mode mode:on`", inline=False)
        await db_set(setup_done_key(interaction.guild_id), datetime.now(timezone.utc).isoformat())
        await interaction.response.send_message(embed=embed, view=SetupGuideView(), ephemeral=True)

    @app_commands.command(name="error_log_channel", description="【管理者】Botエラー通知先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def error_log_channel(self, interaction: discord.Interaction):
        await db_set(error_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"エラー通知先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="command_log_channel", description="【管理者】Bot利用ログ送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def command_log_channel(self, interaction: discord.Interaction):
        await db_set(command_log_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"利用ログ送信先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        embed = discord.Embed(title="コマンド利用", color=0x95A5A6, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="コマンド", value=f"/{command.qualified_name}", inline=True)
        embed.add_field(name="ユーザー", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        embed.add_field(name="チャンネル", value=getattr(interaction.channel, "mention", "不明"), inline=True)
        await self.send_ops_log(interaction.guild_id, command_log_channel_key, embed)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(title="Botエラー", color=0xE74C3C, timestamp=datetime.now(timezone.utc))
        name = interaction.command.qualified_name if interaction.command else "unknown"
        embed.add_field(name="コマンド", value=f"/{name}", inline=True)
        embed.add_field(name="ユーザー", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        embed.add_field(name="内容", value=f"`{type(error).__name__}: {str(error)[:900]}`", inline=False)
        await self.send_ops_log(interaction.guild_id, error_channel_key, embed)

    @app_commands.command(name="permission_audit", description="Botに必要な権限を機能別に診断します")
    @app_commands.default_permissions(manage_guild=True)
    async def permission_audit(self, interaction: discord.Interaction):
        guild = interaction.guild
        me = guild.me if guild else None
        if not guild or not me or not interaction.channel:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        perms = interaction.channel.permissions_for(me)
        guild_perms = me.guild_permissions
        checks = {
            "メッセージ送信": perms.send_messages,
            "埋め込みリンク": perms.embed_links,
            "ファイル添付": perms.attach_files,
            "メッセージ履歴閲覧": perms.read_message_history,
            "リアクション追加": perms.add_reactions,
            "チャンネル管理": guild_perms.manage_channels,
            "ロール管理": guild_perms.manage_roles,
            "メッセージ管理": guild_perms.manage_messages,
            "メンバーKick": guild_perms.kick_members,
            "メンバー表示": guild_perms.view_channel,
            "VC接続": guild_perms.connect,
            "VC発言": guild_perms.speak,
        }
        embed = discord.Embed(title="権限診断", color=0x2ECC71 if all(checks.values()) else 0xE67E22)
        embed.description = "\n".join(f"{'OK' if ok else 'NG'} {name}" for name, ok in checks.items())
        embed.add_field(name="補足", value="役職パネルを使う場合、Botのロールは付与対象ロールより上に置いてください。", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="maintenance_on", description="【管理者】メンテナンスモードを有効化します")
    @app_commands.default_permissions(manage_guild=True)
    async def maintenance_on(self, interaction: discord.Interaction):
        await db_set(maintenance_key(interaction.guild_id), "on")
        await interaction.response.send_message("メンテナンスモードをONにしました。管理者以外のスラッシュコマンドを一時停止します。", ephemeral=True)

    @app_commands.command(name="maintenance_off", description="【管理者】メンテナンスモードを解除します")
    @app_commands.default_permissions(manage_guild=True)
    async def maintenance_off(self, interaction: discord.Interaction):
        await db_set(maintenance_key(interaction.guild_id), "off")
        await interaction.response.send_message("メンテナンスモードをOFFにしました。", ephemeral=True)

    @app_commands.command(name="maintenance_status", description="メンテナンスモードの状態を表示します")
    async def maintenance_status(self, interaction: discord.Interaction):
        status = await db_get(maintenance_key(interaction.guild_id))
        await interaction.response.send_message(f"メンテナンスモード: **{'ON' if status == 'on' else 'OFF'}**", ephemeral=True)

    @app_commands.command(name="data_cleanup", description="【管理者】古いAI履歴や空データを整理します")
    @app_commands.default_permissions(manage_guild=True)
    async def data_cleanup(self, interaction: discord.Interaction, clear_ai_memory: bool = False):
        await interaction.response.defer(ephemeral=True)
        config = await db_get_all_config()
        cleaned = 0
        if clear_ai_memory:
            prefix = f"ai_memory:{interaction.guild_id}:"
            for key in config:
                if key.startswith(prefix):
                    await db_set(key, "[]")
                    cleaned += 1
        await interaction.followup.send(f"データ整理が完了しました。更新件数: **{cleaned}**", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ops(bot))
