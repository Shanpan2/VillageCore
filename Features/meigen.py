import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import random
import re
import os


class Meigen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            path = self._generate_image(text)
            file = discord.File(path, filename="meigen.png")
            await message.reply(file=file)
        except Exception as e:
            await message.reply(f"❌ 画像生成に失敗しました: {e}")

    @staticmethod
    def _generate_image(text: str) -> str:
        bg_dir = "assets/meigen"
        bg_list = [f for f in os.listdir(bg_dir) if f.endswith(".png")]
        if not bg_list:
            raise FileNotFoundError("assets/meigen に背景画像がありません")

        bg_path = os.path.join(bg_dir, random.choice(bg_list))
        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        font = ImageFont.truetype("assets/meigen/font.ttf", 48)
        x, y = 50, 50
        outline = 3

        for dx in [-outline, outline]:
            for dy in [-outline, outline]:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))

        draw.text((x, y), text, font=font, fill=(255, 255, 255))

        out_path = "meigen_temp.png"
        img.save(out_path)
        return out_path


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
