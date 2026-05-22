import random
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_NAMES = {"S": "spade", "H": "heart", "D": "diamond", "C": "club"}
RANKS = list(range(1, 14))
RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}
BOARD_IMAGE_PATH = Path("sevens_board.png")
sevens_games: dict[str, dict] = {}


def rank_label(rank: int) -> str:
    return RANK_LABELS.get(rank, str(rank))


def card_label(card: tuple[str, int]) -> str:
    suit, rank = card
    return f"{SUIT_SYMBOLS[suit]}{rank_label(rank)}"


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
    for suit, rank in hand:
        placed = board[suit]
        if rank in placed:
            continue
        if rank == 7:
            playable.append((suit, rank))
        elif rank < 7 and rank + 1 in placed:
            playable.append((suit, rank))
        elif rank > 7 and rank - 1 in placed:
            playable.append((suit, rank))
    return playable


def status_text(state: dict, prefix: str = "") -> str:
    players = state["players"]
    active_players = [uid for uid in players if str(uid) not in state["finished"]]
    turn_user = players[state["turn_index"]] if active_players else players[0]
    lines = []
    if prefix:
        lines.append(prefix)
    lines.extend([
        "🃏 **7並べ**",
        f"現在のターン: <@{turn_user}>",
        "手札: " + " / ".join(f"<@{uid}> {len(state['hands'].get(str(uid), []))}枚" for uid in players),
        "パス: " + " / ".join(f"<@{uid}> {state['passes'].get(str(uid), 0)}回" for uid in players),
    ])
    return "\n".join(lines)


def render_board_image(state: dict, path: Path = BOARD_IMAGE_PATH) -> Path:
    cell_w, cell_h = 62, 82
    left, top = 76, 58
    width = left + cell_w * len(RANKS) + 28
    height = top + cell_h * len(SUITS) + 28
    image = Image.new("RGB", (width, height), (25, 96, 66))
    draw = ImageDraw.Draw(image)

    try:
        rank_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        suit_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except Exception:
        rank_font = ImageFont.load_default()
        suit_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.text((24, 16), "7並べ", fill=(255, 255, 255), font=suit_font)
    for idx, rank in enumerate(RANKS):
        x = left + idx * cell_w
        draw.text((x + 20, 28), rank_label(rank), fill=(225, 235, 225), font=small_font)

    for row, suit in enumerate(SUITS):
        y = top + row * cell_h
        suit_color = (235, 70, 70) if suit in ("H", "D") else (245, 245, 245)
        draw.text((28, y + 24), SUIT_SYMBOLS[suit], fill=suit_color, font=suit_font)
        placed = set(state["board"][suit])
        for col, rank in enumerate(RANKS):
            x = left + col * cell_w
            is_placed = rank in placed
            fill = (248, 248, 240) if is_placed else (34, 119, 82)
            outline = (230, 230, 220) if is_placed else (74, 151, 111)
            draw.rounded_rectangle((x, y, x + 52, y + 70), radius=8, fill=fill, outline=outline, width=2)
            if is_placed:
                text = f"{SUIT_SYMBOLS[suit]}{rank_label(rank)}"
                color = (190, 35, 35) if suit in ("H", "D") else (25, 25, 25)
                bbox = draw.textbbox((0, 0), text, font=rank_font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((x + 26 - tw / 2, y + 35 - th / 2), text, fill=color, font=rank_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def board_file(state: dict) -> discord.File:
    path = render_board_image(state)
    return discord.File(path, filename="sevens_board.png")


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


def draw_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    card: tuple[str, int],
    font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    playable: bool = False,
):
    x, y = xy
    suit, rank = card
    suit_color = (196, 34, 34) if suit in ("H", "D") else (25, 25, 25)
    outline = (255, 206, 84) if playable else (220, 220, 210)
    width = 4 if playable else 2

    draw.rounded_rectangle(
        (x, y, x + 92, y + 128),
        radius=10,
        fill=(248, 248, 240),
        outline=outline,
        width=width,
    )
    label = rank_label(rank)
    draw.text((x + 10, y + 8), label, fill=suit_color, font=small_font)
    draw.text((x + 10, y + 30), SUIT_SYMBOLS[suit], fill=suit_color, font=small_font)

    center_text = f"{SUIT_SYMBOLS[suit]}{label}"
    bbox = draw.textbbox((0, 0), center_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + 46 - tw / 2, y + 64 - th / 2), center_text, fill=suit_color, font=font)

    if playable:
        draw.rounded_rectangle((x + 9, y + 101, x + 83, y + 121), radius=5, fill=(255, 206, 84))
        draw.text((x + 23, y + 102), "PLAY", fill=(38, 38, 38), font=small_font)


