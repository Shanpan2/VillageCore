import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io
from pathlib import Path
from database.config_db import db_get, db_set

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create_welcome_card(self, member):
        base_path = Path(__file__).resolve().parent.parent
        assets_path = base_path / "assets" / "welcome"

        # キャンバス
        width, height = 900, 300
        # 背景画像
        try:
            background = Image.open(assets_path / "welcome_bg.png").convert("RGBA")
            background = background.resize((width, height), Image.LANCZOS)
        except Exception:
            background = Image.new("RGBA", (width, height), (30, 30, 30, 255))

        # アイコンURL（未設定ユーザー対応）
        avatar_url = member.display_avatar.url if hasattr(member, "display_avatar") else member.avatar.url if member.avatar else member.default_avatar.url

        # アイコン取得
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                avatar_bytes = await resp.read()

        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

        # 高品質丸切り抜き（2倍で作って縮小）
        size = 200
        big = avatar.resize((size*2, size*2))
        mask = Image.new("L", (size*2, size*2), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size*2, size*2), fill=255)
        big.putalpha(mask)
        avatar = big.resize((size, size), Image.LANCZOS)

        # 合成
        avatar_x = 40
        avatar_y = (height - size) // 2
        background.paste(avatar, (avatar_x, avatar_y), avatar)

        # テキスト
        draw = ImageDraw.Draw(background)
        try:
            font_big = ImageFont.truetype(str(assets_path / "rounded.ttf"), 48)
            font_small = ImageFont.truetype(str(assets_path / "rounded.ttf"), 28)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Welcome とユーザー名を右側に表示
        text_x = avatar_x + size + 30
        welcome_text = "ようこそ！"
        name_text = f"{member.display_name}"
        guild_text = f"{member.guild.name}" if member.guild else ""

        draw.text((text_x, avatar_y + 10), welcome_text, fill="white", font=font_small)
        draw.text((text_x, avatar_y + 40), name_text, fill="white", font=font_big)
        if guild_text:
            draw.text((text_x, avatar_y + 100), guild_text, fill=(200,200,200), font=font_small)

        # バイトに変換
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

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
