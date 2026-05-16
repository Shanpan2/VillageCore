import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from database.config_db import db_get, db_set

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _welcome_channel_key(self, guild_id: int) -> str:
        return f"welcome_channel_{guild_id}"

    def _welcome_message_key(self, guild_id: int) -> str:
        return f"welcome_message_{guild_id}"

    async def _get_configured_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        raw = await db_get(self._welcome_channel_key(guild.id))
        if not raw:
            return None
        try:
            channel_id = int(raw)
        except Exception:
            return None
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None
        if not channel.permissions_for(guild.me).send_messages:
            return None
        return channel

    async def _get_configured_message(self, guild: discord.Guild) -> str | None:
        raw = await db_get(self._welcome_message_key(guild.id))
        if not raw:
            return None
        return raw

    def _format_welcome_message(self, member: discord.Member, template: str | None) -> str:
        if template is None:
            return f"{member.mention} さん、ようこそ！"
        guild_name = member.guild.name if member.guild else ""
        return (
            template
            .replace("{mention}", member.mention)
            .replace("{user}", member.display_name)
            .replace("{server}", guild_name)
        )

    async def _get_send_channel(self, member: discord.Member) -> discord.TextChannel | None:
        configured = await self._get_configured_channel(member.guild)
        if configured:
            return configured

        channel = member.guild.system_channel
        if channel and channel.permissions_for(member.guild.me).send_messages:
            return channel

        for text_channel in member.guild.text_channels:
            if text_channel.permissions_for(member.guild.me).send_messages:
                return text_channel
        return None

    @app_commands.command(
        name="welcome_channel",
        description="ウェルカムメッセージ送信先のチャンネルを設定または確認します。"
    )
    @app_commands.describe(channel="ウェルカムメッセージを送信するテキストチャンネル")
    async def welcome_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if channel is None:
            configured = await self._get_configured_channel(interaction.guild)
            if configured:
                await interaction.response.send_message(
                    f"✅ 現在のウェルカム送信先は {configured.mention} です。",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ 現在、ウェルカム送信先は設定されていません。"
                    " system_channel または送信可能なチャンネルが自動で選択されます。",
                    ephemeral=True,
                )
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ このコマンドを使うにはサーバー管理権限が必要です。",
                ephemeral=True,
            )
            return

        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                "❌ ボットがそのチャンネルに送信できません。別のチャンネルを指定してください。",
                ephemeral=True,
            )
            return

        await db_set(self._welcome_channel_key(interaction.guild.id), str(channel.id))
        await interaction.response.send_message(
            f"✅ ウェルカム送信先を {channel.mention} に設定しました。",
            ephemeral=True,
        )

    @app_commands.command(
        name="welcome_message",
        description="ウェルカムメッセージを設定または確認します。"
    )
    @app_commands.describe(message="メッセージ。{mention}、{user}、{server} を使えます。")
    async def welcome_message(
        self,
        interaction: discord.Interaction,
        message: str | None = None,
    ):
        if message is None:
            configured = await self._get_configured_message(interaction.guild)
            if configured:
                await interaction.response.send_message(
                    f"✅ 現在のウェルカムメッセージ: ` {configured} `",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ 現在、ウェルカムメッセージは設定されていません。デフォルトのメッセージが使用されます。",
                    ephemeral=True,
                )
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ このコマンドを使うにはサーバー管理権限が必要です。",
                ephemeral=True,
            )
            return

        if len(message) > 200:
            await interaction.response.send_message(
                "❌ メッセージは200文字以内で設定してください。",
                ephemeral=True,
            )
            return

        await db_set(self._welcome_message_key(interaction.guild.id), message)
        await interaction.response.send_message(
            "✅ ウェルカムメッセージを設定しました。",
            ephemeral=True,
        )

    @app_commands.command(
        name="welcome_message_reset",
        description="ウェルカムメッセージをリセットします。"
    )
    async def welcome_message_reset(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ このコマンドを使うにはサーバー管理権限が必要です。",
                ephemeral=True,
            )
            return

        await db_set(self._welcome_message_key(interaction.guild.id), "")
        await interaction.response.send_message(
            "✅ ウェルカムメッセージをリセットしました。デフォルトメッセージが使用されます。",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = await self._get_send_channel(member)

        if channel is None:
            print(f"⚠️ Welcome: no sendable channel found for guild {member.guild.id}")
            return

        message_template = await self._get_configured_message(member.guild)
        message = self._format_welcome_message(member, message_template)

        try:
            await channel.send(content=message)
        except Exception as e:
            print(f"⚠️ Welcome send failed: {e}")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
