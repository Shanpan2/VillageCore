import json
from datetime import datetime, timezone
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get_all_config, db_set, use_postgres


BACKUP_VERSION = 1


class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="backup_export", description="【管理者】Bot設定と記録データをJSONでバックアップします")
    @app_commands.default_permissions(administrator=True)
    async def export_backup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await db_get_all_config()
        payload = {
            "app": "VillageCore",
            "version": BACKUP_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "guild_id": interaction.guild_id,
            "storage": "postgresql" if use_postgres() else "sqlite",
            "config": config,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        file = discord.File(BytesIO(data), filename=f"villagecore-backup-{interaction.guild_id}.json")
        await interaction.followup.send(
            f"バックアップを作成しました。保存項目数: {len(config)}",
            file=file,
            ephemeral=True,
        )

    @app_commands.command(name="backup_import", description="【管理者】バックアップJSONからBot設定を復元します")
    @app_commands.describe(file="backup_exportで作成したJSONファイル")
    @app_commands.default_permissions(administrator=True)
    async def import_backup(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if not file.filename.lower().endswith(".json"):
            await interaction.followup.send("JSONファイルを指定してください。", ephemeral=True)
            return

        try:
            raw = await file.read()
            payload = json.loads(raw.decode("utf-8"))
            config = payload.get("config")
            if not isinstance(config, dict):
                raise ValueError("config が見つかりません")
        except Exception as e:
            await interaction.followup.send(f"バックアップを読み込めませんでした: `{type(e).__name__}: {e}`", ephemeral=True)
            return

        restored = 0
        for key, value in config.items():
            if not isinstance(key, str) or value is None:
                continue
            await db_set(key, str(value))
            restored += 1

        await interaction.followup.send(
            f"バックアップを復元しました。復元項目数: {restored}\n"
            "一部機能はBot再起動後に反映されます。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
