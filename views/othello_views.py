# views/othello_views.py

import discord


class OthelloView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id

        # 8×8 のボタンを生成
        for y in range(8):
            for x in range(8):
                self.add_item(OthelloButton(x, y, game_id))


class OthelloButton(discord.ui.Button):
    def __init__(self, x: int, y: int, game_id: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=" ",
            row=y,
            custom_id=f"othello_{game_id}_{x}_{y}"
        )
        self.x = x
        self.y = y
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        # ★ここを修正★
        from Features.othello import handle_othello_move
        await handle_othello_move(interaction, self.game_id, self.x, self.y)

