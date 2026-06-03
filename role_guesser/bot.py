from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


ROLE_GUESSER_TOKEN = os.getenv("ROLE_GUESSER_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATA_PATH = Path(__file__).with_name("data") / "roles.csv"

FEATURE_QUESTIONS = {
    "team_crewmate": "その役職はクルー陣営ですか？",
    "team_impostor": "その役職はインポスター陣営ですか？",
    "team_neutral": "その役職は第三陣営ですか？",
    "team_liberal": "その役職はリベラル陣営ですか？",
    "modifier_role": "元の役職に追加されるモディファイアですか？",
    "can_kill": "その役職はキルできますか？",
    "normal_kill": "通常のキルボタンでキルできますか？",
    "special_kill": "特殊能力でキルできますか？",
    "target_kill_power": "指定された対象をキルすることが勝利や能力条件ですか？",
    "uses_vent": "その役職はベントを使えますか？",
    "can_win_alone": "その役職は単独勝利できますか？",
    "additional_win": "他陣営の勝利に便乗して追加勝利しますか？",
    "can_protect": "その役職は誰かを守る能力がありますか？",
    "can_investigate": "その役職は情報を調べる能力がありますか？",
    "compare_power": "複数人を比較して陣営や関係を判定しますか？",
    "meeting_ability": "その役職は会議中に強い能力を発揮しますか？",
    "meeting_message": "会議中や会議後に専用メッセージが出ますか？",
    "has_tasks": "その役職にはタスクがありますか？",
    "task_based_power": "タスク進行で能力が強くなったり発動したりしますか？",
    "death_trigger": "死亡したときに能力が発動しますか？",
    "scheduled_death": "特定のタイミングで自動的に死亡しますか？",
    "ghost_role": "死亡後や幽霊状態で使う役職ですか？",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わる能力がありますか？",
    "vote_power": "投票や会議結果に直接影響する能力ですか？",
    "exile_win": "会議で追放されることが勝利条件ですか？",
    "tracking_power": "誰かの位置や移動を追跡できますか？",
    "role_info_power": "他人の役職や陣営を知る能力がありますか？",
    "public_identity": "自分の役職や存在が他のプレイヤーに分かりますか？",
    "fake_identity": "他人から別陣営や別役職のように見えますか？",
    "body_info_power": "死体・死因・死亡位置に関わる情報を得られますか？",
    "body_clear_power": "死体を消したり処理したりできますか？",
    "delayed_kill": "キルが遅れて発生したり、呪いのように間接的に発生しますか？",
    "disguise_or_invisible": "変身・透明化・姿を偽る能力がありますか？",
    "area_effect": "周囲や部屋全体に影響する能力がありますか？",
    "sabotage_power": "サボタージュに関わる特別な能力がありますか？",
    "door_power": "ドアを開閉する能力がありますか？",
    "revenge_kill": "自分を殺した相手を道連れにできますか？",
    "suicide_risk": "能力の代償や条件で自滅する可能性がありますか？",
    "conversion_power": "陣営変更・指名・感染などで他人の状態を変えますか？",
    "infection_power": "感染や拡散で他人の状態を広げますか？",
    "partner_power": "特定の相手を選んで、その相手の勝利や生存に関わりますか？",
    "lovers_power": "ラバーズや恋人関係を作ったり狙ったりしますか？",
    "alignment_shift_power": "自分の陣営や勝利条件が途中で変わりますか？",
    "control_power": "他人を操作する能力がありますか？",
    "restriction_power": "他人の行動や移動を制限する能力がありますか？",
    "ranged_power": "遠距離から能力やキルを使えますか？",
    "teleport_power": "テレポートや位置入れ替えに関わる能力ですか？",
    "cooldown_power": "キルクールや能力クールダウンを変化させますか？",
    "speed_power": "移動速度を変化させる能力がありますか？",
    "movement_power": "移動方法・移動方向・足場や乗り物の動きに干渉しますか？",
    "report_power": "死体通報や緊急会議ボタンに干渉しますか？",
    "vision_power": "視界を広げたり暗くしたりしますか？",
    "swap_power": "投票先・位置・役職などを入れ替える能力ですか？",
    "extra_vote_power": "追加票や複数票を持ちますか？",
}


@dataclass(frozen=True)
class Role:
    name: str
    display_name: str
    mod: str
    features: dict[str, bool | None]


def parse_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "yes", "y", "1", "はい"}:
        return True
    if normalized in {"false", "no", "n", "0", "いいえ"}:
        return False
    return None


