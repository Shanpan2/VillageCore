import random

import discord
from discord import app_commands
from discord.ext import commands

from utils.game_persistence import (
    save_game as _save_game,
    delete_game as _delete_game,
    load_games_for_guild,
)
from utils.game_cog import BaseGameCog


codenames_games: dict[str, dict] = {}

WORDS = [
    "りんご", "城", "電車", "月", "猫", "海", "学校", "剣", "時計", "雪",
    "花火", "王様", "森", "パン", "飛行機", "本", "温泉", "鍵", "忍者", "砂漠",
    "ロボット", "宝石", "橋", "カレー", "星", "祭り", "船", "山", "ピアノ", "雲",
    "病院", "魔法", "サッカー", "映画", "傘", "卵", "火山", "湖", "手紙", "宇宙",
    "寿司", "ドラゴン", "写真", "駅", "電話", "島", "コーヒー", "氷", "図書館", "風",
    "ゲーム", "キャンプ", "花", "先生", "犬", "トンネル", "王冠", "地図", "太陽", "夜",
]
TEAM_LABELS = {"red": "赤", "blue": "青", "neutral": "市民", "assassin": "暗殺者"}
TEAM_MARKS = {"red": "R", "blue": "B", "neutral": "N", "assassin": "X"}


_PREFIX = "codenames"


async def save_codenames_game(guild_id: int | None, game_id: str, state: dict | None = None):
    await _save_game(_PREFIX, codenames_games, guild_id, game_id, state)


async def delete_codenames_game(guild_id: int | None, game_id: str):
    await _delete_game(_PREFIX, guild_id, game_id)


def _restore_codenames_view(bot: commands.Bot, game_id: str, state: dict) -> None:
    if state.get("phase") == "lobby":
        bot.add_view(CodenamesLobbyView(game_id))


def _validate_codenames(state: dict) -> bool:
    return isinstance(state, dict) and bool(state.get("teams"))


async def load_codenames_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    await load_games_for_guild(
        _PREFIX, codenames_games, bot, guild,
        validate=_validate_codenames,
        restore_view=_restore_codenames_view,
    )


def mention(user_id: int | str) -> str:
    return f"<@{int(user_id)}>"


def team_members(state: dict, team: str) -> str:
    members = " / ".join(mention(uid) for uid in state.get("teams", {}).get(team, []))
    spy = state.get("spymasters", {}).get(team)
    spy_text = f" / スパイマスター: {mention(spy)}" if spy else ""
    return (members or "なし") + spy_text


def lobby_text(state: dict) -> str:
    return (
        "**コードネーム募集**\n"
        f"赤チーム: {team_members(state, 'red')}\n"
        f"青チーム: {team_members(state, 'blue')}\n\n"
        "赤/青に参加し、各チーム1人ずつスパイマスターを決めてください。"
    )


def board_lines(state: dict, reveal_all: bool = False) -> list[str]:
    entries = state.get("board", [])
    lines = []
    for row in range(5):
        parts = []
        for col in range(5):
            idx = row * 5 + col
            card = entries[idx]
            if card.get("revealed") or reveal_all:
                label = TEAM_MARKS.get(card["team"], "?")
                parts.append(f"{idx + 1:02d}.{card['word']}[{label}]")
            else:
                parts.append(f"{idx + 1:02d}.{card['word']}")
        lines.append(" / ".join(parts))
    return lines


def board_text(state: dict) -> str:
    turn = TEAM_LABELS.get(state.get("turn", "red"), "赤")
    clue = state.get("clue")
    clue_text = f"\n現在のヒント: **{clue.get('word')} / {clue.get('count')}** 残り推理: {state.get('guesses_left', 0)}" if clue else ""
    return (
        f"**コードネーム盤面**\n"
        f"手番: **{turn}チーム**{clue_text}\n\n"
        + "\n".join(board_lines(state))
        + "\n\n推理は `/codenames action:推理 text:番号または単語` で行います。"
    )


