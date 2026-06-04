import random
from datetime import datetime, timedelta, timezone
from io import BytesIO

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from cogs.community import apply_coin_rewards, coin_key
from database.config_db import db_get, db_set


JST = timezone(timedelta(hours=9))

LEVELS = {
    "easy": {"label": "初級", "reward": 2, "description": "1手詰め中心。まずは気軽に。"},
    "normal": {"label": "中級", "reward": 5, "description": "少し読む問題。慣れてきた人向け。"},
    "hard": {"label": "上級", "reward": 8, "description": "読みが必要な問題。腕試し向け。"},
}

PIECES = {
    "K": "玉",
    "R": "飛",
    "B": "角",
    "G": "金",
    "S": "銀",
    "N": "桂",
    "L": "香",
    "P": "歩",
    "+R": "龍",
    "+B": "馬",
    "+S": "成銀",
    "+N": "成桂",
    "+L": "成香",
    "+P": "と",
}

PUZZLES = [
    {
        "id": "easy_001",
        "level": "easy",
        "title": "初級 1手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (5, 3): ("sente", "R"),
            (4, 2): ("sente", "G"),
            (6, 2): ("sente", "G"),
        },
        "hands": {"sente": [], "gote": []},
        "answer": "5二飛成",
        "options": ["5二飛成", "4一金", "6一金", "5一飛成"],
        "explanation": "飛車を5三から5二へ成って、玉の逃げ道をふさぐ形です。",
    },
    {
        "id": "easy_002",
        "level": "easy",
        "title": "初級 1手詰め",
        "side": "先手",
        "pieces": {
            (4, 1): ("gote", "K"),
            (4, 3): ("sente", "G"),
            (5, 2): ("sente", "R"),
            (3, 2): ("sente", "S"),
        },
        "hands": {"sente": [], "gote": []},
        "answer": "4二金",
        "options": ["4二金", "5一飛成", "3一銀成", "4一金"],
        "explanation": "玉の正面に金を寄せて逃げ道を消す基本形です。",
    },
    {
        "id": "normal_001",
        "level": "normal",
        "title": "中級 3手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (4, 1): ("gote", "G"),
            (6, 1): ("gote", "G"),
            (5, 3): ("sente", "R"),
            (4, 3): ("sente", "B"),
        },
        "hands": {"sente": ["G"], "gote": []},
        "answer": "5二金",
        "options": ["5二金", "5一飛成", "4二角成", "6二金"],
        "explanation": "持ち駒の金で玉を押さえるのが急所です。飛車や角を先に動かすと逃げ道が残ります。",
    },
    {
        "id": "normal_002",
        "level": "normal",
        "title": "中級 3手詰め",
        "side": "先手",
        "pieces": {
            (3, 1): ("gote", "K"),
            (2, 1): ("gote", "G"),
            (4, 1): ("gote", "S"),
            (3, 3): ("sente", "B"),
            (5, 3): ("sente", "R"),
        },
        "hands": {"sente": ["G"], "gote": []},
        "answer": "3二金",
        "options": ["3二金", "2二角成", "5一飛成", "4二金"],
        "explanation": "3二金で玉の正面を押さえるのが詰み筋です。大駒の王手より金の密着が強い場面です。",
    },
    {
        "id": "hard_001",
        "level": "hard",
        "title": "上級 5手詰め",
        "side": "先手",
        "pieces": {
            (5, 1): ("gote", "K"),
            (4, 1): ("gote", "G"),
            (6, 1): ("gote", "S"),
            (5, 4): ("sente", "R"),
            (3, 3): ("sente", "B"),
            (6, 3): ("sente", "S"),
        },
        "hands": {"sente": ["G", "G"], "gote": []},
        "answer": "5二金",
        "options": ["5二金", "4二金", "5一飛成", "6二銀成"],
        "explanation": "初手は5二金。玉を狭くしてから大駒を使うのがポイントです。",
    },
    {
        "id": "hard_002",
        "level": "hard",
        "title": "上級 5手詰め",
        "side": "先手",
        "pieces": {
            (7, 1): ("gote", "K"),
            (6, 1): ("gote", "G"),
            (8, 1): ("gote", "G"),
            (7, 4): ("sente", "R"),
            (5, 3): ("sente", "B"),
            (8, 3): ("sente", "S"),
        },
        "hands": {"sente": ["G", "S"], "gote": []},
        "answer": "7二金",
        "options": ["7二金", "6二銀成", "7一飛成", "8二金"],
        "explanation": "金を玉の頭に打つことで逃げ道を消します。派手な大駒より、金の打ち込みが急所です。",
    },
]


def shogi_daily_key(guild_id: int, user_id: int, level: str) -> str:
    return f"shogi_puzzle_daily:{guild_id}:{user_id}:{level}"