def load_roles() -> list[Role]:
    if not DATA_PATH.exists():
        return []

    roles: list[Role] = []
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            display_name = (row.get("display_name") or name).strip()
            team = (row.get("team") or "").strip().lower()
            features = {
                key: parse_bool(row.get(key))
                for key in FEATURE_QUESTIONS
                if not key.startswith("team_")
            }
            features["team_crewmate"] = team == "crewmate"
            features["team_impostor"] = team == "impostor"
            features["team_neutral"] = team == "neutral"
            features["team_liberal"] = team == "liberal"
            mod = (row.get("mod") or "Unknown").strip()
            roles.append(
                Role(
                    name=name,
                    display_name=display_name,
                    mod=mod,
                    features=features,
                )
            )
    return roles


def best_question(candidates: list[Role], asked: set[str]) -> str | None:
    best_key = None
    best_score = -1
    for key in FEATURE_QUESTIONS:
        if key in asked:
            continue
        yes_count = sum(1 for role in candidates if role.features.get(key) is True)
        no_count = sum(1 for role in candidates if role.features.get(key) is False)
        known_count = yes_count + no_count
        if known_count == 0:
            continue
        balance = min(yes_count, no_count)
        coverage_bonus = known_count * 0.05
        one_sided_bonus = 0.25 if yes_count == 0 or no_count == 0 else 0
        score = balance + coverage_bonus + one_sided_bonus
        if score > best_score:
            best_key = key
            best_score = score
    return best_key


class GuessSession:
    def __init__(self, user_id: int, roles: list[Role]):
        self.user_id = user_id
        self.candidates = roles[:]
        self.asked: set[str] = set()
        self.current_question: str | None = None

    def apply_answer(self, answer: bool | None) -> None:
        if not self.current_question:
            return
        key = self.current_question
        if key.startswith("guess:"):
            if answer is None:
                return
            guessed_name = key.removeprefix("guess:")
            if answer:
                self.candidates = [role for role in self.candidates if role.name == guessed_name]
            else:
                self.candidates = [role for role in self.candidates if role.name != guessed_name]
            return

        matched = []
        for role in self.candidates:
            feature = role.features.get(key)
            if feature == answer:
                matched.append(role)
                continue
            # Most imported role data is incomplete. A blank feature should not
            # eliminate a role when the user answers "no" to a capability.
            if answer is False and feature is None:
                matched.append(role)
                continue
            # Task assignment can differ between vanilla-like host roles and
            # client/mod roles, so unknown task data should stay flexible.
            if key == "has_tasks" and feature is None:
                matched.append(role)
        if matched:
            self.candidates = matched
            return

        unknown = [
            role
            for role in self.candidates
            if role.features.get(key) is None
        ]
        if unknown:
            self.candidates = unknown

    def next_question(self) -> str | None:
        key = best_question(self.candidates, self.asked)
        if not key:
            for role in self.candidates:
                guess_key = f"guess:{role.name}"
                if guess_key not in self.asked:
                    key = guess_key
                    break
        self.current_question = key
        if key:
            self.asked.add(key)
        return key


sessions: dict[int, GuessSession] = {}


def grouped_candidate_text(roles: list[Role], limit: int = 10) -> str:
    grouped: dict[str, list[Role]] = {}
    for role in roles:
        grouped.setdefault(role.display_name, []).append(role)

    lines = []
    for display_name, items in list(grouped.items())[:limit]:
        mods = " / ".join(sorted({role.mod for role in items}))
        lines.append(f"- {display_name} ({mods})")
    remaining = len(grouped) - limit
    if remaining > 0:
        lines.append(f"ほか {remaining} 種類")
    return "\n".join(lines)


def single_group_result(roles: list[Role]) -> discord.Embed | None:
    display_names = {role.display_name for role in roles}
    if len(display_names) != 1:
        return None
    display_name = next(iter(display_names))
    mods = " / ".join(sorted({role.mod for role in roles}))
    return discord.Embed(
        title="役職当て",
        description=f"たぶん、あなたが思い浮かべた役職は **{display_name}** です。\nMOD: `{mods}`",
        color=0x2ECC71,
    )


def indistinguishable_result(roles: list[Role]) -> discord.Embed | None:
    if len(roles) <= 1:
        return None
    signatures = {
        tuple((key, role.features.get(key)) for key in FEATURE_QUESTIONS)
        for role in roles
    }
    if len(signatures) != 1:
        return None
    return discord.Embed(
        title="役職当て",
        description=(
            "ここから先は、今の役職データだけでは区別できません。\n"
            "候補はこのあたりです。\n"
            f"{grouped_candidate_text(roles)}"
        ),
        color=0xF1C40F,
    )


