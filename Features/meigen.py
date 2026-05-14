# features/meigen.py

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import random
import os


def setup_meigen(bot: commands.Bot):

    @bot.event
    async def on_message(message: discord.Message):

        # bot自身には反応しない
        if message.author.bot:
            return

        # botメンション + 迷言 の形式を検出
        if bot.user.mention not in message.content:
            return

        if "迷言" not in message.content:
            return

        # 迷言テキスト抽出
        # 例: "@Bot 迷言「ホットケーキって冷めたら〜」"
        import re
        match = re.search(r"迷言[「『](.*?)[」』]", message.content)
        if not match:
            await message.reply("迷言の形式は 迷言「テキスト」 だよ。")
            return

        text = match.group(1)

        # 画像生成
        path = generate_meigen_image(text)

        file = discord.File(path, filename="meigen.png")
        await message.reply(file=file)


# ============================================================
# 🖼️ 名言画像生成
# ============================================================

def generate_meigen_image(text: str):

    # 背景画像をランダム選択
    bg_dir = "assets/meigen"
    bg_list = [f for f in os.listdir(bg_dir) if f.endswith(".png")]
    bg_path = os.path.join(bg_dir, random.choice(bg_list))

    img = Image.open(bg_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # フォント
    font = ImageFont.truetype("assets/meigen/font.ttf", 48)

    # テキスト描画位置
    x, y = 50, 50

    # テキスト描画（白文字 + 黒縁取り）
    outline = 3
    for dx in [-outline, outline]:
        for dy in [-outline, outline]:
            draw.text((x+dx, y+dy), text, font=font, fill=(0,0,0))

    draw.text((x, y), text, font=font, fill=(255,255,255))

    # 保存
    out_path = "meigen_temp.png"
    img.save(out_path)
    return out_path
