import random
import asyncio
import json
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from database.config_db import db_get, db_set


SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_NAMES = {"S": "spade", "H": "heart", "D": "diamond", "C": "club"}
RANKS = list(range(1, 14))
RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}
BOARD_IMAGE_PATH = Path("sevens_board.png")
sevens_games: dict[str, dict] = {}


def sevens_index_key(guild_id: int) -> str:
    return f"sevens_games_index:{guild_id}"


def sevens_game_key(guild_id: int, game_id: str) -> str:
    return f"sevens_game:{guild_id}:{game_id}"


async def save_sevens_game(guild_id: int | None, game_id: str, state: dict | None = None):
    if not guild_id:
        return
    state = state or sevens_games.get(game_id)
    if not state:
        return
    state["guild_id"] = guild_id
    await db_set(sevens_game_key(guild_id, game_id), json.dumps(state, ensure_ascii=False))
    try:
        index = json.loads(await db_get(sevens_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(sevens_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_sevens_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(sevens_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(sevens_index_key(guild_id), json.dumps(index, ensure_ascii=False))


async def load_sevens_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(sevens_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []

    changed = False
    for game_id in index:
        raw = await db_get(sevens_game_key(guild.id, game_id))
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
        sevens_games[game_id] = state
        if state.get("started"):
            current = state["players"][state.get("turn_index", 0)]
            bot.add_view(SevensPlayView(game_id, current))
        else:
            bot.add_view(SevensLobbyView(game_id))

    if changed:
        active = [game_id for game_id in index if game_id in sevens_games]
        await db_set(sevens_index_key(guild.id), json.dumps(active, ensure_ascii=False))


def normalize_sevens_state(state: dict) -> dict:
    state["players"] = [int(uid) for uid in state.get("players", [])]
    state["turn_index"] = int(state.get("turn_index", 0) or 0)
    if state["players"]:
        state["turn_index"] %= len(state["players"])
    return state


async def get_sevens_game_state(bot: commands.Bot, game_id: str, guild_id: int | None = None) -> dict | None:
    state = sevens_games.get(game_id)
    if state:
        state = normalize_sevens_state(state)
        sevens_games[game_id] = state
        return state
    guild_ids: list[int] = []
    if guild_id:
        guild_ids.append(int(guild_id))
    guild_ids.extend(guild.id for guild in getattr(bot, "guilds", []) if guild.id not in guild_ids)
    for target_guild_id in guild_ids:
        raw = await db_get(sevens_game_key(target_guild_id, game_id))
        if not raw:
            continue
        try:
            state = normalize_sevens_state(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not state.get("players"):
            continue
        state["guild_id"] = target_guild_id
        sevens_games[game_id] = state
        return state
    return None


def lobby_text(state: dict) -> str:
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", []))
    return (
        "**7並べ募集**\n"
        f"参加者: {players or 'なし'}\n\n"
        "下のボタンで参加、抜ける、開始、中止ができます。"
    )


class SevensLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel"), self.children):
            child.custom_id = f"sevens_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = sevens_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この7並べ募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_sevens_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = sevens_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この7並べ募集は終了しています。", ephemeral=True)
            return
        if state.get("started"):
            await interaction.response.send_message("すでに開始しています。開始後は抜けられません。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"].remove(interaction.user.id)
        if not state["players"]:
            await delete_sevens_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            sevens_games.pop(self.game_id, None)
            await interaction.response.edit_message(content="参加者がいなくなったため、7並べ募集を終了しました。", view=None)
            return
        if state.get("creator_id") == interaction.user.id:
            state["creator_id"] = state["players"][0]
        await save_sevens_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await start_sevens_game(interaction, self.game_id)
            state = sevens_games.get(self.game_id)
            if state and state.get("started") and interaction.message:
                try:
                    await interaction.message.edit(content=lobby_text(state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        except Exception as e:
            print(f"[SevensLobbyView.begin] error: {type(e).__name__}: {e}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send("開始処理中にエラーが発生しました。`/sevens_begin` でもう一度試してください。", ephemeral=True)
            else:
                await interaction.response.send_message("開始処理中にエラーが発生しました。`/sevens_begin` でもう一度試してください。", ephemeral=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = sevens_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この7並べ募集はありません。", ephemeral=True)
            return
        is_creator = interaction.user.id == state.get("creator_id")
        is_admin = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
        if not is_creator and not is_admin:
            await interaction.response.send_message("中止できるのは作成者または管理者だけです。", ephemeral=True)
            return
        await delete_sevens_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        sevens_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="7並べ募集を中止しました。", view=None)


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
    except OSError:
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
    except OSError:
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
    candidate_lines = [
        f"候補 {index}: {card_label(card)}"
        for index, card in enumerate(playable[:25], start=1)
    ]
    candidates = "\n\n出せる候補:\n" + "\n".join(candidate_lines) if candidate_lines else "\n\n今出せるカードはありません。"
    await member.send(
        "あなたの7並べの手札です。\n"
        "黄色い枠のカードは現在出せます。"
        + candidates,
        file=hand_file(member, hand, playable),
    )


async def send_player_hand_update(
    guild: discord.Guild | None,
    user_id: int,
    state: dict,
    *,
    include_candidates: bool = True,
):
    if not guild:
        return
    member = guild.get_member(user_id)
    if not member:
        return
    hand = [tuple(c) for c in state["hands"].get(str(user_id), [])]
    playable = playable_cards(hand, state["board"]) if include_candidates else []
    try:
        await send_hand(member, hand, playable)
    except discord.HTTPException as e:
        print(f"[Sevens] DM send failed for {user_id}: {type(e).__name__}: {e}", flush=True)


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
        options = [
            discord.SelectOption(
                label=f"候補 {index}",
                value=card_value(card),
                description="DMの手札画像で出せるカードを確認してください。",
            )
            for index, card in enumerate(cards, start=1)
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


async def edit_sevens_message(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        if interaction.message:
            await interaction.message.edit(**kwargs)
    else:
        await interaction.response.edit_message(**kwargs)


async def update_game_message(interaction: discord.Interaction, state: dict, prefix: str = ""):
    game_id = str(interaction.channel_id)
    current_user = state["players"][state["turn_index"]]
    await save_sevens_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    await send_player_hand_update(interaction.guild, current_user, state)
    await edit_sevens_message(
        interaction,
        content=status_text(state, prefix),
        attachments=[board_file(state)],
        view=SevensPlayView(game_id, current_user),
    )


async def end_if_needed(interaction: discord.Interaction, state: dict) -> bool:
    remaining = active_players(state)
    if len(remaining) > 1:
        return False

    winner = remaining[0] if remaining else int(state["finished"][0])
    await delete_sevens_game(interaction.guild_id or state.get("guild_id"), str(interaction.channel_id))
    sevens_games.pop(str(interaction.channel_id), None)
    await edit_sevens_message(
        interaction,
        content=f"🎉 7並べ終了！勝者: <@{winner}>",
        attachments=[board_file(state)],
        view=None,
    )
    return True


async def play_card(interaction: discord.Interaction, game_id: str, user_id: int, card: tuple[str, int]):
    state = await get_sevens_game_state(interaction.client, game_id, interaction.guild_id)
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

    await interaction.response.defer()
    hand.remove(card)
    state["hands"][str(user_id)] = [list(c) for c in hand]
    state["board"][card[0]].append(card[1])
    state["board"][card[0]].sort()

    if not hand:
        state["finished"].append(str(user_id))
        if await end_if_needed(interaction, state):
            return
    else:
        await send_player_hand_update(interaction.guild, user_id, state, include_candidates=False)

    await advance_turn(state)
    await update_game_message(interaction, state, f"🃏 <@{user_id}> が **{card_label(card)}** を出しました。")


async def pass_turn(interaction: discord.Interaction, game_id: str, user_id: int):
    state = await get_sevens_game_state(interaction.client, game_id, interaction.guild_id)
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
        await interaction.response.defer()
        if await end_if_needed(interaction, state):
            return
    else:
        prefix = f"⏭️ <@{user_id}> がパスしました。"
        await interaction.response.defer()

    await advance_turn(state)
    await update_game_message(interaction, state, prefix)


async def surrender(interaction: discord.Interaction, game_id: str, user_id: int):
    state = await get_sevens_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    if interaction.user.id != state["players"][state["turn_index"]] or interaction.user.id != user_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    state["finished"].append(str(user_id))
    await interaction.response.defer()
    if await end_if_needed(interaction, state):
        return

    await advance_turn(state)
    await update_game_message(interaction, state, f"🏳️ <@{user_id}> が降参しました。")


class Sevens(commands.Cog):
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
            await load_sevens_games_for_guild(self.bot, guild)

    @app_commands.command(name="sevens_start", description="7並べゲームを作成します")
    async def sevens_start(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)
        if game_id in sevens_games:
            await interaction.response.send_message("このチャンネルにはすでに7並べ募集があります。", ephemeral=True)
            return
        sevens_games[game_id] = {
            "creator_id": interaction.user.id,
            "players": [interaction.user.id],
            "hands": {},
            "board": {suit: [7] for suit in SUITS},
            "turn_index": 0,
            "passes": {},
            "finished": [],
            "started": False,
            "guild_id": interaction.guild_id,
        }
        await save_sevens_game(interaction.guild_id, game_id, sevens_games[game_id])
        await interaction.response.send_message(lobby_text(sevens_games[game_id]), view=SevensLobbyView(game_id))

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
        await save_sevens_game(interaction.guild_id or state.get("guild_id"), game_id, state)
        await interaction.response.send_message(f"🙌 {interaction.user.mention} が参加しました。")

    @app_commands.command(name="sevens_begin", description="7並べを開始します")
    async def sevens_begin(self, interaction: discord.Interaction):
        await start_sevens_game(interaction)


async def start_sevens_game(interaction: discord.Interaction, game_id: str | None = None):
    game_id = game_id or str(interaction.channel_id)
    state = await get_sevens_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ まず `/sevens_start` を実行してください。", ephemeral=True)
        return
    if state["started"]:
        await interaction.response.send_message("❌ すでに開始しています。", ephemeral=True)
        return
    if len(state["players"]) < 2:
        await interaction.response.send_message("❌ 2人以上必要です。", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    deck = [card for card in build_deck() if card[1] != 7]
    random.shuffle(deck)
    hands = {str(uid): [] for uid in state["players"]}
    for index, card in enumerate(deck):
        uid = state["players"][index % len(state["players"])]
        hands[str(uid)].append(list(card))
    state["hands"] = hands
    state["started"] = True
    random.shuffle(state["players"])
    state["guild_id"] = interaction.guild_id
    await save_sevens_game(interaction.guild_id, game_id, state)

    failed_dm = []
    for uid in state["players"]:
        member = interaction.guild.get_member(uid) if interaction.guild else None
        if not member:
            continue
        hand = [tuple(c) for c in hands[str(uid)]]
        try:
            await send_hand(member, hand, playable_cards(hand, state["board"]))
        except discord.HTTPException:
            failed_dm.append(member.mention)

    current_user = state["players"][state["turn_index"]]
    text = status_text(state)
    if failed_dm:
        text += "\n\n⚠️ DM送信に失敗: " + " ".join(failed_dm)
    await interaction.followup.send(text, file=board_file(state), view=SevensPlayView(game_id, current_user))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sevens(bot))
