import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_set


def log_channel_key(guild_id: int) -> str:
    return f"server_log_channel:{guild_id}"


class ServerLogs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        raw = await db_get(log_channel_key(guild.id))
        if not raw:
            return None
        channel = guild.get_channel(int(raw))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self.get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @app_commands.command(name="server_log_channel", description="【管理者】サーバーログの送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def server_log_channel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await db_set(log_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"サーバーログ送信先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(title="メッセージ削除", color=0xE74C3C)
        embed.add_field(name="投稿者", value=f"{message.author.mention} ({message.author.id})", inline=False)
        embed.add_field(name="チャンネル", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="内容", value=message.content[:1000], inline=False)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="メッセージ編集", color=0xF1C40F)
        embed.add_field(name="投稿者", value=f"{before.author.mention} ({before.author.id})", inline=False)
        embed.add_field(name="チャンネル", value=before.channel.mention, inline=True)
        embed.add_field(name="編集前", value=(before.content or "なし")[:800], inline=False)
        embed.add_field(name="編集後", value=(after.content or "なし")[:800], inline=False)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title="メンバー参加", description=f"{member.mention} ({member.id})", color=0x2ECC71)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title="メンバー退出", description=f"{member} ({member.id})", color=0x95A5A6)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self.send_log(role.guild, discord.Embed(title="ロール作成", description=role.mention, color=0x3498DB))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self.send_log(role.guild, discord.Embed(title="ロール削除", description=role.name, color=0xE67E22))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self.send_log(channel.guild, discord.Embed(title="チャンネル作成", description=channel.mention, color=0x3498DB))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self.send_log(channel.guild, discord.Embed(title="チャンネル削除", description=channel.name, color=0xE67E22))


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogs(bot))
