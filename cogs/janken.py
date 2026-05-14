import discord
from discord.ext import commands
from discord import app_commands
import random

# ==========================
# じゃんけんボタン
# ==========================
class JankenButton(discord.ui.Button):
    def __init__(self, label, parent_view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        user_hand = self.label
        bot_hand = random.choice(["✊", "✌️", "✋"])

        result = self.parent_view.judge(user_hand, bot_hand)

        embed = discord.Embed(
            title="🎮 じゃんけん結果",
            description=(
                f"あなた：{user_hand}\n"
                f"BOT：{bot_hand}\n\n"
                f"**{result}**"
            ),
            color=0x00ffcc
        )

        for child in self.parent_view.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self.parent_view)


# ==========================
# じゃんけんビュー
# ==========================
class JankenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

        self.add_item(JankenButton("✊", self))
        self.add_item(JankenButton("✌️", self))
        self.add_item(JankenButton("✋", self))

    def judge(self, user, bot):
        if user == bot:
            return "🤝 あいこ"
        if (
            (user == "✊" and bot == "✌️") or
            (user == "✌️" and bot == "✋") or
            (user == "✋" and bot == "✊")
        ):
            return "🎉 あなたの勝ち！"
        return "😢 あなたの負け…"


# ==========================
# Cog 本体（Slash Command）
# ==========================
class Janken(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="janken", description="じゃんけんで遊びます")
    async def janken(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 じゃんけん",
            description="ボタンを押して手を選んでください！",
            color=0x00ffcc
        )

        await interaction.response.send_message(embed=embed, view=JankenView())


async def setup(bot):
    await bot.add_cog(Janken(bot))