def key_text(state: dict) -> str:
    return "**スパイマスター用盤面**\n" + "\n".join(board_lines(state, reveal_all=True))


class CodenamesLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("red", "blue", "spy_red", "spy_blue", "begin", "cancel", "rules"), self.children):
            child.custom_id = f"codenames_lobby_{action}_{game_id}"

    @discord.ui.button(label="赤に参加", style=discord.ButtonStyle.danger)
    async def red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await join_team(interaction, self.game_id, "red", edit_message=True)

    @discord.ui.button(label="青に参加", style=discord.ButtonStyle.primary)
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await join_team(interaction, self.game_id, "blue", edit_message=True)

    @discord.ui.button(label="赤スパイ", style=discord.ButtonStyle.danger, row=1)
    async def spy_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await set_spymaster(interaction, self.game_id, "red", edit_message=True)

    @discord.ui.button(label="青スパイ", style=discord.ButtonStyle.primary, row=1)
    async def spy_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await set_spymaster(interaction, self.game_id, "blue", edit_message=True)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.success)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await begin_codenames(interaction, self.game_id, edit_message=True)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = codenames_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("中止できるのは作成者または管理者です。", ephemeral=True)
            return
        await delete_codenames_game(interaction.guild_id, self.game_id)
        codenames_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="コードネームの募集を中止しました。", view=None)

    @discord.ui.button(label="ルール", style=discord.ButtonStyle.secondary, row=1)
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="コードネーム のルール",
            description=(
                "赤チームと青チームに分かれ、各チーム1人がスパイマスターになります。\n"
                "スパイマスターだけが正解盤面を見て、1語のヒントと枚数を出します。\n"
                "推理側はヒントから味方チームの単語を選びます。\n\n"
                "暗殺者を選ぶと即敗北です。相手チームや市民を選ぶと手番が移ります。\n"
                "先に自チームの単語を全部開いたチームが勝ちです。\n\n"
                "ヒント: `/codenames action:ヒント text:動物 number:2`\n"
                "推理: `/codenames action:推理 text:番号または単語`"
            ),
            color=0xF1C40F,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def join_team(interaction: discord.Interaction, game_id: str, team: str, edit_message: bool = False):
    state = codenames_games.get(game_id)
    if not state or state.get("phase") != "lobby":
        await interaction.response.send_message("参加できる募集がありません。", ephemeral=True)
        return
    for members in state["teams"].values():
        if interaction.user.id in members:
            members.remove(interaction.user.id)
    for spy_team, spy_id in list(state.get("spymasters", {}).items()):
        if spy_id == interaction.user.id and spy_team != team:
            state["spymasters"].pop(spy_team, None)
    state["teams"][team].append(interaction.user.id)
    await save_codenames_game(interaction.guild_id, game_id, state)
    if edit_message:
        await interaction.response.edit_message(content=lobby_text(state), view=CodenamesLobbyView(game_id))
    else:
        await interaction.response.send_message(lobby_text(state))


async def set_spymaster(interaction: discord.Interaction, game_id: str, team: str, edit_message: bool = False):
    state = codenames_games.get(game_id)
    if not state or state.get("phase") != "lobby":
        await interaction.response.send_message("設定できる募集がありません。", ephemeral=True)
        return
    if interaction.user.id not in state["teams"][team]:
        await interaction.response.send_message("先にそのチームへ参加してください。", ephemeral=True)
        return
    state.setdefault("spymasters", {})[team] = interaction.user.id
    await save_codenames_game(interaction.guild_id, game_id, state)
    if edit_message:
        await interaction.response.edit_message(content=lobby_text(state), view=CodenamesLobbyView(game_id))
    else:
        await interaction.response.send_message(lobby_text(state))


