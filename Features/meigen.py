import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import random
import re
from pathlib import Path
import io


class Meigen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="meigen", description="名言画像を生成します")
    async def meigen(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        try:
            buffer = self._generate_image(text)
            buffer.seek(0)
            await interaction.followup.send(file=discord.File(buffer, filename="meigen.png"))
        except Exception as e:
            await interaction.followup.send(f"❌ 画像生成に失敗しました: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # メンション判定（mentions リストで確実に判定）
        if self.bot.user not in message.mentions:
            return

        if "迷言" not in message.content:
            return

        match = re.search(r"迷言[「『](.*?)[」』]", message.content)
        if not match:
            await message.reply("迷言の形式は 迷言「テキスト」 だよ。")
            return

        text = match.group(1)

        try:
            buffer = self._generate_image(text)
            buffer.seek(0)
            file = discord.File(buffer, filename="meigen.png")
            await message.reply(file=file)
        except Exception as e:
            await message.reply(f"❌ 画像生成に失敗しました: {e}")

    @staticmethod
    def _generate_image(text: str) -> io.BytesIO:
        base_path = Path(__file__).resolve().parent.parent
        assets_path = base_path / "assets" / "meigen"

        bg_list = [f for f in assets_path.iterdir() if f.suffix.lower() == ".png"]
        if not bg_list:
            raise FileNotFoundError("assets/meigen に背景画像がありません")

        bg_path = random.choice(bg_list)
        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        font_path = assets_path / "font.ttf"
        if not font_path.exists():
            raise FileNotFoundError("assets/meigen/font.ttf が見つかりません")
        font = ImageFont.truetype(str(font_path), 48)

        x, y = 50, 50
        outline = 3

        for dx in [-outline, outline]:
            for dy in [-outline, outline]:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))

        draw.text((x, y), text, font=font, fill=(255, 255, 255))

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
