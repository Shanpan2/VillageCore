import inspect
import random

import discord
from discord import app_commands
from discord.ext import commands

from Features.codenames import (
    CodenamesLobbyView,
    begin_codenames,
    codenames_games,
    delete_codenames_game,
    lobby_text as codenames_lobby_text,
    save_codenames_game,
)
from Features.daifugo import (
    DEFAULT_RULES,
    DaifugoLobbyView,
    daifugo_games,
    delete_daifugo_game,
    rules_text,
    save_daifugo_game,
    start_daifugo_game,
)
from Features.ito import ItoLobbyView, DEFAULT_TOPICS, begin_ito, delete_ito_game, ito_games, lobby_text as ito_lobby_text, save_ito_game
from Features.omikuji import run_omikuji
from Features.gomoku import GomokuModeView, delete_gomoku_game, gomoku_games, gomoku_mode_embed
from Features.othello import (
    AI_DIFFICULTIES,
    AI_PLAYER_ID,
    generate_othello_image,
    get_valid_moves,
    new_board,
    othello_games,
    run_ai_turns,
    save_othello_game,
    send_othello_state,
)
from Features.poker import PokerLobbyView, delete_poker_game, poker_games, save_poker_game, set_poker_bet_amount, start_poker_game
from Features.sevens import SUITS as SEVENS_SUITS
from Features.sevens import SevensLobbyView, delete_sevens_game, save_sevens_game, sevens_games, start_sevens_game
from Features.shogi import ShogiPanelView, shogi_panel_embed
from Features.shogi_puzzle import ShogiPuzzleLevelView, shogi_puzzle_embed
from Features.uno import UnoLobbyView, delete_uno_game, save_uno_game, uno_games, start_uno_game
from Features.werewolf import (
    WerewolfLobbyView,
    delete_werewolf_game,
    lobby_text as werewolf_lobby_text,
    save_werewolf_game,
    start_match,
    werewolf_games,
)


PANEL_TIMEOUT_SECONDS = None

GAME_STORES = {
    "uno": ("UNO", uno_games),
    "sevens": ("7並べ", sevens_games),
    "daifugo": ("大富豪", daifugo_games),
    "poker": ("ポーカー", poker_games),
    "othello": ("オセロ", othello_games),
    "gomoku": ("五目並べ", gomoku_games),
    "ito": ("Ito", ito_games),
    "codenames": ("コードネーム", codenames_games),
    "werewolf": ("人狼", werewolf_games),
}

GAME_BEGIN_COMMANDS = {
    "uno": ("Uno", "uno_begin"),
    "sevens": ("Sevens", "sevens_begin"),
    "daifugo": ("Daifugo", "daifugo_begin"),
    "poker": ("Poker", "poker_begin"),
}

