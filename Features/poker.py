import random
from collections import Counter
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from utils.game_persistence import (
    save_game as _save_game,
    delete_game as _delete_game,
    load_games_for_guild,
    get_game_state,
)
from utils.game_cog import BaseGameCog
from utils.coin import get_coin_balance, set_coin_balance


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

_PREFIX = "poker"


async def save_poker_game(guild_id: int | None, game_id: str, state: dict | None = None):
    await _save_game(_PREFIX, poker_games, guild_id, game_id, state)


async def delete_poker_game(guild_id: int | None, game_id: str):
    await _delete_game(_PREFIX, guild_id, game_id)


def _restore_poker_view(bot: commands.Bot, game_id: str, state: dict) -> None:
    if state.get("started"):
        current = state["players"][state.get("turn_index", 0)]
        bot.add_view(PokerDrawView(game_id, current))
    else:
        bot.add_view(PokerLobbyView(game_id))


async def load_poker_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    await load_games_for_guild(
        _PREFIX, poker_games, bot, guild,
        restore_view=_restore_poker_view,
    )


def normalize_poker_state(state: dict) -> dict:
    state["players"] = [int(uid) for uid in state.get("players", [])]
    state["turn_index"] = int(state.get("turn_index", 0) or 0)
    if state["players"]:
        state["turn_index"] %= len(state["players"])
    state["exchanged"] = [str(uid) for uid in state.get("exchanged", [])]
    return state


async def get_poker_game_state(bot: commands.Bot, game_id: str, guild_id: int | None = None) -> dict | None:
    return await get_game_state(
        _PREFIX, poker_games, bot, game_id, guild_id,
        normalize=normalize_poker_state,
    )


def bet_line(state: dict) -> str:
    bet = int(state.get("bet", 0) or 0)
    if bet <= 0:
        return "賭けコイン: なし"
    pot = int(state.get("pot", 0) or 0) or bet * len(state.get("players", []))
    return f"賭けコイン: 1人 **{bet}** / ポット **{pot}**"


async def set_poker_bet_amount(interaction: discord.Interaction, amount: int) -> str:
    state = poker_games.get(str(interaction.channel_id))
    if not state:
        return "まずポーカー募集を作成してください。"
    if state.get("started"):
        return "開始後は賭け額を変更できません。"

    creator_id = state.get("creator_id")
    is_manager = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
    if interaction.user.id != creator_id and not is_manager:
        return "賭け額を設定できるのは作成者または管理者だけです。"
    if amount < 0:
        return "賭け額は0以上にしてください。"

    if amount > 0 and interaction.guild_id:
        shortage = []
        for uid in state.get("players", []):
            balance = await get_coin_balance(interaction.guild_id, uid)
            if balance < amount:
                shortage.append(f"<@{uid}>({balance})")
        if shortage:
            return "コインが足りない参加者がいます: " + " / ".join(shortage)

    state["bet"] = amount
    state["pot"] = 0
    state["bets_collected"] = False
    await save_poker_game(interaction.guild_id, str(interaction.channel_id), state)
    return f"ポーカーの賭け額を1人 **{amount}** コインに設定しました。" if amount else "ポーカーの賭けをなしにしました。"


async def collect_poker_bets(interaction: discord.Interaction, state: dict) -> tuple[bool, str]:
    bet = int(state.get("bet", 0) or 0)
    if bet <= 0:
        state["pot"] = 0
        state["bets_collected"] = True
        return True, ""
    if not interaction.guild_id:
        return False, "サーバー内で実行してください。"
    if state.get("bets_collected"):
        return True, ""

    balances = {}
    shortage = []
    for uid in state["players"]:
        balance = await get_coin_balance(interaction.guild_id, uid)
        balances[uid] = balance
        if balance < bet:
            shortage.append(f"<@{uid}>({balance})")
    if shortage:
        return False, "コインが足りない参加者がいます: " + " / ".join(shortage)

    for uid, balance in balances.items():
        await set_coin_balance(interaction.guild_id, uid, balance - bet)
    state["pot"] = bet * len(state["players"])
    state["bets_collected"] = True
    return True, f"全員から **{bet}** コインを集めました。ポットは **{state['pot']}** コインです。"


async def payout_poker_winners(guild_id: int | None, state: dict, winner_ids: list[int]) -> str:
    pot = int(state.get("pot", 0) or 0)
    if not guild_id or pot <= 0 or not winner_ids:
        return ""

    share = pot // len(winner_ids)
    remainder = pot % len(winner_ids)
    payout_lines = []
    for index, uid in enumerate(winner_ids):
        payout = share + (remainder if index == 0 else 0)
        balance = await get_coin_balance(guild_id, uid)
        await set_coin_balance(guild_id, uid, balance + payout)
        payout_lines.append(f"<@{uid}> +{payout}")
    return "配当: " + " / ".join(payout_lines)


def lobby_text(state: dict) -> str:
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", []))
    return (
        "**ポーカー募集**\n"
        f"{bet_line(state)}\n"
        f"参加者: {players or 'なし'}\n\n"
        "下のボタンで参加、抜ける、賭け額設定、開始ができます。"
    )


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
            bet_line(state),
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


