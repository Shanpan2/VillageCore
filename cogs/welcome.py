import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create_welcome_card(self, member):
        # 背景画像（あなたの好きな画像に変更可能）
        background = Image.open("assets/welcome_bg.png").convert("RGBA")

        # アイコン取得
        async with aiohttp.ClientSession() as session:
            async with session.get(member.avatar.url) as resp:
                avatar_bytes = await resp.read()

        avatar = Image.open(io.BytesIO(avatar_bytes)).resize((200, 200)).convert("RGBA")

        # 丸く切り抜き
        mask = Image.new("L", avatar.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, 200, 200), fill=255)
        avatar.putalpha(mask)

        # 合成
        background.paste(avatar, (50, 50), avatar)

        # テキスト
        draw = ImageDraw.Draw(background)
        font = ImageFont.truetype("assets/rounded.ttf", 60)

        draw.text((300, 80), "Welcome!", fill="white", font=font)
        draw.text((300, 160), f"{member.name}", fill="white", font=font)

        # バイトに変換
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = member.guild.system_channel
        if channel is None:
            return

        card = await self.create_welcome_card(member)

        await channel.send(
            content=f"{member.mention} さん、ようこそ！",
            file=discord.File(card, "welcome.png")
        )

async def setup(bot):
    await bot.add_cog(Welcome(bot))