GAME_RULES = {
    "uno": (
        "UNOは、場のカードと同じ色・数字・記号のカードを出していき、"
        "先に手札をなくした人が勝ちです。出せない時は山札から引きます。"
        "残り1枚になったらUNO宣言を忘れないようにしてください。"
    ),
    "sevens": (
        "7並べは、各マークの7を中心に6、8、5、9のように順番につなげて出します。"
        "出せない時はパスできます。手札を早くなくした人から順位が決まります。"
    ),
    "daifugo": (
        "大富豪は、前の人より強いカード、または同じ枚数の組み合わせを出していき、"
        "先に手札をなくした人が上がりです。革命、8切り、階段、しばり、都落ちなどは"
        "募集時の設定で切り替えできます。"
    ),
    "poker": (
        "ポーカーは5枚の手札がDMで届き、交換したいカードを選びます。"
        "全員の交換が終わると役の強さで勝敗が決まります。"
        "強い順はストレートフラッシュ、フォーカード、フルハウス、フラッシュ、"
        "ストレート、スリーカード、ツーペア、ワンペア、ハイカードです。"
    ),
    "othello": (
        "オセロは黒と白の石で相手の石を挟んで裏返すゲームです。"
        "置ける場所がない時は自動でパスされ、両方が置けなくなると終了します。"
        "最後に石が多いプレイヤーの勝ちです。"
    ),
    "gomoku": (
        "五目並べは黒と白の石を交互に置き、縦・横・斜めのいずれかで先に5個並べた人が勝ちです。"
        "行と列を選んでから「置く」を押します。AI戦は初級・中級・上級から選べます。"
    ),
    "ito": (
        "Itoは、配られた数字を直接言わずに例えで表現する協力ゲームです。"
        "お題に沿って自分の数字の大きさを表現し、最後に全員を小さい順に並べます。"
        "数字の順番が正しければ成功です。例え提出と順番提出は `/ito` から行います。"
    ),
    "codenames": (
        "コードネームは赤青チームに分かれて単語を当てるゲームです。"
        "スパイマスターは正解盤面を見て、1語のヒントと枚数を出します。"
        "推理側は味方の単語を選びます。暗殺者を選ぶと即敗北です。"
    ),
    "werewolf": (
        "人狼は村人陣営と人狼陣営に分かれて正体を探る会話ゲームです。"
        "夜は人狼が襲撃し、占い師や騎士が能力を使います。"
        "昼は話し合いで怪しい人に投票します。"
        "村人陣営は人狼を全員追放すれば勝ち、人狼陣営は人狼の数が村人陣営以上になれば勝ちです。"
    ),
}


def quick_embed() -> discord.Embed:
    embed = discord.Embed(
        title="クイックメニュー",
        description="日頃よく使う機能だけを集めたメニューです。ボタンからそのまま実行できます。",
        color=0x2ECC71,
    )
    embed.add_field(
        name="ゲーム",
        value="ゲームボタンから、UNO / 7並べ / 大富豪 / ポーカー / オセロ / 将棋 / 詰将棋 / Ito / コードネーム / 人狼を選べます。",
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
        "channel_id": interaction.channel_id,
        "players": [interaction.user.id],
        "hands": {},
        "deck": [],
        "discard": [],
        "turn_index": 0,
        "direction": 1,
        "top": None,
        "uno_declared": False,
        "challenge_mode": True,
        "pending": None,
        "guild_id": interaction.guild_id,
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
        "guild_id": interaction.guild_id,
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
        "guild_id": interaction.guild_id,
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
        "bet": 0,
        "pot": 0,
        "bets_collected": False,
        "guild_id": interaction.guild_id,
    }
    return f"ポーカーを作成しました。{interaction.user.mention} は自動参加しました。\n`/poker_join` で参加、`/poker_begin` で開始します。"


def create_ito_game(interaction: discord.Interaction, topic_text: str | None = None) -> str:
    game_id = str(interaction.channel_id)
    if game_id in ito_games:
        return "このチャンネルにはすでにItoがあります。"
    topic = (topic_text or "").strip() or random.choice(DEFAULT_TOPICS)
    ito_games[game_id] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "creator_id": interaction.user.id,
        "phase": "lobby",
        "topic": topic,
        "players": [interaction.user.id],
        "numbers": {},
        "clues": {},
    }
    return f"Itoを作成しました。お題: **{topic}**\n{interaction.user.mention} は自動参加しました。"


def create_codenames_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in codenames_games:
        return "このチャンネルにはすでにコードネームがあります。"
    codenames_games[game_id] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "creator_id": interaction.user.id,
        "phase": "lobby",
        "teams": {"red": [], "blue": []},
        "spymasters": {},
        "board": [],
    }
    return "コードネームを作成しました。赤/青チームに参加し、各チームのスパイマスターを設定してください。"


def create_werewolf_game(interaction: discord.Interaction) -> str:
    game_id = str(interaction.channel_id)
    if game_id in werewolf_games:
        return "このチャンネルにはすでに人狼ゲームがあります。"
    werewolf_games[game_id] = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "creator_id": interaction.user.id,
        "phase": "lobby",
        "players": [interaction.user.id],
        "roles": {},
        "alive": [],
        "day": 0,
        "night_actions": {},
        "votes": {},
    }
    return f"人狼ゲームを作成しました。{interaction.user.mention} は自動参加しました。"


