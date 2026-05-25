import inspect

import discord
from discord import app_commands
from discord.ext import commands


PANEL_TIMEOUT_SECONDS = 600


async def call_command(cog: commands.Cog | None, name: str, interaction: discord.Interaction, *args):
    command = getattr(cog, name, None) if cog else None
    callback = getattr(command, "callback", None)
    if not callback:
        await interaction.response.send_message("この操作は現在利用できません。", ephemeral=True)
        return
    params = list(inspect.signature(callback).parameters)
    if params and params[0] == "self":
        await callback(cog, interaction, *args)
        return
    await callback(interaction, *args)


class MusicPlayModal(discord.ui.Modal, title="音楽を再生"):
    query = discord.ui.TextInput(label="曲名またはURL", max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await call_command(interaction.client.get_cog("Music"), "play", interaction, self.query.value)


class MusicRemoveModal(discord.ui.Modal, title="キューから削除"):
    index = discord.ui.TextInput(label="削除する番号", placeholder="例: 1", max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.index.value)
        except ValueError:
            await interaction.response.send_message("番号は数字で入力してください。", ephemeral=True)
            return
        await call_command(interaction.client.get_cog("Music"), "remove", interaction, value)


class MusicLoopSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="ループなし", value="off"),
            discord.SelectOption(label="1曲ループ", value="single"),
            discord.SelectOption(label="全体ループ", value="all"),
        ]
        super().__init__(placeholder="ループ設定", options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        await call_command(interaction.client.get_cog("Music"), "loop", interaction, self.values[0])


class MusicButton(discord.ui.Button):
    def __init__(self, label: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        if self.action == "play":
            await interaction.response.send_modal(MusicPlayModal())
            return
        if self.action == "remove":
            await interaction.response.send_modal(MusicRemoveModal())
            return
        await call_command(interaction.client.get_cog("Music"), self.action, interaction)


class MusicPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        for label, action, style, row in [
            ("再生", "play", discord.ButtonStyle.primary, 0),
            ("参加", "join", discord.ButtonStyle.secondary, 0),
            ("退出", "leave", discord.ButtonStyle.secondary, 0),
            ("停止", "stop", discord.ButtonStyle.danger, 0),
            ("一時停止", "pause", discord.ButtonStyle.secondary, 1),
            ("再開", "resume", discord.ButtonStyle.secondary, 1),
            ("スキップ", "skip", discord.ButtonStyle.primary, 1),
            ("キュー", "queue", discord.ButtonStyle.secondary, 1),
            ("再生中", "nowplaying", discord.ButtonStyle.secondary, 2),
            ("シャッフル", "shuffle", discord.ButtonStyle.secondary, 2),
            ("削除", "remove", discord.ButtonStyle.danger, 2),
        ]:
            self.add_item(MusicButton(label, action, style, row))
        self.add_item(MusicLoopSelect())


class YoutubeKeywordsModal(discord.ui.Modal, title="YouTube通知キーワード"):
    keywords = discord.ui.TextInput(
        label="検索キーワード",
        placeholder="#おちゃめ村, #切り抜き",
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await call_command(interaction.client.get_cog("YoutubeNotify"), "youtube_notify_keywords", interaction, self.keywords.value)


class YoutubeButton(discord.ui.Button):
    def __init__(self, label: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        admin_actions = {"youtube_notify_channel", "keywords", "youtube_check"}
        if self.action in admin_actions and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("この操作にはサーバー管理権限が必要です。", ephemeral=True)
            return
        if self.action == "keywords":
            await interaction.response.send_modal(YoutubeKeywordsModal())
            return
        await call_command(interaction.client.get_cog("YoutubeNotify"), self.action, interaction)


class YoutubePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(YoutubeButton("通知先をこのチャンネルに設定", "youtube_notify_channel", discord.ButtonStyle.primary, 0))
        self.add_item(YoutubeButton("キーワード設定", "keywords", discord.ButtonStyle.primary, 0))
        self.add_item(YoutubeButton("状態確認", "youtube_notify_status", discord.ButtonStyle.secondary, 1))
        self.add_item(YoutubeButton("今すぐチェック", "youtube_check", discord.ButtonStyle.secondary, 1))


class AttendanceButton(discord.ui.Button):
    def __init__(self, label: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        admin_actions = {
            "attend_set_channel",
            "attend_add_members_bulk",
            "attend_record",
            "attend_record_all",
            "attend_notify",
        }
        if self.action in admin_actions and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("この操作にはサーバー管理権限が必要です。", ephemeral=True)
            return
        await call_command(interaction.client.get_cog("Attendance"), self.action, interaction)


class AttendancePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        for label, action, style, row in [
            ("通知先設定", "attend_set_channel", discord.ButtonStyle.primary, 0),
            ("一括追加", "attend_add_members_bulk", discord.ButtonStyle.primary, 0),
            ("出席記録", "attend_record", discord.ButtonStyle.primary, 1),
            ("一括記録", "attend_record_all", discord.ButtonStyle.primary, 1),
            ("ポイント一覧", "attend_status", discord.ButtonStyle.secondary, 2),
            ("警告一覧", "attend_warnings", discord.ButtonStyle.secondary, 2),
            ("警告通知", "attend_notify", discord.ButtonStyle.secondary, 2),
        ]:
            self.add_item(AttendanceButton(label, action, style, row))


class AdminButton(discord.ui.Button):
    def __init__(self, label: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("この操作にはサーバー管理権限が必要です。", ephemeral=True)
            return
        await call_command(interaction.client.get_cog("Ops"), self.action, interaction)


class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        for label, action, style, row in [
            ("設定確認", "settings_status", discord.ButtonStyle.secondary, 0),
            ("導入ガイド", "setup_wizard", discord.ButtonStyle.secondary, 0),
            ("権限診断", "permission_audit", discord.ButtonStyle.secondary, 0),
            ("エラーログ先", "error_log_channel", discord.ButtonStyle.primary, 1),
            ("利用ログ先", "command_log_channel", discord.ButtonStyle.primary, 1),
            ("メンテON", "maintenance_on", discord.ButtonStyle.danger, 2),
            ("メンテOFF", "maintenance_off", discord.ButtonStyle.success, 2),
            ("メンテ状態", "maintenance_status", discord.ButtonStyle.secondary, 2),
            ("データ整理", "data_cleanup", discord.ButtonStyle.secondary, 3),
        ]:
            self.add_item(AdminButton(label, action, style, row))


class Panels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="music", description="音楽操作パネルを表示します")
    async def music(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="音楽パネル",
            description="再生、停止、スキップ、キュー確認などをボタンで操作できます。",
            color=0x1ABC9C,
        )
        await interaction.response.send_message(embed=embed, view=MusicPanelView())

    @app_commands.command(name="youtube", description="YouTube通知設定パネルを表示します")
    async def youtube(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="YouTube通知パネル",
            description="通知先、キーワード、状態確認、手動チェックをまとめて操作できます。",
            color=0xE74C3C,
        )
        await interaction.response.send_message(embed=embed, view=YoutubePanelView(), ephemeral=True)

    @app_commands.command(name="attendance", description="出席管理パネルを表示します")
    async def attendance(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="出席管理パネル",
            description="出席記録、一覧、警告確認などをボタンで操作できます。",
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, view=AttendancePanelView(), ephemeral=True)

    @app_commands.command(name="admin", description="管理者向け設定パネルを表示します")
    @app_commands.default_permissions(manage_guild=True)
    async def admin(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="管理パネル",
            description="設定確認、権限診断、ログ設定、メンテナンス操作をまとめています。",
            color=0xF39C12,
        )
        await interaction.response.send_message(embed=embed, view=AdminPanelView(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Panels(bot))
