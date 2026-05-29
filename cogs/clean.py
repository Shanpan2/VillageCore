import discord
from discord import app_commands
from discord.ext import commands


class Clean(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="clean", description="指定した数のメッセージを削除します")
    @app_commands.describe(
        amount="確認するメッセージ数。最大100件です",
        member="このメンバーのメッセージだけ削除します",
        contains="この文字を含むメッセージだけ削除します",
    )
    async def clean(
        self,
        interaction: discord.Interaction,
        amount: int,
        member: discord.Member | None = None,
        contains: str | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("メッセージ管理権限が必要です。", ephemeral=True)
            return

        me = interaction.guild.me
        if me and not interaction.channel.permissions_for(me).manage_messages:
            await interaction.response.send_message("Botにメッセージ管理権限がありません。", ephemeral=True)
            return

        if amount < 1 or amount > 100:
            await interaction.response.send_message("削除数は1から100の間で指定してください。", ephemeral=True)
            return

        keyword = contains.strip() if contains else None

        def should_delete(message: discord.Message) -> bool:
            if member and message.author.id != member.id:
                return False
            if keyword and keyword not in message.content:
                return False
            return True

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=amount, check=should_delete, bulk=True)
        except discord.Forbidden:
            await interaction.followup.send("メッセージを削除する権限がありません。", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"削除中にエラーが発生しました: {e}", ephemeral=True)
            return

        filters = []
        if member:
            filters.append(f"対象: {member.mention}")
        if keyword:
            filters.append(f"文字: `{keyword}`")
        suffix = f"\n条件: {' / '.join(filters)}" if filters else ""
        await interaction.followup.send(f"{len(deleted)}件のメッセージを削除しました。{suffix}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Clean(bot))
