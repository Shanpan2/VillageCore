import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import asyncio
import json
import random
import os
from io import BytesIO

from database.config_db import db_get, db_set
from views.uno_views import (
    UnoHandView,
    WildColorSelectView,
    UnoDeclareView,
    ChallengeView,
)


# UNO ゲーム状態（メモリ管理）
uno_games: dict[str, dict] = {}


def uno_index_key(guild_id: int) -> str:
    return f"uno_games_index:{guild_id}"


def uno_game_key(guild_id: int, game_id: str) -> str:
    return f"uno_game:{guild_id}:{game_id}"


def normalize_uno_state(state: dict) -> dict:
    players = [int(uid) for uid in state.get("players", [])]
    state["players"] = players
    hands = state.get("hands") or {}
    state["hands"] = {int(uid): cards for uid, cards in hands.items()} if hands else {}
    if state.get("turn_index") is None:
        state["turn_index"] = 0
    state["turn_index"] = int(state.get("turn_index", 0) or 0)
    if players:
        state["turn_index"] %= len(players)
    pending = state.get("pending")
    if isinstance(pending, dict):
        for key in ("user_id", "attacker_id", "defender_id"):
            if pending.get(key) is not None:
                pending[key] = int(pending[key])
    return state


async def save_uno_game(guild_id: int | None, game_id: str, state: dict | None = None):
    if not guild_id:
        return
    state = normalize_uno_state(state or uno_games.get(game_id) or {})
    if not state:
        return
    state["guild_id"] = guild_id
    await db_set(uno_game_key(guild_id, game_id), json.dumps(state, ensure_ascii=False))
    try:
        index = json.loads(await db_get(uno_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(uno_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_uno_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(uno_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(uno_index_key(guild_id), json.dumps(index, ensure_ascii=False))


async def load_uno_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(uno_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []

    changed = False
    for game_id in index:
        raw = await db_get(uno_game_key(guild.id, game_id))
        if not raw:
            changed = True
            continue
        try:
            state = normalize_uno_state(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            changed = True
            continue
        if not isinstance(state, dict) or not state.get("players"):
            changed = True
            continue
        uno_games[game_id] = state
        pending = state.get("pending")
        if not state.get("hands"):
            bot.add_view(UnoLobbyView(game_id))
        elif pending and pending.get("type") == "wild_color":
            bot.add_view(WildColorSelectView(game_id, int(pending["user_id"]), pending["card"]))
        elif pending and pending.get("type") == "challenge":
            bot.add_view(ChallengeView(game_id, int(pending["attacker_id"]), int(pending["defender_id"])))
        elif pending and pending.get("type") == "uno_declare":
            bot.add_view(UnoDeclareView(game_id, int(pending["user_id"])))
        else:
            current = state["players"][state.get("turn_index", 0)]
            bot.add_view(UnoHandView(game_id, current, state["hands"].get(current, [])))

    if changed:
        active = [game_id for game_id in index if game_id in uno_games]
        await db_set(uno_index_key(guild.id), json.dumps(active, ensure_ascii=False))


async def get_uno_game_state(bot: commands.Bot, game_id: str, guild_id: int | None = None) -> dict | None:
    state = uno_games.get(game_id)
    if state:
        state = normalize_uno_state(state)
        uno_games[game_id] = state
        return state

    guild_ids: list[int] = []
    if guild_id:
        guild_ids.append(int(guild_id))
    guild_ids.extend(guild.id for guild in getattr(bot, "guilds", []) if guild.id not in guild_ids)

    for target_guild_id in guild_ids:
        raw = await db_get(uno_game_key(target_guild_id, game_id))
        if not raw:
            continue
        try:
            state = normalize_uno_state(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not state.get("players"):
            continue
        state["guild_id"] = target_guild_id
        uno_games[game_id] = state
        return state
    return None


def lobby_text(state: dict) -> str:
    players = " / ".join(f"<@{uid}>" for uid in state.get("players", []))
    challenge = "ON" if state.get("challenge_mode", True) else "OFF"
    return (
        "**UNO募集**\n"
        f"チャレンジ機能: **{challenge}**\n"
        f"参加者: {players or 'なし'}\n\n"
        "下のボタンで参加、抜ける、開始、中止ができます。"
    )


class UnoLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel"), self.children):
            child.custom_id = f"uno_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = uno_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このUNO募集は終了しています。", ephemeral=True)
            return
        if state.get("hands"):
            await interaction.response.send_message("すでに開始しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_uno_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = uno_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このUNO募集は終了しています。", ephemeral=True)
            return
        if state.get("hands"):
            await interaction.response.send_message("すでに開始しています。開始後は抜けられません。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"].remove(interaction.user.id)
        if not state["players"]:
            await delete_uno_game(interaction.guild_id or state.get("guild_id"), self.game_id)
            uno_games.pop(self.game_id, None)
            await interaction.response.edit_message(content="参加者がいなくなったため、UNO募集を終了しました。", view=None)
            return
        if state.get("creator_id") == interaction.user.id:
            state["creator_id"] = state["players"][0]
        await save_uno_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await start_uno_game(interaction, self.game_id)
            state = uno_games.get(self.game_id)
            if state and state.get("hands") and interaction.message:
                try:
                    await interaction.message.edit(content=lobby_text(state) + "\n\n開始済みです。", view=None)
                except discord.HTTPException:
                    pass
        except Exception as e:
            print(f"[UnoLobbyView.begin] error: {type(e).__name__}: {e}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send("開始処理中にエラーが発生しました。`/uno_begin` でもう一度試してください。", ephemeral=True)
            else:
                await interaction.response.send_message("開始処理中にエラーが発生しました。`/uno_begin` でもう一度試してください。", ephemeral=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = uno_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("このUNO募集はありません。", ephemeral=True)
            return
        is_creator = interaction.user.id == state.get("creator_id")
        is_admin = bool(getattr(interaction.user.guild_permissions, "manage_guild", False))
        if not is_creator and not is_admin:
            await interaction.response.send_message("中止できるのは作成者または管理者だけです。", ephemeral=True)
            return
        await delete_uno_game(interaction.guild_id or state.get("guild_id"), self.game_id)
        uno_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="UNO募集を中止しました。", view=None)


class Uno(commands.Cog):
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
            await load_uno_games_for_guild(self.bot, guild)

    # -------------------------------------------------------
    # /uno_start
    # -------------------------------------------------------
    @app_commands.command(name="uno_start", description="UNOゲームを作成します")
    @app_commands.describe(challenge="ワイルドドロー4のチャレンジ機能を有効にするか")
    async def uno_start(self, interaction: discord.Interaction, challenge: bool = True):
        game_id = str(interaction.channel_id)
        if game_id in uno_games:
            await interaction.response.send_message("このチャンネルにはすでにUNO募集があります。", ephemeral=True)
            return

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
            "challenge_mode": challenge,
            "pending": None,
            "guild_id": interaction.guild_id,
        }

        await save_uno_game(interaction.guild_id, game_id, uno_games[game_id])
        await interaction.response.send_message(lobby_text(uno_games[game_id]), view=UnoLobbyView(game_id))

    # -------------------------------------------------------
    # /uno_join
    # -------------------------------------------------------
    @app_commands.command(name="uno_join", description="UNOゲームに参加します")
    async def uno_join(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)

        if game_id not in uno_games:
            await interaction.response.send_message(
                "❌ まず `/uno_start` を実行してください。", ephemeral=True
            )
            return

        state = uno_games[game_id]
        user_id = interaction.user.id

        if user_id in state["players"]:
            await interaction.response.send_message(
                "❌ すでに参加しています。", ephemeral=True
            )
            return

        state["players"].append(user_id)
        await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
        await interaction.response.send_message(
            f"🙌 {interaction.user.mention} が参加しました！"
        )

    # -------------------------------------------------------
    # /uno_begin
    # -------------------------------------------------------
    @app_commands.command(name="uno_begin", description="UNOゲームを開始します")
    async def uno_begin(self, interaction: discord.Interaction):
        await start_uno_game(interaction)


# ============================================================
# views から呼び出すハンドラ群
# ============================================================

async def handle_play_card(
    interaction: discord.Interaction, game_id: str, button_user_id: int, card: str
):
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    discard = state["discard"]
    top = state["top"]
    turn_index = state["turn_index"]
    direction = state["direction"]
    current_player_id = int(players[turn_index])
    button_user_id = int(button_user_id)

    if int(interaction.user.id) != button_user_id:
        await interaction.response.send_message(
            "❌ この手札パネルはあなた用ではありません。", ephemeral=True
        )
        return

    if int(interaction.user.id) != current_player_id:
        await interaction.response.send_message(
            f"❌ あなたのターンではありません。現在のターンは <@{current_player_id}> です。", ephemeral=True
        )
        return

    if card not in hands[current_player_id]:
        await interaction.response.send_message(
            "❌ そのカードはあなたの手札にありません。", ephemeral=True
        )
        return

    if not can_play(card, top):
        await interaction.response.send_message(
            "❌ そのカードは現在の場に出せません。", ephemeral=True
        )
        return

    # ワイルド系は色選択へ
    if card.startswith("wild"):
        state["pending"] = {"type": "wild_color", "user_id": current_player_id, "card": card}
        await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
        await interaction.response.edit_message(
            content=f"🎨 **{card}** を出します。色を選んでください。",
            view=WildColorSelectView(game_id, current_player_id, card),
            attachments=[],
        )
        return

    hands[current_player_id].remove(card)
    discard.append(card)
    state["top"] = card
    uno_notice = len(hands[current_player_id]) == 1

    # 残り1枚になったら自動でUNO宣言扱いにして、進行を止めない。
    if uno_notice:
        state["uno_declared"] = True

    # 勝利判定
    if len(hands[current_player_id]) == 0:
        await delete_uno_game(interaction.guild_id or state.get("guild_id"), game_id)
        uno_games.pop(game_id, None)
        await interaction.response.edit_message(content="🎉 勝利しました！", view=None, attachments=[])
        await send_uno_channel_update(interaction.client, game_id, state, f"🎉 <@{current_player_id}> の勝利!!", include_top=False)
        return

    # 効果処理
    if card.endswith("skip"):
        turn_index = (turn_index + direction * 2) % len(players)
    elif card.endswith("reverse"):
        direction *= -1
        state["direction"] = direction
        turn_index = (turn_index + direction) % len(players)
        if len(players) == 2:
            turn_index = (turn_index + direction) % len(players)
    elif card.endswith("draw2"):
        next_index = (turn_index + direction) % len(players)
        next_player = players[next_index]
        if len(deck) < 2:
            deck, discard = refill_deck(deck, discard)
        for _ in range(2):
            if deck:
                hands[next_player].append(deck.pop())
        turn_index = (turn_index + direction * 2) % len(players)
    else:
        turn_index = (turn_index + direction) % len(players)

    # UNO宣言忘れペナルティ
    if len(hands[current_player_id]) == 1 and not state.get("uno_declared", False):
        for _ in range(2):
            if deck:
                hands[current_player_id].append(deck.pop())

    state["uno_declared"] = False
    state["pending"] = None

    if len(deck) == 0:
        deck, discard = refill_deck(deck, discard)

    state.update({"turn_index": turn_index, "hands": hands, "deck": deck, "discard": discard})
    await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"🃏 **{card}** を出しました。",
        view=None,
        attachments=[],
    )
    prefix = f"🃏 <@{current_player_id}> が **{card}** を出しました。"
    if uno_notice:
        prefix += f"\n🎉 <@{current_player_id}> が **UNO！**"
    await send_uno_turn(interaction.client, game_id, state, prefix)


async def handle_wild_color_select(
    interaction: discord.Interaction,
    game_id: str,
    user_id: int,
    card: str,
    color: str,
):
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    discard = state["discard"]
    turn_index = state["turn_index"]
    direction = state["direction"]
    current_player_id = int(players[turn_index])
    user_id = int(user_id)

    if int(interaction.user.id) != user_id:
        await interaction.response.send_message(
            "❌ この色選択パネルはあなた用ではありません。", ephemeral=True
        )
        return

    if int(interaction.user.id) != current_player_id:
        await interaction.response.send_message(
            f"❌ あなたのターンではありません。現在のターンは <@{current_player_id}> です。", ephemeral=True
        )
        return

    new_card = f"wild_{color}"
    hands[current_player_id].remove(card)
    discard.append(new_card)
    state["top"] = new_card

    if card.startswith("wild_draw"):
        next_index = (turn_index + direction) % len(players)
        next_player = players[next_index]

        if state["challenge_mode"]:
            state.update({"hands": hands, "deck": deck, "discard": discard, "pending": {
                "type": "challenge",
                "attacker_id": current_player_id,
                "defender_id": next_player,
            }})
            await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
            await interaction.response.edit_message(
                content="🃏 ワイルドドロー4を出しました。チャレンジ確認を相手に送ります。",
                view=None,
                attachments=[],
            )
            await send_uno_channel_update(
                interaction.client,
                game_id,
                state,
                f"🃏 <@{current_player_id}> が **ワイルドドロー4** を出しました。<@{next_player}> のチャレンジ待ちです。",
            )
            await send_uno_challenge_dm(interaction.client, state, game_id, current_player_id, next_player)
            return

        if len(deck) < 4:
            deck, discard = refill_deck(deck, discard)
        for _ in range(4):
            if deck:
                hands[next_player].append(deck.pop())
        turn_index = (turn_index + direction * 2) % len(players)
    else:
        turn_index = (turn_index + direction) % len(players)

    state.update({"hands": hands, "deck": deck, "discard": discard, "turn_index": turn_index, "pending": None})
    await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    await interaction.response.edit_message(content=f"🎨 色を **{color}** に変更しました。", view=None, attachments=[])
    await send_uno_turn(interaction.client, game_id, state, f"🎨 色は **{color}** に変更されました。")


async def handle_challenge(
    interaction: discord.Interaction,
    game_id: str,
    attacker_id: int,
    defender_id: int,
):
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)

    hands = state["hands"]
    deck = state["deck"]
    players = state["players"]
    turn_index = state["turn_index"]
    direction = state["direction"]

    attacker_id = int(attacker_id)
    defender_id = int(defender_id)
    top_color = state["top"].split("_")[1]
    can_play_other = any(
        (not c.startswith("wild")) and c.split("_")[0] == top_color
        for c in hands[attacker_id]
    )

    if can_play_other:
        if len(deck) < 4:
            deck, _ = refill_deck(deck, state["discard"])
        for _ in range(4):
            if deck:
                hands[attacker_id].append(deck.pop())
        result = f"🎉 チャレンジ成功！\n<@{attacker_id}> が 4 枚引きます。"
    else:
        if len(deck) < 6:
            deck, _ = refill_deck(deck, state["discard"])
        for _ in range(6):
            if deck:
                hands[defender_id].append(deck.pop())
        result = f"💥 チャレンジ失敗！\n<@{defender_id}> が 6 枚引きます。"

    turn_index = (turn_index + direction * 2) % len(players)
    state.update({"hands": hands, "deck": deck, "turn_index": turn_index, "pending": None})
    await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=result,
        view=None,
        attachments=[],
    )
    await send_uno_turn(interaction.client, game_id, state, result)


async def handle_uno_declare(
    interaction: discord.Interaction, game_id: str, user_id: int
):
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)
    user_id = int(user_id)

    if int(interaction.user.id) != user_id:
        await interaction.response.send_message(
            "❌ あなたは UNO を宣言できません。", ephemeral=True
        )
        return

    if len(state["hands"].get(user_id, [])) != 1:
        await interaction.response.send_message(
            "❌ 今は UNO を宣言できません。", ephemeral=True
        )
        return

    state["uno_declared"] = True
    state["pending"] = None
    await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)
    await interaction.response.edit_message(content="🎉 **UNO！** を宣言しました！", view=None, attachments=[])
    await send_uno_channel_update(interaction.client, game_id, state, f"🎉 <@{user_id}> が **UNO！** を宣言しました。")
    current = state["players"][state["turn_index"]]
    await send_uno_hand_dm(interaction.client, state, game_id, current)


async def handle_uno_surrender(
    interaction: discord.Interaction, game_id: str, user_id: int
):
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)
    user_id = int(user_id)

    if int(interaction.user.id) != user_id:
        await interaction.response.send_message(
            "❌ あなたはこの降参ボタンを使えません。", ephemeral=True
        )
        return

    remaining = [uid for uid in state["players"] if uid != user_id]
    winners = ", ".join(f"<@{uid}>" for uid in remaining) if remaining else "なし"
    await delete_uno_game(interaction.guild_id or state.get("guild_id"), game_id)
    uno_games.pop(game_id, None)

    await interaction.response.edit_message(
        content="⛔ 降参しました。",
        view=None,
        attachments=[],
    )
    await send_uno_channel_update(interaction.client, game_id, state, f"⛔ <@{user_id}> が降参しました。\nゲーム終了。勝者: {winners}", include_top=False)


