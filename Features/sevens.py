import random

import discord
from discord import app_commands
from discord.ext import commands


SUITS = ["♠", "♥", "♦", "♣"]
SUIT_NAMES = {"♠": "spade", "♥": "heart", "♦": "diamond", "♣": "club"}
RANKS = list(range(1, 14))
RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}
sevens_games: dict[str, dict] = {}


def card_label(card: tuple[str, int]) -> str:
    suit, rank = card
    return f"{suit}{RANK_LABELS.get(rank, str(rank))}"


def parse_card(value: str) -> tuple[str, int]:
    suit_name, rank = value.split("_", 1)
    suit = next(s for s, name in SUIT_NAMES.items() if name == suit_name)
    return suit, int(rank)


def card_value(card: tuple[str, int]) -> str:
    suit, rank = card
    return f"{SUIT_NAMES[suit]}_{rank}"


def build_deck() -> list[tuple[str, int]]:
    return [(suit, rank) for suit in SUITS for rank in RANKS]


def playable_cards(hand: list[tuple[str, int]], board: dict[str, list[int]]) -> list[tuple[str, int]]:
    playable = []
    for card in hand:
        suit, rank = card
        placed = board[suit]
        if rank in placed:
            continue
        if rank == 7:
            playable.append(card)
            continue
        if rank < 7 and rank + 1 in placed:
            playable.append(card)
        elif rank > 7 and rank - 1 in placed:
            playable.append(card)
    return playable


def board_text(board: dict[str, list[int]]) -> str:
    lines = []
    for suit in SUITS:
        placed = set(board[suit])
        cells = []
        for rank in RANKS:
            cells.append(RANK_LABELS.get(rank, str(rank)) if rank in placed else "・")
        lines.append(f"{suit} " + " ".join(cells))
    return "\n".join(lines)


def status_text(state: dict) -> str:
    players = state["players"]
    turn_user = players[state["turn_index"]]
    lines = [
        "🃏 **7並べ**",
        "",
        board_text(state["board"]),
        "",
        f"現在のターン: <@{turn_user}>",
        "手札枚数: "
        + " / ".join(f"<@{uid}> {len(state['hands'][str(uid)])}枚" for uid in players),
        "パス: "
        + " / ".join(f"<@{uid}> {state['passes'].get(str(uid), 0)}回" for uid in players),
    ]
    return "\n".join(lines)


async def send_hand(member: discord.Member, hand: list[tuple[str, int]], playable: list[tuple[str, int]]):
    playable_set = set(playable)
    labels = [
        f"{card_label(card)}{'*' if card in playable_set else ''}"
        for card in sorted(hand, key=lambda c: (SUITS.index(c[0]), c[1]))
    ]
    await member.send(
        "あなたの7並べの手札です。\n"
        "`*` が付いているカードは現在出せます。\n"
        + " ".join(labels)
    )


class SevensPlayView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        state = sevens_games.get(game_id)
        self.game_id = game_id
        self.user_id = user_id
        if not state:
            return

        hand = [tuple(card) for card in state["hands"].get(str(user_id), [])]
        playable = playable_cards(hand, state["board"])
        if playable:
            self.add_item(SevensCardSelect(game_id, user_id, playable[:25]))
        self.add_item(SevensPassButton(game_id, user_id))


class SevensCardSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, cards: list[tuple[str, int]]):
        options = [
            discord.SelectOption(label=card_label(card), value=card_value(card))
            for card in cards
        ]
        super().__init__(
            placeholder="出すカードを選んでください",
            options=options,
            custom_id=f"sevens_select_{game_id}_{user_id}",
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await play_card(interaction, self.game_id, self.user_id, parse_card(self.values[0]))


class SevensPassButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="パス",
            style=discord.ButtonStyle.secondary,
            custom_id=f"sevens_pass_{game_id}_{user_id}",
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await pass_turn(interaction, self.game_id, self.user_id)


async def advance_turn(state: dict):
    players = state["players"]
    for _ in range(len(players)):
        state["turn_index"] = (state["turn_index"] + 1) % len(players)
        next_user = players[state["turn_index"]]
        if str(next_user) not in state["finished"]:
            return


async def update_game_message(interaction: discord.Interaction, state: dict, content_prefix: str = ""):
    game_id = str(interaction.channel_id)
    current_user = state["players"][state["turn_index"]]
    content = (content_prefix + "\n" if content_prefix else "") + status_text(state)
    view = SevensPlayView(game_id, current_user)
    await interaction.response.edit_message(content=content, view=view)


async def finish_if_needed(interaction: discord.Interaction, state: dict, user_id: int) -> bool:
    hand = state["hands"].get(str(user_id), [])
    if hand:
        return False
    state["finished"].append(str(user_id))
    if len(state["finished"]) >= len(state["players"]) - 1:
        winner = state["finished"][0]
        sevens_games.pop(str(interaction.channel_id), None)
        await interaction.response.edit_message(
            content=f"🎉 7並べ終了！勝者: <@{winner}>",
            view=None,
        )
        return True
    return False


async def play_card(interaction: discord.Interaction, game_id: str, user_id: int, card: tuple[str, int]):
    state = sevens_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    hand = [tuple(c) for c in state["hands"][str(user_id)]]
    playable = playable_cards(hand, state["board"])
    if card not in playable:
        await interaction.response.send_message("❌ そのカードは今出せません。", ephemeral=True)
        return

    hand.remove(card)
    state["hands"][str(user_id)] = [list(c) for c in hand]
    state["board"][card[0]].append(card[1])
    state["board"][card[0]].sort()

    if await finish_if_needed(interaction, state, user_id):
        return

    await advance_turn(state)
    await update_game_message(interaction, state, f"🃏 <@{user_id}> が **{card_label(card)}** を出しました。")


async def pass_turn(interaction: discord.Interaction, game_id: str, user_id: int):
    state = sevens_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    key = str(user_id)
    state["passes"][key] = state["passes"].get(key, 0) + 1
    if state["passes"][key] >= 3:
        state["finished"].append(key)
        prefix = f"⛔ <@{user_id}> は3回パスで脱落しました。"
    else:
        prefix = f"⏭️ <@{user_id}> がパスしました。"

    await advance_turn(state)
    await update_game_message(interaction, state, prefix)


class Sevens(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sevens_start", description="7並べゲームを作成します")
    async def sevens_start(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        sevens_games[game_id] = {
            "players": [interaction.user.id],
            "hands": {},
            "board": {suit: [7] for suit in SUITS},
            "turn_index": 0,
            "passes": {},
            "finished": [],
            "started": False,
        }
        await interaction.response.send_message(
            f"🃏 7並べを作成しました。{interaction.user.mention} は自動参加しました。\n"
            "`/sevens_join` で参加、`/sevens_begin` で開始します。"
        )

    @app_commands.command(name="sevens_join", description="7並べに参加します")
    async def sevens_join(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        state = sevens_games.get(game_id)
        if not state:
            await interaction.response.send_message("❌ まず `/sevens_start` を実行してください。", ephemeral=True)
            return
        if state["started"]:
            await interaction.response.send_message("❌ すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("❌ すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await interaction.response.send_message(f"🙌 {interaction.user.mention} が参加しました。")

    @app_commands.command(name="sevens_begin", description="7並べを開始します")
    async def sevens_begin(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        state = sevens_games.get(game_id)
        if not state:
            await interaction.response.send_message("❌ まず `/sevens_start` を実行してください。", ephemeral=True)
            return
        if state["started"]:
            await interaction.response.send_message("❌ すでに開始しています。", ephemeral=True)
            return
        if len(state["players"]) < 2:
            await interaction.response.send_message("❌ 2人以上必要です。", ephemeral=True)
            return

        await interaction.response.defer()
        deck = [card for card in build_deck() if card[1] != 7]
        random.shuffle(deck)
        hands = {str(uid): [] for uid in state["players"]}
        for index, card in enumerate(deck):
            uid = state["players"][index % len(state["players"])]
            hands[str(uid)].append(list(card))
        state["hands"] = hands
        state["started"] = True
        random.shuffle(state["players"])

        failed_dm = []
        for uid in state["players"]:
            member = interaction.guild.get_member(uid)
            if not member:
                continue
            hand = [tuple(c) for c in hands[str(uid)]]
            try:
                await send_hand(member, hand, playable_cards(hand, state["board"]))
            except Exception:
                failed_dm.append(member.mention)

        current_user = state["players"][state["turn_index"]]
        text = status_text(state)
        if failed_dm:
            text += "\n\n⚠️ DM送信に失敗: " + " ".join(failed_dm)
        await interaction.followup.send(text, view=SevensPlayView(game_id, current_user))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sevens(bot))