def create_othello_game(interaction: discord.Interaction) -> tuple[str, discord.Embed | None, discord.File | None]:
    game_id = str(interaction.channel_id)
    if game_id in othello_games:
        return "このチャンネルにはすでにオセロがあります。", None, None
    board = new_board()
    othello_games[game_id] = {
        "board": board,
        "turn": 1,
        "black_id": interaction.user.id,
        "white_id": None,
        "creator_id": interaction.user.id,
        "guild_id": interaction.guild_id,
    }
    valid_moves = get_valid_moves(board, 1)
    file = discord.File(generate_othello_image(board, valid_moves), filename="othello.png")
    embed = discord.Embed(
        title="🎮 オセロ開始！",
        description=(
            f"黒番（先手）：{interaction.user.mention}\n"
            "白番（後手）：まだ参加していません。\n"
            "参加後、置ける場所を選択してください。"
        ),
        color=0x2ECC71,
    )
    return "オセロを作成しました。", embed, file


async def send_othello_lobby(interaction: discord.Interaction, text_on_error: bool = False):
    from views.othello_views import OthelloView

    text, embed, file = create_othello_game(interaction)
    state = othello_games.get(str(interaction.channel_id))
    if embed and file and state:
        valid_moves = get_valid_moves(state["board"], state["turn"])
        await save_othello_game(interaction.guild_id, str(interaction.channel_id), state)
        await interaction.response.send_message(
            embed=embed,
            file=file,
            view=OthelloView(str(interaction.channel_id), valid_moves, show_join=True),
        )
        return
    await interaction.response.send_message(text, ephemeral=text_on_error)


async def send_othello_ai_lobby(interaction: discord.Interaction, difficulty: str):
    game_id = str(interaction.channel_id)
    if game_id in othello_games:
        await interaction.response.send_message("このチャンネルにはすでにオセロがあります。", ephemeral=True)
        return

    board = new_board()
    othello_games[game_id] = {
        "board": board,
        "turn": 1,
        "black_id": interaction.user.id,
        "white_id": AI_PLAYER_ID,
        "creator_id": interaction.user.id,
        "guild_id": interaction.guild_id,
        "ai": True,
        "human_id": interaction.user.id,
        "human_color": 1,
        "ai_color": 2,
        "difficulty": difficulty,
        "bet": 0,
        "coin_settled": False,
    }
    prefix = f"AI対戦を開始しました。難易度: **{AI_DIFFICULTIES[difficulty]['label']}**"
    prefix = await run_ai_turns(othello_games[game_id], prefix)
    await send_othello_state(interaction, game_id, prefix, initial=True)


def othello_mode_embed() -> discord.Embed:
    return discord.Embed(
        title="オセロ パネル",
        description=(
            "遊び方を選んでください。\n"
            "対人戦は参加ボタンで後手が入ります。AI戦はあなたが先手、賭けなしで開始します。"
        ),
        color=0x3498DB,
    )


