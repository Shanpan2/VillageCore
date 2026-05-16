import re

import discord
from discord.ext import commands


TICKET_OWNER_PREFIX = "ticket_owner_id="


def sanitize_channel_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9ぁ-んァ-ン一-龥ー_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:40] or "user"


def is_ticket_admin(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.manage_channels


def get_ticket_owner_id(channel: discord.TextChannel) -> int | None:
    topic = channel.topic or ""
    for part in topic.split():
        if part.startswith(TICKET_OWNER_PREFIX):
            try:
                return int(part.removeprefix(TICKET_OWNER_PREFIX))
            except ValueError:
                return None
    return None


async def get_or_create_ticket_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    category = discord.utils.get(guild.categories, name="Tickets")
    if category:
        return category

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        return None

    return await guild.create_category("Tickets", reason="Ticket category setup")


class TicketButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketButton())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())


class ClosedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ReopenTicketButton())


class TicketModal(discord.ui.Modal, title="チケットを作成"):
    subject = discord.ui.TextInput(
        label="件名",
        style=discord.TextStyle.short,
        max_length=100,
        placeholder="件名を入力してください",
    )
    description = discord.ui.TextInput(
        label="詳細",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        placeholder="チケットの内容を詳しく入力してください",
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ サーバー内で実行してください。", ephemeral=True)
            return

        me = guild.me
        if not me or not me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ Botにチャンネル管理権限がありません。", ephemeral=True
            )
            return

        category = await get_or_create_ticket_category(guild)
        base_name = sanitize_channel_name(interaction.user.display_name)
        channel_name = f"ticket-{base_name}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"{TICKET_OWNER_PREFIX}{interaction.user.id} status=open",
            reason=f"Ticket created by {interaction.user}",
        )

        embed = discord.Embed(
            title="🎫 新しいチケット",
            description=self.description.value,
            color=0x534AB7,
        )
        embed.add_field(name="送信者", value=interaction.user.mention, inline=True)
        embed.add_field(name="件名", value=self.subject.value, inline=False)
        embed.set_footer(text="対応が完了したら「チケットを閉じる」を押してください。")

        await channel.send(
            content=f"{interaction.user.mention} チケットを作成しました。",
            embed=embed,
            view=TicketControlView(),
        )
        await interaction.response.send_message(
            f"✅ チケットを作成しました: {channel.mention}", ephemeral=True
        )


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📩 チケットを作成",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_button",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal(self.view.bot))


class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="チケットを閉じる",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close",
        )

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or not interaction.guild:
            await interaction.response.send_message("❌ チケットチャンネルで実行してください。", ephemeral=True)
            return

        owner_id = get_ticket_owner_id(channel)
        is_owner = owner_id == interaction.user.id
        if not is_owner and not is_ticket_admin(interaction.user):
            await interaction.response.send_message("❌ このチケットを閉じる権限がありません。", ephemeral=True)
            return

        owner = interaction.guild.get_member(owner_id) if owner_id else None
        if owner:
            await channel.set_permissions(
                owner,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
                reason=f"Ticket closed by {interaction.user}",
            )

        if not channel.name.startswith("closed-"):
            try:
                await channel.edit(
                    name=f"closed-{channel.name}"[:100],
                    topic=f"{TICKET_OWNER_PREFIX}{owner_id} status=closed",
                    reason=f"Ticket closed by {interaction.user}",
                )
            except discord.HTTPException:
                await channel.edit(
                    topic=f"{TICKET_OWNER_PREFIX}{owner_id} status=closed",
                    reason=f"Ticket closed by {interaction.user}",
                )

        embed = discord.Embed(
            title="🔒 チケットを閉じました",
            description="管理者は下のボタンから再オープンできます。",
            color=0xE67E22,
        )
        await interaction.response.send_message(embed=embed, view=ClosedTicketView())


class ReopenTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="再オープン",
            style=discord.ButtonStyle.success,
            custom_id="ticket_reopen",
        )

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or not interaction.guild:
            await interaction.response.send_message("❌ チケットチャンネルで実行してください。", ephemeral=True)
            return

        if not is_ticket_admin(interaction.user):
            await interaction.response.send_message("❌ 管理者のみ再オープンできます。", ephemeral=True)
            return

        owner_id = get_ticket_owner_id(channel)
        owner = interaction.guild.get_member(owner_id) if owner_id else None
        if owner:
            await channel.set_permissions(
                owner,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                reason=f"Ticket reopened by {interaction.user}",
            )

        new_name = channel.name.removeprefix("closed-")
        try:
            await channel.edit(
                name=new_name,
                topic=f"{TICKET_OWNER_PREFIX}{owner_id} status=open",
                reason=f"Ticket reopened by {interaction.user}",
            )
        except discord.HTTPException:
            await channel.edit(
                topic=f"{TICKET_OWNER_PREFIX}{owner_id} status=open",
                reason=f"Ticket reopened by {interaction.user}",
            )

        embed = discord.Embed(
            title="🔓 チケットを再オープンしました",
            description="ユーザーが再びこのチャンネルを閲覧・送信できます。",
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, view=TicketControlView())
