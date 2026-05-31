# views/uno_views.py

import discord


# Discord のボタンは1メッセージ最大25個のため、手札が多いとボタンが溢れる。
# → 手札をセレクトメニュー（最大25択）で選ぶ方式に変更。
# ※ UNO の手札が25枚を超えるケースは稀だが、超えた場合は先頭25枚を表示。


# ============================================================
# 🎴 手札セレクトメニュー
# ============================================================

class UnoHandView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int, hand: list[str]):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.user_id = user_id
        self.add_item(UnoCardSelect(game_id, user_id, hand))
        self.add_item(UnoDrawButton(game_id, user_id))
        self.add_item(UnoSurrenderButton(game_id, user_id))


class UnoCardSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, hand: list[str]):
        # 25枚超えはセレクト上限のため先頭25枚に絞る
        display = hand[:25]
        options = [
            discord.SelectOption(label=card, value=card)
            for card in display
        ]
        super().__init__(
            placeholder="カードを選んで出す",
            options=options,
            custom_id=f"uno_select_{game_id}_{user_id}",
            row=0,
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        from Features.uno import handle_play_card
        await handle_play_card(
            interaction,
            self.game_id,
            self.user_id,
            self.values[0],
        )


class UnoDrawButton(discord.ui.Button):
    """山札から1枚引く"""
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="🃏 山札から引く",
            style=discord.ButtonStyle.secondary,
            custom_id=f"uno_draw_{game_id}_{user_id}",
            row=1,
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        from Features.uno import handle_draw_card
        await handle_draw_card(interaction, self.game_id, self.user_id)


class UnoSurrenderButton(discord.ui.Button):
    """降参してゲームを終了する"""
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="⚔️ 降参",
            style=discord.ButtonStyle.danger,
            custom_id=f"uno_surrender_{game_id}_{user_id}",
            row=2,
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        from Features.uno import handle_uno_surrender
        await handle_uno_surrender(interaction, self.game_id, self.user_id)


# ============================================================
# 🎨 ワイルド色選択
# ============================================================

class WildColorSelectView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int, card: str):
        super().__init__(timeout=None)
        self.add_item(WildColorSelect(game_id, user_id, card))


class WildColorSelect(discord.ui.Select):
    def __init__(self, game_id: str, user_id: int, card: str):
        options = [
            discord.SelectOption(label="🔴 赤", value="red"),
            discord.SelectOption(label="🟡 黄", value="yellow"),
            discord.SelectOption(label="🟢 緑", value="green"),
            discord.SelectOption(label="🔵 青", value="blue"),
        ]
        super().__init__(
            placeholder="色を選択してください",
            options=options,
            custom_id=f"uno_color_{game_id}_{user_id}_{card}",
            row=0,
        )
        self.game_id = game_id
        self.user_id = user_id
        self.card = card

    async def callback(self, interaction: discord.Interaction):
        from Features.uno import handle_wild_color_select
        await handle_wild_color_select(
            interaction,
            self.game_id,
            self.user_id,
            self.card,
            self.values[0],
        )


# ============================================================
# 🔔 UNO 宣言
# ============================================================

class UnoDeclareView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        self.add_item(UnoDeclareButton(game_id, user_id))


class UnoDeclareButton(discord.ui.Button):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(
            label="UNO!",
            style=discord.ButtonStyle.danger,
            custom_id=f"uno_declare_{game_id}_{user_id}",
            row=0,
        )
        self.game_id = game_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        from Features.uno import handle_uno_declare
        await handle_uno_declare(interaction, self.game_id, self.user_id)


# ============================================================
# 🃏 チャレンジ（ワイルドドロー4）
# ============================================================

class ChallengeView(discord.ui.View):
    def __init__(self, game_id: str, attacker_id: int, defender_id: int):
        super().__init__(timeout=None)
        self.add_item(ChallengeYesButton(game_id, attacker_id, defender_id))
        self.add_item(ChallengeNoButton(game_id, attacker_id, defender_id))


class ChallengeYesButton(discord.ui.Button):
    def __init__(self, game_id: str, attacker_id: int, defender_id: int):
        super().__init__(
            label="チャレンジする",
            style=discord.ButtonStyle.danger,
            custom_id=f"uno_challenge_yes_{game_id}",
            row=0,
        )
        self.game_id = game_id
        self.attacker_id = attacker_id
        self.defender_id = defender_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.defender_id:
            await interaction.response.send_message(
                "❌ あなたはチャレンジできません。", ephemeral=True
            )
            return

        from Features.uno import handle_challenge
        await handle_challenge(
            interaction, self.game_id, self.attacker_id, self.defender_id
        )


class ChallengeNoButton(discord.ui.Button):
    def __init__(self, game_id: str, attacker_id: int, defender_id: int):
        super().__init__(
            label="チャレンジしない",
            style=discord.ButtonStyle.secondary,
            custom_id=f"uno_challenge_no_{game_id}",
            row=0,
        )
        self.game_id = game_id
        self.attacker_id = attacker_id
        self.defender_id = defender_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.defender_id:
            await interaction.response.send_message(
                "❌ あなたは選択できません。", ephemeral=True
            )
            return

        from Features.uno import save_uno_game, uno_games, refill_deck, send_uno_turn
        state = uno_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("❌ ゲームが存在しません。", ephemeral=True)
            return

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

        # チャレンジしない → 次のプレイヤーが4枚引いてスキップ
        turn_index = (turn_index + direction * 2) % len(players)
        state["turn_index"] = turn_index
        state["deck"] = deck
        state["hands"] = hands
        state["pending"] = None
        await save_uno_game(interaction.guild_id or state.get("guild_id"), self.game_id, state)

        next_player_id = players[turn_index]

        await interaction.response.edit_message(
            content=(
                f"🃏 チャレンジしませんでした。\n"
                f"<@{next_player}> が 4 枚引きます。\n"
                f"次のターン：<@{next_player_id}>"
            ),
            view=None,
        )
        await send_uno_turn(
            interaction.client,
            self.game_id,
            state,
            f"🃏 チャレンジなし。<@{next_player}> が4枚引き、<@{next_player_id}> のターンです。",
        )