def result_file(
    guild: discord.Guild | None,
    results: list[tuple[tuple[int, list[int]], int, list[dict]]],
    winners: list[tuple[tuple[int, list[int]], int, list[dict]]],
) -> discord.File:
    card_w, card_h, gap = 82, 116, 10
    row_h = 164
    width = 860
    height = 92 + row_h * max(1, len(results)) + 28
    image = Image.new("RGB", (width, height), (24, 50, 44))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        name_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
        card_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        card_small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except Exception:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        card_font = ImageFont.load_default()
        card_small_font = ImageFont.load_default()

    winner_ids = {uid for _, uid, _ in winners}
    draw.text((30, 24), "ポーカー最終結果", fill=(255, 255, 255), font=title_font)
    if winners:
        winner_names = []
        for _, uid, _ in winners:
            member = guild.get_member(uid) if guild else None
            winner_names.append(member.display_name if member else str(uid))
        draw.text((32, 62), "勝者: " + " / ".join(winner_names), fill=(255, 224, 130), font=small_font)

    y = 96
    for index, (score, uid, hand) in enumerate(results, start=1):
        member = guild.get_member(uid) if guild else None
        name = member.display_name if member else f"User {uid}"
        name = name[:24]
        is_winner = uid in winner_ids
        panel_fill = (39, 84, 66) if is_winner else (31, 66, 58)
        outline = (255, 211, 99) if is_winner else (76, 126, 105)
        draw.rounded_rectangle((24, y, width - 24, y + row_h - 18), radius=12, fill=panel_fill, outline=outline, width=3 if is_winner else 1)
        draw.text((44, y + 18), f"{index}. {name}", fill=(255, 255, 255), font=name_font)
        draw.text((44, y + 48), HAND_NAMES[score[0]], fill=(220, 238, 228), font=small_font)

        start_x = 270
        for card_index, card in enumerate(sorted(hand, key=card_sort_key)):
            x = start_x + card_index * (card_w + gap)
            draw_card(draw, (x, y + 18), card, card_font, card_small_font)
        y += row_h

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="poker_result.png")


async def send_hand(member: discord.Member, hand: list[dict], title: str = "ポーカーの手札"):
    await member.send(
        f"あなたの{title}です。\n公開パネルの「カード1」から順に、画像の左から1枚目、2枚目...に対応します。",
        file=hand_file(member, hand, title),
    )


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
        payout_text = await payout_poker_winners(interaction.guild_id, state, [uid for _, uid, _ in winners])
        winner_text = " / ".join(f"<@{uid}>" for _, uid, _ in winners)
        lines = [prefix, "**ポーカー終了**", f"勝者: {winner_text} ({HAND_NAMES[best_score[0]]})"]
        if payout_text:
            lines.append(payout_text)
        lines.append("")
        for index, (score, uid, hand) in enumerate(results, start=1):
            lines.append(f"{index}. <@{uid}> - {HAND_NAMES[score[0]]} / {', '.join(card_label(card) for card in sorted(hand, key=card_sort_key))}")
        await delete_poker_game(interaction.guild_id or state.get("guild_id"), game_id)
        poker_games.pop(game_id, None)
        await interaction.response.edit_message(
            content="\n".join(lines),
            attachments=[result_file(interaction.guild, results, winners)],
            view=None,
        )
        return

    await advance_turn(state)
    await save_poker_game(interaction.guild_id or state.get("guild_id"), game_id, state)
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
            discord.SelectOption(
                label=f"カード {index}",
                value=encode_card(card),
                description="DMの手札画像の左から順番に対応します。",
            )
            for index, card in enumerate(sorted(hand, key=card_sort_key), start=1)
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


class PokerBetModal(discord.ui.Modal, title="ポーカー賭け額設定"):
    amount = discord.ui.TextInput(
        label="1人あたりの賭けコイン数",
        placeholder="0で賭けなし / 例: 10",
        required=True,
        max_length=8,
    )

    def __init__(self, game_id: str):
        super().__init__()
        self.game_id = game_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message("数字で入力してください。", ephemeral=True)
            return
        message = await set_poker_bet_amount(interaction, bet)
        state = poker_games.get(self.game_id)
        if state and interaction.message:
            try:
                await interaction.message.edit(content=lobby_text(state), view=PokerLobbyView(self.game_id))
            except discord.HTTPException:
                pass
        await interaction.response.send_message(message, ephemeral=True)


class PokerLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "bet", "begin", "cancel"), self.children):
            child.custom_id = f"poker_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = poker_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このポーカー募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        if len(state["players"]) >= 8:
            await interaction.response.send_message("参加できるのは最大8人までです。", ephemeral=True)
            return

        bet = int(state.get("bet", 0) or 0)
        if bet > 0 and interaction.guild_id:
            balance = await get_coin_balance(interaction.guild_id, interaction.user.id)
            if balance < bet:
                await interaction.response.send_message(f"参加に **{bet}** コイン必要です。現在の所持コインは **{balance}** です。", ephemeral=True)
                return

        state["players"].append(interaction.user.id)
        await save_poker_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = poker_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このポーカー募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。開始後は抜けられません。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"].remove(interaction.user.id)
        if not state["players"]:
            await delete_poker_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            poker_games.pop(self.game_id, None)
            await interaction.response.edit_message(content="参加者がいなくなったため、ポーカー募集を終了しました。", view=None)
            return
        if state.get("creator_id") == interaction.user.id:
            state["creator_id"] = state["players"][0]
        await save_poker_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="賭け額", style=discord.ButtonStyle.secondary)
    async def bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PokerBetModal(self.game_id))

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await start_poker_game(interaction, self.game_id)
            state = poker_games.get(self.game_id)
            if state and state.get("started") and interaction.message:
                try:
                    await interaction.message.edit(content=lobby_text(state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        except Exception as e:
            print(f"[PokerLobbyView.begin] error: {type(e).__name__}: {e}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send("開始処理中にエラーが発生しました。`/poker_begin` でもう一度試してください。", ephemeral=True)
            else:
                await interaction.response.send_message("開始処理中にエラーが発生しました。`/poker_begin` でもう一度試してください。", ephemeral=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = poker_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このポーカー募集はありません。", ephemeral=True)
            return
        is_creator = interaction.user.id == state.get("creator_id")
        is_admin = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
        if not is_creator and not is_admin:
            await interaction.response.send_message("中止できるのは作成者または管理者だけです。", ephemeral=True)
            return
        await delete_poker_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        poker_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="ポーカー募集を中止しました。", view=None)


async def exchange_cards(interaction: discord.Interaction, game_id: str, user_id: int, selected: list[str]):
    state = await get_poker_game_state(interaction.client, game_id, interaction.guild_id)
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


async def start_poker_game(interaction: discord.Interaction, game_id: str | None = None):
    game_id = game_id or str(interaction.channel_id)
    state = await get_poker_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("まず `/poker_start` を実行してください。", ephemeral=True)
        return
    if state["started"]:
        await interaction.response.send_message("すでに開始しています。", ephemeral=True)
        return
    if len(state["players"]) < 2:
        await interaction.response.send_message("2人以上必要です。", ephemeral=True)
        return

    ok, bet_message = await collect_poker_bets(interaction, state)
    if not ok:
        await interaction.response.send_message(bet_message, ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    deck = build_deck()
    random.shuffle(deck)
    random.shuffle(state["players"])
    state["deck"] = deck
    state["hands"] = {str(uid): draw_cards(state, 5) for uid in state["players"]}
    state["started"] = True
    state["guild_id"] = interaction.guild_id
    await save_poker_game(interaction.guild_id, game_id, state)

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
    prefix = "ポーカーを開始しました。"
    if bet_message:
        prefix += f"\n{bet_message}"
    text = status_text(state, prefix)
    if failed_dm:
        text += "\n\nDM送信に失敗: " + " ".join(failed_dm)
    await interaction.followup.send(text, view=PokerDrawView(game_id, current))


class Poker(BaseGameCog):
    _load_guild = staticmethod(load_poker_games_for_guild)

    @app_commands.command(name="poker_start", description="ポーカーゲームを作成します")
    @app_commands.describe(bet="1人あたりの賭けコイン数。0で賭けなし")
    async def poker_start(self, interaction: discord.Interaction, bet: int = 0):
        game_id = str(interaction.channel_id)
        if game_id in poker_games:
            await interaction.response.send_message("このチャンネルにはすでにポーカー募集があります。", ephemeral=True)
            return
        if bet < 0:
            await interaction.response.send_message("賭け額は0以上にしてください。", ephemeral=True)
            return
        if bet > 0 and interaction.guild_id:
            balance = await get_coin_balance(interaction.guild_id, interaction.user.id)
            if balance < bet:
                await interaction.response.send_message(f"コインが足りません。現在の所持コインは **{balance}** です。", ephemeral=True)
                return
        poker_games[game_id] = {
            "creator_id": interaction.user.id,
            "players": [interaction.user.id],
            "hands": {},
            "deck": [],
            "turn_index": 0,
            "started": False,
            "exchanged": [],
            "bet": bet,
            "pot": 0,
            "bets_collected": False,
            "guild_id": interaction.guild_id,
        }
        await save_poker_game(interaction.guild_id, game_id, poker_games[game_id])
        await interaction.response.send_message(lobby_text(poker_games[game_id]), view=PokerLobbyView(game_id))

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
        bet = int(state.get("bet", 0) or 0)
        if bet > 0 and interaction.guild_id:
            balance = await get_coin_balance(interaction.guild_id, interaction.user.id)
            if balance < bet:
                await interaction.response.send_message(f"参加に **{bet}** コイン必要です。現在の所持コインは **{balance}** です。", ephemeral=True)
                return
        state["players"].append(interaction.user.id)
        await save_poker_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
        await interaction.response.send_message(f"{interaction.user.mention} が参加しました。")

    @app_commands.command(name="poker_begin", description="ポーカーを開始します")
    async def poker_begin(self, interaction: discord.Interaction):
        await start_poker_game(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Poker(bot))
