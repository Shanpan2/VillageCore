import itertools
import random
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANKS = list(range(3, 15)) + [2]
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A", 15: "2", 16: "JOKER"}
daifugo_games: dict[str, dict] = {}


def rank_label(rank: int) -> str:
    return RANK_LABELS.get(rank, str(rank))


def build_deck() -> list[dict]:
    deck = [{"suit": suit, "rank": rank} for suit in SUITS for rank in RANKS]
    deck.append({"suit": "J", "rank": 16})
    return deck


def card_sort_key(card: dict) -> tuple[int, str]:
    return card["rank"], card["suit"]


def card_label(card: dict) -> str:
    if card["rank"] == 16:
        return "JOKER"
    return f"{SUIT_SYMBOLS[card['suit']]}{rank_label(card['rank'])}"


def group_label(cards: list[dict]) -> str:
    return " ".join(card_label(card) for card in cards)


def encode_group(cards: list[dict]) -> str:
    return ",".join(f"{card['suit']}{card['rank']}" for card in cards)


def decode_group(value: str, hand: list[dict]) -> list[dict]:
    keys = value.split(",")
    result = []
    remaining = hand.copy()
    for key in keys:
        for card in remaining:
            if f"{card['suit']}{card['rank']}" == key:
                result.append(card)
                remaining.remove(card)
                break
    return result


def legal_groups(hand: list[dict], last_play: list[dict] | None) -> list[list[dict]]:
    sorted_hand = sorted(hand, key=card_sort_key)
    groups = []
    required_count = len(last_play) if last_play else None
    required_rank = max(card["rank"] for card in last_play) if last_play else 0

    by_rank: dict[int, list[dict]] = {}
    for card in sorted_hand:
        by_rank.setdefault(card["rank"], []).append(card)

    for card in sorted_hand:
        if required_count in (None, 1) and card["rank"] > required_rank:
            groups.append([card])

    for rank, cards in by_rank.items():
        if rank == 16:
            continue
        for count in (2, 3, 4):
            if required_count not in (None, count):
                continue
            if len(cards) >= count and rank > required_rank:
                groups.append(cards[:count])

    return groups[:25]


def active_players(state: dict) -> list[int]:
    return [uid for uid in state["players"] if str(uid) not in state["finished"]]


def status_text(state: dict, prefix: str = "") -> str:
    current = state["players"][state["turn_index"]]
    last_play = state.get("last_play")
    last_text = group_label(last_play) if last_play else "なし"
    lines = []
    if prefix:
        lines.append(prefix)
    lines.extend(
        [
            "**大富豪**",
            f"現在のターン: <@{current}>",
            f"場: {last_text}",
            "手札: " + " / ".join(f"<@{uid}> {len(state['hands'].get(str(uid), []))}枚" for uid in state["players"]),
            "上がり: " + (", ".join(f"<@{uid}>" for uid in state["finished"]) if state["finished"] else "なし"),
        ]
    )
    return "\n".join(lines)


def draw_card(draw: ImageDraw.ImageDraw, xy: tuple[int, int], card: dict, font, small_font):
    x, y = xy
    red = card["suit"] in ("H", "D")
    suit_color = (190, 35, 35) if red else (25, 25, 25)
    fill = (34, 34, 40) if card["rank"] == 16 else (248, 248, 240)
    text_color = (255, 255, 255) if card["rank"] == 16 else suit_color
    draw.rounded_rectangle((x, y, x + 92, y + 128), radius=10, fill=fill, outline=(220, 220, 210), width=2)
    label = "JK" if card["rank"] == 16 else rank_label(card["rank"])
    suit = "★" if card["rank"] == 16 else SUIT_SYMBOLS[card["suit"]]
    draw.text((x + 10, y + 8), label, fill=text_color, font=small_font)
    draw.text((x + 10, y + 30), suit, fill=text_color, font=small_font)
    center = f"{suit}{label}"
    bbox = draw.textbbox((0, 0), center, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + 46 - tw / 2, y + 64 - th / 2), center, fill=text_color, font=font)


