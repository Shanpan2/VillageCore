import discord
import traceback


class OthelloView(discord.ui.View):
    def __init__(self, game_id: str, valid_moves: list[tuple[int, int]]):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.selected_move: tuple[int, int] | None = None
        self.add_item(OthelloMoveSelect(game_id, valid_moves))
        self.add_item(OthelloConfirmButton(game_id))


class OthelloMoveSelect(discord.ui.Select):
    def __init__(self, game_id: str, valid_moves: list[tuple[int, int]]):
        options = [
            discord.SelectOption(label=f"{chr(65+x)}{y+1}", value=f"{x},{y}")
            for x, y in valid_moves
        ]
        if not options:
            options = [discord.SelectOption(label="置ける場所がありません", value="none", disabled=True)]

        super().__init__(
            placeholder="置ける場所を選択してください",
            options=options,
            custom_id=f"othello_move_{game_id}",
            row=0,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        if self.values and self.values[0] != "none":
            x, y = map(int, self.values[0].split(","))
            self.view.selected_move = (x, y)
        await interaction.response.defer(ephemeral=True)


class OthelloConfirmButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(
            label="ここに置く ✅",
            style=discord.ButtonStyle.success,
            custom_id=f"othello_confirm_{game_id}",
            row=1,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        try:
            if view.selected_move is None:
                await interaction.response.send_message(
                    "❌ 置きたい場所を選択してから確定してください。",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()

            x, y = view.selected_move
            from Features.othello import handle_othello_move

            await handle_othello_move(
                interaction,
                self.game_id,
                x,
                y,
            )

            view.selected_move = None
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
