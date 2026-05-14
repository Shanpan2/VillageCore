# views/othello_views.py

import discord


# Discord のボタンは1メッセージ最大25個（5行×5列）のため
# 8×8=64マスのボタンは実装不可。
# → 列(A〜H)と行(1〜8)をセレクトメニューで選ぶ2段階方式に変更。


class OthelloView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.add_item(OthelloColSelect(game_id))
        self.add_item(OthelloRowSelect(game_id))
        self.add_item(OthelloConfirmButton(game_id))

    # 選択中の列・行を一時保持（View インスタンス内）
    selected_col: int | None = None
    selected_row: int | None = None


class OthelloColSelect(discord.ui.Select):
    def __init__(self, game_id: str):
        options = [
            discord.SelectOption(label=f"列 {chr(65+i)}（{i}）", value=str(i))
            for i in range(8)
        ]
        super().__init__(
            placeholder="① 列を選択（A〜H）",
            options=options,
            custom_id=f"othello_col_{game_id}",
            row=0,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_col = int(self.values[0])
        await interaction.response.defer()


class OthelloRowSelect(discord.ui.Select):
    def __init__(self, game_id: str):
        options = [
            discord.SelectOption(label=f"行 {i+1}", value=str(i))
            for i in range(8)
        ]
        super().__init__(
            placeholder="② 行を選択（1〜8）",
            options=options,
            custom_id=f"othello_row_{game_id}",
            row=1,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_row = int(self.values[0])
        await interaction.response.defer()


class OthelloConfirmButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(
            label="ここに置く ✅",
            style=discord.ButtonStyle.success,
            custom_id=f"othello_confirm_{game_id}",
            row=2,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        view: OthelloView = self.view

        if view.selected_col is None or view.selected_row is None:
            await interaction.response.send_message(
                "❌ 列と行を両方選んでから確定してください。", ephemeral=True
            )
            return

        from Features.othello import handle_othello_move
        await handle_othello_move(
            interaction, self.game_id, view.selected_col, view.selected_row
        )

        # 選択状態をリセット
        view.selected_col = None
        view.selected_row = None
