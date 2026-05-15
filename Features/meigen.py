import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import random
import re
import textwrap
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

        content = message.content
        content = content.replace(f"<@!{self.bot.user.id}>", "").replace(f"<@{self.bot.user.id}>", "").strip()
        # If user only mentioned bot with no text, try to use previous non-bot message
        if not content:
            prev = None
            async for m in message.channel.history(limit=6):
                if m.id == message.id:
                    continue
                if m.author.bot:
                    continue
                if m.content and m.content.strip():
                    prev = m
                    break
            if prev:
                content = prev.content.strip()
            else:
                await message.reply("迷言にするテキストが見つかりません。メンションに続けてテキストを送るか、直前のメッセージをメンションだけで参照できます。")
                return

        text = None
        match = re.search(r"迷言[「『](.*?)[」』]", content)
        if match:
            text = match.group(1).strip()
        else:
            raw = content
            if raw.lower().startswith("meigen"):
                raw = raw[len("meigen"):].strip()
            if raw.startswith("名言"):
                raw = raw[len("名言"):].strip()
            if raw.startswith("迷言"):
                raw = raw[len("迷言"):].strip()
            if raw.startswith("「") or raw.startswith("『"):
                raw = raw[1:]
            if raw.endswith("」") or raw.endswith("』"):
                raw = raw[:-1]
            text = raw.strip()
            if not text:
                await message.reply("迷言の形式は 迷言「テキスト」 だよ。例: @bot 迷言「テキスト」 または @bot テキスト")
                return

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

        bg_files = []
        if assets_path.exists():
            for path in assets_path.iterdir():
                if path.suffix.lower() == ".png":
                    try:
                        with Image.open(path) as im:
                            im.verify()
                        bg_files.append(path)
                    except Exception:
                        continue

        if bg_files:
            bg_path = random.choice(bg_files)
            img = Image.open(bg_path).convert("RGBA")
        else:
            img = Meigen._generate_fallback_background()

        draw = ImageDraw.Draw(img)

        font_path = assets_path / "font.ttf"
        if font_path.exists():
            try:
                font = ImageFont.truetype(str(font_path), 48)
            except Exception:
                font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()

        # Choose font size to fit the image width
        max_width = img.width - 120
        # try decreasing font sizes until the longest wrapped line fits
        size = 64
        while size >= 18:
            try:
                test_font = ImageFont.truetype(str(font_path), size) if font_path.exists() else ImageFont.load_default()
            except Exception:
                test_font = ImageFont.load_default()
            # wrap by characters approximate; then measure
            lines = textwrap.wrap(text, width=40)
            too_big = False
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=test_font)
                if bbox[2] - bbox[0] > max_width:
                    too_big = True
                    break
            if not too_big:
                font = test_font
                break
            size -= 4

        # center vertically
        lines = textwrap.wrap(text, width=40)
        line_heights = [draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]
        total_h = sum(line_heights) + (len(lines)-1) * 12
        y = (img.height - total_h) // 2
        for line, lh in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (img.width - w) // 2
            # outline
            for dx in (-2, -1, 1, 2):
                for dy in (-2, -1, 1, 2):
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
            draw.text((x, y), line, font=font, fill=(255, 255, 255))
            y += lh + 12

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def _generate_fallback_background() -> Image.Image:
        width, height = 800, 400
        img = Image.new("RGBA", (width, height), (30, 30, 40, 255))
        draw = ImageDraw.Draw(img)

        for i in range(0, height, 20):
            color = 40 + (i // 10 % 2) * 10
            draw.rectangle([0, i, width, i + 10], fill=(color, color + 10, color + 20, 255))

        draw.rectangle([0, 0, width, height], outline=(255, 255, 255, 30), width=4)
        return img


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
