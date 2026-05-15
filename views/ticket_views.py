import discord

class TicketButtonView(discord.ui.View):
    def __init__(self, bot: discord.ext.commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketButton())


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

    def __init__(self, bot: discord.ext.commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        ticket_text = (
            f"**🎫 新しいチケット**\n"
            f"送信者: {interaction.user.mention}\n"
            f"件名: {self.subject.value}\n"
            f"内容:\n{self.description.value}"
        )

        await interaction.response.send_message(
            "✅ チケットを送信しました。管理者が確認します。",
            ephemeral=True,
        )

        guild = interaction.guild
        if guild is None:
            return

        target_channel = None
        for channel in guild.text_channels:
            if channel.name in ("ticket", "tickets", "support", "help"):
                target_channel = channel
                break

        if target_channel is None:
            target_channel = guild.system_channel

        if target_channel is None:
            try:
                owner = guild.owner
                if owner is not None:
                    await owner.send(ticket_text)
                    return
            except Exception:
                target_channel = interaction.channel

        if target_channel is not None:
            try:
                await target_channel.send(ticket_text)
            except Exception:
                pass


class TicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📩 チケットを作成",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_button",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal(self.view.bot))
