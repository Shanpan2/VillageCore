import discord
import traceback

class OthelloView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.selected_col = None
        self.selected_row = None

        self.add_item(OthelloColSelect(game_id))
        self.add_item(OthelloRowSelect(game_id))
        self.add_item(OthelloConfirmButton(game_id))


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
        await interaction.response.defer(ephemeral=True)


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
        await interaction.response.defer(ephemeral=True)


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
        view = self.view
        try:
            if view.selected_col is None or view.selected_row is None:
                await interaction.response.send_message(
                    "❌ 列と行を両方選んでから確定してください。",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            from Features.othello import handle_othello_move

            await handle_othello_move(
                interaction,
                self.game_id,
                view.selected_col,
                view.selected_row
            )

            view.selected_col = None
            view.selected_row = None
        except Exception as e:
            print(f"[OthelloView] button error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    "❌ オセロ操作中にエラーが発生しました。",
                    ephemeral=True,
                )
            except Exception:
                pass
