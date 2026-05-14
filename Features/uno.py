# features/uno.py

import discord
from discord.ext import commands
from discord import app_commands
import random
import os

from views.uno_views import (
    UnoHandView,
    WildColorSelectView,
    UnoDeclareView,
    ChallengeView
)

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# UNO ゲーム状態（メモリ管理）
# ============================================================

uno_games = {}   # game_id → state


# ============================================================
# UNO ゲームセットアップ
# ============================================================

def setup_uno(bot: commands.Bot):

    # ---------------------------
    # /uno_start
    # ---------------------------
    @bot.tree.command(name="uno_start", description="UNOゲームを作成します")
    @app_commands.describe(
        challenge="ワイルドドロー4のチャレンジ機能を有効にするか？（true/false）"
    )
    async def uno_start(interaction: discord.Interaction, challenge: bool = True):

        game_id = str(interaction.channel_id)

        uno_games[game_id] = {
            "players": [],
            "hands": {},
            "deck": [],
            "discard": [],
            "turn_index": 0,
            "direction": 1,
            "top": None,
            "uno_declared": False,
            "challenge_mode": challenge
        }

        await interaction.response.send_message(
            f"🎮 UNOゲームを作成しました！\n"
            f"`/uno_join` で参加してください。\n"
            f"チャレンジ機能：**{'ON' if challenge else 'OFF'}**"
        )

    # ---------------------------
    # /uno_join
    # ---------------------------
    @bot.tree.command(name="uno_join", description="UNOゲームに参加します")
    async def uno_join(interaction: discord.Interaction):

        game_id = str(interaction.channel_id)

        if game_id not in uno_games:
            await interaction.response.send_message("❌ まず `/uno_start` を実行してください。", ephemeral=True)
            return

        state = uno_games[game_id]
        user_id = interaction.user.id

        if user_id in state["players"]:
            await interaction.response.send_message("❌ すでに参加しています。", ephemeral=True)
            return

        state["players"].append(user_id)

        await interaction.response.send_message(
            f"🙌 {interaction.user.mention} が参加しました！"
        )

    # ---------------------------
    # /uno_begin
    # ---------------------------
    @bot.tree.command(name="uno_begin", description="UNOゲームを開始します")
    async def uno_begin(interaction: discord.Interaction):

        game_id = str(interaction.channel_id)

        if game_id not in uno_games:
            await interaction.response.send_message("❌ まず `/uno_start` を実行してください。", ephemeral=True)
            return

        state = uno_games[game_id]

        if len(state["players"]) < 2:
            await interaction.response.send_message("❌ 2人以上必要です。", ephemeral=True)
            return

        # 山札生成
        deck = generate_deck()
        random.shuffle(deck)

        # 手札配布
        hands = {}
        for user_id in state["players"]:
            hands[user_id] = [deck.pop() for _ in range(7)]

        # 場札
        top = deck.pop()

        state["deck"] = deck
        state["hands"] = hands
        state["discard"] = [top]
        state["top"] = top
        state["turn_index"] = 0
        state["direction"] = 1
        state["uno_declared"] = False

        # 手札画像を DM 送信
        for user_id in state["players"]:
            path = generate_hand_image(hands[user_id])
            file = discord.File(path, filename="hand.png")
            user = interaction.guild.get_member(user_id)
            await user.send(file=file)

        first_player = state["players"][0]

        await interaction.response.send_message(
            f"🎮 UNO開始！\n最初のカード：**{top}**\n最初のターン：<@{first_player}>",
            view=UnoHandView(game_id, first_player, hands[first_player])
        )


# ============================================================
# 山札生成
# ============================================================

def generate_deck():
    colors = ["red", "yellow", "green", "blue"]
    deck = []

    for color in colors:
        for n in range(10):
            deck.append(f"{color}_{n}")

        deck += [
            f"{color}_skip",
            f"{color}_reverse",
            f"{color}_draw2"
        ]

    deck += ["wild", "wild_draw"] * 4

    return deck


# ============================================================
# 手札画像生成
# ============================================================