def game_lobby_text(game: str, state: dict | None) -> str:
    if game == "ito" and state:
        return ito_lobby_text(state)
    if game == "codenames" and state:
        return codenames_lobby_text(state)
    if game == "werewolf" and state:
        return werewolf_lobby_text(state)
    label, _ = GAME_STORES[game]
    if not state:
        return f"{label}の募集はありません。"
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", []))
    lines = [
        f"**{label}募集**",
        f"参加者: {players or 'なし'}",
    ]
    if game == "poker":
        bet = int(state.get("bet", 0) or 0)
        pot = int(state.get("pot", 0) or 0) or bet * len(state.get("players", []))
        lines.insert(1, f"賭けコイン: {'なし' if bet <= 0 else f'1人 {bet} / ポット {pot}'}")
    if game == "daifugo":
        lines.insert(1, f"有効ルール: {rules_text(state)}")
    lines.append("")
    lines.append("下のボタンで参加、抜ける、開始、中止、ルール確認ができます。")
    return "\n".join(lines)


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
            "ito": create_ito_game,
            "codenames": create_codenames_game,
            "werewolf": create_werewolf_game,
        }
        if self.game == "othello":
            await interaction.response.send_message(embed=othello_mode_embed(), view=OthelloModeView())
            return
        if self.game == "gomoku":
            await interaction.response.send_message(embed=gomoku_mode_embed(), view=GomokuModeView())
            return
        text = creators[self.game](interaction)
        _, store = GAME_STORES[self.game]
        state = store.get(str(interaction.channel_id))
        if self.game == "poker" and state:
            await save_poker_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "sevens" and state:
            await save_sevens_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "daifugo" and state:
            await save_daifugo_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "uno" and state:
            await save_uno_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "ito" and state:
            await save_ito_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "codenames" and state:
            await save_codenames_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "werewolf" and state:
            await save_werewolf_game(interaction.guild_id, str(interaction.channel_id), state)
        if self.game == "poker" and state:
            view = PokerLobbyView(str(interaction.channel_id))
        elif self.game == "uno" and state:
            view = UnoLobbyView(str(interaction.channel_id))
        elif self.game == "sevens" and state:
            view = SevensLobbyView(str(interaction.channel_id))
        elif self.game == "daifugo" and state:
            view = DaifugoLobbyView(str(interaction.channel_id))
        elif self.game == "ito" and state:
            view = ItoLobbyView(str(interaction.channel_id))
        elif self.game == "codenames" and state:
            view = CodenamesLobbyView(str(interaction.channel_id))
        elif self.game == "werewolf" and state:
            view = WerewolfLobbyView(str(interaction.channel_id))
        else:
            view = GameControlView(self.game)
        await interaction.response.send_message(game_lobby_text(self.game, state) if state else text, view=view)


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


class PokerBetModal(discord.ui.Modal, title="ポーカー賭け額設定"):
    amount = discord.ui.TextInput(
        label="1人あたりの賭けコイン数",
        placeholder="0で賭けなし / 例: 10",
        required=True,
        max_length=8,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message("数字で入力してください。", ephemeral=True)
            return
        message = await set_poker_bet_amount(interaction, bet)
        await interaction.response.send_message(message, ephemeral=True)


class PokerBetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="賭け額", style=discord.ButtonStyle.secondary, row=1, custom_id="game_action_poker_bet")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PokerBetModal())


def game_status_embed(game: str) -> discord.Embed:
    label, store = GAME_STORES[game]
    state = store.get("__none__")
    embed = discord.Embed(title=f"{label} パネル", color=0x3498DB)
    embed.description = "下のボタンから募集作成、参加、抜ける、開始、中止、ルール確認ができます。"
    return embed


def join_game(interaction: discord.Interaction, game: str) -> str:
    label, store = GAME_STORES[game]
    state = store.get(str(interaction.channel_id))
    if not state:
        return f"このチャンネルに{label}の募集はありません。先に「募集作成」を押してください。"
    if state.get("started") or state.get("hands"):
        return f"{label}はすでに開始されています。"
    if interaction.user.id in state["players"]:
        return "すでに参加しています。"
    if game == "poker" and len(state["players"]) >= 8:
        return "ポーカーに参加できるのは最大8人までです。"
    state["players"].append(interaction.user.id)
    return f"{interaction.user.mention} が{label}に参加しました。現在の参加者: {len(state['players'])}人"


def leave_game(interaction: discord.Interaction, game: str) -> str:
    label, store = GAME_STORES[game]
    state = store.get(str(interaction.channel_id))
    if not state:
        return f"このチャンネルに{label}の募集はありません。"
    if state.get("started") or state.get("hands"):
        return f"{label}はすでに開始されています。開始後は降参ボタンを使ってください。"
    players = state.get("players", [])
    if interaction.user.id not in players:
        return "まだ参加していません。"
    players.remove(interaction.user.id)
    if not players:
        store.pop(str(interaction.channel_id), None)
        return f"{interaction.user.mention} が抜けたため、{label}募集を終了しました。"
    if state.get("creator_id") == interaction.user.id:
        state["creator_id"] = players[0]
    return f"{interaction.user.mention} が{label}から抜けました。現在の参加者: {len(players)}人"


