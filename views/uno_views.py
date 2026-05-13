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
        from features.uno import handle_play_card
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
        from features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "red")

    @discord.ui.button(label="🟡 黄", style=discord.ButtonStyle.secondary)
    async def yellow(self, inter, btn):
        from features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "yellow")

    @discord.ui.button(label="🟢 緑", style=discord.ButtonStyle.success)
    async def green(self, inter, btn):
        from features.uno import handle_color_select
        await handle_color_select(inter, self.game_id, "green")

    @discord.ui.button(label="🔵 青", style=discord.ButtonStyle.primary)
    async def blue(self, inter, btn):
        from features.uno import handle_color_select
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
        from features.uno import handle_draw
        await handle_draw(inter, self.game_id)

    @discord.ui.button(label="⏭️ パス", style=discord.ButtonStyle.secondary)
    async def skip(self, inter, btn):
        from features.uno import handle_skip
        await handle_skip(inter, self.game_id)
