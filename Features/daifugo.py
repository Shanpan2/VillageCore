import random
import asyncio
import json
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from database.config_db import db_get, db_set


SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣", "J": "★"}
RANKS = list(range(3, 15)) + [15]
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A", 15: "2", 16: "JOKER"}
DEFAULT_RULES = {
    "revolution": True,
    "eight_cut": True,
    "sequence": True,
    "suit_lock": True,
    "capital_fall": True,
}

daifugo_games: dict[str, dict] = {}


def daifugo_index_key(guild_id: int) -> str:
    return f"daifugo_games_index:{guild_id}"


def daifugo_game_key(guild_id: int, game_id: str) -> str:
    return f"daifugo_game:{guild_id}:{game_id}"


async def save_daifugo_game(guild_id: int | None, game_id: str, state: dict | None = None):
    if not guild_id:
        return
    state = state or daifugo_games.get(game_id)
    if not state:
        return
    state["guild_id"] = guild_id
    await db_set(daifugo_game_key(guild_id, game_id), json.dumps(state, ensure_ascii=False))
    try:
        index = json.loads(await db_get(daifugo_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(daifugo_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_daifugo_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(daifugo_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(daifugo_index_key(guild_id), json.dumps(index, ensure_ascii=False))


async def load_daifugo_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(daifugo_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []

    changed = False
    for game_id in index:
        raw = await db_get(daifugo_game_key(guild.id, game_id))
        if not raw:
            changed = True
            continue
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            changed = True
            continue
        if not isinstance(state, dict) or not state.get("players"):
            changed = True
            continue
        daifugo_games[game_id] = state
        if state.get("started"):
            current = state["players"][state.get("turn_index", 0)]
            bot.add_view(DaifugoPlayView(game_id, current))
        else:
            bot.add_view(DaifugoLobbyView(game_id))

    if changed:
        active = [game_id for game_id in index if game_id in daifugo_games]
        await db_set(daifugo_index_key(guild.id), json.dumps(active, ensure_ascii=False))


def lobby_text(state: dict) -> str:
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", []))
    note = ""
    if state["rules"].get("capital_fall") and not state.get("previous_daifugo_id"):
        note = "\n都落ちは前回大富豪を指定した場合に発動します。"
    return (
        "**大富豪募集**\n"
        f"有効ルール: {rules_text(state)}{note}\n"
        f"参加者: {players or 'なし'}\n\n"
        "下のボタンで参加、抜ける、開始、中止ができます。"
    )


class DaifugoLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel"), self.children):
            child.custom_id = f"daifugo_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = daifugo_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この大富豪募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_daifugo_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = daifugo_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この大富豪募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。開始後は抜けられません。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"].remove(interaction.user.id)
        if not state["players"]:
            await delete_daifugo_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            daifugo_games.pop(self.game_id, None)
            await interaction.response.edit_message(content="参加者がいなくなったため、大富豪募集を終了しました。", view=None)
            return
        if state.get("creator_id") == interaction.user.id:
            state["creator_id"] = state["players"][0]
        await save_daifugo_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cog = interaction.client.get_cog("Daifugo")
            if not cog:
                await interaction.response.send_message("開始処理を呼び出せませんでした。", ephemeral=True)
                return
            await cog.daifugo_begin.callback(cog, interaction)
            state = daifugo_games.get(self.game_id)
            if state and state.get("started") and interaction.message:
                try:
                    await interaction.message.edit(content=lobby_text(state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        except Exception as e:
            print(f"[DaifugoLobbyView.begin] error: {type(e).__name__}: {e}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send("開始処理中にエラーが発生しました。`/daifugo_begin` でもう一度試してください。", ephemeral=True)
            else:
                await interaction.response.send_message("開始処理中にエラーが発生しました。`/daifugo_begin` でもう一度試してください。", ephemeral=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = daifugo_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この大富豪募集はありません。", ephemeral=True)
            return
        is_creator = interaction.user.id == state.get("creator_id")
        is_admin = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
        if not is_creator and not is_admin:
            await interaction.response.send_message("中止できるのは作成者または管理者だけです。", ephemeral=True)
            return
        await delete_daifugo_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        daifugo_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="大富豪募集を中止しました。", view=None)


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


def suit_key(cards: list[dict]) -> tuple[str, ...]:
    return tuple(sorted(card["suit"] for card in cards))


def beats(new_rank: int, old_rank: int, revolution: bool) -> bool:
    if old_rank <= 0:
        return True
    if new_rank == 16:
        return old_rank != 16
    if old_rank == 16:
        return False
    return new_rank < old_rank if revolution else new_rank > old_rank


def group_info(cards: list[dict]) -> dict | None:
    if not cards:
        return None
    ranks = [card["rank"] for card in cards]
    if len(cards) == 1:
        return {"type": "single", "count": 1, "rank": ranks[0], "suits": suit_key(cards)}
    if 16 not in ranks and len(set(ranks)) == 1:
        return {"type": "set", "count": len(cards), "rank": ranks[0], "suits": suit_key(cards)}
    if 16 in ranks:
        return None
    suits = {card["suit"] for card in cards}
    ordered = sorted(ranks)
    is_sequence = len(suits) == 1 and len(cards) >= 3 and ordered == list(range(ordered[0], ordered[0] + len(cards)))
    if is_sequence:
        return {"type": "sequence", "count": len(cards), "rank": ordered[-1], "suits": suit_key(cards)}
    return None


def can_play(group: list[dict], state: dict) -> bool:
    info = group_info(group)
    if not info:
        return False
    locked_suits = state.get("locked_suits")
    if locked_suits and info["suits"] != tuple(locked_suits):
        return False
    last_info = state.get("last_info")
    if not last_info:
        return True
    if info["type"] != last_info["type"] or info["count"] != last_info["count"]:
        return False
    return beats(info["rank"], last_info["rank"], state.get("revolution", False))


def sequence_groups(hand: list[dict]) -> list[list[dict]]:
    groups = []
    for suit in SUITS:
        cards = sorted((card for card in hand if card["suit"] == suit and card["rank"] != 16), key=card_sort_key)
        by_rank = {card["rank"]: card for card in cards}
        ranks = sorted(by_rank)
        for start_index, start_rank in enumerate(ranks):
            current = [by_rank[start_rank]]
            previous = start_rank
            for rank in ranks[start_index + 1:]:
                if rank != previous + 1:
                    break
                current.append(by_rank[rank])
                previous = rank
                if len(current) >= 3:
                    groups.append(current.copy())
    return groups


def legal_groups(hand: list[dict], state: dict) -> list[list[dict]]:
    sorted_hand = sorted(hand, key=card_sort_key)
    groups = []

    for card in sorted_hand:
        groups.append([card])

    by_rank: dict[int, list[dict]] = {}
    for card in sorted_hand:
        by_rank.setdefault(card["rank"], []).append(card)

    for rank, cards in by_rank.items():
        if rank == 16:
            continue
        for count in (2, 3, 4):
            if len(cards) >= count:
                groups.append(cards[:count])

    if state["rules"].get("sequence", True):
        groups.extend(sequence_groups(sorted_hand))

    return [group for group in groups if can_play(group, state)][:25]


def active_players(state: dict) -> list[int]:
    removed = set(state["finished"]) | set(state.get("fallen", []))
    return [uid for uid in state["players"] if str(uid) not in removed]


def rules_text(state: dict) -> str:
    labels = {
        "revolution": "革命",
        "eight_cut": "8切り",
        "sequence": "階段",
        "suit_lock": "しばり",
        "capital_fall": "都落ち",
    }
    enabled = [label for key, label in labels.items() if state["rules"].get(key)]
    return " / ".join(enabled) if enabled else "追加ルールなし"


def status_text(state: dict, prefix: str = "") -> str:
    current = state["players"][state["turn_index"]]
    last_play = state.get("last_play")
    last_text = group_label(last_play) if last_play else "なし"
    revolution_text = "革命中" if state.get("revolution") else "通常"
    lock_text = ""
    if state.get("locked_suits"):
        lock_text = " / しばり: " + " ".join(SUIT_SYMBOLS.get(suit, suit) for suit in state["locked_suits"])

    lines = []
    if prefix:
        lines.append(prefix)
    lines.extend(
        [
            "**大富豪**",
            f"現在のターン: <@{current}>",
            f"場: {last_text} ({revolution_text}{lock_text})",
            f"ルール: {rules_text(state)}",
            "手札: " + " / ".join(f"<@{uid}> {len(state['hands'].get(str(uid), []))}枚" for uid in state["players"]),
            "上がり: " + (", ".join(f"<@{uid}>" for uid in state["finished"]) if state["finished"] else "なし"),
        ]
    )
    if state.get("fallen"):
        lines.append("都落ち: " + ", ".join(f"<@{uid}>" for uid in state["fallen"]))
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

    draw.text((30, 22), f"{member.display_name} の手札", fill=(255, 255, 255), font=title_font)
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


def clear_field(state: dict):
    state["last_play"] = None
    state["last_info"] = None
    state["last_player"] = None
    state["passed"] = []
    state["locked_suits"] = None


async def advance_turn(state: dict):
    players = state["players"]
    active = set(active_players(state))
    for _ in range(len(players)):
        state["turn_index"] = (state["turn_index"] + 1) % len(players)
        if players[state["turn_index"]] in active:
            return


def apply_capital_fall(state: dict, winner_id: int) -> str:
    if not state["rules"].get("capital_fall"):
        return ""
    previous = state.get("previous_daifugo_id")
    if not previous or previous == winner_id:
        return ""
    if previous not in state["players"]:
        return ""
    if str(previous) in state["finished"] or str(previous) in state.get("fallen", []):
        return ""
    state.setdefault("fallen", []).append(str(previous))
    return f"\n都落ち: 前回大富豪の <@{previous}> は最下位扱いになりました。"


async def end_if_needed(interaction: discord.Interaction, state: dict) -> bool:
    remaining = active_players(state)
    if len(remaining) > 1:
        return False
    if remaining and str(remaining[0]) not in state["finished"]:
        state["finished"].append(str(remaining[0]))
    ranking_order = state["finished"] + state.get("fallen", [])
    ranking = "\n".join(f"{index + 1}. <@{uid}>" for index, uid in enumerate(ranking_order))
    await delete_daifugo_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id))
    daifugo_games.pop(str(interaction.channel_id), None)
    await interaction.response.edit_message(content=f"**大富豪終了**\n{ranking}", view=None)
    return True


async def update_table(interaction: discord.Interaction, state: dict, prefix: str = ""):
    game_id = str(interaction.channel_id)
    current = state["players"][state["turn_index"]]
    await save_daifugo_game(interaction.guild_id or state.get("guild_id"), game_id, state)
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
        groups = legal_groups(hand, state)
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
    legal_encoded = {encode_group(group) for group in legal_groups(hand, state)}
    if not cards or encode_group(cards) not in legal_encoded:
        await interaction.response.send_message("そのカードは今出せません。", ephemeral=True)
        return

    previous_info = state.get("last_info")
    info = group_info(cards)
    for card in cards:
        hand.remove(card)
    state["hands"][str(user_id)] = hand
    state["last_play"] = cards
    state["last_info"] = info
    state["last_player"] = user_id
    state["passed"] = []

    prefix = f"<@{user_id}> が **{group_label(cards)}** を出しました。"
    if state["rules"].get("suit_lock") and previous_info and info and info["suits"] == tuple(previous_info.get("suits", ())):
        state["locked_suits"] = info["suits"]
        prefix += "\nしばりが発生しました。"

    if state["rules"].get("revolution") and len(cards) >= 4:
        state["revolution"] = not state.get("revolution", False)
        prefix += "\n革命が発生しました。" if state["revolution"] else "\n革命が解除されました。"

    eight_cut = state["rules"].get("eight_cut") and any(card["rank"] == 8 for card in cards)

    if not hand and str(user_id) not in state["finished"]:
        state["finished"].append(str(user_id))
        prefix += apply_capital_fall(state, user_id)
        if await end_if_needed(interaction, state):
            return

    if eight_cut:
        clear_field(state)
        prefix += "\n8切りで場が流れました。"
        if user_id in active_players(state):
            state["turn_index"] = state["players"].index(user_id)
        else:
            await advance_turn(state)
    else:
        await advance_turn(state)
    await update_table(interaction, state, prefix)


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
        last_player = state.get("last_player")
        clear_field(state)
        if last_player in active_players(state):
            state["turn_index"] = state["players"].index(last_player)
        prefix += "\n場が流れました。"
    else:
        await advance_turn(state)
    await update_table(interaction, state, prefix)


class Daifugo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restore_task = None

    async def cog_load(self):
        self._restore_task = asyncio.create_task(self._restore_saved_games())

    async def cog_unload(self):
        if self._restore_task:
            self._restore_task.cancel()

    async def _restore_saved_games(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await load_daifugo_games_for_guild(self.bot, guild)

    @app_commands.command(name="daifugo_start", description="大富豪ゲームを作成します")
    @app_commands.describe(
        revolution="革命を有効にします",
        eight_cut="8切りを有効にします",
        sequence="階段を有効にします",
        suit_lock="しばりを有効にします",
        capital_fall="都落ちを有効にします",
        previous_daifugo="都落ちで前回大富豪として扱うメンバー",
    )
    async def daifugo_start(
        self,
        interaction: discord.Interaction,
        revolution: bool = True,
        eight_cut: bool = True,
        sequence: bool = True,
        suit_lock: bool = True,
        capital_fall: bool = True,
        previous_daifugo: discord.Member | None = None,
    ):
        game_id = str(interaction.channel_id)
        if game_id in daifugo_games:
            await interaction.response.send_message("このチャンネルにはすでに大富豪募集があります。", ephemeral=True)
            return
        rules = {
            "revolution": revolution,
            "eight_cut": eight_cut,
            "sequence": sequence,
            "suit_lock": suit_lock,
            "capital_fall": capital_fall,
        }
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
            "previous_daifugo_id": previous_daifugo.id if previous_daifugo else None,
            "guild_id": interaction.guild_id,
        }
        await save_daifugo_game(interaction.guild_id, game_id, daifugo_games[game_id])
        await interaction.response.send_message(lobby_text(daifugo_games[game_id]), view=DaifugoLobbyView(game_id))

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
        await save_daifugo_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id), state)
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
        random.shuffle(state["players"])
        hands = {str(uid): [] for uid in state["players"]}
        for index, card in enumerate(deck):
            hands[str(state["players"][index % len(state["players"])])].append(card)

        state["hands"] = hands
        state["started"] = True
        state["guild_id"] = interaction.guild_id
        await save_daifugo_game(interaction.guild_id, game_id, state)

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
