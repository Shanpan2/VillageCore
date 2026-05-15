import discord
import traceback


class OthelloView(discord.ui.View):
    def __init__(self, game_id: str, valid_moves: list[tuple[int, int]], show_join: bool = True):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.selected_move: tuple[int, int] | None = None
        self.add_item(OthelloMoveSelect(game_id, valid_moves))
        self.add_item(OthelloConfirmButton(game_id))
        if show_join:
            self.add_item(JoinButton(game_id))
        else:
            self.add_item(SurrenderButton(game_id))


class OthelloMoveSelect(discord.ui.Select):
    def __init__(self, game_id: str, valid_moves: list[tuple[int, int]]):
        # Use label-style values (e.g. "D3") to avoid coordinate mixups
        options = [
            discord.SelectOption(label=f"{chr(65+x)}{y+1}", value=f"{chr(65+x)}{y+1}")
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
        try:
            from Features.othello import othello_games
            game = othello_games.get(self.game_id)
            if not game:
                await interaction.response.send_message("❌ ゲームが見つかりません。", ephemeral=True)
                return
            # 参加者かつ手番の人のみ選択可能
            cur_turn = game["turn"]
            allowed_id = game.get("black_id") if cur_turn == 1 else game.get("white_id")
            if allowed_id is None or interaction.user.id != allowed_id:
                await interaction.response.send_message("❌ 今の手番のプレイヤーのみ選択できます。", ephemeral=True)
                return
        except Exception:
            pass

        if self.values and self.values[0] != "none":
            val = self.values[0]
            # Convert label like 'D3' back to coordinates
            try:
                x = ord(val[0].upper()) - 65
                y = int(val[1:]) - 1
                self.view.selected_move = (x, y)
            except Exception:
                self.view.selected_move = None
        # Acknowledge selection with a short ephemeral message
        try:
            await interaction.response.send_message(f"選択しました: {self.values[0]}", ephemeral=True)
        except Exception:
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass


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


class JoinButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(
            label="参加する 🟡",
            style=discord.ButtonStyle.secondary,
            custom_id=f"othello_join_{game_id}",
            row=2,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        try:
            from Features.othello import othello_games, get_valid_moves, generate_othello_image

            game = othello_games.get(self.game_id)
            if not game:
                await interaction.response.send_message("❌ ゲームが見つかりません。", ephemeral=True)
                return

            if game.get("white_id") is not None:
                await interaction.response.send_message("❌ 既に後手プレイヤーが参加しています。", ephemeral=True)
                return

            if interaction.user.id == game.get("black_id"):
                await interaction.response.send_message("❌ 先手と同じ人は後手に参加できません。", ephemeral=True)
                return

            # 参加登録
            game["white_id"] = interaction.user.id

            # 盤面更新
            board = game["board"]
            valid_moves = get_valid_moves(board, game["turn"])
            img = generate_othello_image(board, valid_moves)
            file = discord.File(img, filename="othello.png")

            player_text = (
                f"黒: <@{game['black_id']}>\n白: <@{game['white_id']}>\n"
            )
            embed = discord.Embed(
                title="🎮 オセロ",
                description=(
                    f"{player_text}"
                    f"{'黒' if game['turn'] == 1 else '白'}番です。\n"
                    "置ける場所を選択してください。"
                ),
                color=0x2ECC71,
            )

            # 編集は interaction.message を使って行う
            await interaction.response.send_message("✅ 後手として参加しました。", ephemeral=True)
            await interaction.message.edit(embed=embed, attachments=[file], view=OthelloView(self.game_id, valid_moves, show_join=False))
        except Exception as e:
            print(f"[OthelloView.Join] error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ 参加処理中にエラーが発生しました。", ephemeral=True)
            except Exception:
                pass


class SurrenderButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(
            label="降参する 🛑",
            style=discord.ButtonStyle.danger,
            custom_id=f"othello_surrender_{game_id}",
            row=2,
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        try:
            from Features.othello import othello_games

            game = othello_games.get(self.game_id)
            if not game:
                await interaction.response.send_message("❌ ゲームが見つかりません。", ephemeral=True)
                return

            user_id = interaction.user.id
            if user_id != game.get("black_id") and user_id != game.get("white_id"):
                await interaction.response.send_message("❌ ゲーム参加者のみ降参できます。", ephemeral=True)
                return

            # 決着: 押した人が降参 -> 相手の勝利
            if user_id == game.get("black_id"):
                winner = "白"
            else:
                winner = "黒"

            # ゲームデータを削除
            try:
                othello_games.pop(self.game_id, None)
            except Exception:
                pass

            # 表示更新
            await interaction.response.send_message(f"✅ 降参しました。{winner} の勝利です。", ephemeral=True)
            try:
                await interaction.message.edit(
                    embed=discord.Embed(
                        title="🎮 オセロ 終了",
                        description=f"降参により {winner} の勝利です。",
                        color=0x2ECC71,
                    ),
                    view=None,
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[OthelloView.Surrender] error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ 降参処理中にエラーが発生しました。", ephemeral=True)
            except Exception:
                pass