def hand_file(member: discord.Member, hand: list[dict]) -> discord.File:
    cards = sorted(hand, key=card_sort_key)
    card_w, card_h, gap = 92, 128, 14
    cols = min(8, max(1, len(cards)))
    rows = max(1, (len(cards) + cols - 1) // cols)
    width = 34 + cols * card_w + (cols - 1) * gap + 34
    height = 72 + rows * card_h + (rows - 1) * gap + 42
    image = Image.new("RGB", (width, height), (31, 78, 98))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        card_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except Exception:
        title_font = ImageFont.load_default()
        card_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.text((30, 22), "Daifugo hand", fill=(255, 255, 255), font=title_font)
    for index, card in enumerate(cards):
        x = 34 + (index % cols) * (card_w + gap)
        y = 72 + (index // cols) * (card_h + gap)
        draw_card(draw, (x, y), card, card_font, small_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename=f"daifugo_hand_{member.id}.png")


async def send_hand(member: discord.Member, hand: list[dict]):
    await member.send("あなたの大富豪の手札です。", file=hand_file(member, hand))


async def advance_turn(state: dict):
    players = state["players"]
    for _ in range(len(players)):
        state["turn_index"] = (state["turn_index"] + 1) % len(players)
        if str(players[state["turn_index"]]) not in state["finished"]:
            return


async def end_if_needed(interaction: discord.Interaction, state: dict) -> bool:
    remaining = active_players(state)
    if len(remaining) > 1:
        return False
    if remaining:
        state["finished"].append(str(remaining[0]))
    ranking = "\n".join(f"{index + 1}. <@{uid}>" for index, uid in enumerate(state["finished"]))
    daifugo_games.pop(str(interaction.channel_id), None)
    await interaction.response.edit_message(content=f"**大富豪終了**\n{ranking}", view=None)
    return True


async def update_table(interaction: discord.Interaction, state: dict, prefix: str = ""):
    game_id = str(interaction.channel_id)
    current = state["players"][state["turn_index"]]
    member = interaction.guild.get_member(current) if interaction.guild else None
    if member:
        try:
            await send_hand(member, state["hands"][str(current)])
        except Exception:
            pass
    await interaction.response.edit_message(content=status_text(state, prefix), view=DaifugoPlayView(game_id, current))


class DaifugoPlayView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        state = daifugo_games.get(game_id)
        if not state:
            return
        hand = state["hands"].get(str(user_id), [])
        groups = legal_groups(hand, state.get("last_play"))
        if groups:
            self.add_item(DaifugoCardSelect(game_id, user_id, groups))
        self.add_item(DaifugoPassButton(game_id, user_id))


class DaifugoCardSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, groups: list[list[dict]]):
        options = [
            discord.SelectOption(label=group_label(group)[:100], value=encode_group(group))
            for group in groups
        ]
        super().__init__(placeholder="出すカードを選んでください", options=options, custom_id=f"daifugo_select_{game_id}_{user_id}")
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await play_cards(interaction, self.game_id, self.user_id, self.values[0])


class DaifugoPassButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(label="パス", style=discord.ButtonStyle.secondary, custom_id=f"daifugo_pass_{game_id}_{user_id}")
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await pass_turn(interaction, self.game_id, self.user_id)


async def play_cards(interaction: discord.Interaction, game_id: str, user_id: int, encoded: str):
    state = daifugo_games.get(game_id)
    if not state:
        await interaction.response.send_message("ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("あなたのターンではありません。", ephemeral=True)
        return

    hand = state["hands"][str(user_id)]
    cards = decode_group(encoded, hand)
    if not cards or encode_group(cards) not in [encode_group(group) for group in legal_groups(hand, state.get("last_play"))]:
        await interaction.response.send_message("そのカードは今出せません。", ephemeral=True)
        return

    for card in cards:
        hand.remove(card)
    state["hands"][str(user_id)] = hand
    state["last_play"] = cards
    state["last_player"] = user_id
    state["passed"] = []

    if not hand and str(user_id) not in state["finished"]:
        state["finished"].append(str(user_id))
        if await end_if_needed(interaction, state):
            return

    await advance_turn(state)
    await update_table(interaction, state, f"<@{user_id}> が **{group_label(cards)}** を出しました。")


async def pass_turn(interaction: discord.Interaction, game_id: str, user_id: int):
    state = daifugo_games.get(game_id)
    if not state:
        await interaction.response.send_message("ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("あなたのターンではありません。", ephemeral=True)
        return

    if not state.get("last_play"):
        await interaction.response.send_message("場が空なのでパスできません。", ephemeral=True)
        return

    state["passed"].append(user_id)
    active = [uid for uid in active_players(state) if uid != state.get("last_player")]
    prefix = f"<@{user_id}> がパスしました。"
    if all(uid in state["passed"] for uid in active):
        state["last_play"] = None
        state["passed"] = []
        if state.get("last_player") in active_players(state):
            state["turn_index"] = state["players"].index(state["last_player"])
        prefix += "\n場が流れました。"
    else:
        await advance_turn(state)
    await update_table(interaction, state, prefix)


class Daifugo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daifugo_start", description="大富豪ゲームを作成します")
    async def daifugo_start(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        daifugo_games[game_id] = {
            "players": [interaction.user.id],
            "hands": {},
            "turn_index": 0,
            "started": False,
            "last_play": None,
            "last_player": None,
            "passed": [],
            "finished": [],
        }
        await interaction.response.send_message(
            f"大富豪を作成しました。{interaction.user.mention} は自動参加しました。\n"
            "`/daifugo_join` で参加、`/daifugo_begin` で開始します。"
        )

    @app_commands.command(name="daifugo_join", description="大富豪に参加します")
    async def daifugo_join(self, interaction: discord.Interaction):
        state = daifugo_games.get(str(interaction.channel_id))
        if not state:
            await interaction.response.send_message("まず `/daifugo_start` を実行してください。", ephemeral=True)
            return
        if state["started"]:
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} が参加しました。")

    @app_commands.command(name="daifugo_begin", description="大富豪を開始します")
    async def daifugo_begin(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        state = daifugo_games.get(game_id)
        if not state:
            await interaction.response.send_message("まず `/daifugo_start` を実行してください。", ephemeral=True)
            return
        if state["started"]:
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if len(state["players"]) < 2:
            await interaction.response.send_message("2人以上必要です。", ephemeral=True)
            return

        await interaction.response.defer()
        deck = build_deck()
        random.shuffle(deck)
        hands = {str(uid): [] for uid in state["players"]}
        for index, card in enumerate(deck):
            hands[str(state["players"][index % len(state["players"])])].append(card)

        state["hands"] = hands
        state["started"] = True
        random.shuffle(state["players"])

        failed_dm = []
        for uid in state["players"]:
            member = interaction.guild.get_member(uid) if interaction.guild else None
            if not member:
                continue
            try:
                await send_hand(member, hands[str(uid)])
            except Exception:
                failed_dm.append(member.mention)

        current = state["players"][state["turn_index"]]
        text = status_text(state, "大富豪を開始しました。")
        if failed_dm:
            text += "\n\nDM送信に失敗: " + " ".join(failed_dm)
        await interaction.followup.send(text, view=DaifugoPlayView(game_id, current))


async def setup(bot: commands.Bot):
    await bot.add_cog(Daifugo(bot))
