# views/uno_views.py

import discord

from Features.uno import (
    handle_play_card,
    handle_wild_color_select,
    handle_uno_declare,
    handle_challenge
)


# ============================================================
# 🎴 手札ボタン
# ============================================================

class UnoHandView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int, hand: list[str]):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.user_id = user_id

        for card in hand:
            self.add_item(UnoCardButton(game_id, user_id, card))


class UnoCardButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int, card: str):
        super().__init__(
            label=card,
            style=discord.ButtonStyle.primary,
            custom_id=f"uno_play_{game_id}_{user_id}_{card}"
        )
        self.game_id = game_id
        self.user_id = user_id
        self.card = card

    async def callback(self, interaction: discord.Interaction):
        await handle_play_card(
            interaction,
            self.game_id,
            self.user_id,
            self.card
        )


# ============================================================
# 🎨 ワイルド色選択
# ============================================================

class WildColorSelectView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int, card: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.user_id = user_id
        self.card = card

        colors = {
            "red": "🔴 赤",
            "yellow": "🟡 黄",
            "green": "🟢 緑",
            "blue": "🔵 青"
        }

        for color, label in colors.items():
            self.add_item(WildColorButton(game_id, user_id, card, color, label))


class WildColorButton(discord.ui.Button):
    def __init__(self, game_id, user_id, card, color, label):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=f"uno_color_{game_id}_{user_id}_{card}_{color}"
        )
        self.game_id = game_id
        self.user_id = user_id
        self.card = card
        self.color = color

    async def callback(self, interaction: discord.Interaction):
        await handle_wild_color_select(
            interaction,
            self.game_id,
            self.user_id,
            self.card,
            self.color
        )


# ============================================================
# 🔔 UNO 宣言
# ============================================================

class UnoDeclareButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="UNO!",
            style=discord.ButtonStyle.danger,
            custom_id=f"uno_declare_{game_id}_{user_id}"
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await handle_uno_declare(interaction, self.game_id, self.user_id)


class UnoDeclareView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        self.add_item(UnoDeclareButton(game_id, user_id))


# ============================================================
# 🃏 チャレンジ（ワイルドドロー4）
# ============================================================

class ChallengeView(discord.ui.View):
    def __init__(self, game_id: str, attacker_id: int, defender_id: int):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.attacker_id = attacker_id
        self.defender_id = defender_id

        self.add_item(ChallengeYesButton(game_id, attacker_id, defender_id))
        self.add_item(ChallengeNoButton(game_id, attacker_id, defender_id))


class ChallengeYesButton(discord.ui.Button):
    def __init__(self, game_id, attacker_id, defender_id):
        super().__init__(
            label="チャレンジする",
            style=discord.ButtonStyle.danger,
            custom_id=f"uno_challenge_yes_{game_id}"
        )
        self.game_id = game_id
        self.attacker_id = attacker_id
        self.defender_id = defender_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.defender_id:
            await interaction.response.send_message("❌ あなたはチャレンジできません。", ephemeral=True)
            return

        await handle_challenge(
            interaction,
            self.game_id,
            self.attacker_id,
            self.defender_id
        )


class ChallengeNoButton(discord.ui.Button):
    def __init__(self, game_id, attacker_id, defender_id):
        super().__init__(
            label="チャレンジしない",
            style=discord.ButtonStyle.secondary,
            custom_id=f"uno_challenge_no_{game_id}"
        )
        self.game_id = game_id
        self.attacker_id = attacker_id
        self.defender_id = defender_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.defender_id:
            await interaction.response.send_message("❌ あなたは選択できません。", ephemeral=True)
            return

        # チャレンジしない → 無条件で4枚ドロー
        from Features.uno import uno_games, refill_deck

        state = uno_games[self.game_id]
        deck = state["deck"]
        hands = state["hands"]
        players = state["players"]
        turn_index = state["turn_index"]
        direction = state["direction"]

        next_index = (turn_index + direction) % len(players)
        next_player = players[next_index]

        if len(deck) < 4:
            deck, _ = refill_deck(deck, state["discard"])

        for _ in range(4):
            if deck:
                hands[next_player].append(deck.pop())

        # ターン進行
        turn_index = (turn_index + direction) % len(players)
        turn_index = (turn_index + direction) % len(players)

        state["turn_index"] = turn_index

        next_player_id = players[turn_index]

        await interaction.response.edit_message(
            content=f"🃏 チャレンジしませんでした。\n<@{next_player}> が 4 枚引きます。\n次のターン：<@{next_player_id}>",
            view=UnoHandView(self.game_id, next_player_id, hands[next_player_id])
        )