def generate_hand_image(cards):
    card_width = 150
    card_height = 220

    img = Image.new("RGBA", (card_width * len(cards), card_height), (0, 0, 0, 0))

    for i, card in enumerate(cards):
        path = f"assets/uno/{card}.png"
        if os.path.exists(path):
            card_img = Image.open(path).resize((card_width, card_height))
        else:
            card_img = Image.new("RGBA", (card_width, card_height), (255, 255, 255, 255))
            draw = ImageDraw.Draw(card_img)
            font = ImageFont.truetype("assets/meigen/font.ttf", 40)
            draw.text((10, 80), card, fill=(0,0,0), font=font)

        img.paste(card_img, (i * card_width, 0), card_img)

    out = "uno_hand.png"
    img.save(out)
    return out


# ============================================================
# 🎴 カードを出す
# ============================================================

async def handle_play_card(interaction, game_id, button_user_id, card):

    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    discard = state["discard"]
    top = state["top"]
    turn_index = state["turn_index"]
    direction = state["direction"]

    current_player_id = players[turn_index]

    # ターンチェック
    if interaction.user.id != current_player_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    # 手札チェック
    if card not in hands[current_player_id]:
        await interaction.response.send_message("❌ そのカードはあなたの手札にありません。", ephemeral=True)
        return

    # 出せるか判定
    if not can_play(card, top):
        await interaction.response.send_message("❌ そのカードは現在の場に出せません。", ephemeral=True)
        return

    # ---------------------------
    # ★ ワイルド系は色選択へ
    # ---------------------------
    if card.startswith("wild"):
        await interaction.response.edit_message(
            content=f"🎨 <@{current_player_id}> が **{card}** を出しました。\n色を選んでください。",
            view=WildColorSelectView(game_id, current_player_id, card)
        )
        return

    # ---------------------------
    # ★ カードを出す
    # ---------------------------
    hands[current_player_id].remove(card)
    discard.append(card)
    state["top"] = card

    # ---------------------------
    # ★ UNO 宣言チェック
    # ---------------------------
    if len(hands[current_player_id]) == 1:
        await interaction.response.edit_message(
            content=f"⚠️ <@{current_player_id}> の手札が残り1枚です❗ UNO を宣言してください!!",
            view=UnoDeclareView(game_id, current_player_id)
        )
        return

    # ---------------------------
    # ★ 勝利判定
    # ---------------------------
    if len(hands[current_player_id]) == 0:
        await interaction.response.edit_message(
            content=f"🎉 <@{current_player_id}> の勝利!!",
            view=None
        )
        uno_games.pop(game_id, None)
        return

    # ---------------------------
    # ★ 効果処理
    # ---------------------------
    effect = None
    if card.endswith("skip"):
        effect = "skip"
    elif card.endswith("reverse"):
        effect = "reverse"
    elif card.endswith("draw2"):
        effect = "draw2"

    if effect == "skip":
        turn_index = (turn_index + direction) % len(players)
        turn_index = (turn_index + direction) % len(players)

    elif effect == "reverse":
        direction *= -1
        state["direction"] = direction
        if len(players) == 2:
            turn_index = (turn_index + direction) % len(players)

    elif effect == "draw2":
        next_index = (turn_index + direction) % len(players)
        next_player = players[next_index]

        if len(deck) < 2:
            deck, discard = refill_deck(deck, discard)

        for _ in range(2):
            if deck:
                hands[next_player].append(deck.pop())

        turn_index = (turn_index + direction) % len(players)
        turn_index = (turn_index + direction) % len(players)

    else:
        turn_index = (turn_index + direction) % len(players)

    # UNO 宣言忘れペナルティ
    if len(hands[current_player_id]) == 1:
        if not state.get("uno_declared", False):
            for _ in range(2):
                if deck:
                    hands[current_player_id].append(deck.pop())

    state["uno_declared"] = False

    # 山札補充
    if len(deck) == 0:
        deck, discard = refill_deck(deck, discard)

    state["turn_index"] = turn_index
    state["hands"] = hands
    state["deck"] = deck
    state["discard"] = discard

    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"🃏 <@{current_player_id}> が **{card}** を出しました。\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id])
    )


# ============================================================
# 🎨 ワイルド色選択
# ============================================================

