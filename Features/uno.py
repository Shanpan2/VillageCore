import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import random
import os

from views.uno_views import (
    UnoHandView,
    WildColorSelectView,
    UnoDeclareView,
    ChallengeView,
)


# UNO ゲーム状態（メモリ管理）
uno_games: dict[str, dict] = {}


class Uno(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------
    # /uno_start
    # -------------------------------------------------------
    @app_commands.command(name="uno_start", description="UNOゲームを作成します")
    @app_commands.describe(challenge="ワイルドドロー4のチャレンジ機能を有効にするか？")
    async def uno_start(self, interaction: discord.Interaction, challenge: bool = True):
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
            "challenge_mode": challenge,
        }

        await interaction.response.send_message(
            f"🎮 UNOゲームを作成しました！\n"
            f"`/uno_join` で参加してください。\n"
            f"チャレンジ機能：**{'ON' if challenge else 'OFF'}**"
        )

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
        await interaction.response.send_message(
            f"🙌 {interaction.user.mention} が参加しました！"
        )

    # -------------------------------------------------------
    # /uno_begin
    # -------------------------------------------------------
    @app_commands.command(name="uno_begin", description="UNOゲームを開始します")
    async def uno_begin(self, interaction: discord.Interaction):
        game_id = str(interaction.channel_id)

        if game_id not in uno_games:
            await interaction.response.send_message(
                "❌ まず `/uno_start` を実行してください。", ephemeral=True
            )
            return

        state = uno_games[game_id]

        if len(state["players"]) < 2:
            await interaction.response.send_message(
                "❌ 2人以上必要です。", ephemeral=True
            )
            return

        # ★ DM送信・画像生成で時間がかかるため先にdefer
        await interaction.response.defer()

        deck = generate_deck()
        random.shuffle(deck)

        hands = {uid: [deck.pop() for _ in range(7)] for uid in state["players"]}
        top = deck.pop()

        state.update({
            "deck": deck,
            "hands": hands,
            "discard": [top],
            "top": top,
            "turn_index": 0,
            "direction": 1,
            "uno_declared": False,
        })

        # 手札画像をDM送信
        failed_dm: list[str] = []
        for user_id in state["players"]:
            path = generate_hand_image(hands[user_id])
            file = discord.File(path, filename="hand.png")
            member = interaction.guild.get_member(user_id)
            if member:
                try:
                    await member.send(file=file)
                except Exception:
                    failed_dm.append(member.mention)

        first_player = state["players"][0]
        followup_text = (
            f"🎮 UNO開始！\n最初のカード：**{top}**\n最初のターン：<@{first_player}>"
        )
        if failed_dm:
            followup_text += "\n\n⚠️ DM送信に失敗したプレイヤーがあります。DMを受信できる状態にしてください。\n"
            followup_text += " " + " ".join(failed_dm)

        await interaction.followup.send(
            followup_text,
            view=UnoHandView(game_id, first_player, hands[first_player]),
        )


# ============================================================
# views から呼び出すハンドラ群
# ============================================================

async def handle_play_card(
    interaction: discord.Interaction, game_id: str, button_user_id: int, card: str
):
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

    if interaction.user.id != current_player_id:
        await interaction.response.send_message(
            "❌ あなたのターンではありません。", ephemeral=True
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
        await interaction.response.edit_message(
            content=f"🎨 <@{current_player_id}> が **{card}** を出しました。\n色を選んでください。",
            view=WildColorSelectView(game_id, current_player_id, card),
        )
        return

    hands[current_player_id].remove(card)
    discard.append(card)
    state["top"] = card

    # UNO宣言チェック（残り1枚）
    if len(hands[current_player_id]) == 1:
        await interaction.response.edit_message(
            content=f"⚠️ <@{current_player_id}> の手札が残り1枚です❗ UNO を宣言してください!!",
            view=UnoDeclareView(game_id, current_player_id),
        )
        return

    # 勝利判定
    if len(hands[current_player_id]) == 0:
        await interaction.response.edit_message(
            content=f"🎉 <@{current_player_id}> の勝利!!", view=None
        )
        uno_games.pop(game_id, None)
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

    if len(deck) == 0:
        deck, discard = refill_deck(deck, discard)

    state.update({"turn_index": turn_index, "hands": hands, "deck": deck, "discard": discard})
    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"🃏 <@{current_player_id}> が **{card}** を出しました。\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id]),
    )