async def begin_codenames(interaction: discord.Interaction, game_id: str, edit_message: bool = False):
    state = codenames_games.get(game_id)
    if not state:
        await interaction.response.send_message("コードネーム募集がありません。", ephemeral=True)
        return
    if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("開始できるのは作成者または管理者です。", ephemeral=True)
        return
    if not state["teams"]["red"] or not state["teams"]["blue"]:
        await interaction.response.send_message("赤青それぞれ1人以上必要です。", ephemeral=True)
        return
    if not state["spymasters"].get("red") or not state["spymasters"].get("blue"):
        await interaction.response.send_message("赤青それぞれスパイマスターを設定してください。", ephemeral=True)
        return

    words = random.sample(WORDS, 25)
    teams = ["red"] * 9 + ["blue"] * 8 + ["neutral"] * 7 + ["assassin"]
    random.shuffle(teams)
    state["phase"] = "playing"
    state["turn"] = "red"
    state["clue"] = None
    state["guesses_left"] = 0
    state["board"] = [{"word": word, "team": team, "revealed": False} for word, team in zip(words, teams)]
    await save_codenames_game(interaction.guild_id, game_id, state)

    for team in ("red", "blue"):
        spy_id = state["spymasters"][team]
        member = interaction.guild.get_member(int(spy_id)) or await interaction.client.fetch_user(int(spy_id))
        try:
            await member.send(key_text(state))
        except discord.HTTPException:
            pass

    if edit_message:
        await interaction.response.edit_message(content=board_text(state), view=None)
    else:
        await interaction.response.send_message(board_text(state))
    await interaction.followup.send("スパイマスターに正解盤面をDMしました。", ephemeral=True)


def switch_turn(state: dict):
    state["turn"] = "blue" if state.get("turn") == "red" else "red"
    state["clue"] = None
    state["guesses_left"] = 0


def remaining_team_cards(state: dict, team: str) -> int:
    return sum(1 for card in state.get("board", []) if card["team"] == team and not card.get("revealed"))


async def finish_game(interaction: discord.Interaction, game_id: str, winner: str, reason: str):
    state = codenames_games.get(game_id)
    await delete_codenames_game(interaction.guild_id, game_id)
    codenames_games.pop(game_id, None)
    await interaction.followup.send(
        f"{reason}\n\n**{TEAM_LABELS[winner]}チームの勝利です。**\n\n{key_text(state)}"
    )


