import io
import re
from datetime import timedelta

import discord
from discord.ext import commands

from cogs.server_logs import send_server_log


TIME_VALUE_RE = re.compile(r"(\d+)\s*(秒|分|時間|日)")
ANALYZE_RE = re.compile(r"(?:この|今の)?チャンネル.*?(?:分析|要約)|(?:分析|要約).*?(?:この|今の)?チャンネル")


def clean_command_text(bot_user: discord.ClientUser, message: discord.Message) -> str:
    return re.sub(rf"<@!?{bot_user.id}>", "", message.content).strip()


def is_admin_mention_command(text: str) -> bool:
    normalized = text.replace("　", " ")
    return bool(
        "タイムアウト" in normalized
        or "キック" in normalized
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
        target: discord.Member,
        *,
        duration: timedelta | None = None,
        role: discord.Role | None = None,
        reason: str | None = None,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.requester_id = requester_id
        self.action = action
        self.target = target
        self.duration = duration
        self.role = role
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
        target: discord.Member,
        *,
        duration: timedelta | None,
        role: discord.Role | None,
        reason: str,
    ) -> tuple[bool, str]:
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

        if ANALYZE_RE.search(text):
            await self.analyze_channel(message)
            return

        targets = [member for member in message.mentions if member.id != self.bot.user.id]
        if not targets:
            await message.reply("命令対象のメンバーもメンションしてください。", mention_author=False)
            return
        target = targets[0]
        reason_match = re.search(r"理由\s*[:：]\s*(.+)$", text)
        reason = reason_match.group(1).strip()[:300] if reason_match else None

        action = None
        duration = None
        role = message.role_mentions[0] if message.role_mentions else None
        required_permission = None
        summary = ""
        timeout_match = TIME_VALUE_RE.search(text)
        if "タイムアウト" in text:
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
