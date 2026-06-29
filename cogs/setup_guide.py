import discord
from discord import app_commands
from discord.ext import commands


GUIDE_TEXT = (
    "まず設定すると便利な項目です。\n\n"
    "`/bot_status` Bot/API/DB診断\n"
    "`/permission_check` 権限とロール位置確認\n"
    "`/server_log_channel` サーバーログ送信先設定\n"
    "`/ticket_log_channel` チケットログ送信先設定\n"
    "`/youtube_notify_channel` YouTube通知先設定\n"
    "`/youtube_notify_keyword` YouTube通知タグ設定\n"
    "`/role_panel_setup` 役職パネル設置\n"
)


class SetupGuide(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup_guide", description="Botの初期設定ガイドを表示します")
    @app_commands.default_permissions(administrator=True)
    async def setup_guide(self, interaction: discord.Interaction):
        embed = discord.Embed(title="初期設定ガイド", description=GUIDE_TEXT, color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        embed = discord.Embed(title="むらびと君 初期設定", description=GUIDE_TEXT, color=0x5865F2)
        target = guild.system_channel
        if target and target.permissions_for(guild.me).send_messages:
            try:
                await target.send(embed=embed)
                return
            except discord.HTTPException as e:
                print(f"[SetupGuide] system_channel send failed for guild {guild.id}: {type(e).__name__}: {e}", flush=True)

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    print(f"[SetupGuide] fallback channel send failed for guild {guild.id}: {type(e).__name__}: {e}", flush=True)
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupGuide(bot))
