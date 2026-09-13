import io
import re
from datetime import timedelta

import discord
from discord.ext import commands

from cogs.server_logs import mark_command_deleted_messages, send_server_log, unmark_command_deleted_messages


TIME_VALUE_RE = re.compile(r"(\d+)\s*(秒|分|時間|日)")
MESSAGE_COUNT_RE = re.compile(r"(\d+)\s*件")
USER_ID_RE = re.compile(r"(?:ユーザー\s*)?ID\s*[:：]?\s*(\d{15,22})", re.IGNORECASE)
MESSAGE_LINK_RE = re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
ANALYZE_RE = re.compile(r"(?:この|今の)?チャンネル.*?(?:分析|要約)|(?:分析|要約).*?(?:この|今の)?チャンネル")


def clean_command_text(bot_user: discord.ClientUser, message: discord.Message) -> str:
    return re.sub(rf"<@!?{bot_user.id}>", "", message.content).strip()


def is_admin_mention_command(text: str) -> bool:
    normalized = text.replace("　", " ")
    return bool(
        "タイムアウト" in normalized
        or "キック" in normalized
        or "BAN" in normalized.upper()
        or ("チャンネル" in normalized and "削除" in normalized)
        or ("メッセージ" in normalized and "削除" in normalized)
        or (MESSAGE_LINK_RE.search(normalized) and any(word in normalized for word in ("転送", "スレッド")))
        or ANALYZE_RE.search(normalized)
        or ("ロール" in normalized and any(word in normalized for word in ("付与", "付けて", "つけて", "解除", "外して", "削除")))
    )


def timeout_delta(value: int, unit: str) -> timedelta:
    if unit == "秒":
        return timedelta(seconds=value)
    if unit == "分":
        return timedelta(minutes=value)
    if unit == "時間":
        return timedelta(hours=value)
    return timedelta(days=value)


def display_name(value) -> str:
    return discord.utils.escape_markdown(getattr(value, "display_name", getattr(value, "name", str(value))))


class AdminCommandConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "MentionCommands",
        requester_id: int,
        action: str,
        target: discord.Member | None = None,
        *,
        duration: timedelta | None = None,
        role: discord.Role | None = None,
        channel: discord.abc.GuildChannel | None = None,
        amount: int | None = None,
        before_message_id: int | None = None,
        target_user_id: int | None = None,
        target_label: str | None = None,
        delete_all: bool = False,
        all_channels: bool = False,
        delete_everyone: bool = False,
        reason: str | None = None,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.requester_id = requester_id
        self.action = action
        self.target = target
        self.duration = duration
        self.role = role
        self.channel = channel
        self.amount = amount
        self.before_message_id = before_message_id
        self.target_user_id = target_user_id
        self.target_label = target_label
        self.delete_all = delete_all
        self.all_channels = all_channels
        self.delete_everyone = delete_everyone
        self.reason = reason or "むらびと君へのメンション命令"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("この命令を確定できるのは、命令を出した管理者だけです。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="実行", style=discord.ButtonStyle.danger)
    async def execute(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, result = await self.cog.execute_action(
            interaction.guild,
            interaction.user,
            self.action,
            self.target,
            duration=self.duration,
            role=self.role,
            channel=self.channel,
            amount=self.amount,
            before_message_id=self.before_message_id,
            target_user_id=self.target_user_id,
            target_label=self.target_label,
            delete_all=self.delete_all,
            all_channels=self.all_channels,
            delete_everyone=self.delete_everyone,
            reason=self.reason,
        )
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass
        await interaction.followup.send(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="命令をキャンセルしました。", view=self)


class MentionCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def target_error(self, guild: discord.Guild, actor: discord.Member, target: discord.Member) -> str | None:
        me = guild.me
        if target.id == actor.id:
            return "自分自身には実行できません。"
        if target.id == guild.owner_id:
            return "サーバー所有者には実行できません。"
        if target.bot:
            return "Botにはこの管理命令を実行できません。"
        if actor != guild.owner and target.top_role >= actor.top_role:
            return "自分と同じか、自分より上位のメンバーには実行できません。"
        if not me or target.top_role >= me.top_role:
            return "対象メンバーのロールがむらびと君以上のため実行できません。"
        return None

    async def execute_action(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        action: str,
        target: discord.Member | None,
        *,
        duration: timedelta | None,
        role: discord.Role | None,
        channel: discord.abc.GuildChannel | None,
        amount: int | None,
        before_message_id: int | None,
        target_user_id: int | None,
        target_label: str | None,
        delete_all: bool,
        all_channels: bool,
        delete_everyone: bool,
        reason: str,
    ) -> tuple[bool, str]:
        if action == "message_delete":
            if not actor.guild_permissions.manage_messages:
                return False, "「メッセージの管理」権限が必要です。"
            resolved_target_id = target.id if target else target_user_id
            resolved_target_label = "全ユーザー" if delete_everyone else (
                display_name(target) if target else (target_label or f"ユーザーID {resolved_target_id}")
            )
            if (resolved_target_id is None and not delete_everyone) or (
                not all_channels and not isinstance(channel, discord.TextChannel)
            ):
                return False, "削除対象を取得できませんでした。"
            me = guild.me
            if not me:
                return False, "サーバー内のBot情報を取得できませんでした。"

            channels = guild.text_channels if all_channels else [channel]
            readable_channels = [
                item
                for item in channels
                if item.permissions_for(me).view_channel
                and item.permissions_for(me).read_message_history
                and item.permissions_for(me).manage_messages
            ]
            if not readable_channels:
                return False, "履歴の閲覧とメッセージ削除ができる対象チャンネルがありません。"

            targets = []
            before = discord.Object(id=before_message_id) if before_message_id else None
            try:
                for target_channel in readable_channels:
                    async for item in target_channel.history(limit=None if delete_all else 1000, before=before):
                        if delete_everyone or item.author.id == resolved_target_id:
                            targets.append(item)
            except (discord.Forbidden, discord.HTTPException) as exc:
                return False, f"メッセージ履歴を取得できませんでした: {exc}"

            targets.sort(key=lambda item: item.created_at, reverse=True)
            if not delete_all and amount is not None:
                targets = targets[:amount]

            mark_command_deleted_messages(targets)
            deleted = []
            for item in targets:
                try:
                    await item.delete(reason=f"{reason} / 実行者: {actor} ({actor.id})")
                    deleted.append(item)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    unmark_command_deleted_messages([item])

            embed = discord.Embed(
                title="メンション命令: ユーザーメッセージ削除",
                color=0xE74C3C,
                timestamp=discord.utils.utcnow(),
            )
            target_value = resolved_target_label if delete_everyone else f"{resolved_target_label} (`{resolved_target_id}`)"
            embed.add_field(name="対象", value=target_value, inline=False)
            channel_label = "すべてのテキストチャンネル" if all_channels else f"#{channel.name} (`{channel.id}`)"
            embed.add_field(name="チャンネル", value=channel_label, inline=False)
            embed.add_field(name="実行者", value=f"{display_name(actor)} (`{actor.id}`)", inline=False)
            embed.add_field(name="指定件数", value="すべて" if delete_all else str(amount), inline=True)
            embed.add_field(name="削除件数", value=str(len(deleted)), inline=True)
            embed.add_field(name="理由", value=reason[:1000], inline=False)
            await send_server_log(self.bot, guild, embed, "command_delete")
            return True, f"{resolved_target_label} のメッセージを{len(deleted)}件削除しました。"

        if action == "channel_delete":
            if not actor.guild_permissions.manage_channels:
                return False, "「チャンネルの管理」権限が必要です。"
            if not guild.me or not guild.me.guild_permissions.manage_channels:
                return False, "むらびと君に「チャンネルの管理」権限がありません。"
            if channel is None or channel.guild.id != guild.id:
                return False, "削除対象のチャンネルを取得できませんでした。"

            channel_name = channel.name
            channel_id = channel.id
            try:
                await channel.delete(reason=f"{reason} / 実行者: {actor} ({actor.id})")
            except (discord.Forbidden, discord.HTTPException) as exc:
                return False, f"チャンネルを削除できませんでした: {exc}"
            embed = discord.Embed(
                title="メンション命令: チャンネル削除",
                color=0xE74C3C,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="対象", value=f"#{channel_name} (`{channel_id}`)", inline=False)
            embed.add_field(name="実行者", value=f"{display_name(actor)} (`{actor.id}`)", inline=False)
            embed.add_field(name="理由", value=reason[:1000], inline=False)
            await send_server_log(self.bot, guild, embed, "role_channel")
            return True, f"#{channel_name} を削除しました。"

        if target is None:
            return False, "命令対象のメンバーを取得できませんでした。"

        if action in {"role_give", "role_delete"}:
            if not actor.guild_permissions.manage_roles:
                return False, "「ロールの管理」権限が必要です。"
            role_cog = self.bot.get_cog("RoleAdmin")
            if not role_cog or role is None:
                return False, "ロール管理機能を取得できませんでした。"
            return await role_cog.change_role(
                guild,
                actor,
                target,
                role,
                give=action == "role_give",
                reason=reason,
            )

        error = self.target_error(guild, actor, target)
        if error:
            return False, error

        if action == "timeout":
            if not actor.guild_permissions.moderate_members:
                return False, "「メンバーをタイムアウト」権限が必要です。"
            if not guild.me or not guild.me.guild_permissions.moderate_members:
                return False, "むらびと君に「メンバーをタイムアウト」権限がありません。"
            try:
                await target.timeout(duration, reason=f"{reason} / 実行者: {actor} ({actor.id})")
            except (discord.Forbidden, discord.HTTPException) as exc:
                return False, f"タイムアウトできませんでした: {exc}"
            action_label = f"タイムアウト（{int(duration.total_seconds())}秒）"
        elif action == "kick":
            if not actor.guild_permissions.kick_members:
                return False, "「メンバーをキック」権限が必要です。"
            if not guild.me or not guild.me.guild_permissions.kick_members:
                return False, "むらびと君に「メンバーをキック」権限がありません。"
            try:
                await target.kick(reason=f"{reason} / 実行者: {actor} ({actor.id})")
            except (discord.Forbidden, discord.HTTPException) as exc:
                return False, f"キックできませんでした: {exc}"
            action_label = "キック"
        elif action == "ban":
            if not actor.guild_permissions.ban_members:
                return False, "「メンバーをBAN」権限が必要です。"
            if not guild.me or not guild.me.guild_permissions.ban_members:
                return False, "むらびと君に「メンバーをBAN」権限がありません。"
            try:
                await guild.ban(target, reason=f"{reason} / 実行者: {actor} ({actor.id})")
            except (discord.Forbidden, discord.HTTPException) as exc:
                return False, f"BANできませんでした: {exc}"
            action_label = "BAN"
        else:
            return False, "未対応の命令です。"

        embed = discord.Embed(title=f"メンション命令: {action_label}", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="対象", value=f"{display_name(target)} (`{target.id}`)", inline=False)
        embed.add_field(name="実行者", value=f"{display_name(actor)} (`{actor.id}`)", inline=False)
        embed.add_field(name="理由", value=reason[:1000], inline=False)
        await send_server_log(self.bot, guild, embed, "moderation")
        return True, f"{display_name(target)} さんを{action_label}しました。"

    async def analyze_channel(self, message: discord.Message):
        if not isinstance(message.author, discord.Member) or not message.author.guild_permissions.manage_messages:
            await message.reply("チャンネル分析には「メッセージの管理」権限が必要です。", mention_author=False)
            return
        if not isinstance(message.channel, discord.TextChannel):
            await message.reply("テキストチャンネルで実行してください。", mention_author=False)
            return

        status = await message.reply("直近100件のメッセージを分析しています...", mention_author=False)
        try:
            history = [
                item
                async for item in message.channel.history(limit=101, before=message, oldest_first=True)
                if not item.author.bot and (item.content or item.attachments)
            ][-100:]
        except discord.Forbidden:
            await status.edit(content="メッセージ履歴を読む権限がありません。")
            return
        if not history:
            await status.edit(content="分析できるメッセージがありませんでした。")
            return

        minutes_cog = self.bot.get_cog("Minutes")
        if not minutes_cog:
            await status.edit(content="分析機能を取得できませんでした。")
            return
        source, participants = minutes_cog.build_source_text(history)
        summary = await minutes_cog.summarize("チャンネル分析", source, participants, len(history))
        output = f"**チャンネル分析（直近{len(history)}件）**\n\n{summary}"
        if len(output) <= 1900:
            await status.edit(content=output, allowed_mentions=discord.AllowedMentions.none())
        else:
            await status.edit(content="分析結果が長いため、テキストファイルで出力します。")
            await message.channel.send(
                file=discord.File(io.BytesIO(output.encode("utf-8")), filename="channel_analysis.txt"),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def handle_message_link_command(self, message: discord.Message, text: str) -> bool:
        match = MESSAGE_LINK_RE.search(text)
        if not match or not isinstance(message.author, discord.Member):
            return False
        guild_id, channel_id, message_id = map(int, match.groups())
        if not message.guild or guild_id != message.guild.id:
            await message.reply("同じサーバー内のメッセージリンクを指定してください。", mention_author=False)
            return True
        if not message.author.guild_permissions.manage_messages:
            await message.reply("この命令には「メッセージの管理」権限が必要です。", mention_author=False)
            return True

        source_channel = message.guild.get_channel_or_thread(channel_id)
        if not isinstance(source_channel, (discord.TextChannel, discord.Thread)):
            await message.reply("リンク元のチャンネルを取得できませんでした。", mention_author=False)
            return True
        try:
            source = await source_channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await message.reply("リンク先のメッセージを取得できませんでした。", mention_author=False)
            return True

        if "転送" in text:
            destination = message.channel_mentions[0] if message.channel_mentions else None
            if not isinstance(destination, discord.TextChannel):
                await message.reply("転送先のテキストチャンネルをメンションしてください。", mention_author=False)
                return True
            me = message.guild.me
            if not me or not destination.permissions_for(me).send_messages:
                await message.reply("むらびと君が転送先へメッセージを送信できません。", mention_author=False)
                return True
            embed = discord.Embed(
                description=(source.content or "本文なし")[:4000],
                color=0x3498DB,
                timestamp=source.created_at,
            )
            embed.set_author(
                name=f"{source.author} から転送",
                icon_url=source.author.display_avatar.url,
            )
            links = [attachment.url for attachment in source.attachments]
            if links:
                embed.add_field(name="添付ファイル", value="\n".join(links)[:1024], inline=False)
                if source.attachments[0].content_type and source.attachments[0].content_type.startswith("image/"):
                    embed.set_image(url=source.attachments[0].url)
            embed.add_field(name="元のメッセージ", value=f"[開く]({source.jump_url})", inline=False)
            try:
                forwarded = await destination.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException) as exc:
                await message.reply(f"転送できませんでした: {exc}", mention_author=False)
                return True
            await message.reply(f"{destination.mention} に転送しました: {forwarded.jump_url}", mention_author=False)
            return True

        if "スレッド" in text:
            if not isinstance(source.channel, discord.TextChannel):
                await message.reply("通常のテキストチャンネルにあるメッセージを指定してください。", mention_author=False)
                return True
            name_match = re.search(r"[「『\"]([^」』\"]{1,100})[」』\"]", text)
            thread_name = name_match.group(1).strip() if name_match else f"{source.author.display_name}のメッセージ"
            try:
                thread = await source.create_thread(name=thread_name[:100], reason=f"作成者: {message.author} ({message.author.id})")
            except (discord.Forbidden, discord.HTTPException) as exc:
                await message.reply(f"スレッドを作成できませんでした: {exc}", mention_author=False)
                return True
            await message.reply(f"スレッドを作成しました: {thread.mention}", mention_author=False)
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.bot
            or not message.guild
            or not self.bot.user
            or not any(user.id == self.bot.user.id for user in message.mentions)
        ):
            return
        text = clean_command_text(self.bot.user, message).replace("　", " ")
        if not is_admin_mention_command(text):
            return
        if not isinstance(message.author, discord.Member):
            return

        if await self.handle_message_link_command(message, text):
            return

        if ANALYZE_RE.search(text):
            await self.analyze_channel(message)
            return

        targets = [member for member in message.mentions if member.id != self.bot.user.id]
        target = targets[0] if targets else None
        user_id_match = USER_ID_RE.search(text)
        target_user_id = int(user_id_match.group(1)) if user_id_match else None
        target_label = f"ユーザーID {target_user_id}" if target_user_id else None
        channel = message.channel_mentions[0] if message.channel_mentions else None
        reason_match = re.search(r"理由\s*[:：]\s*(.+)$", text)
        reason = reason_match.group(1).strip()[:300] if reason_match else None

        action = None
        duration = None
        role = message.role_mentions[0] if message.role_mentions else None
        amount = None
        delete_all = False
        all_channels = False
        delete_everyone = False
        required_permission = None
        summary = ""
        timeout_match = TIME_VALUE_RE.search(text)
        if "メッセージ" in text and "削除" in text:
            delete_all = any(
                word in text
                for word in ("すべて削除", "全部削除", "全削除", "すべてのメッセージ", "全メッセージ")
            )
            delete_everyone = target is None and target_user_id is None and delete_all
            if target is None and target_user_id is None and not delete_everyone:
                await message.reply(
                    "削除対象をユーザーメンションまたは `ユーザーID:123456789012345678` で指定してください。",
                    mention_author=False,
                )
                return
            all_channels = "すべてのチャンネル" in text or "全チャンネル" in text
            target_channel = channel or message.channel
            if not all_channels and not isinstance(target_channel, discord.TextChannel):
                await message.reply("削除対象にはテキストチャンネルを指定してください。", mention_author=False)
                return
            count_match = MESSAGE_COUNT_RE.search(text)
            amount = int(count_match.group(1)) if count_match else (None if delete_all else 10)
            if amount is not None and not 1 <= amount <= 100:
                await message.reply("削除件数は1～100件で指定してください。", mention_author=False)
                return
            channel = target_channel
            action = "message_delete"
            required_permission = (
                message.author.guild_permissions.administrator
                if delete_everyone
                else message.author.guild_permissions.manage_messages
            )
            shown_target = "全ユーザー" if delete_everyone else (display_name(target) if target else target_label)
            scope = "すべてのテキストチャンネル" if all_channels else f"#{channel.name}"
            count_label = "すべて" if delete_all else f"最大{amount}件"
            summary = f"{scope}にある {shown_target} のメッセージを{count_label}削除"
        elif "チャンネル" in text and "削除" in text:
            if channel is None:
                await message.reply("削除するチャンネルをメンションしてください。例: `#チャンネルを削除して`", mention_author=False)
                return
            action = "channel_delete"
            required_permission = message.author.guild_permissions.manage_channels
            summary = f"#{channel.name} を削除"
        elif target is None:
            await message.reply("命令対象のメンバーもメンションしてください。", mention_author=False)
            return
        elif "タイムアウト" in text:
            value = int(timeout_match.group(1)) if timeout_match else 10
            unit = timeout_match.group(2) if timeout_match else "分"
            duration = timeout_delta(value, unit)
            if value <= 0 or duration > timedelta(days=28):
                await message.reply("タイムアウト時間は1秒以上28日以内で指定してください。", mention_author=False)
                return
            action = "timeout"
            required_permission = message.author.guild_permissions.moderate_members
            summary = f"{display_name(target)} さんを {value}{unit}タイムアウト"
        elif "キック" in text:
            action = "kick"
            required_permission = message.author.guild_permissions.kick_members
            summary = f"{display_name(target)} さんをキック"
        elif "BAN" in text.upper():
            action = "ban"
            required_permission = message.author.guild_permissions.ban_members
            summary = f"{display_name(target)} さんをBAN"
        elif role and any(word in text for word in ("付与", "付けて", "つけて")):
            action = "role_give"
            required_permission = message.author.guild_permissions.manage_roles
            summary = f"{display_name(target)} さんへ @{display_name(role)} を付与"
        elif role and any(word in text for word in ("解除", "外して", "削除")):
            action = "role_delete"
            required_permission = message.author.guild_permissions.manage_roles
            summary = f"{display_name(target)} さんから @{display_name(role)} を解除"

        if not action:
            await message.reply(
                "命令を認識できませんでした。対象メンバー・時間・ロールを確認してください。",
                mention_author=False,
            )
            return
        if not required_permission:
            await message.reply("この命令を実行する管理権限がありません。", mention_author=False)
            return

        view = AdminCommandConfirmView(
            self,
            message.author.id,
            action,
            target,
            duration=duration,
            role=role,
            channel=channel,
            amount=amount,
            before_message_id=message.id,
            target_user_id=target_user_id,
            target_label=target_label,
            delete_all=delete_all,
            all_channels=all_channels,
            delete_everyone=delete_everyone,
            reason=reason,
        )
        reason_text = f"\n理由: {reason}" if reason else ""
        await message.reply(
            f"次の管理命令を実行しますか？\n**{summary}**{reason_text}",
            view=view,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MentionCommands(bot))
