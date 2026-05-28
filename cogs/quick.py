import inspect
import random

import discord
from discord import app_commands
from discord.ext import commands

from Features.daifugo import DEFAULT_RULES, daifugo_games, rules_text
from Features.omikuji import run_omikuji
from Features.othello import (
    AI_DIFFICULTIES,
    AI_PLAYER_ID,
    generate_othello_image,
    get_valid_moves,
    new_board,
    othello_games,
    run_ai_turns,
    send_othello_state,
)
from Features.poker import poker_games, set_poker_bet_amount
from Features.sevens import SUITS as SEVENS_SUITS
from Features.sevens import sevens_games
from Features.uno import uno_games


PANEL_TIMEOUT_SECONDS = 600

GAME_STORES = {
    "uno": ("UNO", uno_games),
    "sevens": ("7並べ", sevens_games),
    "daifugo": ("大富豪", daifugo_games),
    "poker": ("ポーカー", poker_games),
    "othello": ("オセロ", othello_games),
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
}


def quick_embed() -> discord.Embed:
    embed = discord.Embed(
        title="クイックメニュー",
        description="日頃よく使う機能だけを集めたメニューです。ボタンからそのまま実行できます。",
        color=0x2ECC71,
    )
    embed.add_field(
        name="ゲーム作成",
        value="UNO / 7並べ / 大富豪 / ポーカー / オセロ",
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
        "bet": 0,
        "pot": 0,
        "bets_collected": False,
    }
    return f"ポーカーを作成しました。{interaction.user.mention} は自動参加しました。\n`/poker_join` で参加、`/poker_begin` で開始します。"


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
        }
        if self.game == "othello":
            await interaction.response.send_message(embed=othello_mode_embed(), view=OthelloModeView())
            return
        text = creators[self.game](interaction)
        _, store = GAME_STORES[self.game]
        state = store.get(str(interaction.channel_id))
        await interaction.response.send_message(game_lobby_text(self.game, state) if state else text, view=GameControlView(self.game))


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
        super().__init__(label="賭け額", style=discord.ButtonStyle.secondary, row=1)

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
    cog_name, command_name = GAME_BEGIN_COMMANDS[game]
    cog = interaction.client.get_cog(cog_name)
    command = getattr(cog, command_name, None) if cog else None
    if not command or not getattr(command, "callback", None):
        await interaction.response.send_message("開始処理を呼び出せませんでした。個別の開始コマンドを使ってください。", ephemeral=True)
        return
    callback = command.callback
    params = list(inspect.signature(callback).parameters)
    if params and params[0] == "self":
        await callback(cog, interaction)
        return
    await callback(interaction)


class GameActionButton(discord.ui.Button):
    def __init__(self, label: str, game: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, style=style, row=row)
        self.game = game
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        creators = {
            "uno": create_uno_game,
            "sevens": create_sevens_game,
            "daifugo": create_daifugo_game,
            "poker": create_poker_game,
        }

        if self.action == "create":
            if self.game == "othello":
                await send_othello_lobby(interaction, text_on_error=True)
                return
            text = creators[self.game](interaction)
            _, store = GAME_STORES[self.game]
            state = store.get(str(interaction.channel_id))
            await interaction.response.send_message(game_lobby_text(self.game, state) if state else text, view=GameControlView(self.game))
        elif self.action == "join":
            if self.game == "othello":
                await interaction.response.send_message("オセロは作成された盤面の「参加する」ボタンから参加してください。", ephemeral=True)
                return
            _, store = GAME_STORES[self.game]
            before_state = store.get(str(interaction.channel_id))
            before_players = list(before_state.get("players", [])) if before_state else []
            text = join_game(interaction, self.game)
            state = store.get(str(interaction.channel_id))
            if state and interaction.message and len(state.get("players", [])) > len(before_players):
                await interaction.response.edit_message(content=game_lobby_text(self.game, state), view=self.view)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        elif self.action == "leave":
            _, store = GAME_STORES[self.game]
            before_state = store.get(str(interaction.channel_id))
            text = leave_game(interaction, self.game)
            state = store.get(str(interaction.channel_id))
            if before_state and not state and interaction.message:
                await interaction.response.edit_message(content=text, view=None)
            elif state and interaction.message:
                await interaction.response.edit_message(content=game_lobby_text(self.game, state), view=self.view)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        elif self.action == "begin":
            await begin_game(interaction, self.game)
            _, store = GAME_STORES[self.game]
            state = store.get(str(interaction.channel_id))
            if state and state.get("started") and interaction.message:
                try:
                    await interaction.message.edit(content=game_lobby_text(self.game, state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        elif self.action == "cancel":
            ok, text = cancel_game(interaction, self.game)
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
        super().__init__(label=label, style=style, row=row)
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
        if game != "othello":
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
        ]
        super().__init__(placeholder="遊ぶゲームを選んでください", options=options)

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        label, _ = GAME_STORES[game]
        if game == "othello":
            await interaction.response.send_message(embed=othello_mode_embed(), view=OthelloModeView())
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


class QuickView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT_SECONDS)
        self.add_item(GameStartButton("UNO作成", "uno", 0))
        self.add_item(GameStartButton("7並べ作成", "sevens", 0))
        self.add_item(GameStartButton("大富豪作成", "daifugo", 0))
        self.add_item(GameStartButton("ポーカー作成", "poker", 0))
        self.add_item(GameStartButton("オセロ作成", "othello", 1))
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
