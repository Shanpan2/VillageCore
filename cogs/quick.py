import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_set
from Features.daifugo import DEFAULT_RULES, daifugo_games, rules_text
from Features.poker import poker_games
from Features.sevens import SUITS as SEVENS_SUITS
from Features.sevens import sevens_games
from Features.uno import uno_games


JST = datetime.timezone(datetime.timedelta(hours=9))

GAME_STORES = {
    "uno": ("UNO", uno_games),
    "sevens": ("7並べ", sevens_games),
    "daifugo": ("大富豪", daifugo_games),
    "poker": ("ポーカー", poker_games),
}


def quick_embed() -> discord.Embed:
    embed = discord.Embed(
        title="クイックメニュー",
        description="日頃よく使う機能だけを集めたメニューです。ボタンからそのまま実行できます。",
        color=0x2ECC71,
    )
    embed.add_field(
        name="ゲーム作成",
        value="UNO / 7並べ / 大富豪 / ポーカー",
        inline=False,
    )
    embed.add_field(
        name="すぐ遊ぶ",
        value="おみくじ / ダイス / じゃんけん",
        inline=False,
    )
    embed.add_field(
        name="便利系",
        value="検索 / 投票 / リマインダー / 出席確認の使い方案内",
        inline=False,
    )
    return embed


async def run_omikuji(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)

    today = datetime.datetime.now(JST).date().isoformat()
    key = f"omikuji_last_{interaction.guild.id}_{interaction.user.id}"
    last_draw = await db_get(key)
    if last_draw == today:
        await interaction.followup.send("今日はすでにおみくじを引いています。また明日引いてください。")
        return

    fortunes = [
        ("大吉", "今日は勢いがあります。やりたいことを一つ進めると良さそうです。"),
        ("中吉", "いい流れです。焦らず丁寧にいきましょう。"),
        ("小吉", "小さな良いことが見つかりそうです。"),
        ("吉", "安定した一日になりそうです。"),
        ("末吉", "ゆっくり整える日に向いています。"),
        ("凶", "無理は禁物です。慎重に動くと回避できます。"),
        ("大凶", "今日は安全第一で。大事な判断は少し置いてもよさそうです。"),
    ]
    result, message = random.choice(fortunes)
    await db_set(key, today)
    embed = discord.Embed(title="おみくじ", description=f"**{result}**\n{message}", color=0xE67E22)
    await interaction.followup.send(embed=embed)


def roll_dice_embed() -> discord.Embed:
    roll = random.randint(1, 100)
    if roll <= 5:
        note = "クリティカル"
        color = 0xFFD700
    elif roll >= 96:
        note = "ファンブル"
        color = 0xE74C3C
    elif roll <= 50:
        note = "成功"
        color = 0x2ECC71
    else:
        note = "失敗"
        color = 0x95A5A6
    return discord.Embed(title="1d100", description=f"結果: **{roll}**\n{note}", color=color)


def create_uno_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in uno_games:
        return "このチャンネルにはすでにUNOがあります。"
    uno_games[game_id] = {
        "creator_id": interaction.user.id,
        "players": [interaction.user.id],
        "hands": {},
        "deck": [],
        "discard": [],
        "turn_index": 0,
        "direction": 1,
        "top": None,
        "uno_declared": False,
        "challenge_mode": True,
    }
    return f"UNOを作成しました。{interaction.user.mention} は自動参加しました。\n`/uno_join` で参加、`/uno_begin` で開始します。"


def create_sevens_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in sevens_games:
        return "このチャンネルにはすでに7並べがあります。"
    sevens_games[game_id] = {
        "creator_id": interaction.user.id,
        "players": [interaction.user.id],
        "hands": {},
        "board": {suit: [7] for suit in SEVENS_SUITS},
        "turn_index": 0,
        "passes": {},
        "finished": [],
        "started": False,
    }
    return f"7並べを作成しました。{interaction.user.mention} は自動参加しました。\n`/sevens_join` で参加、`/sevens_begin` で開始します。"


def create_daifugo_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in daifugo_games:
        return "このチャンネルにはすでに大富豪があります。"
    rules = DEFAULT_RULES.copy()
    daifugo_games[game_id] = {
        "creator_id": interaction.user.id,
        "players": [interaction.user.id],
        "hands": {},
        "turn_index": 0,
        "started": False,
        "last_play": None,
        "last_info": None,
        "last_player": None,
        "passed": [],
        "finished": [],
        "fallen": [],
        "locked_suits": None,
        "revolution": False,
        "rules": rules,
        "previous_daifugo_id": None,
    }
    state = daifugo_games[game_id]
    return (
        f"大富豪を作成しました。{interaction.user.mention} は自動参加しました。\n"
        f"有効ルール: {rules_text(state)}\n"
        "`/daifugo_join` で参加、`/daifugo_begin` で開始します。"
    )


