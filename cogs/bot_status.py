import os
import shutil

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, use_postgres


class BotStatus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="bot_status", description="BotのAPI/DB/権限状態を診断します")
    @app_commands.default_permissions(administrator=True)
    async def show_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        db_ok = False
        try:
            await db_get("__healthcheck__")
            db_ok = True
        except Exception:
            db_ok = False

        guild = interaction.guild
        me = guild.me if guild else None
        perms = interaction.channel.permissions_for(me) if guild and me and interaction.channel else None
        command_count = len([c for c in self.bot.tree.walk_commands() if c.parent is None])

        embed = discord.Embed(title="Bot診断", color=0x2ECC71 if db_ok else 0xE67E22)
        embed.add_field(name="DB", value=("PostgreSQL" if use_postgres() else "SQLite") + (" / OK" if db_ok else " / NG"), inline=False)
        embed.add_field(name="Discord Token", value="OK" if os.getenv("DISCORD_TOKEN") else "未設定", inline=True)
        embed.add_field(name="YouTube API", value="OK" if os.getenv("YOUTUBE_API_KEY") else "未設定", inline=True)
        embed.add_field(name="Gemini API", value="OK" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")) else "未設定", inline=True)
        embed.add_field(name="ffmpeg", value="OK" if shutil.which("ffmpeg") else "未検出", inline=True)
        embed.add_field(name="登録コマンド数", value=str(command_count), inline=True)

        if me and perms:
            checks = {
                "管理者": me.guild_permissions.administrator,
                "チャンネル管理": me.guild_permissions.manage_channels,
                "ロール管理": me.guild_permissions.manage_roles,
                "メッセージ送信": perms.send_messages,
                "ファイル添付": perms.attach_files,
                "履歴閲覧": perms.read_message_history,
            }
            embed.add_field(
                name="権限",
                value="\n".join(f"{'OK' if ok else 'NG'} {name}" for name, ok in checks.items()),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotStatus(bot))
