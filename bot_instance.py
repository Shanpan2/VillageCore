import discord
from discord.ext import commands

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",  # スラッシュコマンドのみ使うので実質使わない文字に変更
            intents=intents,
            application_id=1501521359963033741
        )

    async def on_message(self, message: discord.Message):
        # prefix コマンドの処理（必須）
        await self.process_commands(message)

bot = MyBot()