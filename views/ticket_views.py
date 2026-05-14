# views/ticket_views.py

import discord


# ============================================================
# 📩 チケット作成ボタン（パネル側）
# ============================================================

class TicketButtonView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="📩 チケットを発行する",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_create",
    )
    async def create_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
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

        await inter.response.send_modal(
            TicketInputModal(user=user, channel=channel, ticket_id=ticket_id)
        )


# ============================================================
# 📝 モーダル（チケット内容入力）
# ============================================================

class TicketInputModal(discord.ui.Modal, title="ご意見・改善案の入力"):
    content_input = discord.ui.TextInput(
        label="内容",
        placeholder="村への意見・改善案などを自由にご記入ください",
        style=discord.TextStyle.long,
        max_length=1000,
    )

    def __init__(self, user: discord.Member, channel: discord.TextChannel, ticket_id: str):
        super().__init__()
        self.user = user
        self.channel = channel
        self.ticket_id = ticket_id

    async def on_submit(self, modal_inter: discord.Interaction):
        embed = discord.Embed(
            title=f"📮 チケット #{self.ticket_id}",
            description=self.content_input.value,
            color=0x534AB7,
        )
        embed.set_author(
            name=self.user.display_name,
            icon_url=self.user.display_avatar.url,
        )

        view = TicketManageView(self.user, self.channel)
        await self.channel.send(content=f"{self.user.mention}", embed=embed, view=view)

        await modal_inter.response.send_message(
            f"✅ チケット #{self.ticket_id} を作成しました！\n{self.channel.mention}",
            ephemeral=True,
        )


# ============================================================
# 🗂️ チケット管理（閉じる / 削除）
# ============================================================

class TicketManageView(discord.ui.View):
    def __init__(self, user: discord.Member, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel

    @discord.ui.button(label="✅ チケットを閉じる", style=discord.ButtonStyle.success)
    async def close_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        if inter.user != self.user and not inter.user.guild_permissions.manage_channels:
            await inter.response.send_message("❌ 権限がありません。", ephemeral=True)
            return

        new_overwrites = self.channel.overwrites.copy()
        new_overwrites[self.user] = discord.PermissionOverwrite(
            view_channel=True, send_messages=False
        )
        new_overwrites[self.channel.guild.default_role] = discord.PermissionOverwrite(
            view_channel=False
        )

        await self.channel.edit(overwrites=new_overwrites)
        await inter.response.send_message("🗂️ チケットをクローズしました。", ephemeral=True)

    @discord.ui.button(label="🗑️ チャンネルを削除する", style=discord.ButtonStyle.danger)
    async def delete_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not inter.user.guild_permissions.manage_channels:
            await inter.response.send_message("❌ 管理者のみ使用できます。", ephemeral=True)
            return

        await inter.response.send_message("🗑️ 削除します...", ephemeral=True)
        await self.channel.delete()
