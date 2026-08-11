import random
import datetime
import json

import discord
from discord import app_commands
from discord.ext import commands

from cogs.community import (
    add_unique_json_value,
    apply_coin_rewards,
    badges_key,
    coin_key,
    get_json,
    set_json,
    titles_key,
)
from database.config_db import db_get, db_get_all_config, db_set


JST = datetime.timezone(datetime.timedelta(hours=9))

FORTUNES = [
    {
        "name": "超大吉",
        "message": "かなり珍しい運勢です。今日は思い切った一歩が良い流れを呼びそうです。",
        "weight": 1,
        "coins": 15,
        "color": 0xFFD700,
        "badge": "超大吉の人",
    },
    {
        "name": "大吉",
        "message": "今日は勢いがあります。やりたいことを一つ進めると良さそうです。",
        "weight": 8,
        "coins": 8,
        "color": 0xF1C40F,
        "badge": "幸運の持ち主",
    },
    {"name": "中吉", "message": "いい流れです。焦らず丁寧にいきましょう。", "weight": 16, "coins": 5, "color": 0x2ECC71},
    {"name": "小吉", "message": "小さな良いことが見つかりそうです。", "weight": 18, "coins": 4, "color": 0x58D68D},
    {"name": "吉", "message": "安定した一日になりそうです。", "weight": 22, "coins": 3, "color": 0x3498DB},
    {"name": "末吉", "message": "ゆっくり整える日に向いています。", "weight": 16, "coins": 2, "color": 0x95A5A6},
    {"name": "凶", "message": "無理は禁物です。慎重に動くと回避できます。", "weight": 12, "coins": 1, "color": 0xE67E22},
    {"name": "大凶", "message": "今日は安全第一で。大事な判断は少し置いてもよさそうです。", "weight": 7, "coins": 0, "color": 0xE74C3C},
]

LUCKY_COLORS = ["赤", "青", "緑", "黄", "白", "黒", "紫", "水色", "金", "銀"]
LUCKY_ITEMS = [
    "お茶",
    "メモ帳",
    "イヤホン",
    "サイコロ",
    "本",
    "時計",
    "コイン",
    "お気に入りの曲",
    "温かい飲み物",
    "深呼吸",
    "スマホスタンド",
    "充電器",
    "お気に入りのスタンプ",
    "スクリーンショット",
    "水",
    "チョコ",
    "飴",
    "ノート",
    "ペン",
    "カレンダー",
    "ヘッドホン",
    "マイク",
    "ゲームコントローラー",
    "トランプ",
    "ラッキーコイン",
    "小さなメモ",
    "お気に入りの動画",
    "朝の挨拶",
    "休憩時間",
    "早めの睡眠",
]

OMIKUJI_STREAK_TITLES = [
    (7, "おみくじ習慣"),
    (14, "二週間の運試し"),
    (30, "月間おみくじ民"),
    (100, "百日の運守り"),
]


def omikuji_last_key(guild_id: int, user_id: int) -> str:
    return f"omikuji_last_{guild_id}_{user_id}"


def omikuji_streak_key(guild_id: int, user_id: int) -> str:
    return f"omikuji_streak:{guild_id}:{user_id}"


def choose_fortune() -> dict:
    return random.choices(FORTUNES, weights=[item["weight"] for item in FORTUNES], k=1)[0]


async def grant_omikuji_streak_titles(guild_id: int, user_id: int, streak: int) -> list[str]:
    notes = []
    for required_days, title in OMIKUJI_STREAK_TITLES:
        if streak < required_days:
            continue
        added = await add_unique_json_value(titles_key(guild_id, user_id), title)
        if added:
            notes.append(f"{required_days}日連続ボーナス: 称号「{title}」を獲得")
    return notes


async def backfill_omikuji_streak_titles() -> int:
    all_config = await db_get_all_config()
    granted = 0
    for key, raw in all_config.items():
        if not key.startswith("omikuji_streak:"):
            continue
        parts = key.split(":")
        if len(parts) != 3:
            continue
        try:
            guild_id = int(parts[1])
            user_id = int(parts[2])
            data = json.loads(raw or "{}")
            streak = int(data.get("count", 0) or 0)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        granted += len(await grant_omikuji_streak_titles(guild_id, user_id, streak))
    return granted