def jst_today() -> str:
    return datetime.now(JST).date().isoformat()


def puzzle_for_level(level: str) -> dict:
    candidates = [puzzle for puzzle in PUZZLES if puzzle["level"] == level]
    return random.choice(candidates)


def load_font(size: int, bold: bool = False):
    names = [
        "meiryo.ttc",
        "YuGothB.ttc" if bold else "YuGothM.ttc",
        "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
        "NotoSansJP-Bold.otf" if bold else "NotoSansJP-Regular.otf",
        "ipaexg.ttf",
        "ipag.ttf",
        "TakaoGothic.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def piece_text(piece: str) -> str:
    return PIECES.get(piece, piece)


def piece_short(piece: str) -> str:
    return {
        "K": "K",
        "R": "R",
        "B": "B",
        "G": "G",
        "S": "S",
        "N": "N",
        "L": "L",
        "P": "P",
        "+R": "+R",
        "+B": "+B",
        "+S": "+S",
        "+N": "+N",
        "+L": "+L",
        "+P": "+P",
    }.get(piece, piece)


def render_puzzle_image(puzzle: dict) -> discord.File:
    cell = 70
    board_left = 56
    board_top = 72
    board_size = cell * 9
    width = board_left + board_size + 250
    height = board_top + board_size + 72
    image = Image.new("RGB", (width, height), (47, 68, 57))
    draw = ImageDraw.Draw(image)

    title_font = load_font(28, bold=True)
    small_font = load_font(18)
    coord_font = load_font(16, bold=True)
    piece_font = load_font(28, bold=True)
    piece_short_font = load_font(13, bold=True)

    draw.text((34, 22), f"詰将棋 - {puzzle['title']}", fill=(255, 255, 255), font=title_font)
    draw.text((board_left + board_size + 36, 84), f"手番: {puzzle['side']}", fill=(255, 245, 210), font=small_font)
    draw.text((board_left + board_size + 36, 122), "持ち駒", fill=(255, 255, 255), font=small_font)
    hand = puzzle.get("hands", {}).get("sente", [])
    hand_text = " ".join(piece_text(piece) for piece in hand) if hand else "なし"
    draw.text((board_left + board_size + 36, 154), hand_text, fill=(255, 245, 210), font=small_font)
    draw.text((board_left + board_size + 36, 216), "正解手を選んでください。", fill=(220, 236, 222), font=small_font)

    draw.rectangle(
        (board_left, board_top, board_left + board_size, board_top + board_size),
        fill=(226, 174, 96),
        outline=(64, 42, 24),
        width=3,
    )
    for index in range(10):
        x = board_left + index * cell
        y = board_top + index * cell
        draw.line((x, board_top, x, board_top + board_size), fill=(80, 52, 28), width=1)
        draw.line((board_left, y, board_left + board_size, y), fill=(80, 52, 28), width=1)

    for file_num in range(9, 0, -1):
        col = 9 - file_num
        x = board_left + col * cell + 28
        draw.text((x, board_top - 25), str(file_num), fill=(235, 235, 220), font=coord_font)
    for rank in range(1, 10):
        y = board_top + (rank - 1) * cell + 24
        draw.text((board_left - 28, y), str(rank), fill=(235, 235, 220), font=coord_font)

    for (file_num, rank), (owner, piece) in puzzle["pieces"].items():
        col = 9 - file_num
        row = rank - 1
        x = board_left + col * cell + 8
        y = board_top + row * cell + 8
        fill = (250, 222, 151) if owner == "sente" else (238, 196, 118)
        outline = (82, 54, 26)
        points = [
            (x + 27, y),
            (x + 54, y + 14),
            (x + 48, y + 56),
            (x + 6, y + 56),
            (x, y + 14),
        ]
        if owner == "gote":
            points = [(px, y + 56 - (py - y)) for px, py in points]
        draw.polygon(points, fill=fill, outline=outline)
        label = piece_text(piece)
        bbox = draw.textbbox((0, 0), label, font=piece_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x + 27 - tw / 2, y + 25 - th / 2), label, fill=(34, 28, 22), font=piece_font)
        short = piece_short(piece)
        bbox = draw.textbbox((0, 0), short, font=piece_short_font)
        sw = bbox[2] - bbox[0]
        draw.text((x + 27 - sw / 2, y + 41), short, fill=(82, 54, 26), font=piece_short_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="shogi_puzzle.png")