class Codenames(BaseGameCog):
    _load_guild = staticmethod(load_codenames_games_for_guild)

    @app_commands.command(name="codenames", description="コードネームを遊びます")
    @app_commands.describe(action="操作", text="ヒントや推理する単語、番号", number="ヒントで関連する枚数")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="募集", value="start"),
            app_commands.Choice(name="赤に参加", value="join_red"),
            app_commands.Choice(name="青に参加", value="join_blue"),
            app_commands.Choice(name="赤スパイマスター", value="spy_red"),
            app_commands.Choice(name="青スパイマスター", value="spy_blue"),
            app_commands.Choice(name="開始", value="begin"),
            app_commands.Choice(name="ヒント", value="clue"),
            app_commands.Choice(name="推理", value="guess"),
            app_commands.Choice(name="パス", value="pass"),
            app_commands.Choice(name="状況", value="status"),
            app_commands.Choice(name="終了", value="end"),
        ]
    )
    async def codenames(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        text: str | None = None,
        number: int | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return
        game_id = str(interaction.channel_id)
        state = codenames_games.get(game_id)

        if action.value == "start":
            if state and state.get("phase") != "ended":
                await interaction.response.send_message("このチャンネルではすでにコードネームがあります。", ephemeral=True)
                return
            state = {
                "guild_id": interaction.guild_id,
                "channel_id": interaction.channel_id,
                "creator_id": interaction.user.id,
                "phase": "lobby",
                "teams": {"red": [], "blue": []},
                "spymasters": {},
                "board": [],
            }
            codenames_games[game_id] = state
            await save_codenames_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state), view=CodenamesLobbyView(game_id))
            return

        if not state:
            await interaction.response.send_message("このチャンネルにコードネームはありません。", ephemeral=True)
            return

        if action.value == "join_red":
            await join_team(interaction, game_id, "red")
            return
        if action.value == "join_blue":
            await join_team(interaction, game_id, "blue")
            return

        if action.value in {"spy_red", "spy_blue"}:
            if state.get("phase") != "lobby":
                await interaction.response.send_message("開始後は変更できません。", ephemeral=True)
                return
            team = "red" if action.value == "spy_red" else "blue"
            if interaction.user.id not in state["teams"][team]:
                await interaction.response.send_message("先にそのチームへ参加してください。", ephemeral=True)
                return
            state["spymasters"][team] = interaction.user.id
            await save_codenames_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state))
            return

        if action.value == "begin":
            await begin_codenames(interaction, game_id)
            return

        if action.value == "status":
            content = board_text(state) if state.get("phase") == "playing" else lobby_text(state)
            await interaction.response.send_message(content, ephemeral=True)
            return

        if action.value == "end":
            if interaction.user.id != state.get("creator_id") and not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("終了できるのは作成者または管理者です。", ephemeral=True)
                return
            await delete_codenames_game(interaction.guild_id, game_id)
            codenames_games.pop(game_id, None)
            await interaction.response.send_message("コードネームを終了しました。")
            return

        if state.get("phase") != "playing":
            await interaction.response.send_message("開始後に使う操作です。", ephemeral=True)
            return

        turn = state.get("turn", "red")
        if action.value == "clue":
            if state["spymasters"].get(turn) != interaction.user.id:
                await interaction.response.send_message("ヒントを出せるのは手番チームのスパイマスターだけです。", ephemeral=True)
                return
            clue = (text or "").strip()
            if not clue or not number or number < 1 or number > 9:
                await interaction.response.send_message("ヒント文字と1から9の枚数を指定してください。", ephemeral=True)
                return
            state["clue"] = {"word": clue[:20], "count": number}
            state["guesses_left"] = number + 1
            await save_codenames_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(board_text(state))
            return

        if action.value == "pass":
            if interaction.user.id not in state["teams"].get(turn, []):
                await interaction.response.send_message("パスできるのは手番チームだけです。", ephemeral=True)
                return
            switch_turn(state)
            await save_codenames_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(board_text(state))
            return

        if action.value == "guess":
            if not state.get("clue"):
                await interaction.response.send_message("先にスパイマスターがヒントを出してください。", ephemeral=True)
                return
            if interaction.user.id not in state["teams"].get(turn, []):
                await interaction.response.send_message("推理できるのは手番チームだけです。", ephemeral=True)
                return
            guess = (text or "").strip()
            if not guess:
                await interaction.response.send_message("推理する番号または単語を `text` に入力してください。", ephemeral=True)
                return
            card = None
            if guess.isdigit() and 1 <= int(guess) <= 25:
                card = state["board"][int(guess) - 1]
            else:
                for item in state["board"]:
                    if item["word"] == guess:
                        card = item
                        break
            if not card or card.get("revealed"):
                await interaction.response.send_message("未公開の盤面番号または単語を指定してください。", ephemeral=True)
                return
            card["revealed"] = True
            team = card["team"]
            await interaction.response.send_message(f"選んだ単語: **{card['word']}** / {TEAM_LABELS[team]}")
            if team == "assassin":
                winner = "blue" if turn == "red" else "red"
                await finish_game(interaction, game_id, winner, "暗殺者を選んでしまいました。")
                return
            if remaining_team_cards(state, "red") == 0:
                await finish_game(interaction, game_id, "red", "赤チームの単語がすべて開きました。")
                return
            if remaining_team_cards(state, "blue") == 0:
                await finish_game(interaction, game_id, "blue", "青チームの単語がすべて開きました。")
                return
            if team == turn:
                state["guesses_left"] = max(0, int(state.get("guesses_left", 0)) - 1)
                if state["guesses_left"] <= 0:
                    switch_turn(state)
            else:
                switch_turn(state)
            await save_codenames_game(interaction.guild_id, game_id, state)
            await interaction.followup.send(board_text(state))


async def setup(bot):
    await bot.add_cog(Codenames(bot))
