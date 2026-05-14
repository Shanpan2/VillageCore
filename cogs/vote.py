import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import asyncio

PREFIX = "投票-"  # ロール名につける prefix


# ==========================
# 投票ボタン
# ==========================
class VoteButton(Button):
    def __init__(self, label: str, vote_view: "VoteView"):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.vote_view = vote_view

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        option = self.label

        role_name = f"{PREFIX}{option}"
        role = discord.utils.get(guild.roles, name=role_name)

        # ロールが無ければ作成
        if role is None:
            role = await guild.create_role(name=role_name)

        # トグル式：すでに投票済みなら取り消し
        if user.id in self.vote_view.votes[option]:
            self.vote_view.votes[option].discard(user.id)
            await user.remove_roles(role)
            msg_text = f"↩️ **{option}** の投票を取り消しました。"
        else:
            self.vote_view.votes[option].add(user.id)
            await user.add_roles(role)
            msg_text = f"🗳️ **{option}** に投票しました！"

        # Embed 更新
        embed = self.vote_view.message.embeds[0]
        embed.description = "\n".join(
            f"{opt}: **{len(self.vote_view.votes[opt])}票**"
            for opt in self.vote_view.options
        )
        await self.vote_view.message.edit(embed=embed)

        await interaction.response.send_message(msg_text, ephemeral=True)


# ==========================
# 投票ビュー
# ==========================
class VoteView(View):
    def __init__(self, options: list[str], message: discord.Message, cog: "Vote"):
        super().__init__(timeout=None)
        self.options = options
        self.message = message
        self.cog = cog
        self.votes: dict[str, set] = {opt: set() for opt in options}

        for opt in options:
            self.add_item(VoteButton(opt, self))


# ==========================
# Cog 本体
# ==========================
class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # message_id: {"options": [...], "channel_id": int, "view": VoteView}
        self.active_votes: dict[int, dict] = {}

    # -------------------------------------------------------
    # /vote  question options... [duration]
    # -------------------------------------------------------
    @app_commands.command(name="vote", description="投票を開始します")
    @app_commands.describe(
        question="投票のタイトル・質問",
        options="選択肢をスペース区切りで入力（例: りんご バナナ みかん）",
        duration="自動終了までの時間（例: 30s / 5m / 1h）省略で無制限",
    )
    async def vote(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        duration: str = None,
    ):
        opts = options.split()
        if len(opts) < 2:
            await interaction.response.send_message(
                "❌ 選択肢は2つ以上スペース区切りで入力してください。", ephemeral=True
            )
            return

        # 時間解析
        seconds = self._parse_duration(duration) if duration else None

        embed = discord.Embed(
            title=f"📊 投票：{question}",
            description="\n".join(f"{opt}: **0票**" for opt in opts),
            color=0x00FFCC,
        )
        if seconds:
            embed.set_footer(text=f"⏰ {duration} 後に自動終了")

        # まず応答してからメッセージを取得
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        view = VoteView(opts, msg, self)
        await msg.edit(view=view)

        self.active_votes[msg.id] = {
            "options": opts,
            "channel_id": interaction.channel.id,
            "view": view,
        }

        if seconds:
            asyncio.create_task(
                self._auto_end(interaction.guild, msg.id, seconds)
            )

    # -------------------------------------------------------
    # /vote_end  message_id
    # -------------------------------------------------------
    @app_commands.command(name="vote_end", description="投票を手動で終了します")
    @app_commands.describe(message_id="終了させたい投票メッセージのID")
    @app_commands.default_permissions(manage_roles=True)
    async def vote_end(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                "❌ メッセージIDは数値で入力してください。", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        result = await self._end_vote(interaction.guild, interaction.channel, mid)
        await interaction.followup.send(result, ephemeral=True)

    # -------------------------------------------------------
    # 内部処理
    # -------------------------------------------------------
    async def _auto_end(self, guild: discord.Guild, message_id: int, seconds: int):
        await asyncio.sleep(seconds)
        if message_id in self.active_votes:
            channel_id = self.active_votes[message_id]["channel_id"]
            channel = guild.get_channel(channel_id)
            await self._end_vote(guild, channel, message_id)

    async def _end_vote(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: int,
    ) -> str:
        if message_id not in self.active_votes:
            return "❌ その投票は見つかりません（すでに終了済みかもしれません）。"

        data = self.active_votes.pop(message_id)
        options: list[str] = data["options"]
        view: VoteView = data["view"]

        results = {opt: len(view.votes[opt]) for opt in options}

        # ロール削除
        deleted = []
        for opt in options:
            role = discord.utils.get(guild.roles, name=f"{PREFIX}{opt}")
            if role:
                await role.delete()
                deleted.append(role.name)

        # 元メッセージを終了表示に変更
        try:
            msg = await channel.fetch_message(message_id)
            embed = msg.embeds[0]
            embed.title = embed.title.replace("📊", "📕") + "（終了）"
            embed.color = 0xFF5555
            await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        # 結果メッセージ
        result_lines = "\n".join(
            f"**{opt}** → {results[opt]}票" for opt in options
        )
        deleted_text = (
            f"\n🗑️ 削除されたロール: {', '.join(deleted)}" if deleted else ""
        )
        await channel.send(f"📕 **投票結果**\n{result_lines}{deleted_text}")

        return "✅ 投票を終了しました。"

    @staticmethod
    def _parse_duration(t: str) -> int | None:
        """'30s' '5m' '1h' などを秒数に変換。解析失敗時は None を返す"""
        sec = 0
        num = ""
        found = False
        for c in t:
            if c.isdigit():
                num += c
            elif c in ("s", "m", "h") and num:
                found = True
                if c == "s":
                    sec += int(num)
                elif c == "m":
                    sec += int(num) * 60
                elif c == "h":
                    sec += int(num) * 3600
                num = ""
        return sec if found else None


async def setup(bot: commands.Bot):
    await bot.add_cog(Vote(bot))