async def grant_reward(interaction: discord.Interaction, level: str) -> tuple[int, str]:
    if not interaction.guild_id:
        return 0, ""
    today = jst_today()
    daily_key = shogi_daily_key(interaction.guild_id, interaction.user.id, level)
    if await db_get(daily_key) == today:
        return 0, "このレベルの今日の報酬は受け取り済みです。"

    reward = LEVELS[level]["reward"]
    key = coin_key(interaction.guild_id, interaction.user.id)
    current = int(await db_get(key) or "0")
    new_balance = current + reward
    await db_set(key, str(new_balance))
    await db_set(daily_key, today)
    rewards = await apply_coin_rewards(interaction.guild, interaction.user, new_balance)
    reward_text = f"{reward}コイン獲得しました。現在 **{new_balance}** コインです。"
    if rewards:
        reward_text += "\n" + "\n".join(f"🎖 {message}" for message in rewards)
    return reward, reward_text


class ShogiPuzzleAnswerView(discord.ui.View):
    def __init__(self, puzzle: dict, owner_id: int):
        super().__init__(timeout=600)
        self.puzzle = puzzle
        self.owner_id = owner_id
        for option in puzzle["options"]:
            style = discord.ButtonStyle.secondary
            self.add_item(ShogiPuzzleAnswerButton(option, style))


class ShogiPuzzleAnswerButton(discord.ui.Button):
    def __init__(self, answer: str, style: discord.ButtonStyle):
        super().__init__(label=answer, style=style)
        self.answer = answer

    async def callback(self, interaction: discord.Interaction):
        view: ShogiPuzzleAnswerView = self.view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("この詰将棋に回答できるのは開始した人だけです。", ephemeral=True)
            return

        puzzle = view.puzzle
        correct = self.answer == puzzle["answer"]
        for item in view.children:
            item.disabled = True
            if isinstance(item, discord.ui.Button) and item.label == puzzle["answer"]:
                item.style = discord.ButtonStyle.success
            elif isinstance(item, discord.ui.Button) and item.label == self.answer:
                item.style = discord.ButtonStyle.danger

        if correct:
            _, reward_text = await grant_reward(interaction, puzzle["level"])
            result = f"正解です！ **{puzzle['answer']}**\n{reward_text}"
        else:
            result = f"惜しいです。正解は **{puzzle['answer']}** です。"
        result += f"\n\n解説: {puzzle['explanation']}"
        await interaction.response.edit_message(content=result, view=view)


class ShogiPuzzleLevelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShogiPuzzleLevelButton("初級", "easy", discord.ButtonStyle.success, 0))
        self.add_item(ShogiPuzzleLevelButton("中級", "normal", discord.ButtonStyle.primary, 0))
        self.add_item(ShogiPuzzleLevelButton("上級", "hard", discord.ButtonStyle.danger, 0))
        self.add_item(ShogiPuzzleRulesButton())


class ShogiPuzzleLevelButton(discord.ui.Button):
    def __init__(self, label: str, level: str, style: discord.ButtonStyle, row: int):
        super().__init__(
            label=label,
            style=style,
            row=row,
            custom_id=f"shogi_puzzle_level_{level}",
        )
        self.level = level

    async def callback(self, interaction: discord.Interaction):
        puzzle = puzzle_for_level(self.level)
        level = LEVELS[self.level]
        content = (
            f"**詰将棋: {level['label']}**\n"
            f"{level['description']}\n"
            f"正解すると **{level['reward']}コイン** 獲得できます。同じレベルの報酬は1日1回までです。"
        )
        await interaction.response.send_message(
            content,
            file=render_puzzle_image(puzzle),
            view=ShogiPuzzleAnswerView(puzzle, interaction.user.id),
        )


class ShogiPuzzleRulesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ルール",
            style=discord.ButtonStyle.secondary,
            row=1,
            custom_id="shogi_puzzle_rules",
        )

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="詰将棋の遊び方",
            description=(
                "表示された盤面で、相手玉を詰ます最初の一手を選びます。\n"
                "初級は1手詰め中心、中級と上級は読みが必要な問題です。\n"
                "正解するとコインがもらえますが、同じレベルの報酬は1日1回までです。\n\n"
                "報酬: 初級2 / 中級5 / 上級8 コイン"
            ),
            color=0xD6A24A,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def shogi_puzzle_embed() -> discord.Embed:
    embed = discord.Embed(
        title="詰将棋",
        description=(
            "レベルを選んで詰将棋に挑戦できます。\n"
            "正解するとコイン報酬があります。報酬は同じレベルにつき1日1回までです。"
        ),
        color=0xD6A24A,
    )
    embed.add_field(name="初級", value="1手詰め中心 / 2コイン", inline=True)
    embed.add_field(name="中級", value="少し読む問題 / 5コイン", inline=True)
    embed.add_field(name="上級", value="腕試し / 8コイン", inline=True)
    return embed


class ShogiPuzzle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(ShogiPuzzle(bot))
