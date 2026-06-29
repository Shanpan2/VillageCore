import json
from datetime import datetime, timezone
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get_all_config, db_set, use_postgres


BACKUP_VERSION = 1

# Keys that contain a guild ID scope use one of these prefix patterns.
# Only keys belonging to the importing guild (or global non-guild keys)
# are allowed during import to prevent cross-guild data injection.
_GUILD_SCOPED_PREFIXES = (
    "server_log_channel:",
    "server_log_settings:",
    "ticket_log_channel:",
    "ticket_counter:",
    "youtube_notify_channel_id:",
    "youtube_notify_keywords:",
    "youtube_posted_ids:",
    "birthday_settings:",
    "birthday_bonus:",
    "ng_words:",
    "ops_error_channel:",
    "ops_command_log_channel:",
    "ops_maintenance:",
    "ops_setup_done:",
    "community_profile:",
    "community_coin:",
    "community_coin_daily:",
    "community_coin_gamble_lock:",
    "community_coin_gamble_lock_reason:",
    "community_gamble_role_expirations:",
    "community_titles:",
    "community_badges:",
    "community_event:",
    "community_event_index:",
    "community_topic:",
    "community_faq:",
    "community_faq_index:",
    "community_rule:",
    "community_report_channel:",
    "community_report_cooldown:",
    "community_coin_shop_expirations:",
    "welcome_channel_",
    "welcome_message_",
    "ai_memory:",
    "role_panel:",
    "bot_guild:",
    "music_state:",
    "attendance_",
)


def _is_key_for_guild(key: str, guild_id: int | None) -> bool:
    """Return True if the key belongs to the given guild or is not guild-scoped."""
    if guild_id is None:
        return False
    guild_str = str(guild_id)
    for prefix in _GUILD_SCOPED_PREFIXES:
        if key.startswith(prefix):
            remainder = key[len(prefix):]
            # The guild ID should be the next segment (before any further ':' or '_')
            segment = remainder.split(":")[0].split("_")[0]
            return segment == guild_str
    # Non-guild-scoped keys (e.g. global config) are allowed
    return True


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

        guild_id = interaction.guild_id
        restored = 0
        skipped = 0
        for key, value in config.items():
            if not isinstance(key, str) or value is None:
                continue
            if not _is_key_for_guild(key, guild_id):
                skipped += 1
                continue
            await db_set(key, str(value))
            restored += 1

        skip_note = f"\nスキップ項目数: {skipped}（他サーバーのデータは復元されません）" if skipped else ""
        await interaction.followup.send(
            f"バックアップを復元しました。復元項目数: {restored}{skip_note}\n"
            "一部機能はBot再起動後に反映されます。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
