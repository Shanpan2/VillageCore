import discord
from discord import app_commands
from discord.ext import commands
from views.ticket_views import TicketButtonView


def setup_ticket_system(bot: commands.Bot):

    @bot.tree.command(name="ticket_setup", description="【管理者】チケット発行ボタンを設置します")
    @app_commands.describe(
        title="ボタンメッセージのタイトル",
        description="ボタンメッセージの説明文"
    )
    async def ticket_setup(
        interaction: discord.Interaction,
        title: str = "📮 ご意見・改善案はこちら",
        description: str = "村への意見・改善案がある方は下のボタンを押してチケットを発行してください。\n内容は管理者のみに共有されます。"
    ):

        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ このコマンドは管理者のみ使用できます。", ephemeral=True)
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x534AB7
        )
        embed.set_footer(text="チケットの内容は管理者のみに共有されます。")

        await interaction.response.send_message(
            embed=embed,
            view=TicketButtonView(bot)
        )


    # ============================================================
    # 🎫 チケット作成処理（View の custom_id を拾う）
    # ============================================================
    @bot.event
    async def on_interaction(inter: discord.Interaction):

        if inter.data and inter.data.get("custom_id") == "ticket_create":

            user = inter.user
            guild = inter.guild

            category = discord.utils.get(guild.categories, name="📮 チケット")
            if category is None:
                category = await guild.create_category(
                    "📮 チケット",
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True),
                    }
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
                topic=f"チケット#{ticket_id} | {user.display_name}"
            )

            class TicketModal(discord.ui.Modal, title="ご意見・改善案の入力"):
                content = discord.ui.TextInput(
                    label="内容",
                    placeholder="村への意見・改善案などを自由にご記入ください",
                    style=discord.TextStyle.long,
                    max_length=1000
                )

                async def on_submit(self, modal_inter: discord.Interaction):

                    embed = discord.Embed(
                        title=f"📮 チケット #{ticket_id}",
                        description=self.content.value,
                        color=0x534AB7
                    )
                    embed.set_author(
                        name=user.display_name,
                        icon_url=user.display_avatar.url
                    )

                    from views.ticket_views import TicketManageView
                    view = TicketManageView(user, channel)

                    await channel.send(
                        content=f"{user.mention}",
                        embed=embed,
                        view=view
                    )

                    await modal_inter.response.send_message(
                        f"✅ チケット #{ticket_id} を作成しました！\n{channel.mention}",
                        ephemeral=True
                    )

            await inter.response.send_modal(TicketModal())



