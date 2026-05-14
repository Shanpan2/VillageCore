# views/uno_views.py

import discord


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
        from Features.uno import handle_play_card
        await handle_play_card(interaction, self.game_id, self.user_id, self.card)



# ============================================================
# 🎨 色選択（ワイルド用）
# ============================================================

class UnoColorSelectView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id

    @discord.ui.button(label="🔴 赤", style=discord.ButtonStyle.danger)
    async def red(self, inter, btn):
        from Features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "red")

    @discord.ui.button(label="🟡 黄", style=discord.ButtonStyle.secondary)
    async def yellow(self, inter, btn):
        from Features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "yellow")

    @discord.ui.button(label="🟢 緑", style=discord.ButtonStyle.success)
    async def green(self, inter, btn):
        from Features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "green")

    @discord.ui.button(label="🔵 青", style=discord.ButtonStyle.primary)
    async def blue(self, inter, btn):
        from Features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "blue")


# ============================================================
# 🃏 アクション（ドロー / パス）
# ============================================================

class UnoActionView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id

    @discord.ui.button(label="🃏 ドロー", style=discord.ButtonStyle.secondary)
    async def draw(self, inter, btn):
        from Features.uno import handle_draw
        await handle_draw(inter, self.game_id)

    @discord.ui.button(label="⏭️ パス", style=discord.ButtonStyle.secondary)
    async def skip(self, inter, btn):
        from Features.uno import handle_skip
        await handle_skip(inter, self.game_id)


# ============================================================
# 🎨 ワイルド色選択（新方式）
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
        from Features.uno import handle_wild_color_select
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
        from Features.uno import handle_uno_declare
        await handle_uno_declare(interaction, self.game_id, self.user_id)


class UnoDeclareView(discord.ui.View):
    def __init__(self, game_id: str, user_id: int):
        super().__init__(timeout=None)
        self.add_item(UnoDeclareButton(game_id, user_id))


