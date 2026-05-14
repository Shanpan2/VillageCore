import discord
from discord.ext import commands
from discord import app_commands

from views.ticket_views import TicketButtonView, TicketManageView


class Ticket(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------
    # /ticket_setup
    # -------------------------------------------------------
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

        await interaction.response.send_message(
            embed=embed, view=TicketButtonView(self.bot)
        )

    # -------------------------------------------------------
    # on_interaction でチケット作成を処理
    # -------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        if not (inter.data and inter.data.get("custom_id") == "ticket_create"):
            return

        user = inter.user
        guild = inter.guild

        # カテゴリ取得 or 作成
        category = discord.utils.get(guild.categories, name="📮 チケット")
        if category is None:
            category = await guild.create_category(
                "📮 チケット",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True),
                },
            )

        existing = [c for c in category.channels if c.name.startswith("ticket-")]
        ticket_id = f"{len(existing) + 1:02d}"

        channel = await guild.create_text_channel(
            name=f"ticket-{ticket_id}-{user.name.lower().replace(' ', '-')}",
            category=category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
            topic=f"チケット#{ticket_id} | {user.display_name}",
        )

        # モーダル定義（クロージャで channel / ticket_id / user を参照）
        class TicketModal(discord.ui.Modal, title="ご意見・改善案の入力"):
            content = discord.ui.TextInput(
                label="内容",
                placeholder="村への意見・改善案などを自由にご記入ください",
                style=discord.TextStyle.long,
                max_length=1000,
            )

            async def on_submit(self, modal_inter: discord.Interaction):
                embed = discord.Embed(
                    title=f"📮 チケット #{ticket_id}",
                    description=self.content.value,
                    color=0x534AB7,
                )
                embed.set_author(
                    name=user.display_name,
                    icon_url=user.display_avatar.url,
                )

                view = TicketManageView(user, channel)
                await channel.send(content=f"{user.mention}", embed=embed, view=view)

                await modal_inter.response.send_message(
                    f"✅ チケット #{ticket_id} を作成しました！\n{channel.mention}",
                    ephemeral=True,
                )

        await inter.response.send_modal(TicketModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))
