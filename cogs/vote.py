import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

# ==========================
# 投票ボタン
# ==========================
class VoteButton(discord.ui.Button):
    def __init__(self, label, role_name, parent_view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.role_name = role_name
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        # ロールが存在しなければ作成
        role = discord.utils.get(guild.roles, name=self.role_name)
        if role is None:
            role = await guild.create_role(name=self.role_name)

        # ロール付与（複数選択OK）
        if role not in member.roles:
            await member.add_roles(role)
            await interaction.response.send_message(
                f"👍 **{self.role_name}** に投票しました！",
                ephemeral=True
            )
        else:
            # もう一度押したらロール削除（トグル式）
            await member.remove_roles(role)
            await interaction.response.send_message(
                f"↩️ **{self.role_name}** の投票を取り消しました。",
                ephemeral=True
            )

        # リアルタイム更新
        await self.parent_view.update_votes()


# ==========================
# 投票ビュー
# ==========================
class VoteView(discord.ui.View):
    def __init__(self, options, message, cog):
        super().__init__(timeout=None)
        self.options = options
        self.message = message
        self.cog = cog

        for opt in options:
            self.add_item(VoteButton(opt, opt, self))

    async def update_votes(self):
        """リアルタイムで票数を更新"""
        guild = self.message.guild

        counts = []
        for opt in self.options:
            role = discord.utils.get(guild.roles, name=opt)
            if role:
                counts.append(f"{opt}: **{len(role.members)}票**")
            else:
                counts.append(f"{opt}: **0票**")

        embed = self.message.embeds[0]
        embed.description = "\n".join(counts)

        await self.message.edit(embed=embed, view=self)


# ==========================
# Cog 本体
# ==========================
class Vote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_votes = {}  # message_id: {"options": [...], "channel": channel_id}

    # --------------------------
    # 投票開始
    # --------------------------
    @commands.command(name="vote")
    async def vote(self, ctx, question: str, *args):
        """
        投票開始:
        /vote 好きな色は？ 赤 青 緑 10m
        """

        if len(args) < 2:
            await ctx.send("❌ 選択肢は2つ以上必要です。")
            return

        # 時間制限判定
        time_str = args[-1]
        options = list(args)
        duration = None

        if any(x in time_str for x in ["s", "m", "h"]):
            duration = self.parse_relative(time_str)
            options = options[:-1]

        embed = discord.Embed(
            title=f"📊 投票：{question}",
            description="\n".join(f"{opt}: **0票**" for opt in options),
            color=0x00ffcc
        )

        msg = await ctx.send(embed=embed)
        view = VoteView(options, msg, self)
        await msg.edit(view=view)

        self.active_votes[msg.id] = {
            "options": options,
            "channel": ctx.channel.id
        }

        if duration:
            await ctx.send(f"⏰ 投票は **{time_str}** 後に自動終了します。")
            asyncio.create_task(self.auto_end_vote(ctx.guild, msg.id, duration))

    # --------------------------
    # 自動終了
    # --------------------------
    async def auto_end_vote(self, guild, message_id, duration):
        await asyncio.sleep(duration)
        if message_id in self.active_votes:
            channel_id = self.active_votes[message_id]["channel"]
            channel = guild.get_channel(channel_id)
            await self.end_vote(channel, message_id)

    # --------------------------
    # 手動終了
    # --------------------------
    @commands.command(name="vote_end")
    @commands.has_permissions(manage_roles=True)
    async def vote_end(self, ctx, message_id: int):
        await self.end_vote(ctx.channel, message_id)

    # --------------------------
    # 投票終了処理
    # --------------------------
    async def end_vote(self, channel, message_id):
        if message_id not in self.active_votes:
            await channel.send("❌ その投票は見つかりません。")
            return

        options = self.active_votes[message_id]["options"]
        del self.active_votes[message_id]

        # ロール削除
        deleted = []
        for opt in options:
            role = discord.utils.get(channel.guild.roles, name=opt)
            if role:
                await role.delete()
                deleted.append(opt)

        # メッセージを終了表示に変更
        try:
            msg = await channel.fetch_message(message_id)
            embed = msg.embeds[0]
            embed.title = "📕 投票（終了）"
            embed.color = 0xff5555
            await msg.edit(embed=embed, view=None)
        except:
            pass

        await channel.send(
            f"📕 投票を終了しました。\n🗑️ 削除されたロール: {', '.join(deleted)}"
        )

    # --------------------------
    # 相対時間解析
    # --------------------------
    def parse_relative(self, t: str):
        sec = 0
        num = ""
        for c in t:
            if c.isdigit():
                num += c
            else:
                if c == "s": sec += int(num)
                if c == "m": sec += int(num) * 60
                if c == "h": sec += int(num) * 3600
                num = ""
        return sec


async def setup(bot):
    await bot.add_cog(Vote(bot))



