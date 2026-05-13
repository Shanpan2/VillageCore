# features/ticket.py

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db_get_config, db_set_config
from core.utils import check_admin, is_admin, get_admin_role_name


# ============================================================
# 🎫 チケットシステム（分割構成用）
# ============================================================

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
        if not await check_admin(interaction):
            return

        # ==========================
        # Ticket Button View
        # ==========================
        class TicketButtonView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label="📩 チケットを発行する", style=discord.ButtonStyle.primary, custom_id="ticket_create")
            async def create_ticket(self, inter: discord.Interaction, button: discord.ui.Button):

                # チケット番号
                ticket_num_str = await db_get_config("ticket_counter")
                ticket_num = int(ticket_num_str) + 1 if ticket_num_str else 1
                await db_set_config("ticket_counter", str(ticket_num))
                ticket_id = f"{ticket_num:02d}"

                # 管理者ロール
                admin_role_name = await get_admin_role_name(inter.guild.id)
                admin_role = discord.utils.get(inter.guild.roles, name=admin_role_name)

                # カテゴリ
                category = discord.utils.get(inter.guild.categories, name="📮 チケット")
                if category is None:
                    category = await inter.guild.create_category(
                        "📮 チケット",
                        overwrites={
                            inter.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                            inter.guild.me: discord.PermissionOverwrite(view_channel=True),
                        }
                    )

                # チャンネル作成
                channel = await inter.guild.create_text_channel(
                    name=f"ticket-{ticket_id}-{inter.user.name.lower().replace(' ', '-')}",
                    category=category,
                    overwrites={
                        inter.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                        inter.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                        admin_role: discord.PermissionOverwrite(view_channel=True, send_messages=True) if admin_role else None
                    },
                    topic=f"チケット#{ticket_id} | {inter.user.display_name}"
                )

                # ==========================
                # Modal
                # ==========================
                class TicketInputModal(discord.ui.Modal, title="ご意見・改善案の入力"):
                    content_input = discord.ui.TextInput(
                        label="内容",
                        placeholder="村への意見・改善案などを自由にご記入ください",
                        style=discord.TextStyle.long,
                        max_length=1000
                    )

                    async def on_submit(self, modal_inter: discord.Interaction):

                        embed = discord.Embed(
                            title=f"📮 チケット #{ticket_id}",
                            description=self.content_input.value,
                            color=0x534AB7
                        )
                        embed.set_author(
                            name=inter.user.display_name,
                            icon_url=inter.user.display_avatar.url
                        )

                        # ==========================
                        # Close / Delete View
                        # ==========================
                        class CloseView(discord.ui.View):
                            def __init__(self):
                                super().__init__(timeout=None)

                            @discord.ui.button(label="✅ チケットを閉じる", style=discord.ButtonStyle.success)
                            async def close_btn(self, close_inter: discord.Interaction, btn):
                                if not await is_admin(close_inter) and close_inter.user.id != inter.user.id:
                                    await close_inter.response.send_message("❌ 権限がありません。", ephemeral=True)
                                    return

                                new_overwrites = channel.overwrites.copy()

                                new_overwrites[inter.user] = discord.PermissionOverwrite(
                                    view_channel=True,
                                    send_messages=False
                                )

                                if admin_role:
                                    new_overwrites[admin_role] = discord.PermissionOverwrite(
                                        view_channel=True,
                                        send_messages=True
                                    )

                                new_overwrites[inter.guild.default_role] = discord.PermissionOverwrite(
                                    view_channel=False
                                )

                                await channel.edit(overwrites=new_overwrites)
                                await close_inter.response.send_message("🗂️ チケットをクローズしました。", ephemeral=True)

                            @discord.ui.button(label="🗑️ チャンネルを削除する", style=discord.ButtonStyle.danger)
                            async def delete_btn(self, close_inter: discord.Interaction, btn):
                                if not await is_admin(close_inter):
                                    await close_inter.response.send_message("❌ 管理者のみ使用できます。", ephemeral=True)
                                    return
                                await close_inter.response.send_message("🗑️ 削除します...", ephemeral=True)
                                await channel.delete()

                        await channel.send(
                            content=f"{inter.user.mention} {admin_role.mention if admin_role else ''}",
                            embed=embed,
                            view=CloseView()
                        )

                        await modal_inter.response.send_message(
                            f"✅ チケット #{ticket_id} を作成しました！\n{channel.mention}",
                            ephemeral=True
                        )

                await inter.response.send_modal(TicketInputModal())

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x534AB7
        )
        embed.set_footer(text="チケットの内容は管理者のみに共有されます。")

        await interaction.response.send_message(embed=embed, view=TicketButtonView())