def cancel_game(interaction: discord.Interaction, game: str) -> tuple[bool, str]:
    label, store = GAME_STORES[game]
    state = store.get(str(interaction.channel_id))
    if not state:
        return False, f"このチャンネルに{label}の募集はありません。"

    is_admin = interaction.user.guild_permissions.manage_guild
    creator_id = state.get("creator_id") or (state.get("players") or [None])[0]
    is_creator = interaction.user.id == creator_id
    already_started = bool(state.get("started") or state.get("hands"))
    if already_started and not is_admin:
        return False, "開始済みのゲームを終了できるのは管理者だけです。"
    if not is_creator and not is_admin:
        return False, "募集を中止できるのは作成者または管理者です。"

    store.pop(str(interaction.channel_id), None)
    status = "強制終了" if already_started else "募集を中止"
    return True, f"{label}を{status}しました。"


async def begin_game(interaction: discord.Interaction, game: str):
    if game == "poker":
        await start_poker_game(interaction, str(interaction.channel_id))
        return
    if game == "uno":
        await start_uno_game(interaction, str(interaction.channel_id))
        return
    if game == "sevens":
        await start_sevens_game(interaction, str(interaction.channel_id))
        return
    if game == "daifugo":
        await start_daifugo_game(interaction, str(interaction.channel_id))
        return
    if game == "ito":
        await begin_ito(interaction, str(interaction.channel_id))
        return
    if game == "codenames":
        await begin_codenames(interaction, str(interaction.channel_id))
        return
    if game == "werewolf":
        state = werewolf_games.get(str(interaction.channel_id))
        await start_match(interaction, str(interaction.channel_id), state or {})
        return
    cog_name, command_name = GAME_BEGIN_COMMANDS[game]
    cog = interaction.client.get_cog(cog_name)
    command = getattr(cog, command_name, None) if cog else None
    if not command or not getattr(command, "callback", None):
        await interaction.response.send_message("開始処理を呼び出せませんでした。個別の開始コマンドを使ってください。", ephemeral=True)
        return
    callback = command.callback
    params = list(inspect.signature(callback).parameters)
    try:
        if params and params[0] == "self":
            await callback(cog, interaction)
            return
        await callback(interaction)
    except Exception as e:
        print(f"[quick.begin_game] {game} error: {type(e).__name__}: {e}", flush=True)
        message = "開始処理中にエラーが発生しました。個別の開始コマンドでもう一度試してください。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class ItoTopicModal(discord.ui.Modal, title="Itoのお題"):
    topic = discord.ui.TextInput(
        label="お題",
        placeholder="空欄ならランダムお題で作成します",
        required=False,
        max_length=80,
    )

    async def on_submit(self, interaction: discord.Interaction):
        text = create_ito_game(interaction, str(self.topic.value))
        state = ito_games.get(str(interaction.channel_id))
        if state:
            await save_ito_game(interaction.guild_id, str(interaction.channel_id), state)
        await interaction.response.send_message(
            game_lobby_text("ito", state) if state else text,
            view=ItoLobbyView(str(interaction.channel_id)) if state else None,
        )