# ============================================================
# ユーティリティ
# ============================================================

def generate_deck() -> list[str]:
    colors = ["red", "yellow", "green", "blue"]
    deck = []
    for color in colors:
        for n in range(10):
            deck.append(f"{color}_{n}")
        deck += [f"{color}_skip", f"{color}_reverse", f"{color}_draw2"]
    deck += ["wild", "wild_draw"] * 4
    return deck


def render_hand_image(cards: list[str]) -> Image.Image:
    card_width, card_height = 120, 180
    gap = 10
    margin = 14
    width = max(1, len(cards)) * card_width + max(0, len(cards) - 1) * gap + margin * 2
    height = card_height + margin * 2
    img = Image.new("RGBA", (width, height), (32, 36, 45, 255))

    for i, card in enumerate(cards):
        path = f"assets/uno/{card}.png"
        card_img = None
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                card_img = Image.open(path).convert("RGBA").resize((card_width, card_height))
            except Exception:
                card_img = None

        if card_img is None:
            card_img = draw_uno_card(card, card_width, card_height)
        img.paste(card_img, (margin + i * (card_width + gap), margin), card_img)

    return img


def generate_hand_file(cards: list[str], filename: str = "hand.png") -> discord.File:
    buffer = BytesIO()
    render_hand_image(cards).save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