async def handle_wild_color_select(interaction, game_id, user_id, card, color):

    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    discard = state["discard"]
    turn_index = state["turn_index"]
    direction = state["direction"]

    current_player_id = players[turn_index]

    if interaction.user.id != current_player_id:
        await interaction.response.send_message("❌ あなたのターンではありません。", ephemeral=True)
        return

    new_card = f"wild_{color}"

    hands[current_player_id].remove(card)
    discard.append(new_card)
    state["top"] = new_card

    # ---------------------------
    # ★ ワイルドドロー4
    # ---------------------------
    if card.startswith("wild_draw"):

        next_index = (turn_index + direction) % len(players)
        next_player = players[next_index]

        # チャレンジ機能 ON の場合
        if state["challenge_mode"]:
            await interaction.response.edit_message(
                content=f"🃏 <@{current_player_id}> が **ワイルドドロー4** を出しました！\n"
                        f"<@{next_player}> はチャレンジしますか？",
                view=ChallengeView(game_id, current_player_id, next_player)
            )
            return

        # チャレンジ OFF → 無条件で4枚
        if len(deck) < 4:
            deck, discard = refill_deck(deck, discard)

        for _ in range(4):
            if deck:
                hands[next_player].append(deck.pop())

        turn_index = (turn_index + direction) % len(players)
        turn_index = (turn_index + direction) % len(players)

    else:
        turn_index = (turn_index + direction) % len(players)

    state["hands"] = hands
    state["deck"] = deck
    state["turn_index"] = turn_index

    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"🎨 色は **{color}** に変更されました！\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id])
    )


# ============================================================
# 🎴 出せるか判定
# ============================================================

def can_play(card, top):
    if card.startswith("wild"):
        return True

    c_color, c_val = card.split("_")
    t_color, t_val = top.split("_")

    return c_color == t_color or c_val == t_val


# ============================================================
# 🃏 チャレンジ処理
# ============================================================

async def handle_challenge(interaction, game_id, attacker_id, defender_id):

    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    hands = state["hands"]
    deck = state["deck"]
    players = state["players"]
    turn_index = state["turn_index"]
    direction = state["direction"]

    defender_hand = hands[attacker_id]

    # 出せるカードがあったら → チャレンジ成功
    top_color = state["top"].split("_")[1]

    can_play_other = any(
        (not c.startswith("wild")) and c.split("_")[0] == top_color
        for c in defender_hand
    )

    next_index = (turn_index + direction) % len(players)
    next_player = players[next_index]

    if can_play_other:
        # チャレンジ成功 → 出した側が4枚
        if len(deck) < 4:
            deck, _ = refill_deck(deck, state["discard"])

        for _ in range(4):
            if deck:
                hands[attacker_id].append(deck.pop())

        result = f"🎉 チャレンジ成功！\n<@{attacker_id}> が 4 枚引きます。"

    else:
        # チャレンジ失敗 → チャレンジ側が6枚
        if len(deck) < 6:
            deck, _ = refill_deck(deck, state["discard"])

        for _ in range(6):
            if deck:
                hands[defender_id].append(deck.pop())

        result = f"💥 チャレンジ失敗！\n<@{defender_id}> が 6 枚引きます。"

    # ターン進行
    turn_index = (turn_index + direction) % len(players)
    turn_index = (turn_index + direction) % len(players)

    state["hands"] = hands
    state["deck"] = deck
    state["turn_index"] = turn_index

    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"{result}\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id])
    )


# ============================================================
# 山札補充
# ============================================================

def refill_deck(deck, discard):
    if len(discard) <= 1:
        return deck, discard

    top = discard[-1]
    new_deck = discard[:-1]
    random.shuffle(new_deck)

    return new_deck, [top]


# ============================================================
# UNO 宣言
# ============================================================

async def handle_uno_declare(interaction, game_id, user_id):

    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    hands = state["hands"]

    if interaction.user.id != user_id:
        await interaction.response.send_message("❌ あなたは UNO を宣言できません。", ephemeral=True)
        return

    if len(hands[user_id]) != 1:
        await interaction.response.send_message("❌ 今は UNO を宣言できません。", ephemeral=True)
        return

    state["uno_declared"] = True

    await interaction.response.edit_message(
        content=f"🎉 <@{user_id}> が **UNO！** を宣言しました！",
        view=None
    )