def hand_file(member: discord.Member, hand: list[tuple[str, int]], playable: list[tuple[str, int]]) -> discord.File:
    sorted_hand = sorted(hand, key=lambda c: (SUITS.index(c[0]), c[1]))
    playable_set = set(playable)
    card_w, card_h = 92, 128
    gap = 14
    cols = min(7, max(1, len(sorted_hand)))
    rows = max(1, (len(sorted_hand) + cols - 1) // cols)
    width = 34 + cols * card_w + (cols - 1) * gap + 34
    height = 72 + rows * card_h + (rows - 1) * gap + 42
    image = Image.new("RGB", (width, height), (33, 94, 72))
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        card_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except Exception:
        title_font = ImageFont.load_default()
        card_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.text((30, 22), "Your hand - Sevens", fill=(255, 255, 255), font=title_font)
    for index, card in enumerate(sorted_hand):
        col = index % cols
        row = index // cols
        x = 34 + col * (card_w + gap)
        y = 72 + row * (card_h + gap)
        draw_card(draw, (x, y), card, card_font, small_font, card in playable_set)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename=f"sevens_hand_{member.id}.png")


async def send_hand(member: discord.Member, hand: list[tuple[str, int]], playable: list[tuple[str, int]]):
    await member.send(
        "あなたの7並べの手札です。\n"
        "黄色い枠のカードは現在出せます。",
        file=hand_file(member, hand, playable),
    )


class SevensPlayView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        state = sevens_games.get(game_id)
        if not state:
            return

        hand = [tuple(card) for card in state["hands"].get(str(user_id), [])]
        playable = playable_cards(hand, state["board"])
        if playable:
            self.add_item(SevensCardSelect(game_id, user_id, playable[:25]))
        self.add_item(SevensPassButton(game_id, user_id))
        self.add_item(SevensSurrenderButton(game_id, user_id))


class SevensCardSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, cards: list[tuple[str, int]]):
        options = [discord.SelectOption(label=card_label(card), value=card_value(card)) for card in cards]
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


class SevensSurrenderButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="降参",
            style=discord.ButtonStyle.danger,
            custom_id=f"sevens_surrender_{game_id}_{user_id}",
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await surrender(interaction, self.game_id, self.user_id)


def active_players(state: dict) -> list[int]:
    return [uid for uid in state["players"] if str(uid) not in state["finished"]]


async def advance_turn(state: dict):
    players = state["players"]
    for _ in range(len(players)):
        state["turn_index"] = (state["turn_index"] + 1) % len(players)
        next_user = players[state["turn_index"]]
        if str(next_user) not in state["finished"]:
            return


async def update_game_message(interaction: discord.Interaction, state: dict, prefix: str = ""):
    game_id = str(interaction.channel_id)
    current_user = state["players"][state["turn_index"]]
    await interaction.response.edit_message(
        content=status_text(state, prefix),
        attachments=[board_file(state)],
        view=SevensPlayView(game_id, current_user),
    )


async def end_if_needed(interaction: discord.Interaction, state: dict) -> bool:
    remaining = active_players(state)
    if len(remaining) > 1:
        return False

    winner = remaining[0] if remaining else int(state["finished"][0])
    sevens_games.pop(str(interaction.channel_id), None)
    await interaction.response.edit_message(
        content=f"🎉 7並べ終了！勝者: <@{winner}>",
        attachments=[board_file(state)],
        view=None,
    )
    return True


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

    if not hand:
        state["finished"].append(str(user_id))
        if await end_if_needed(interaction, state):
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
        if await end_if_needed(interaction, state):
            return
    else:
        prefix = f"⏭️ <@{user_id}> がパスしました。"

    await advance_turn(state)
    await update_game_message(interaction, state, prefix)


async def surrender(interaction: discord.Interaction, game_id: str, user_id: int):
    state = sevens_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    state["finished"].append(str(user_id))
    if await end_if_needed(interaction, state):
        return

    await advance_turn(state)
    await update_game_message(interaction, state, f"🏳️ <@{user_id}> が降参しました。")


class Sevens(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sevens_start", description="7並べゲームを作成します")
    async def sevens_start(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        sevens_games[game_id] = {
            "creator_id": interaction.user.id,
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
        await interaction.followup.send(text, file=board_file(state), view=SevensPlayView(game_id, current_user))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sevens(bot))
