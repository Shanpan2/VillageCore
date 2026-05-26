import discord
from discord.ext import commands
from discord import app_commands

from database.config_db import db_set
from views.ticket_views import TicketButtonView
from views.ticket_views import ticket_counter_key
from views.ticket_views import ticket_log_channel_key


class Ticket(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ticket_setup", description="【管理者】チケット発行ボタンを設置します")
    @app_commands.describe(
        title="ボタンメッセージのタイトル",
        description="ボタンメッセージの説明文",
    )
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        title: str = "📮 ご意見・改善案はこちら",
        description: str = (
            "村への意見・改善案がある方は下のボタンを押してチケットを発行してください。\n"
            "内容は管理者のみに共有されます。"
        ),
    ):
        embed = discord.Embed(title=title, description=description, color=0x534AB7)
        embed.set_footer(text="チケットの内容は管理者のみに共有されます。")

        await interaction.response.send_message(embed=embed, view=TicketButtonView(self.bot))

    @app_commands.command(name="ticket_log_channel", description="【管理者】チケットログの送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_log_channel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await db_set(ticket_log_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"チケットログ送信先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="ticket_number_reset", description="【管理者】チケット番号をリセットします")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_number_reset(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await db_set(ticket_counter_key(interaction.guild_id), "0")
        await interaction.response.send_message("チケット番号をリセットしました。次のチケットは `001` から始まります。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))
