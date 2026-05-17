import random
from collections import Counter
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANKS = list(range(2, 15))
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}
HAND_NAMES = {
    8: "ストレートフラッシュ",
    7: "フォーカード",
    6: "フルハウス",
    5: "フラッシュ",
    4: "ストレート",
    3: "スリーカード",
    2: "ツーペア",
    1: "ワンペア",
    0: "ハイカード",
}

poker_games: dict[str, dict] = {}


def rank_label(rank: int) -> str:
    return RANK_LABELS.get(rank, str(rank))


def build_deck() -> list[dict]:
    return [{"suit": suit, "rank": rank} for suit in SUITS for rank in RANKS]


def card_sort_key(card: dict) -> tuple[int, str]:
    return card["rank"], card["suit"]


def card_label(card: dict) -> str:
    return f"{SUIT_SYMBOLS[card['suit']]}{rank_label(card['rank'])}"


def encode_card(card: dict) -> str:
    return f"{card['suit']}{card['rank']}"


def evaluate_hand(cards: list[dict]) -> tuple[int, list[int]]:
    ranks = sorted([card["rank"] for card in cards], reverse=True)
    suits = [card["suit"] for card in cards]
    counts = Counter(ranks)
    count_groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks), reverse=True)
    is_wheel = unique_ranks == [14, 5, 4, 3, 2]
    is_straight = len(unique_ranks) == 5 and (unique_ranks[0] - unique_ranks[-1] == 4 or is_wheel)
    straight_high = 5 if is_wheel else unique_ranks[0]

    if is_straight and is_flush:
        return 8, [straight_high]
    if count_groups[0][1] == 4:
        four = count_groups[0][0]
        kicker = max(rank for rank in ranks if rank != four)
        return 7, [four, kicker]
    if count_groups[0][1] == 3 and count_groups[1][1] == 2:
        return 6, [count_groups[0][0], count_groups[1][0]]
    if is_flush:
        return 5, ranks
    if is_straight:
        return 4, [straight_high]
    if count_groups[0][1] == 3:
        triple = count_groups[0][0]
        kickers = sorted([rank for rank in ranks if rank != triple], reverse=True)
        return 3, [triple] + kickers
    pairs = sorted([rank for rank, count in counts.items() if count == 2], reverse=True)
    if len(pairs) == 2:
        kicker = max(rank for rank in ranks if rank not in pairs)
        return 2, pairs + [kicker]
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted([rank for rank in ranks if rank != pair], reverse=True)
        return 1, [pair] + kickers
    return 0, ranks


def hand_name(cards: list[dict]) -> str:
    score, _ = evaluate_hand(cards)
    return HAND_NAMES[score]


def status_text(state: dict, prefix: str = "") -> str:
    current = state["players"][state["turn_index"]]
    exchanged = set(state["exchanged"])
    lines = []
    if prefix:
        lines.append(prefix)
    lines.extend(
        [
            "**ポーカー / 5カードドロー**",
            f"現在の交換ターン: <@{current}>",
            "参加者: " + " / ".join(f"<@{uid}>{' 済' if str(uid) in exchanged else ''}" for uid in state["players"]),
        ]
    )
    return "\n".join(lines)


def draw_card(draw: ImageDraw.ImageDraw, xy: tuple[int, int], card: dict, font, small_font):
    x, y = xy
    red = card["suit"] in ("H", "D")
    color = (190, 35, 35) if red else (25, 25, 25)
    draw.rounded_rectangle((x, y, x + 96, y + 136), radius=10, fill=(248, 248, 240), outline=(220, 220, 210), width=2)
    rank = rank_label(card["rank"])
    suit = SUIT_SYMBOLS[card["suit"]]
    draw.text((x + 10, y + 8), rank, fill=color, font=small_font)
    draw.text((x + 10, y + 32), suit, fill=color, font=small_font)
    center = f"{suit}{rank}"
    bbox = draw.textbbox((0, 0), center, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + 48 - tw / 2, y + 68 - th / 2), center, fill=color, font=font)


def hand_file(member: discord.Member, hand: list[dict], title: str = "ポーカーの手札") -> discord.File:
    cards = sorted(hand, key=card_sort_key)
    card_w, card_h, gap = 96, 136, 14
    width = 34 + len(cards) * card_w + max(0, len(cards) - 1) * gap + 34
    height = 250
    image = Image.new("RGB", (width, height), (30, 80, 64))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        card_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
    except Exception:
        title_font = ImageFont.load_default()
        card_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.text((30, 20), f"{member.display_name} の{title}", fill=(255, 255, 255), font=title_font)
    draw.text((30, 54), f"役: {hand_name(cards)}", fill=(230, 245, 235), font=small_font)
    for index, card in enumerate(cards):
        x = 34 + index * (card_w + gap)
        draw_card(draw, (x, 92), card, card_font, small_font)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename=f"poker_hand_{member.id}.png")


async def send_hand(member: discord.Member, hand: list[dict], title: str = "ポーカーの手札"):
    await member.send(f"あなたの{title}です。", file=hand_file(member, hand, title))


def draw_cards(state: dict, count: int) -> list[dict]:
    drawn = []
    for _ in range(count):
        if not state["deck"]:
            break
        drawn.append(state["deck"].pop())
    return drawn


