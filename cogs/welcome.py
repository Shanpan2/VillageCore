import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create_welcome_card(self, member):
        # 背景画像
        try:
            background = Image.open("assets/welcome_bg.png").convert("RGBA")
        except:
            background = Image.new("RGBA", (800, 400), (30, 30, 30, 255))

        # アイコンURL（未設定ユーザー対応）
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url

        # アイコン取得
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                avatar_bytes = await resp.read()

        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

        # 高品質丸切り抜き（2倍で作って縮小）
        size = 200
        big = avatar.resize((size*2, size*2))
        mask = Image.new("L", (size*2, size*2), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size*2, size*2), fill=255)
        big.putalpha(mask)
        avatar = big.resize((size, size), Image.LANCZOS)

        # 合成
        background.paste(avatar, (50, 50), avatar)

        # テキスト
        draw = ImageDraw.Draw(background)
        try:
            font = ImageFont.truetype("assets/rounded.ttf", 60)
        except:
            font = ImageFont.load_default()

        draw.text((300, 80), "Welcome!", fill="white", font=font)
        draw.text((300, 160), f"{member.name}", fill="white", font=font)

        # バイトに変換
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # system_channel が無い場合の fallback
        channel = member.guild.system_channel or member.guild.text_channels[0]

        card = await self.create_welcome_card(member)

        await channel.send(
            content=f"{member.mention} さん、ようこそ！",
            file=discord.File(card, "welcome.png")
        )

async def setup(bot):
    await bot.add_cog(Welcome(bot))