def create_poker_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in poker_games:
        return "このチャンネルにはすでにポーカーがあります。"
    poker_games[game_id] = {
        "creator_id": interaction.user.id,
        "players": [interaction.user.id],
        "hands": {},
        "deck": [],
        "turn_index": 0,
        "started": False,
        "exchanged": [],
    }
    return f"ポーカーを作成しました。{interaction.user.mention} は自動参加しました。\n`/poker_join` で参加、`/poker_begin` で開始します。"


class GameStartButton(discord.ui.Button):
    def __init__(self, label: str, game: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=row)
        self.game = game

    async def callback(self, interaction: discord.Interaction):
        creators = {
            "uno": create_uno_game,
            "sevens": create_sevens_game,
            "daifugo": create_daifugo_game,
            "poker": create_poker_game,
        }
        text = creators[self.game](interaction)
        await interaction.response.send_message(text)


class OmikujiButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="おみくじ", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction):
        await run_omikuji(interaction)


class DiceButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="1d100", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=roll_dice_embed())


class JankenChoiceButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        user_hand = self.label
        bot_hand = random.choice(["グー", "チョキ", "パー"])
        if user_hand == bot_hand:
            result = "あいこ"
        elif (user_hand, bot_hand) in (("グー", "チョキ"), ("チョキ", "パー"), ("パー", "グー")):
            result = "あなたの勝ち"
        else:
            result = "あなたの負け"
        for child in self.view.children:
            child.disabled = True
        embed = discord.Embed(
            title="じゃんけん結果",
            description=f"あなた: {user_hand}\nBOT: {bot_hand}\n\n**{result}**",
            color=0x00BFFF,
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class JankenButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="じゃんけん", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=30)
        for label in ("グー", "チョキ", "パー"):
            view.add_item(JankenChoiceButton(label))
        await interaction.response.send_message("手を選んでください。", view=view)


class GuideButton(discord.ui.Button):
    def __init__(self, label: str, text: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=2)
        self.text = text

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.text, ephemeral=True)


class QuickView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(GameStartButton("UNO作成", "uno", 0))
        self.add_item(GameStartButton("7並べ作成", "sevens", 0))
        self.add_item(GameStartButton("大富豪作成", "daifugo", 0))
        self.add_item(GameStartButton("ポーカー作成", "poker", 0))
        self.add_item(OmikujiButton())
        self.add_item(DiceButton())
        self.add_item(JankenButton())
        self.add_item(GuideButton("検索", "`/google_search query:検索したい内容` で検索できます。"))
        self.add_item(GuideButton("投票", "`/vote` で投票を作成できます。"))
        self.add_item(GuideButton("リマインダー", "`/remind` で指定時間後の通知を作成できます。"))
        self.add_item(GuideButton("出席確認", "`/attend_status` で出席ポイント一覧を確認できます。"))


class Quick(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="quick", description="日頃よく使う機能をボタンで表示します")
    async def quick(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=quick_embed(), view=QuickView())

    @app_commands.command(name="game_cancel", description="このチャンネルのゲーム募集を中止します")
    @app_commands.describe(game="中止するゲーム", reason="中止理由")
    @app_commands.choices(
        game=[
            app_commands.Choice(name="UNO", value="uno"),
            app_commands.Choice(name="7並べ", value="sevens"),
            app_commands.Choice(name="大富豪", value="daifugo"),
            app_commands.Choice(name="ポーカー", value="poker"),
        ]
    )
    async def game_cancel(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        reason: str = "",
    ):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        label, store = GAME_STORES[game.value]
        game_id = str(interaction.channel_id)
        state = store.get(game_id)
        if not state:
            await interaction.response.send_message(f"このチャンネルに{label}の募集はありません。", ephemeral=True)
            return

        is_admin = interaction.user.guild_permissions.manage_guild
        creator_id = state.get("creator_id") or (state.get("players") or [None])[0]
        is_creator = interaction.user.id == creator_id
        already_started = bool(state.get("started") or state.get("hands"))

        if already_started and not is_admin:
            await interaction.response.send_message("開始済みのゲームを終了できるのは管理者だけです。", ephemeral=True)
            return
        if not is_creator and not is_admin:
            await interaction.response.send_message("募集を中止できるのは作成者または管理者です。", ephemeral=True)
            return

        store.pop(game_id, None)
        suffix = f"\n理由: {reason[:500]}" if reason else ""
        status = "強制終了" if already_started else "募集を中止"
        await interaction.response.send_message(f"{label}を{status}しました。{suffix}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Quick(bot))
