import discord
from discord.ext import commands
from discord import app_commands

from views.ticket_views import TicketButtonView


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


async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))
