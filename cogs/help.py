import discord
from discord.ext import commands
from discord import app_commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="利用可能なスラッシュコマンドを表示します")
    async def help(self, interaction: discord.Interaction):
        commands_list = sorted(
            [c for c in self.bot.tree.walk_commands() if c.parent is None],
            key=lambda c: c.name,
        )

        lines = [f"/{command.name} — {command.description or '説明なし'}" for command in commands_list]
        if not lines:
            await interaction.response.send_message("❌ 表示するコマンドが見つかりませんでした。", ephemeral=True)
            return

        description = "\n".join(lines)
        if len(description) > 1900:
            description = "\n".join(lines[:30])
            description += f"\n\n...他 {len(lines) - 30} 件"

        embed = discord.Embed(
            title="📘 コマンドヘルプ",
            description=description,
            color=0x00BFFF,
        )
        embed.set_footer(text="/ でコマンドを入力できます。よく使うものをまとめています。")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