async def advance_or_finish(interaction: discord.Interaction, state: dict, prefix: str):
    game_id = str(interaction.channel_id)
    if len(state["exchanged"]) >= len(state["players"]):
        results = []
        for uid in state["players"]:
            hand = state["hands"][str(uid)]
            score = evaluate_hand(hand)
            results.append((score, uid, hand))
        results.sort(key=lambda item: item[0], reverse=True)
        best_score = results[0][0]
        winners = [item for item in results if item[0] == best_score]
        winner_text = " / ".join(f"<@{uid}>" for _, uid, _ in winners)
        lines = [prefix, "**ポーカー終了**", f"勝者: {winner_text} ({HAND_NAMES[best_score[0]]})", ""]
        for index, (score, uid, hand) in enumerate(results, start=1):
            lines.append(f"{index}. <@{uid}> - {HAND_NAMES[score[0]]} / {', '.join(card_label(card) for card in sorted(hand, key=card_sort_key))}")
        poker_games.pop(game_id, None)
        await interaction.response.edit_message(content="\n".join(lines), view=None)
        return

    await advance_turn(state)
    current = state["players"][state["turn_index"]]
    member = interaction.guild.get_member(current) if interaction.guild else None
    if member:
        try:
            await send_hand(member, state["hands"][str(current)])
        except Exception:
            prefix += f"\n<@{current}> へのDM送信に失敗しました。"
    await interaction.response.edit_message(content=status_text(state, prefix), view=PokerDrawView(game_id, current))


async def advance_turn(state: dict):
    players = state["players"]
    for _ in range(len(players)):
        state["turn_index"] = (state["turn_index"] + 1) % len(players)
        if str(players[state["turn_index"]]) not in state["exchanged"]:
            return


class PokerDrawSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, hand: list[dict]):
        options = [
            discord.SelectOption(label=card_label(card), value=encode_card(card))
            for card in sorted(hand, key=card_sort_key)
        ]
        super().__init__(
            placeholder="交換するカードを選んでください",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id=f"poker_draw_{game_id}_{user_id}",
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await exchange_cards(interaction, self.game_id, self.user_id, self.values)


class PokerKeepButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(label="交換しない", style=discord.ButtonStyle.success, custom_id=f"poker_keep_{game_id}_{user_id}")
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await exchange_cards(interaction, self.game_id, self.user_id, [])


class PokerDrawView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        state = poker_games.get(game_id)
        if not state:
            return
        hand = state["hands"].get(str(user_id), [])
        self.add_item(PokerDrawSelect(game_id, user_id, hand))
        self.add_item(PokerKeepButton(game_id, user_id))


async def exchange_cards(interaction: discord.Interaction, game_id: str, user_id: int, selected: list[str]):
    state = poker_games.get(game_id)
    if not state:
        await interaction.response.send_message("ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("あなたの交換ターンではありません。", ephemeral=True)
        return
    if str(user_id) in state["exchanged"]:
        await interaction.response.send_message("すでに交換済みです。", ephemeral=True)
        return

    hand = state["hands"][str(user_id)]
    selected_set = set(selected)
    keep = [card for card in hand if encode_card(card) not in selected_set]
    discard_count = len(hand) - len(keep)
    state["hands"][str(user_id)] = keep + draw_cards(state, discard_count)
    state["exchanged"].append(str(user_id))

    member = interaction.guild.get_member(user_id) if interaction.guild else None
    if member:
        try:
            await send_hand(member, state["hands"][str(user_id)], "交換後の手札")
        except Exception:
            pass

    prefix = f"<@{user_id}> が {discard_count} 枚交換しました。" if discard_count else f"<@{user_id}> は交換しませんでした。"
    await advance_or_finish(interaction, state, prefix)


class Poker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="poker_start", description="ポーカーゲームを作成します")
    async def poker_start(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        poker_games[game_id] = {
            "players": [interaction.user.id],
            "hands": {},
            "deck": [],
            "turn_index": 0,
            "started": False,
            "exchanged": [],
        }
        await interaction.response.send_message(
            f"ポーカーを作成しました。{interaction.user.mention} は自動参加しました。\n"
            "`/poker_join` で参加、`/poker_begin` で開始します。"
        )

    @app_commands.command(name="poker_join", description="ポーカーに参加します")
    async def poker_join(self, interaction: discord.Interaction):
        state = poker_games.get(str(interaction.channel_id))
        if not state:
            await interaction.response.send_message("まず `/poker_start` を実行してください。", ephemeral=True)
            return
        if state["started"]:
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        if len(state["players"]) >= 8:
            await interaction.response.send_message("参加できるのは最大8人までです。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} が参加しました。")

    @app_commands.command(name="poker_begin", description="ポーカーを開始します")
    async def poker_begin(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        state = poker_games.get(game_id)
        if not state:
            await interaction.response.send_message("まず `/poker_start` を実行してください。", ephemeral=True)
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
        random.shuffle(state["players"])
        state["deck"] = deck
        state["hands"] = {str(uid): draw_cards(state, 5) for uid in state["players"]}
        state["started"] = True

        failed_dm = []
        for uid in state["players"]:
            member = interaction.guild.get_member(uid) if interaction.guild else None
            if not member:
                continue
            try:
                await send_hand(member, state["hands"][str(uid)])
            except Exception:
                failed_dm.append(member.mention)

        current = state["players"][state["turn_index"]]
        text = status_text(state, "ポーカーを開始しました。")
        if failed_dm:
            text += "\n\nDM送信に失敗: " + " ".join(failed_dm)
        await interaction.followup.send(text, view=PokerDrawView(game_id, current))


async def setup(bot: commands.Bot):
    await bot.add_cog(Poker(bot))
