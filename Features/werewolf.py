import asyncio
import json
import random

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_set


werewolf_games: dict[str, dict] = {}

ROLE_LABELS = {
    "werewolf": "人狼",
    "seer": "占い師",
    "knight": "騎士",
    "villager": "村人",
}
ROLE_HELP = {
    "werewolf": "夜に `/werewolf action:襲撃 target:@相手` で襲撃先を選びます。",
    "seer": "夜に `/werewolf action:占う target:@相手` で相手が人狼か確認できます。",
    "knight": "夜に `/werewolf action:守る target:@相手` で襲撃から守ります。",
    "villager": "昼の議論後に `/werewolf action:投票 target:@相手` で追放先を選びます。",
}


def werewolf_index_key(guild_id: int) -> str:
    return f"werewolf_games_index:{guild_id}"


def werewolf_game_key(guild_id: int, game_id: str) -> str:
    return f"werewolf_game:{guild_id}:{game_id}"


async def save_werewolf_game(guild_id: int | None, game_id: str, state: dict | None = None):
    if not guild_id:
        return
    state = state or werewolf_games.get(game_id)
    if not state:
        return
    state["guild_id"] = guild_id
    await db_set(werewolf_game_key(guild_id, game_id), json.dumps(state, ensure_ascii=False))
    try:
        index = json.loads(await db_get(werewolf_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    if game_id not in index:
        index.append(game_id)
        await db_set(werewolf_index_key(guild_id), json.dumps(index[-100:], ensure_ascii=False))


async def delete_werewolf_game(guild_id: int | None, game_id: str):
    if not guild_id:
        return
    try:
        index = json.loads(await db_get(werewolf_index_key(guild_id)) or "[]")
    except json.JSONDecodeError:
        index = []
    index = [item for item in index if item != game_id]
    await db_set(werewolf_index_key(guild_id), json.dumps(index, ensure_ascii=False))


async def load_werewolf_games_for_guild(bot: commands.Bot, guild: discord.Guild):
    try:
        index = json.loads(await db_get(werewolf_index_key(guild.id)) or "[]")
    except json.JSONDecodeError:
        index = []

    changed = False
    for game_id in index:
        raw = await db_get(werewolf_game_key(guild.id, game_id))
        if not raw:
            changed = True
            continue
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            changed = True
            continue
        if not isinstance(state, dict) or not state.get("players"):
            changed = True
            continue
        werewolf_games[game_id] = state
        if state.get("phase") == "lobby":
            bot.add_view(WerewolfLobbyView(game_id))

    if changed:
        active = [game_id for game_id in index if game_id in werewolf_games]
        await db_set(werewolf_index_key(guild.id), json.dumps(active, ensure_ascii=False))


def mention(user_id: int | str) -> str:
    return f"<@{int(user_id)}>"


def alive_ids(state: dict) -> list[int]:
    return [int(uid) for uid in state.get("alive", [])]


def role_of(state: dict, user_id: int | str) -> str | None:
    return state.get("roles", {}).get(str(user_id))


def has_manage_permission(interaction: discord.Interaction) -> bool:
    return bool(getattr(interaction.user.guild_permissions, "manage_guild", False))


def lobby_text(state: dict) -> str:
    players = " / ".join(mention(uid) for uid in state.get("players", [])) or "まだいません"
    return (
        "**人狼ゲーム募集**\n"
        f"参加者: {players}\n"
        f"人数: {len(state.get('players', []))}/12\n\n"
        "ボタンまたは `/werewolf action:参加` で参加できます。"
    )


def status_text(state: dict) -> str:
    phase = state.get("phase", "lobby")
    if phase == "lobby":
        return lobby_text(state)
    alive = " / ".join(mention(uid) for uid in alive_ids(state)) or "なし"
    phase_label = "夜" if phase == "night" else "昼" if phase == "day" else "終了"
    if phase == "night":
        guide = "人狼、占い師、騎士は自分の夜行動を実行してください。"
    elif phase == "day":
        guide = "話し合い後、全員が `/werewolf action:投票 target:@相手` で投票してください。"
    else:
        guide = "ゲームは終了しています。"
    return (
        f"**人狼ゲーム 状況**\n"
        f"日数: {state.get('day', 1)}日目 / フェーズ: {phase_label}\n"
        f"生存者: {alive}\n\n"
        f"{guide}"
    )


def assign_roles(players: list[int]) -> dict[str, str]:
    shuffled = players[:]
    random.shuffle(shuffled)
    wolf_count = 2 if len(players) >= 8 else 1
    roles: dict[str, str] = {}
    for user_id in shuffled[:wolf_count]:
        roles[str(user_id)] = "werewolf"
    cursor = wolf_count
    roles[str(shuffled[cursor])] = "seer"
    cursor += 1
    if len(players) >= 5:
        roles[str(shuffled[cursor])] = "knight"
        cursor += 1
    for user_id in shuffled[cursor:]:
        roles[str(user_id)] = "villager"
    return roles


async def dm_roles(bot: commands.Bot, guild: discord.Guild, state: dict):
    wolves = [mention(uid) for uid, role in state.get("roles", {}).items() if role == "werewolf"]
    for user_id, role in state.get("roles", {}).items():
        member = guild.get_member(int(user_id)) or await bot.fetch_user(int(user_id))
        role_label = ROLE_LABELS.get(role, role)
        extra = f"\n人狼仲間: {' / '.join(wolves)}" if role == "werewolf" else ""
        try:
            await member.send(f"あなたの役職は **{role_label}** です。\n{ROLE_HELP.get(role, '')}{extra}")
        except discord.HTTPException:
            pass


async def start_match(interaction: discord.Interaction, game_id: str, state: dict):
    if len(state.get("players", [])) < 4:
        await interaction.response.send_message("人狼は4人以上で開始できます。", ephemeral=True)
        return
    if interaction.user.id != state.get("creator_id") and not has_manage_permission(interaction):
        await interaction.response.send_message("開始できるのは作成者または管理者です。", ephemeral=True)
        return

    players = [int(uid) for uid in state["players"]]
    state["phase"] = "night"
    state["day"] = 1
    state["alive"] = players
    state["roles"] = assign_roles(players)
    state["night_actions"] = {}
    state["votes"] = {}
    await save_werewolf_game(interaction.guild_id, game_id, state)
    if getattr(interaction, "message", None):
        await interaction.response.edit_message(content=status_text(state), view=None)
    else:
        await interaction.response.send_message(status_text(state))
    await dm_roles(interaction.client, interaction.guild, state)
    await interaction.followup.send(
        "役職をDMに送信しました。届かない場合は `/werewolf action:自分の役職` で確認できます。",
        ephemeral=True,
    )


def required_night_actions(state: dict) -> set[str]:
    alive = set(str(uid) for uid in alive_ids(state))
    roles = state.get("roles", {})
    required = set()
    if any(role == "werewolf" and uid in alive for uid, role in roles.items()):
        required.add("attack")
    if any(role == "seer" and uid in alive for uid, role in roles.items()):
        required.add("see")
    if any(role == "knight" and uid in alive for uid, role in roles.items()):
        required.add("guard")
    return required


def check_winner(state: dict) -> str | None:
    alive = set(str(uid) for uid in alive_ids(state))
    wolves = [uid for uid, role in state.get("roles", {}).items() if role == "werewolf" and uid in alive]
    villagers = [uid for uid in alive if state.get("roles", {}).get(uid) != "werewolf"]
    if not wolves:
        return "村人陣営"
    if len(wolves) >= len(villagers):
        return "人狼陣営"
    return None


async def finish_game(interaction: discord.Interaction, game_id: str, state: dict, winner: str, reason: str):
    state["phase"] = "ended"
    await save_werewolf_game(interaction.guild_id, game_id, state)
    await delete_werewolf_game(interaction.guild_id, game_id)
    werewolf_games.pop(game_id, None)
    roles = "\n".join(
        f"{mention(uid)}: {ROLE_LABELS.get(role, role)}"
        for uid, role in state.get("roles", {}).items()
    )
    await interaction.followup.send(
        f"{reason}\n\n**{winner}の勝利です。**\n\n役職一覧:\n{roles}",
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def resolve_night(interaction: discord.Interaction, game_id: str, state: dict) -> bool:
    actions = state.get("night_actions", {})
    if not required_night_actions(state).issubset(set(actions)):
        return False

    protected = actions.get("guard")
    attacked = actions.get("attack")
    if attacked and attacked != protected and int(attacked) in alive_ids(state):
        state["alive"] = [uid for uid in alive_ids(state) if uid != int(attacked)]
        result = f"夜が明けました。{mention(attacked)} が襲撃されました。"
    elif attacked:
        result = "夜が明けました。昨晩の襲撃は防がれました。"
    else:
        result = "夜が明けました。昨晩は誰も襲撃されませんでした。"

    winner = check_winner(state)
    if winner:
        await finish_game(interaction, game_id, state, winner, result)
        return True

    state["phase"] = "day"
    state["votes"] = {}
    state["night_actions"] = {}
    await save_werewolf_game(interaction.guild_id, game_id, state)
    await interaction.followup.send(f"{result}\n\n{status_text(state)}")
    return True


async def resolve_votes(interaction: discord.Interaction, game_id: str, state: dict) -> bool:
    votes = state.get("votes", {})
    if not set(str(uid) for uid in alive_ids(state)).issubset(set(votes)):
        return False

    counts: dict[str, int] = {}
    for target in votes.values():
        counts[target] = counts.get(target, 0) + 1
    top = max(counts.values())
    targets = [target for target, count in counts.items() if count == top]
    if len(targets) == 1:
        eliminated = int(targets[0])
        state["alive"] = [uid for uid in alive_ids(state) if uid != eliminated]
        result = f"投票の結果、{mention(eliminated)} が追放されました。"
    else:
        result = "投票が同数だったため、今日は誰も追放されませんでした。"

    winner = check_winner(state)
    if winner:
        await finish_game(interaction, game_id, state, winner, result)
        return True

    state["phase"] = "night"
    state["day"] = int(state.get("day", 1)) + 1
    state["votes"] = {}
    state["night_actions"] = {}
    await save_werewolf_game(interaction.guild_id, game_id, state)
    await interaction.followup.send(f"{result}\n\n夜になりました。役職持ちは行動してください。")
    return True


class WerewolfLobbyView(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=None)
        self.game_id = game_id
        for action, child in zip(("join", "leave", "begin", "cancel"), self.children):
            child.custom_id = f"werewolf_lobby_{action}_{game_id}"

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = werewolf_games.get(self.game_id)
        if not state or state.get("phase") != "lobby":
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id in state["players"]:
            await interaction.response.send_message("すでに参加しています。", ephemeral=True)
            return
        if len(state["players"]) >= 12:
            await interaction.response.send_message("参加上限は12人です。", ephemeral=True)
            return
        state["players"].append(interaction.user.id)
        await save_werewolf_game(interaction.guild_id, self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="抜ける", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = werewolf_games.get(self.game_id)
        if not state or state.get("phase") != "lobby":
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id not in state["players"]:
            await interaction.response.send_message("まだ参加していません。", ephemeral=True)
            return
        state["players"] = [uid for uid in state["players"] if uid != interaction.user.id]
        await save_werewolf_game(interaction.guild_id, self.game_id, state)
        await interaction.response.edit_message(content=lobby_text(state), view=self)

    @discord.ui.button(label="開始", style=discord.ButtonStyle.primary)
    async def begin(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = werewolf_games.get(self.game_id)
        if not state or state.get("phase") != "lobby":
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        await start_match(interaction, self.game_id, state)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = werewolf_games.get(self.game_id)
        if not state:
            await interaction.response.send_message("この募集は終了しています。", ephemeral=True)
            return
        if interaction.user.id != state.get("creator_id") and not has_manage_permission(interaction):
            await interaction.response.send_message("中止できるのは作成者または管理者です。", ephemeral=True)
            return
        await delete_werewolf_game(interaction.guild_id, self.game_id)
        werewolf_games.pop(self.game_id, None)
        await interaction.response.edit_message(content="人狼ゲームの募集を中止しました。", view=None)


class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._restore_task = None

    async def cog_load(self):
        self._restore_task = asyncio.create_task(self._restore_saved_games())

    async def cog_unload(self):
        if self._restore_task:
            self._restore_task.cancel()

    async def _restore_saved_games(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await load_werewolf_games_for_guild(self.bot, guild)

    @app_commands.command(name="werewolf", description="人狼ゲームを操作します")
    @app_commands.describe(action="操作を選んでください", target="対象メンバー。襲撃、占い、守り、投票で使います")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="募集", value="start"),
            app_commands.Choice(name="参加", value="join"),
            app_commands.Choice(name="抜ける", value="leave"),
            app_commands.Choice(name="開始", value="begin"),
            app_commands.Choice(name="状況", value="status"),
            app_commands.Choice(name="自分の役職", value="role"),
            app_commands.Choice(name="襲撃", value="attack"),
            app_commands.Choice(name="占う", value="see"),
            app_commands.Choice(name="守る", value="guard"),
            app_commands.Choice(name="投票", value="vote"),
            app_commands.Choice(name="終了", value="end"),
        ]
    )
    async def werewolf(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        target: discord.Member | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return

        game_id = str(interaction.channel_id)
        state = werewolf_games.get(game_id)

        if action.value == "start":
            if state and state.get("phase") != "ended":
                await interaction.response.send_message("このチャンネルではすでに人狼ゲームがあります。", ephemeral=True)
                return
            state = {
                "guild_id": interaction.guild_id,
                "channel_id": interaction.channel_id,
                "creator_id": interaction.user.id,
                "phase": "lobby",
                "players": [interaction.user.id],
                "roles": {},
                "alive": [],
                "day": 0,
                "night_actions": {},
                "votes": {},
            }
            werewolf_games[game_id] = state
            await save_werewolf_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state), view=WerewolfLobbyView(game_id))
            return

        if not state:
            await interaction.response.send_message("このチャンネルに人狼ゲームはありません。", ephemeral=True)
            return

        if action.value == "join":
            if state.get("phase") != "lobby":
                await interaction.response.send_message("開始後は参加できません。", ephemeral=True)
                return
            if interaction.user.id in state["players"]:
                await interaction.response.send_message("すでに参加しています。", ephemeral=True)
                return
            if len(state["players"]) >= 12:
                await interaction.response.send_message("参加上限は12人です。", ephemeral=True)
                return
            state["players"].append(interaction.user.id)
            await save_werewolf_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state))
            return

        if action.value == "leave":
            if state.get("phase") != "lobby":
                await interaction.response.send_message("開始後は抜けられません。", ephemeral=True)
                return
            if interaction.user.id not in state["players"]:
                await interaction.response.send_message("まだ参加していません。", ephemeral=True)
                return
            state["players"] = [uid for uid in state["players"] if uid != interaction.user.id]
            await save_werewolf_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(lobby_text(state))
            return

        if action.value == "begin":
            if state.get("phase") != "lobby":
                await interaction.response.send_message("すでに開始しています。", ephemeral=True)
                return
            await start_match(interaction, game_id, state)
            return

        if action.value == "status":
            await interaction.response.send_message(status_text(state), ephemeral=True)
            return

        if action.value == "role":
            role = role_of(state, interaction.user.id)
            if not role:
                await interaction.response.send_message("あなたはこのゲームに参加していません。", ephemeral=True)
                return
            await interaction.response.send_message(
                f"あなたの役職は **{ROLE_LABELS.get(role, role)}** です。\n{ROLE_HELP.get(role, '')}",
                ephemeral=True,
            )
            return

        if action.value == "end":
            if interaction.user.id != state.get("creator_id") and not has_manage_permission(interaction):
                await interaction.response.send_message("終了できるのは作成者または管理者です。", ephemeral=True)
                return
            await delete_werewolf_game(interaction.guild_id, game_id)
            werewolf_games.pop(game_id, None)
            await interaction.response.send_message("人狼ゲームを終了しました。")
            return

        if state.get("phase") not in {"night", "day"}:
            await interaction.response.send_message("ゲーム開始後に使う操作です。", ephemeral=True)
            return
        if interaction.user.id not in alive_ids(state):
            await interaction.response.send_message("生存者のみ操作できます。", ephemeral=True)
            return
        if not target:
            await interaction.response.send_message("対象メンバーを指定してください。", ephemeral=True)
            return
        if target.bot or target.id not in alive_ids(state):
            await interaction.response.send_message("生存している参加者を指定してください。", ephemeral=True)
            return

        user_role = role_of(state, interaction.user.id)

        if action.value in {"attack", "see", "guard"}:
            if state.get("phase") != "night":
                await interaction.response.send_message("夜の行動は夜フェーズだけ実行できます。", ephemeral=True)
                return
            if action.value == "attack":
                if user_role != "werewolf":
                    await interaction.response.send_message("襲撃できるのは人狼だけです。", ephemeral=True)
                    return
                if role_of(state, target.id) == "werewolf":
                    await interaction.response.send_message("人狼仲間は襲撃できません。", ephemeral=True)
                    return
            elif action.value == "see":
                if user_role != "seer":
                    await interaction.response.send_message("占えるのは占い師だけです。", ephemeral=True)
                    return
            elif action.value == "guard":
                if user_role != "knight":
                    await interaction.response.send_message("守れるのは騎士だけです。", ephemeral=True)
                    return

            state.setdefault("night_actions", {})[action.value] = str(target.id)
            await save_werewolf_game(interaction.guild_id, game_id, state)
            if action.value == "see":
                result = "人狼です。" if role_of(state, target.id) == "werewolf" else "人狼ではありません。"
                await interaction.response.send_message(f"{target.mention} は **{result}**", ephemeral=True)
            else:
                await interaction.response.send_message("夜行動を受け付けました。", ephemeral=True)
            await interaction.followup.send("夜行動が進みました。", ephemeral=True)
            await resolve_night(interaction, game_id, state)
            return

        if action.value == "vote":
            if state.get("phase") != "day":
                await interaction.response.send_message("投票は昼フェーズだけ実行できます。", ephemeral=True)
                return
            if target.id == interaction.user.id:
                await interaction.response.send_message("自分には投票できません。", ephemeral=True)
                return
            state.setdefault("votes", {})[str(interaction.user.id)] = str(target.id)
            await save_werewolf_game(interaction.guild_id, game_id, state)
            await interaction.response.send_message(f"{target.mention} に投票しました。", ephemeral=True)
            await interaction.followup.send("投票を受け付けました。", ephemeral=True)
            await resolve_votes(interaction, game_id, state)
            return


async def setup(bot):
    await bot.add_cog(Werewolf(bot))
