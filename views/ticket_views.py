import re
from io import BytesIO
from pathlib import Path

import discord
from discord.ext import commands


TICKET_OWNER_PREFIX = "ticket_owner_id="
TICKET_LOG_DIR = Path("ticket_logs")


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


async def create_ticket_log(channel: discord.TextChannel, closed_by: discord.abc.User) -> tuple[discord.File, Path]:
    lines = [
        f"Ticket Log: #{channel.name}",
        f"Guild: {channel.guild.name} ({channel.guild.id})",
        f"Channel ID: {channel.id}",
        f"Closed by: {closed_by} ({closed_by.id})",
        "-" * 60,
        "",
    ]

    async for message in channel.history(limit=None, oldest_first=True):
        created_at = message.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        author = f"{message.author} ({message.author.id})"
        content = message.content or ""
        lines.append(f"[{created_at}] {author}")
        if content:
            lines.append(content)
        for embed in message.embeds:
            if embed.title:
                lines.append(f"[Embed Title] {embed.title}")
            if embed.description:
                lines.append(f"[Embed Description] {embed.description}")
            for field in embed.fields:
                lines.append(f"[Embed Field] {field.name}: {field.value}")
        for attachment in message.attachments:
            lines.append(f"[Attachment] {attachment.filename}: {attachment.url}")
        lines.append("")

    text = "\n".join(lines)
    safe_name = sanitize_channel_name(channel.name)
    file_name = f"{safe_name}-{channel.id}.txt"
    TICKET_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = TICKET_LOG_DIR / file_name
    path.write_text(text, encoding="utf-8")
    return discord.File(BytesIO(text.encode("utf-8")), filename=file_name), path


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
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        me = guild.me
        if not me or not me.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "Botにチャンネル管理権限がありません。",
                ephemeral=True,
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
            title="新しいチケット",
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
            f"チケットを作成しました: {channel.mention}",
            ephemeral=True,
        )


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="チケットを作成",
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
            await interaction.response.send_message("チケットチャンネルで実行してください。", ephemeral=True)
            return

        owner_id = get_ticket_owner_id(channel)
        is_owner = owner_id == interaction.user.id
        if not is_owner and not is_ticket_admin(interaction.user):
            await interaction.response.send_message("このチケットを閉じる権限がありません。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            log_file, log_path = await create_ticket_log(channel, interaction.user)
            log_note = f"ログ保存先: `{log_path}`"
        except Exception as e:
            log_file = None
            log_note = f"ログ保存に失敗しました: `{type(e).__name__}: {e}`"

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
            title="チケットを閉じました",
            description="管理者は下のボタンから再オープンできます。\n" + log_note,
            color=0xE67E22,
        )
        files = [log_file] if log_file else []
        await channel.send(embed=embed, view=ClosedTicketView(), files=files)
        await interaction.followup.send("チケットを閉じました。", ephemeral=True)


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
            await interaction.response.send_message("チケットチャンネルで実行してください。", ephemeral=True)
            return

        if not is_ticket_admin(interaction.user):
            await interaction.response.send_message("管理者のみ再オープンできます。", ephemeral=True)
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
            title="チケットを再オープンしました",
            description="ユーザーが再びこのチャンネルを閲覧・送信できます。",
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, view=TicketControlView())
