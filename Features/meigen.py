import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
import random
import re
import textwrap
from pathlib import Path
import aiohttp
import io


class Meigen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="meigen", description="名言画像を生成します")
    async def meigen(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        try:
            avatar_url = interaction.user.display_avatar.url if interaction.user else None
            if not avatar_url and self.bot.user:
                avatar_url = self.bot.user.display_avatar.url
            buffer = await Meigen._generate_image(text, avatar_url=avatar_url)
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
            avatar_url = message.author.display_avatar.url if message.author else None
            if not avatar_url and self.bot.user:
                avatar_url = self.bot.user.display_avatar.url
            buffer = await Meigen._generate_image(text, avatar_url=avatar_url)
            buffer.seek(0)
            file = discord.File(buffer, filename="meigen.png")
            await message.reply(file=file)
        except Exception as e:
            await message.reply(f"❌ 画像生成に失敗しました: {e}")

    @staticmethod
    async def _generate_image(text: str, avatar_url: str | None = None) -> io.BytesIO:
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

        avatar_img = None
        if avatar_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(avatar_url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            avatar_img = Image.open(io.BytesIO(data)).convert("RGBA")
            except Exception:
                avatar_img = None

        output_size = (900, 500)
        img = img.resize(output_size, Image.LANCZOS)

        if avatar_img is not None:
            avatar_bg = ImageOps.fit(avatar_img, (650, 650), Image.LANCZOS).convert("RGBA")
            avatar_bg = ImageEnhance.Color(avatar_bg).enhance(1.05)
            avatar_bg = ImageEnhance.Brightness(avatar_bg).enhance(1.1)
            avatar_bg = avatar_bg.filter(ImageFilter.GaussianBlur(radius=24))

            overlay = Image.new("RGBA", output_size, (255, 255, 255, 0))
            avatar_x = output_size[0] - 520
            avatar_y = (output_size[1] - 650) // 2
            avatar_mask = avatar_bg.split()[3].point(lambda p: min(p, 220))
            overlay.paste(avatar_bg, (avatar_x, avatar_y), avatar_mask)
            overlay = ImageEnhance.Brightness(overlay).enhance(1.02)
            overlay = Image.alpha_composite(img, overlay)

            tone = Image.new("RGBA", output_size, (255, 255, 255, 36))
            shadow = Image.new("RGBA", output_size, (0, 0, 0, 18))
            img = Image.alpha_composite(overlay, tone)
            img = Image.alpha_composite(img, shadow)

        draw = ImageDraw.Draw(img)

        font_path = assets_path / "font.ttf"

        def find_system_font(names):
            possible_dirs = [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path("C:/Windows/Fonts"),
                Path("/Library/Fonts"),
                Path("/System/Library/Fonts"),
            ]
            for root in possible_dirs:
                if not root.exists():
                    continue
                for name in names:
                    for path in root.rglob(name):
                        if path.is_file():
                            yield path

        def get_truetype(size: int):
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), size)
                except Exception:
                    pass

            candidate_names = [
                "NotoSansJP-VF.ttf",
                "NotoSerifJP-VF.ttf",
                "NotoSansCJKjp-Regular.otf",
                "NotoSansCJKjp-Regular.ttf",
                "NotoSansJP-Regular.otf",
                "NotoSansJP-Regular.ttf",
                "meiryo.ttc",
                "meiryo.ttf",
                "msgothic.ttc",
                "msgothic.ttf",
                "YuGothicUI.ttf",
                "YuGothic.ttf",
                "MS Gothic.ttf",
                "Yu Gothic UI.ttf",
                "ipag.ttf",
                "ipagp.ttf",
                "TakaoPGothic.ttf",
                "TakaoPMincho.ttf",
                "arial.ttf",
            ]
            for name in candidate_names:
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    continue

            for path in find_system_font(candidate_names):
                try:
                    return ImageFont.truetype(str(path), size)
                except Exception:
                    continue

            return ImageFont.load_default()

        def wrap_text(raw_text: str, font_obj: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
            lines: list[str] = []
            current = ""
            for ch in raw_text:
                candidate = current + ch
                bbox = draw.textbbox((0, 0), candidate, font=font_obj)
                if bbox[2] - bbox[0] <= max_width or not current:
                    current = candidate
                else:
                    lines.append(current)
                    current = ch
            if current:
                lines.append(current)
            return lines

        max_text_width = img.width - 120
        font_size = 110
        font = get_truetype(font_size)
        lines = wrap_text(text, font, max_text_width)

        while font_size > 38:
            too_big = False
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                if bbox[2] - bbox[0] > max_text_width:
                    too_big = True
                    break
            if too_big or len(lines) > 4:
                font_size -= 4
                font = get_truetype(font_size)
                lines = wrap_text(text, font, max_text_width)
                continue
            break

        if len(lines) > 4 and font_size <= 38:
            wrapped = []
            for line in lines:
                wrapped.extend(wrap_text(line, font, max_text_width))
            lines = wrapped

        line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
        total_h = sum(line_heights) + max(0, len(lines) - 1) * 18
        y = max(40, (img.height - total_h) // 2)

        if total_h > 0:
            max_w = max(draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines)
            pad_x, pad_y = 40, 30
            box_x0 = (img.width - max_w) // 2 - pad_x
            box_y0 = y - pad_y
            box_x1 = (img.width + max_w) // 2 + pad_x
            box_y1 = y + total_h + pad_y
            box_x0 = max(18, box_x0)
            box_y0 = max(18, box_y0)
            box_x1 = min(img.width - 18, box_x1)
            box_y1 = min(img.height - 18, box_y1)
            draw.rounded_rectangle(
                [box_x0, box_y0, box_x1, box_y1],
                radius=24,
                fill=(18, 22, 32, 230),
            )
            draw.rounded_rectangle(
                [box_x0, box_y0, box_x1, box_y1],
                radius=24,
                outline=(255, 255, 255, 80),
                width=2,
            )

        stroke_width = max(2, font_size // 16)
        for line, lh in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (img.width - (bbox[2] - bbox[0])) // 2
            draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0, 220),
            )
            y += lh + 18

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def _generate_fallback_background() -> Image.Image:
        width, height = 900, 500
        img = Image.new("RGBA", (width, height), (34, 42, 61, 255))
        draw = ImageDraw.Draw(img)

        for y in range(0, height, 25):
            alpha = 24 if (y // 25) % 2 == 0 else 16
            draw.rectangle([0, y, width, y + 25], fill=(38, 50, 76, alpha))

        dark = Image.new("RGBA", (width, height), (8, 14, 28, 120))
        img = Image.alpha_composite(img, dark)
        img.putalpha(255)

        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, width, height], outline=(255, 255, 255, 20), width=3)
        return img


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