def generate_card_file(card: str, filename: str = "uno_top.png") -> discord.File:
    image = draw_uno_card(card, 180, 270)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


def uno_public_text(state: dict, prefix: str = "") -> str:
    top = state.get("top") or "なし"
    lines = []
    if prefix:
        lines.append(prefix)
    lines.extend(
        [
            "**UNO**",
            f"場のカード: **{top}**",
            "現在のターン: 参加者のDMに送信済み",
            "手札と操作パネルはターンの人のDMに送られます。",
        ]
    )
    return "\n".join(lines)


async def send_uno_channel_update(bot, game_id: str, state: dict, prefix: str = "", include_top: bool = True):
    channel_id = int(state.get("channel_id") or game_id)
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return
    kwargs = {}
    if include_top and state.get("top"):
        kwargs["file"] = generate_card_file(state["top"])
    await channel.send(
        uno_public_text(state, prefix) if include_top else prefix,
        allowed_mentions=discord.AllowedMentions.none(),
        **kwargs,
    )


async def send_uno_hand_dm(bot, state: dict, game_id: str, user_id: int):
    guild = bot.get_guild(int(state.get("guild_id") or 0)) if state.get("guild_id") else None
    member = guild.get_member(user_id) if guild else bot.get_user(user_id)
    if not member:
        try:
            member = await bot.fetch_user(user_id)
        except Exception:
            member = None
    if not member:
        return False
    hand = state["hands"].get(user_id) or state["hands"].get(str(user_id), [])
    try:
        await member.send(
            f"あなたのターンです。場のカード: **{state.get('top')}**",
            file=generate_hand_file(hand),
            view=UnoHandView(game_id, user_id, hand),
        )
        return True
    except Exception:
        return False