async def handle_wild_color_select(
    interaction: discord.Interaction,
    game_id: str,
    user_id: int,
    card: str,
    color: str,
):
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
        await interaction.response.send_message(
            "❌ あなたのターンではありません。", ephemeral=True
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
            await interaction.response.edit_message(
                content=f"🃏 <@{current_player_id}> が **ワイルドドロー4** を出しました！\n"
                        f"<@{next_player}> はチャレンジしますか？",
                view=ChallengeView(game_id, current_player_id, next_player),
            )
            return

        if len(deck) < 4:
            deck, discard = refill_deck(deck, discard)
        for _ in range(4):
            if deck:
                hands[next_player].append(deck.pop())
        turn_index = (turn_index + direction * 2) % len(players)
    else:
        turn_index = (turn_index + direction) % len(players)

    state.update({"hands": hands, "deck": deck, "turn_index": turn_index})
    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"🎨 色は **{color}** に変更されました！\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id]),
    )


async def handle_challenge(
    interaction: discord.Interaction,
    game_id: str,
    attacker_id: int,
    defender_id: int,
):
    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    hands = state["hands"]
    deck = state["deck"]
    players = state["players"]
    turn_index = state["turn_index"]
    direction = state["direction"]

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
    state.update({"hands": hands, "deck": deck, "turn_index": turn_index})
    next_player_id = players[turn_index]

    await interaction.response.edit_message(
        content=f"{result}\n次のターン：<@{next_player_id}>",
        view=UnoHandView(game_id, next_player_id, hands[next_player_id]),
    )


async def handle_uno_declare(
    interaction: discord.Interaction, game_id: str, user_id: int
):
    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    if interaction.user.id != user_id:
        await interaction.response.send_message(
            "❌ あなたは UNO を宣言できません。", ephemeral=True
        )
        return

    if len(state["hands"][user_id]) != 1:
        await interaction.response.send_message(
            "❌ 今は UNO を宣言できません。", ephemeral=True
        )
        return

    state["uno_declared"] = True
    await interaction.response.edit_message(
        content=f"🎉 <@{user_id}> が **UNO！** を宣言しました！", view=None
    )


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


def generate_hand_image(cards: list[str]) -> str:
    card_width, card_height = 150, 220
    img = Image.new("RGBA", (card_width * len(cards), card_height), (0, 0, 0, 0))

    for i, card in enumerate(cards):
        path = f"assets/uno/{card}.png"
        if os.path.exists(path):
            card_img = Image.open(path).resize((card_width, card_height))
        else:
            card_img = Image.new("RGBA", (card_width, card_height), (255, 255, 255, 255))
            draw = ImageDraw.Draw(card_img)
            font = ImageFont.load_default()
            draw.text((10, 80), card, fill=(0, 0, 0), font=font)
        img.paste(card_img, (i * card_width, 0), card_img)

    out = "uno_hand.png"
    img.save(out)
    return out


def can_play(card: str, top: str) -> bool:
    if card.startswith("wild"):
        return True
    c_color, c_val = card.split("_", 1)
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
    state = uno_games.get(game_id)
    if not state:
        await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
        return

    players = state["players"]
    hands = state["hands"]
    deck = state["deck"]
    turn_index = state["turn_index"]
    current_player_id = players[turn_index]

    if interaction.user.id != current_player_id:
        await interaction.response.send_message(
            "❌ あなたのターンではありません。", ephemeral=True
        )
        return

    if len(deck) == 0:
        deck, state["discard"] = refill_deck(deck, state["discard"])

    if deck:
        drawn = deck.pop()
        hands[current_player_id].append(drawn)
        state["deck"] = deck

    await interaction.response.edit_message(
        content=f"🃏 <@{current_player_id}> が山札から1枚引きました。",
        view=UnoHandView(game_id, current_player_id, hands[current_player_id]),
    )


async def setup(bot: commands.Bot):
    await bot.add_cog(Uno(bot))
