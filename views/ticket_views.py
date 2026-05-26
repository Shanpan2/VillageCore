import asyncio
import re
from io import BytesIO
from pathlib import Path

import discord
from discord.ext import commands

from database.config_db import db_get, db_set


TICKET_OWNER_PREFIX = "ticket_owner_id="
TICKET_LOG_DIR = Path("ticket_logs")


def ticket_log_channel_key(guild_id: int) -> str:
    return f"ticket_log_channel:{guild_id}"


def ticket_counter_key(guild_id: int) -> str:
    return f"ticket_counter:{guild_id}"


def sanitize_channel_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9ぁ-んァ-ン一-龥ー_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:40] or "user"


def sanitize_category_suffix(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^\wぁ-んァ-ン一-龥ー-]+", "", value)
    return value[:80] or "ticket"


async def next_ticket_number(guild_id: int) -> int:
    current = int(await db_get(ticket_counter_key(guild_id)) or "0")
    current += 1
    await db_set(ticket_counter_key(guild_id), str(current))
    return current


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


async def get_or_create_ticket_category(guild: discord.Guild, panel_title: str) -> discord.CategoryChannel | None:
    category_name = f"Tickets_{sanitize_category_suffix(panel_title)}"[:100]
    category = discord.utils.get(guild.categories, name=category_name)
    if category:
        return category

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        return None

    return await guild.create_category(category_name, reason="Ticket category setup")


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


def ticket_log_file_from_path(path: Path) -> discord.File:
    return discord.File(BytesIO(path.read_bytes()), filename=path.name)


async def send_ticket_log_to_archive(
    guild: discord.Guild,
    ticket_channel: discord.TextChannel,
    closed_by: discord.abc.User,
    log_path: Path | None,
):
    raw = await db_get(ticket_log_channel_key(guild.id))
    if not raw or log_path is None or not log_path.exists():
        return

    archive_channel = guild.get_channel(int(raw))
    if not isinstance(archive_channel, discord.TextChannel):
        return

    embed = discord.Embed(title="チケットログ", color=0x534AB7)
    embed.add_field(name="チケット", value=f"#{ticket_channel.name} (`{ticket_channel.id}`)", inline=False)
    embed.add_field(name="閉じた人", value=f"{closed_by.mention} (`{closed_by.id}`)", inline=False)
    await archive_channel.send(embed=embed, file=ticket_log_file_from_path(log_path))


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
        self.add_item(DeleteTicketChannelButton())


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

    def __init__(self, bot: commands.Bot, panel_title: str):
        super().__init__()
        self.bot = bot
        self.panel_title = panel_title

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

        category = await get_or_create_ticket_category(guild, self.panel_title)
        title_slug = sanitize_channel_name(self.panel_title)
        ticket_number = await next_ticket_number(guild.id)
        channel_name = f"{title_slug}_ticket-{ticket_number:03d}"[:100]

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
            topic=(
                f"{TICKET_OWNER_PREFIX}{interaction.user.id} "
                f"status=open ticket_number={ticket_number:03d} ticket_title={title_slug}"
            ),
            reason=f"Ticket created by {interaction.user}",
        )

        embed = discord.Embed(
            title="新しいチケット",
            description=self.description.value,
            color=0x534AB7,
        )
        embed.add_field(name="送信者", value=interaction.user.mention, inline=True)
        embed.add_field(name="チケット番号", value=f"{ticket_number:03d}", inline=True)
        embed.add_field(name="タイトル", value=self.panel_title[:1024], inline=False)
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
        panel_title = "ticket"
        if interaction.message and interaction.message.embeds:
            panel_title = interaction.message.embeds[0].title or panel_title
        await interaction.response.send_modal(TicketModal(self.view.bot, panel_title))


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
            log_path = None
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
        await send_ticket_log_to_archive(interaction.guild, channel, interaction.user, log_path)
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


class DeleteTicketChannelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="チャンネルを削除",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_delete_channel",
        )

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or not interaction.guild:
            await interaction.response.send_message("チケットチャンネルで実行してください。", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member) or not is_ticket_admin(interaction.user):
            await interaction.response.send_message("管理者のみチャンネルを削除できます。", ephemeral=True)
            return

        me = interaction.guild.me
        if not me or not channel.permissions_for(me).manage_channels:
            await interaction.response.send_message("Botにチャンネル管理権限がありません。", ephemeral=True)
            return

        await interaction.response.send_message("3秒後にこのチケットチャンネルを削除します。", ephemeral=True)
        await asyncio.sleep(3)
        await channel.delete(reason=f"Ticket channel deleted by {interaction.user}")