class GameActionButton(discord.ui.Button):
    def __init__(self, label: str, game: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row, custom_id=f"game_action_{game}_{action}")
        self.game = game
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        creators = {
            "uno": create_uno_game,
            "sevens": create_sevens_game,
            "daifugo": create_daifugo_game,
            "poker": create_poker_game,
            "ito": create_ito_game,
            "codenames": create_codenames_game,
            "werewolf": create_werewolf_game,
        }

        if self.action == "create":
            if self.game == "othello":
                await send_othello_lobby(interaction, text_on_error=True)
                return
            if self.game == "gomoku":
                await interaction.response.send_message(embed=gomoku_mode_embed(), view=GomokuModeView())
                return
            if self.game == "ito":
                await interaction.response.send_modal(ItoTopicModal())
                return
            text = creators[self.game](interaction)
            _, store = GAME_STORES[self.game]
            state = store.get(str(interaction.channel_id))
            if self.game == "poker" and state:
                await save_poker_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "sevens" and state:
                await save_sevens_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "daifugo" and state:
                await save_daifugo_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "uno" and state:
                await save_uno_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "ito" and state:
                await save_ito_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "codenames" and state:
                await save_codenames_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "werewolf" and state:
                await save_werewolf_game(interaction.guild_id, str(interaction.channel_id), state)
            if self.game == "poker" and state:
                view = PokerLobbyView(str(interaction.channel_id))
            elif self.game == "uno" and state:
                view = UnoLobbyView(str(interaction.channel_id))
            elif self.game == "sevens" and state:
                view = SevensLobbyView(str(interaction.channel_id))
            elif self.game == "daifugo" and state:
                view = DaifugoLobbyView(str(interaction.channel_id))
            elif self.game == "ito" and state:
                view = ItoLobbyView(str(interaction.channel_id))
            elif self.game == "codenames" and state:
                view = CodenamesLobbyView(str(interaction.channel_id))
            elif self.game == "werewolf" and state:
                view = WerewolfLobbyView(str(interaction.channel_id))
            else:
                view = GameControlView(self.game)
            await interaction.response.send_message(game_lobby_text(self.game, state) if state else text, view=view)
        elif self.action == "join":
            if self.game == "othello":
                await interaction.response.send_message("オセロは作成された盤面の「参加する」ボタンから参加してください。", ephemeral=True)
                return
            if self.game == "gomoku":
                await interaction.response.send_message("五目並べは作成された盤面の「参加する」ボタンから参加してください。", ephemeral=True)
                return
            _, store = GAME_STORES[self.game]
            before_state = store.get(str(interaction.channel_id))
            before_players = list(before_state.get("players", [])) if before_state else []
            text = join_game(interaction, self.game)
            state = store.get(str(interaction.channel_id))
            if self.game == "poker" and state and len(state.get("players", [])) > len(before_players):
                await save_poker_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if self.game == "sevens" and state and len(state.get("players", [])) > len(before_players):
                await save_sevens_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if self.game == "daifugo" and state and len(state.get("players", [])) > len(before_players):
                await save_daifugo_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if self.game == "uno" and state and len(state.get("players", [])) > len(before_players):
                await save_uno_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if self.game == "ito" and state and len(state.get("players", [])) > len(before_players):
                await save_ito_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if self.game == "werewolf" and state and len(state.get("players", [])) > len(before_players):
                await save_werewolf_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
            if state and interaction.message and len(state.get("players", [])) > len(before_players):
                await interaction.response.edit_message(content=game_lobby_text(self.game, state), view=self.view)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        elif self.action == "leave":
            _, store = GAME_STORES[self.game]
            before_state = store.get(str(interaction.channel_id))
            text = leave_game(interaction, self.game)
            state = store.get(str(interaction.channel_id))
            if self.game == "poker":
                if state:
                    await save_poker_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_poker_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "sevens":
                if state:
                    await save_sevens_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_sevens_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "daifugo":
                if state:
                    await save_daifugo_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_daifugo_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "uno":
                if state:
                    await save_uno_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_uno_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "ito":
                if state:
                    await save_ito_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_ito_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "werewolf":
                if state:
                    await save_werewolf_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
                elif before_state:
                    await delete_werewolf_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if before_state and not state and interaction.message:
                await interaction.response.edit_message(content=text, view=None)
            elif state and interaction.message:
                await interaction.response.edit_message(content=game_lobby_text(self.game, state), view=self.view)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        elif self.action == "begin":
            try:
                await begin_game(interaction, self.game)
            except Exception as e:
                print(f"[GameActionButton.begin] {self.game} error: {type(e).__name__}: {e}", flush=True)
                message = "開始処理中にエラーが発生しました。少し待ってから、もう一度開始ボタンを押してください。"
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(message, ephemeral=True)
                    else:
                        await interaction.response.send_message(message, ephemeral=True)
                except Exception:
                    pass
                return
            _, store = GAME_STORES[self.game]
            state = store.get(str(interaction.channel_id))
            if state and state.get("started") and interaction.message:
                try:
                    await interaction.message.edit(content=game_lobby_text(self.game, state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        elif self.action == "cancel":
            _, store = GAME_STORES[self.game]
            before_state = store.get(str(interaction.channel_id))
            ok, text = cancel_game(interaction, self.game)
            if self.game == "poker" and ok and before_state:
                await delete_poker_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "sevens" and ok and before_state:
                await delete_sevens_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "daifugo" and ok and before_state:
                await delete_daifugo_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "uno" and ok and before_state:
                await delete_uno_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "ito" and ok and before_state:
                await delete_ito_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "codenames" and ok and before_state:
                await delete_codenames_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if self.game == "werewolf" and ok and before_state:
                await delete_werewolf_game(interaction.guild_id or before_state.get("guild_id"), str(interaction.channel_id))
            if ok and interaction.message:
                await interaction.response.edit_message(content=text, view=None)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        elif self.action == "rules":
            label, _ = GAME_STORES[self.game]
            embed = discord.Embed(title=f"{label} のルール", description=GAME_RULES[self.game], color=0xF1C40F)
            await interaction.response.send_message(embed=embed, ephemeral=True)


class OthelloModeButton(discord.ui.Button):
    def __init__(self, label: str, mode: str, difficulty: str | None = None, row: int = 0):
        style = discord.ButtonStyle.primary if mode == "pvp" else discord.ButtonStyle.success
        custom_id = f"game_othello_mode_{mode}_{difficulty or 'pvp'}"
        super().__init__(label=label, style=style, row=row, custom_id=custom_id)
        self.mode = mode
        self.difficulty = difficulty

    async def callback(self, interaction: discord.Interaction):
        if self.mode == "pvp":
            await send_othello_lobby(interaction, text_on_error=True)
            return
        await send_othello_ai_lobby(interaction, self.difficulty or "normal")


class OthelloModeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(OthelloModeButton("対人作成", "pvp", row=0))
        self.add_item(OthelloModeButton("AI: 易", "ai", "easy", row=0))
        self.add_item(OthelloModeButton("AI: 普通", "ai", "normal", row=0))
        self.add_item(OthelloModeButton("AI: 難", "ai", "hard", row=1))
        self.add_item(OthelloModeButton("AI: 達人", "ai", "master", row=1))
        self.add_item(GameActionButton("ルール", "othello", "rules", discord.ButtonStyle.secondary, 1))


class GameControlView(discord.ui.View):
    def __init__(self, game: str):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(GameActionButton("募集作成", game, "create", discord.ButtonStyle.primary, 0))
        if game not in ("othello", "codenames"):
            self.add_item(GameActionButton("参加", game, "join", discord.ButtonStyle.success, 0))
            self.add_item(GameActionButton("抜ける", game, "leave", discord.ButtonStyle.secondary, 0))
            self.add_item(GameActionButton("開始", game, "begin", discord.ButtonStyle.primary, 1))
        self.add_item(GameActionButton("中止", game, "cancel", discord.ButtonStyle.danger, 1))
        if game == "poker":
            self.add_item(PokerBetButton())
        self.add_item(GameActionButton("ルール", game, "rules", discord.ButtonStyle.secondary, 1))


class GameSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="UNO", value="uno", description="色・数字・記号を合わせて手札をなくすゲーム"),
            discord.SelectOption(label="7並べ", value="sevens", description="7を中心にカードを順番につなげるゲーム"),
            discord.SelectOption(label="大富豪", value="daifugo", description="手札を早く出し切る定番トランプゲーム"),
            discord.SelectOption(label="ポーカー", value="poker", description="5枚の役で勝負するトランプゲーム"),
            discord.SelectOption(label="オセロ", value="othello", description="盤面に石を置いて相手の石を裏返すゲーム"),
            discord.SelectOption(label="五目並べ", value="gomoku", description="先に5つ石を並べる定番盤面ゲーム"),
            discord.SelectOption(label="将棋", value="shogi", description="2人で対局する仮版の本将棋"),
            discord.SelectOption(label="詰将棋", value="shogi_puzzle", description="レベル別の詰将棋に挑戦してコインを獲得"),
            discord.SelectOption(label="Ito", value="ito", description="数字を言わずに例えで順番を当てる協力ゲーム"),
            discord.SelectOption(label="コードネーム", value="codenames", description="ヒントから味方チームの単語を当てるチームゲーム"),
            discord.SelectOption(label="人狼", value="werewolf", description="会話と投票で人狼を探す正体隠匿ゲーム"),
        ]
        super().__init__(placeholder="遊ぶゲームを選んでください", options=options, custom_id="game_select_menu")

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        if game == "shogi_puzzle":
            await interaction.response.send_message(embed=shogi_puzzle_embed(), view=ShogiPuzzleLevelView())
            return
        if game == "shogi":
            await interaction.response.send_message(embed=shogi_panel_embed(), view=ShogiPanelView())
            return
        label, _ = GAME_STORES[game]
        if game == "othello":
            await interaction.response.send_message(embed=othello_mode_embed(), view=OthelloModeView())
            return
        if game == "gomoku":
            await interaction.response.send_message(embed=gomoku_mode_embed(), view=GomokuModeView())
            return
        embed = discord.Embed(
            title=f"{label} パネル",
            description="募集作成、参加、抜ける、開始、中止、ルール確認をボタンで操作できます。",
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, view=GameControlView(game))


class GameMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(GameSelect())


class GameMenuButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="ゲーム", style=discord.ButtonStyle.primary, row=0)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="ゲームパネル",
            description=(
                "遊びたいゲームを選んでください。\n"
                "選択後に、募集作成・参加・抜ける・開始・中止・ルール確認をボタンで操作できます。"
            ),
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, view=GameMenuView())


class QuickView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(GameMenuButton())
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

    @app_commands.command(name="game", description="ゲームを選んでボタンで操作します")
    async def game(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="ゲームパネル",
            description=(
                "遊びたいゲームを選んでください。\n"
                "選択後に、募集作成・参加・抜ける・開始・中止・ルール確認をボタンで操作できます。"
            ),
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, view=GameMenuView())

    @app_commands.command(name="game_cancel", description="このチャンネルのゲーム募集を中止します")
    @app_commands.describe(game="中止するゲーム", reason="中止理由")
    @app_commands.choices(
        game=[
            app_commands.Choice(name="UNO", value="uno"),
            app_commands.Choice(name="7並べ", value="sevens"),
            app_commands.Choice(name="大富豪", value="daifugo"),
            app_commands.Choice(name="ポーカー", value="poker"),
            app_commands.Choice(name="オセロ", value="othello"),
            app_commands.Choice(name="五目並べ", value="gomoku"),
            app_commands.Choice(name="Ito", value="ito"),
            app_commands.Choice(name="コードネーム", value="codenames"),
            app_commands.Choice(name="人狼", value="werewolf"),
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
        if game.value == "poker":
            await delete_poker_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "sevens":
            await delete_sevens_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "daifugo":
            await delete_daifugo_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "uno":
            await delete_uno_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "ito":
            await delete_ito_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "codenames":
            await delete_codenames_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "werewolf":
            await delete_werewolf_game(interaction.guild_id or state.get("guild_id"), game_id)
        if game.value == "gomoku":
            await delete_gomoku_game(interaction.guild_id or state.get("guild_id"), game_id)
        suffix = f"\n理由: {reason[:500]}" if reason else ""
        status = "強制終了" if already_started else "募集を中止"
        await interaction.response.send_message(f"{label}を{status}しました。{suffix}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Quick(bot))