async def run_omikuji(interaction: discord.Interaction, *, deferred: bool = False):
    if not interaction.guild or not interaction.guild_id:
        send = interaction.followup.send if deferred else interaction.response.send_message
        await send("サーバー内で実行してください。", ephemeral=True)
        return

    if not deferred:
        await interaction.response.defer(thinking=True)

    today = datetime.datetime.now(JST).date()
    today_key = today.isoformat()
    last_key = omikuji_last_key(interaction.guild.id, interaction.user.id)
    last_draw = await db_get(last_key)
    if last_draw == today_key:
        await interaction.followup.send("今日はすでにおみくじを引いています。また明日引いてください。", ephemeral=True)
        return

    streak_data = await get_json(omikuji_streak_key(interaction.guild.id, interaction.user.id), {})
    yesterday_key = (today - datetime.timedelta(days=1)).isoformat()
    streak = int(streak_data.get("count", 0) or 0) + 1 if streak_data.get("last") == yesterday_key else 1

    fortune = choose_fortune()
    coin_bonus = int(fortune["coins"])
    balance_key = coin_key(interaction.guild.id, interaction.user.id)
    current = int(await db_get(balance_key) or "0")
    new_balance = current + coin_bonus

    await db_set(last_key, today_key)
    await set_json(omikuji_streak_key(interaction.guild.id, interaction.user.id), {"last": today_key, "count": streak})
    if coin_bonus:
        await db_set(balance_key, str(new_balance))

    notes = []
    badge = fortune.get("badge")
    if badge:
        badges = await get_json(badges_key(interaction.guild.id, interaction.user.id), [])
        if badge not in badges:
            badges.append(badge)
            await set_json(badges_key(interaction.guild.id, interaction.user.id), badges[:30])
            notes.append(f"バッジ「{badge}」を獲得")

    notes.extend(await grant_omikuji_streak_titles(interaction.guild.id, interaction.user.id, streak))

    rewards = await apply_coin_rewards(interaction.guild, interaction.user, new_balance)
    notes.extend(rewards)

    embed = discord.Embed(
        title="🎴 おみくじ",
        description=f"**{fortune['name']}**\n{fortune['message']}",
        color=fortune["color"],
    )
    embed.add_field(name="ラッキーカラー", value=random.choice(LUCKY_COLORS), inline=True)
    embed.add_field(name="ラッキーアイテム", value=random.choice(LUCKY_ITEMS), inline=True)
    embed.add_field(name="連続おみくじ", value=f"{streak}日目", inline=True)
    embed.add_field(name="コイン", value=f"+{coin_bonus} / 現在 {new_balance}", inline=False)
    if notes:
        embed.add_field(name="獲得", value="\n".join(f"🎖 {note}" for note in notes)[:1024], inline=False)

    await interaction.followup.send(embed=embed)


async def run_omikuji_prefix(ctx: commands.Context):
    if not ctx.guild:
        return

    today = datetime.datetime.now(JST).date()
    today_key = today.isoformat()
    last_key = omikuji_last_key(ctx.guild.id, ctx.author.id)
    last_draw = await db_get(last_key)
    if last_draw == today_key:
        await ctx.reply("今日はすでにおみくじを引いています。また明日引いてください。", mention_author=False, delete_after=60)
        return

    streak_data = await get_json(omikuji_streak_key(ctx.guild.id, ctx.author.id), {})
    yesterday_key = (today - datetime.timedelta(days=1)).isoformat()
    streak = int(streak_data.get("count", 0) or 0) + 1 if streak_data.get("last") == yesterday_key else 1

    fortune = choose_fortune()
    coin_bonus = int(fortune["coins"])
    balance_key = coin_key(ctx.guild.id, ctx.author.id)
    current = int(await db_get(balance_key) or "0")
    new_balance = current + coin_bonus

    await db_set(last_key, today_key)
    await set_json(omikuji_streak_key(ctx.guild.id, ctx.author.id), {"last": today_key, "count": streak})
    if coin_bonus:
        await db_set(balance_key, str(new_balance))

    notes = []
    badge = fortune.get("badge")
    if badge:
        badges = await get_json(badges_key(ctx.guild.id, ctx.author.id), [])
        if badge not in badges:
            badges.append(badge)
            await set_json(badges_key(ctx.guild.id, ctx.author.id), badges[:30])
            notes.append(f"バッジ「{badge}」を獲得")

    notes.extend(await grant_omikuji_streak_titles(ctx.guild.id, ctx.author.id, streak))

    member = ctx.author if isinstance(ctx.author, discord.Member) else None
    rewards = await apply_coin_rewards(ctx.guild, member, new_balance)
    notes.extend(rewards)

    embed = discord.Embed(
        title="🎴 おみくじ",
        description=f"**{fortune['name']}**\n{fortune['message']}",
        color=fortune["color"],
    )
    embed.add_field(name="ラッキーカラー", value=random.choice(LUCKY_COLORS), inline=True)
    embed.add_field(name="ラッキーアイテム", value=random.choice(LUCKY_ITEMS), inline=True)
    embed.add_field(name="連続おみくじ", value=f"{streak}日目", inline=True)
    embed.add_field(name="コイン", value=f"+{coin_bonus} / 現在 {new_balance}", inline=False)
    if notes:
        embed.add_field(name="獲得", value="\n".join(f"🎖 {note}" for note in notes)[:1024], inline=False)

    await ctx.reply(embed=embed, mention_author=False)


class Omikuji(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._streak_backfill_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._streak_backfill_done:
            return
        self._streak_backfill_done = True
        try:
            granted = await backfill_omikuji_streak_titles()
            if granted:
                print(f"[Omikuji] backfilled {granted} streak title rewards", flush=True)
        except Exception as exc:
            print(f"[Omikuji] streak title backfill failed: {exc}", flush=True)

    @app_commands.command(name="omikuji", description="おみくじを引きます")
    async def omikuji(self, interaction: discord.Interaction):
        await run_omikuji(interaction)

    @commands.command(name="omikuji")
    async def omikuji_prefix(self, ctx: commands.Context):
        await run_omikuji_prefix(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Omikuji(bot))