def session_embed(session: GuessSession) -> discord.Embed:
    if len(session.candidates) == 0:
        return discord.Embed(
            title="役職当て",
            description="候補がなくなりました。役職データが足りないか、どこかの回答が違うかもしれません。",
            color=0xE74C3C,
        )

    grouped_result = single_group_result(session.candidates)
    if grouped_result:
        return grouped_result

    indistinguishable = indistinguishable_result(session.candidates)
    if indistinguishable:
        return indistinguishable

    if len(session.candidates) == 1:
        role = session.candidates[0]
        name_line = f"**{role.display_name}**"
        if role.display_name != role.name:
            name_line += f" (`{role.name}`)"
        return discord.Embed(
            title="役職当て",
            description=f"たぶん、あなたが思い浮かべた役職は {name_line} です。\nMOD: `{role.mod}`",
            color=0x2ECC71,
        )

    key = session.current_question or session.next_question()
    if not key:
        return discord.Embed(
            title="役職当て",
            description=f"候補をすべて確認しました。残っている候補はこのあたりです。\n{grouped_candidate_text(session.candidates)}",
            color=0xF1C40F,
        )

    if key.startswith("guess:"):
        guessed_name = key.removeprefix("guess:")
        role = next((role for role in session.candidates if role.name == guessed_name), None)
        if role:
            name_line = f"**{role.display_name}**"
            if role.display_name != role.name:
                name_line += f" (`{role.name}`)"
            return discord.Embed(
                title="役職当て",
                description=(
                    f"あなたが思い浮かべた役職は {name_line} ですか？\n"
                    f"MOD: `{role.mod}`\n\n"
                    f"残り候補: **{len(session.candidates)}** 件"
                ),
                color=0x2ECC71,
            )

    return discord.Embed(
        title="役職当て",
        description=(
            f"{FEATURE_QUESTIONS[key]}\n\n"
            f"残り候補: **{len(session.candidates)}** 件"
        ),
        color=0x3498DB,
    )


class GuessView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このゲームを始めた人だけが回答できます。", ephemeral=True)
        return False

    async def answer(self, interaction: discord.Interaction, value: bool | None) -> None:
        session = sessions.get(self.user_id)
        if not session:
            await interaction.response.edit_message(
                embed=discord.Embed(title="役職当て", description="このゲームは終了しています。", color=0x95A5A6),
                view=None,
            )
            return

        session.apply_answer(value)
        session.current_question = None
        embed = session_embed(session)
        finished = (
            len(session.candidates) <= 1
            or single_group_result(session.candidates) is not None
            or indistinguishable_result(session.candidates) is not None
            or "候補がなくなりました" in embed.description
            or "候補をすべて確認しました" in embed.description
        )
        if finished:
            sessions.pop(self.user_id, None)
        await interaction.response.edit_message(embed=embed, view=None if finished else self)

    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, True)

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, False)

    @discord.ui.button(label="どちらでもない/不明", style=discord.ButtonStyle.secondary)
    async def unknown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, None)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions.pop(self.user_id, None)
        await interaction.response.edit_message(
            embed=discord.Embed(title="役職当て", description="ゲームを中止しました。", color=0x95A5A6),
            view=None,
        )


class RoleGuesserBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


role_bot = RoleGuesserBot()


@role_bot.event
async def on_ready():
    print(f"Role Guesser ready: {role_bot.user} ({role_bot.user.id})", flush=True)


@role_bot.tree.command(name="guess", description="Among Us系Modの役職当てを始めます")
async def guess(interaction: discord.Interaction):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    session = GuessSession(interaction.user.id, roles)
    sessions[interaction.user.id] = session
    await interaction.response.send_message(embed=session_embed(session), view=GuessView(interaction.user.id))


@role_bot.tree.command(name="roles", description="登録されている役職数を表示します")
async def roles(interaction: discord.Interaction):
    loaded_roles = load_roles()
    mods = sorted({role.mod for role in loaded_roles})
    await interaction.response.send_message(
        f"登録役職: **{len(loaded_roles)}** 件\n登録MOD: {', '.join(mods) or 'なし'}",
        ephemeral=True,
    )


async def start_role_guesser_bot() -> None:
    if not ROLE_GUESSER_TOKEN:
        print("ROLE_GUESSER_TOKEN is not set; Role Guesser bot skipped.", flush=True)
        return
    try:
        await role_bot.start(ROLE_GUESSER_TOKEN)
    except Exception as exc:
        print(f"Role Guesser bot failed to start: {type(exc).__name__}: {exc}", flush=True)