async def send_uno_turn(bot, game_id: str, state: dict, prefix: str = ""):
    await send_uno_channel_update(bot, game_id, state, prefix)
    current = state["players"][state.get("turn_index", 0)]
    ok = await send_uno_hand_dm(bot, state, game_id, current)
    if not ok:
        await send_uno_channel_update(bot, game_id, state, f"⚠️ <@{current}> へのDM送信に失敗しました。DMを受信できる状態にしてください。", include_top=False)


async def send_uno_challenge_dm(bot, state: dict, game_id: str, attacker_id: int, defender_id: int):
    guild = bot.get_guild(int(state.get("guild_id") or 0)) if state.get("guild_id") else None
    member = guild.get_member(defender_id) if guild else bot.get_user(defender_id)
    if not member:
        try:
            member = await bot.fetch_user(defender_id)
        except Exception:
            member = None
    if not member:
        return False
    try:
        await member.send(
            f"<@{attacker_id}> がワイルドドロー4を出しました。チャレンジしますか？",
            view=ChallengeView(game_id, attacker_id, defender_id),
        )
        return True
    except Exception:
        await send_uno_channel_update(bot, game_id, state, f"⚠️ <@{defender_id}> へのDM送信に失敗しました。", include_top=False)
        return False


def draw_uno_card(card: str, width: int, height: int) -> Image.Image:
    color_map = {
        "red": (219, 58, 52),
        "yellow": (242, 198, 65),
        "green": (56, 156, 85),
        "blue": (54, 116, 204),
        "wild": (34, 34, 40),
    }
    label_map = {
        "skip": "SKIP",
        "reverse": "↺",
        "draw2": "+2",
        "draw": "+2",
        "wild": "WILD",
        "wild_draw": "+4",
        "wild_draw4": "+4",
    }

    parts = card.split("_")
    color = parts[0] if parts[0] in color_map else "wild"
    value = "_".join(parts[1:]) if len(parts) > 1 else card
    if card.startswith("wild"):
        color = "wild"
        value = card

    bg = color_map[color]
    text = label_map.get(value, label_map.get(card, value.upper()))
    if value.isdigit():
        text = value

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=14, fill=(245, 245, 245), outline=(20, 20, 20), width=3)
    draw.rounded_rectangle((8, 8, width - 9, height - 9), radius=11, fill=bg)
    draw.ellipse((20, 40, width - 20, height - 40), fill=(245, 245, 245))

    if color == "wild":
        quadrants = [
            ((22, 42, width // 2, height // 2), color_map["red"]),
            ((width // 2, 42, width - 22, height // 2), color_map["yellow"]),
            ((22, height // 2, width // 2, height - 42), color_map["green"]),
            ((width // 2, height // 2, width - 22, height - 42), color_map["blue"]),
        ]
        for box, fill in quadrants:
            draw.pieslice(box, 0, 360, fill=fill)

    big_font = ImageFont.load_default()
    small_font = ImageFont.load_default()
    try:
        big_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
        small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except Exception:
        pass

    text_color = (20, 20, 20) if color == "yellow" else (255, 255, 255)
    center_color = (20, 20, 20)
    draw.text((12, 12), text, fill=text_color, font=small_font)
    bbox = draw.textbbox((0, 0), text, font=big_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((width - tw) / 2, (height - th) / 2 - 2), text, fill=center_color, font=big_font)
    draw.text((width - 12, height - 12), text, fill=text_color, font=small_font, anchor="rd")
    return image


def can_play(card: str, top: str) -> bool:
    if card.startswith("wild"):
        return True
    c_color, c_val = card.split("_", 1)
    if top.startswith("wild_"):
        chosen_color = top.split("_", 1)[1]
        return c_color == chosen_color
    t_color, t_val = top.split("_", 1)
    return c_color == t_color or c_val == t_val


def refill_deck(deck: list, discard: list) -> tuple[list, list]:
    if len(discard) <= 1:
        return deck, discard
    top = discard[-1]
    new_deck = discard[:-1]
    random.shuffle(new_deck)
    return new_deck, [top]


async def handle_draw_card(interaction: discord.Interaction, game_id: str, user_id: int):
    """山札から1枚引く"""
    state = await get_uno_game_state(interaction.client, game_id, interaction.guild_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return
    state = normalize_uno_state(state)
    user_id = int(user_id)

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    turn_index = state["turn_index"]
    current_player_id = int(players[turn_index])

    if int(interaction.user.id) != user_id:
        await interaction.response.send_message(
            "❌ この手札パネルはあなた用ではありません。", ephemeral=True
        )
        return

    if int(interaction.user.id) != current_player_id:
        await interaction.response.send_message(
            f"❌ あなたのターンではありません。現在のターンは <@{current_player_id}> です。", ephemeral=True
        )
        return

    if len(deck) == 0:
        deck, state["discard"] = refill_deck(deck, state["discard"])

    if deck:
        drawn = deck.pop()
        hands[current_player_id].append(drawn)
        state["deck"] = deck
        state["hands"] = hands
        await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)

    await interaction.response.edit_message(
        content="🃏 山札から1枚引きました。",
        view=None,
        attachments=[],
    )
    await send_uno_channel_update(interaction.client, game_id, state, f"🃏 <@{current_player_id}> が山札から1枚引きました。")
    await send_uno_hand_dm(interaction.client, state, game_id, current_player_id)


async def start_uno_game(interaction: discord.Interaction, game_id: str | None = None):
    game_id = game_id or str(interaction.channel_id)

    if game_id not in uno_games:
        await interaction.response.send_message("❌ まず `/uno_start` を実行してください。", ephemeral=True)
        return

    state = uno_games[game_id]
    state = normalize_uno_state(state)
    if state.get("hands"):
        await interaction.response.send_message("❌ このUNOゲームはすでに開始しています。", ephemeral=True)
        return
    if len(state["players"]) < 2:
        await interaction.response.send_message("❌ 2人以上必要です。", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    deck = generate_deck()
    random.shuffle(deck)
    hands = {uid: [deck.pop() for _ in range(7)] for uid in state["players"]}
    top = deck.pop()
    while top.startswith("wild") and deck:
        deck.insert(0, top)
        random.shuffle(deck)
        top = deck.pop()
    state.update({
        "channel_id": state.get("channel_id") or interaction.channel_id,
        "deck": deck,
        "hands": hands,
        "discard": [top],
        "top": top,
        "turn_index": 0,
        "direction": 1,
        "uno_declared": False,
        "pending": None,
    })
    await save_uno_game(interaction.guild_id or state.get("guild_id"), game_id, state)

    failed_dm: list[str] = []
    for user_id in state["players"]:
        if user_id == state["players"][0]:
            continue
        member = interaction.guild.get_member(user_id) if interaction.guild else None
        if member:
            try:
                await member.send(
                    "あなたのUNOの手札です。ターンが来たら操作パネルを送ります。",
                    file=generate_hand_file(hands[user_id]),
                )
            except Exception:
                failed_dm.append(member.mention)

    first_player = state["players"][0]
    followup_text = f"🎮 UNO開始！\n最初のカード：**{top}**\n最初のターンの人にDMを送りました。"
    if failed_dm:
        followup_text += "\n\n⚠️ DM送信に失敗したプレイヤーがあります。DMを受信できる状態にしてください。\n"
        followup_text += " " + " ".join(failed_dm)

    await interaction.followup.send(
        followup_text,
        file=generate_card_file(top),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if not await send_uno_hand_dm(interaction.client, state, game_id, first_player):
        await send_uno_channel_update(
            interaction.client,
            game_id,
            state,
            "⚠️ ターンの人へのDM送信に失敗しました。参加者はDMを受信できる状態にしてください。",
            include_top=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Uno(bot))
