from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


ROLE_GUESSER_TOKEN = os.getenv("ROLE_GUESSER_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATA_PATH = Path(__file__).with_name("data") / "roles.csv"

MOD_ALIASES = {
    "vanilla": "Vanilla",
    "among us": "Vanilla",
    "amongus": "Vanilla",
    "バニラ": "Vanilla",
    "town of host": "TOH",
    "toh": "TOH",
    "tohk": "TOHK",
    "supernewroles": "SNR",
    "super new roles": "SNR",
    "snr": "SNR",
    "extremeroles": "ExR",
    "extreme roles": "ExR",
    "exr": "ExR",
    "torgmia": "TORGMIA",
    "nos": "NOS",
}

FEATURE_QUESTIONS = {
    "team_crewmate": "その役職はクルー陣営ですか？",
    "team_impostor": "その役職はインポスター陣営ですか？",
    "team_neutral": "その役職は第三陣営ですか？",
    "team_liberal": "その役職はリベラル陣営ですか？",
    "modifier_role": "メイン役職に追加で付く属性・モディファイアですか？",
    "can_kill": "自分の操作で誰かを死亡させる能力がありますか？",
    "normal_kill": "普通のキルボタンでキルする役職ですか？",
    "special_kill": "普通のキルボタン以外で死亡させる能力がありますか？（例: 爆破、推測、ビーム、罠、会議キル）",
    "target_power": "特定の相手を選ぶ能力ですか？（例: 指名、恋人化、投獄、ターゲット指定）",
    "target_kill_power": "特定の相手を殺す/死なせることが目的や能力条件ですか？（例: 賞金首、復讐対象、推測キル）",
    "guard_piercing_power": "ガードやシールドを貫通するキル能力がありますか？",
    "wave_cannon_power": "波動砲・レーザー・ビームのような直線攻撃ですか？",
    "uses_vent": "その役職はベントを使えますか？",
    "can_win_alone": "その役職は単独勝利できますか？",
    "additional_win": "他陣営の勝利に便乗して追加勝利しますか？",
    "can_protect": "誰かを守る能力がありますか？（例: ガード、バリア、キル防止）",
    "can_investigate": "情報を調べる能力がありますか？（例: 役職/陣営/死因/位置を調査）",
    "compare_power": "複数人を比較して判定しますか？（例: 同陣営か、関係があるか）",
    "meeting_ability": "会議中に使う能力がありますか？（例: 推測、追加投票、投票操作、会議中の調査）",
    "meeting_message": "会議中や会議後に専用メッセージが出ますか？（例: パン屋通知、生存通知、能力報告）",
    "has_tasks": "その役職にはタスクがありますか？",
    "task_based_power": "タスク進行で能力・勝利条件・覚醒が変わりますか？",
    "extra_task_power": "追加タスクや専用タスクが割り当てられますか？",
    "death_trigger": "自分や対象が死亡した時に能力が発動しますか？（例: 道連れ、後追い、通知、変化）",
    "scheduled_death": "決まった条件やタイミングで自動的に死亡しますか？",
    "ghost_role": "死亡後・幽霊状態で使う役職ですか？",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わる能力がありますか？（例: 霊視、蘇生、幽霊能力）",
    "vote_power": "投票や会議結果に直接影響しますか？（例: 追加票、票を減らす、同数処理、強制追放）",
    "exile_win": "会議で追放されることが勝利条件ですか？",
    "tracking_power": "誰かの位置や死体位置を矢印・通知などで追えますか？",
    "role_info_power": "他人の役職や陣営を知る能力がありますか？",
    "public_identity": "自分の役職や存在が他のプレイヤーに分かりますか？",
    "fake_identity": "他人から別陣営・別役職・別人のように見える能力ですか？",
    "dummy_power": "ダミーや分身を表示する能力がありますか？",
    "body_info_power": "死体・死因・死亡位置に関する情報を得られますか？",
    "body_clear_power": "死体を消したり処理したりできますか？（例: 食べる、掃除、蘇生用に消す）",
    "body_move_power": "死体を運んだり別の場所へ動かしたりできますか？",
    "delayed_kill": "能力を使ってから遅れて死亡しますか？（例: 呪い、時限爆弾、後で発動するキル）",
    "disguise_or_invisible": "変身・透明化・姿の偽装ができますか？",
    "area_effect": "周囲や部屋全体に影響しますか？（例: 範囲キル、爆発、全員の移動制限）",
    "sabotage_power": "サボタージュに関わる特別な能力がありますか？（例: 独自サボ、即修理、サボクール操作）",
    "lights_sabotage_power": "停電サボタージュに特化した能力や制限がありますか？",
    "critical_sabotage_power": "リアクター・O2などの緊急サボタージュに特化した能力や制限がありますか？",
    "door_power": "ドアを開閉・一括開放・妨害する能力がありますか？",
    "specific_door_power": "特定の場所や設備のドアだけに作用しますか？（例: トイレ、特定部屋）",
    "revenge_kill": "自分を殺した相手を道連れにできますか？",
    "suicide_risk": "能力の代償や条件で自滅する可能性がありますか？",
    "conversion_power": "他人の役職・陣営・状態を変えますか？（例: サイドキック化、感染、投獄、蘇生）",
    "infection_power": "感染や拡散で他人の状態を広げますか？",
    "partner_power": "特定の相方・主人・対象とペアやチームになりますか？",
    "lovers_power": "ラバーズや恋人関係を作ったり狙ったりしますか？",
    "alignment_shift_power": "自分の陣営や勝利条件が途中で変わりますか？",
    "control_power": "他人の移動や行動を直接操作できますか？",
    "restriction_power": "他人の行動や移動を制限しますか？（例: 動けない、通報不可、能力不可、スキップ不可）",
    "ranged_power": "離れた場所から能力やキルを使えますか？（例: 狙撃、投擲、ビーム）",
    "wall_piercing_power": "壁や障害物越しに能力やキルを通せますか？",
    "teleport_power": "テレポートや位置入れ替えに関わる能力ですか？",
    "cooldown_power": "キルクールや能力クールタイムを変化させますか？",
    "speed_power": "移動速度を変化させますか？",
    "movement_power": "移動方法・移動方向・足場や乗り物の動きに干渉しますか？",
    "report_power": "死体通報や緊急会議ボタンに干渉しますか？（例: 通報不可、強制会議、ポータブルボタン）",
    "vision_power": "視界を広げたり暗くしたりしますか？",
    "swap_power": "投票先・位置・役職などを入れ替えますか？",
    "extra_vote_power": "追加票や複数票を持ちますか？",
}

QUIZ_HINTS = {
    "team_crewmate": "クルー陣営の役職です。",
    "team_impostor": "インポスター陣営の役職です。",
    "team_neutral": "第三陣営の役職です。",
    "team_liberal": "リベラル陣営の役職です。",
    "modifier_role": "元の役職に追加される役職・属性です。",
    "can_kill": "キル能力に関わります。",
    "normal_kill": "通常キルに関わります。",
    "special_kill": "特殊キルに関わります。",
    "target_power": "特定の対象を選ぶ能力があります。",
    "target_kill_power": "指定対象のキルが能力や勝利条件に関わります。",
    "guard_piercing_power": "ガードや防御を貫通する能力に関わります。",
    "wave_cannon_power": "波動砲やビームに関わります。",
    "uses_vent": "ベントを使えます。",
    "can_win_alone": "単独勝利できます。",
    "additional_win": "追加勝利に関わります。",
    "can_protect": "誰かを守る能力があります。",
    "can_investigate": "情報を調べる能力があります。",
    "compare_power": "複数人の関係や陣営を比較します。",
    "meeting_ability": "会議中に強い能力を発揮します。",
    "meeting_message": "会議中や会議後に専用メッセージが出ます。",
    "has_tasks": "タスクがあります。",
    "task_based_power": "タスク進行が能力や勝利条件に関わります。",
    "extra_task_power": "追加タスクや専用タスクに関わります。",
    "death_trigger": "死亡時に能力が発動します。",
    "scheduled_death": "特定タイミングで自動死亡します。",
    "ghost_role": "死亡後や幽霊状態で使う役職です。",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わります。",
    "vote_power": "投票や会議結果に干渉します。",
    "exile_win": "追放されることが勝利条件に関わります。",
    "tracking_power": "位置や移動を追跡できます。",
    "role_info_power": "役職や陣営情報を知る能力があります。",
    "public_identity": "存在や役職が他人に分かります。",
    "fake_identity": "別陣営や別役職のように見える要素があります。",
    "dummy_power": "ダミーや分身を表示します。",
    "body_info_power": "死体・死因・死亡位置に関わります。",
    "body_clear_power": "死体を消したり処理したりできます。",
    "body_move_power": "死体を運んだり動かしたりできます。",
    "delayed_kill": "遅延キルや間接キルに関わります。",
    "disguise_or_invisible": "変身・透明化・姿の偽装に関わります。",
    "area_effect": "周囲や部屋全体に影響します。",
    "sabotage_power": "サボタージュに関わります。",
    "lights_sabotage_power": "停電サボタージュに特化しています。",
    "critical_sabotage_power": "リアクター・O2などに特化しています。",
    "door_power": "ドアに干渉します。",
    "specific_door_power": "特定の場所や設備のドアに干渉します。",
    "revenge_kill": "道連れや復讐キルに関わります。",
    "suicide_risk": "能力や条件で自滅する可能性があります。",
    "conversion_power": "他人の状態や役職を変えます。",
    "infection_power": "感染や拡散に関わります。",
    "partner_power": "特定の相手との関係に関わります。",
    "lovers_power": "ラバーズや恋人関係に関わります。",
    "alignment_shift_power": "陣営や勝利条件が途中で変わります。",
    "control_power": "他人を操作できます。",
    "restriction_power": "他人の行動や移動を制限します。",
    "ranged_power": "遠距離から能力やキルを使えます。",
    "wall_piercing_power": "壁や障害物越しに能力が通ります。",
    "teleport_power": "テレポートや位置移動に関わります。",
    "cooldown_power": "クールダウンを変化させます。",
    "speed_power": "移動速度を変化させます。",
    "movement_power": "移動方法や足場に干渉します。",
    "report_power": "通報や緊急会議ボタンに干渉します。",
    "vision_power": "視界に干渉します。",
    "swap_power": "投票先・位置・役職などを入れ替えます。",
    "extra_vote_power": "追加票や複数票に関わります。",
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


def normalize_mod_name(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "Unknown"
    key = raw.lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    compact_key = key.replace(" ", "")
    return MOD_ALIASES.get(key) or MOD_ALIASES.get(compact_key) or raw


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
            mod = normalize_mod_name(row.get("mod"))
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
    def __init__(self, user_id: int, roles: list[Role], selected_mod: str | None = None):
        self.user_id = user_id
        self.candidates = roles[:]
        self.selected_mod = selected_mod
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


def feature_signature(role: Role) -> tuple[tuple[str, bool | None], ...]:
    return tuple((key, role.features.get(key)) for key in FEATURE_QUESTIONS)


def grouped_candidate_text(roles: list[Role], limit: int = 10) -> str:
    grouped: dict[tuple[str, tuple[tuple[str, bool | None], ...]], list[Role]] = {}
    for role in roles:
        grouped.setdefault((role.display_name, feature_signature(role)), []).append(role)

    lines = []
    for (display_name, _), items in list(grouped.items())[:limit]:
        mods = " / ".join(sorted({role.mod for role in items}))
        lines.append(f"- {display_name} ({mods})")
    remaining = len(grouped) - limit
    if remaining > 0:
        lines.append(f"ほか {remaining} 種類")
    return "\n".join(lines)


def role_label(role: Role) -> str:
    if role.display_name == role.name:
        return role.display_name
    return f"{role.display_name}"


def quiz_hints_for(role: Role, max_hints: int = 5) -> list[str]:
    priority = [
        "team_crewmate",
        "team_impostor",
        "team_neutral",
        "team_liberal",
        "modifier_role",
        "ghost_role",
        "can_kill",
        "normal_kill",
        "special_kill",
        "can_win_alone",
        "additional_win",
        "meeting_ability",
        "vote_power",
        "exile_win",
        "task_based_power",
        "extra_task_power",
        "can_protect",
        "can_investigate",
        "role_info_power",
        "body_info_power",
        "conversion_power",
        "infection_power",
        "partner_power",
        "lovers_power",
        "sabotage_power",
        "door_power",
        "teleport_power",
        "cooldown_power",
        "speed_power",
        "vision_power",
        "restriction_power",
        "control_power",
        "ranged_power",
        "area_effect",
        "death_trigger",
        "suicide_risk",
    ]
    hints = [
        QUIZ_HINTS[key]
        for key in priority
        if role.features.get(key) is True and key in QUIZ_HINTS
    ]
    return hints[:max_hints] or ["この役職は、まだ詳しいヒントが少ない役職です。"]


def build_quiz_embed(answer: Role, choices: list[Role], selected_mod: str | None = None) -> discord.Embed:
    mod_line = f"対象MOD: `{selected_mod}`\n" if selected_mod else "対象MOD: `すべて`\n"
    hints = "\n".join(f"- {hint}" for hint in quiz_hints_for(answer))
    options = "\n".join(
        f"{index + 1}. {role_label(role)}"
        for index, role in enumerate(choices)
    )
    return discord.Embed(
        title="役職クイズ",
        description=(
            f"{mod_line}"
            "次のヒントに当てはまる役職を選んでください。\n\n"
            f"{hints}\n\n"
            f"{options}"
        ),
        color=0x9B59B6,
    )


def single_group_result(roles: list[Role]) -> discord.Embed | None:
    display_names = {role.display_name for role in roles}
    if len(display_names) != 1:
        return None
    signatures = {feature_signature(role) for role in roles}
    if len(signatures) != 1:
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
    signatures = {feature_signature(role) for role in roles}
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

    mod_line = f"対象MOD: `{session.selected_mod}`\n" if session.selected_mod else "対象MOD: `すべて`\n"
    embed = discord.Embed(
        title="役職当て",
        description=(
            mod_line +
            f"{FEATURE_QUESTIONS[key]}\n\n"
            f"残り候補: **{len(session.candidates)}** 件"
        ),
        color=0x3498DB,
    )
    embed.set_footer(text="質問の意味が分からない、設定次第で変わる、どちらとも言えない時は「どちらでもない/不明」を選んでください。")
    return embed


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


class QuizChoiceButton(discord.ui.Button):
    def __init__(self, index: int, role: Role):
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, QuizView):
            return
        await view.answer(interaction, self.role)


class QuizView(discord.ui.View):
    def __init__(self, user_id: int, answer: Role, choices: list[Role]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.answer_role = answer
        for index, role in enumerate(choices):
            self.add_item(QuizChoiceButton(index, role))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このクイズを始めた人だけが回答できます。", ephemeral=True)
        return False

    async def answer(self, interaction: discord.Interaction, selected: Role) -> None:
        correct = selected.name == self.answer_role.name
        color = 0x2ECC71 if correct else 0xE74C3C
        result = "正解です！" if correct else "不正解です。"
        embed = discord.Embed(
            title="役職クイズ",
            description=(
                f"{result}\n\n"
                f"答え: **{role_label(self.answer_role)}**\n"
                f"MOD: `{self.answer_role.mod}`\n"
                f"あなたの回答: **{role_label(selected)}**"
            ),
            color=color,
        )
        await interaction.response.edit_message(embed=embed, view=None)


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


async def mod_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    mods = sorted({role.mod for role in load_roles()})
    current_lower = current.lower()
    choices = [
        app_commands.Choice(name=mod, value=mod)
        for mod in mods
        if current_lower in mod.lower()
    ]
    return choices[:25]


@role_bot.tree.command(name="guess", description="Among Us系Modの役職当てを始めます")
@app_commands.describe(mod="絞り込むMOD名。未指定なら全MODから当てます")
@app_commands.autocomplete(mod=mod_autocomplete)
async def guess(interaction: discord.Interaction, mod: str | None = None):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    selected_mod = normalize_mod_name(mod) if mod else ""
    if selected_mod:
        matched_roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
        if not matched_roles:
            mods = ", ".join(sorted({role.mod for role in roles}))
            await interaction.response.send_message(
                f"`{selected_mod}` は登録されていません。\n登録MOD: {mods or 'なし'}",
                ephemeral=True,
            )
            return
        roles = matched_roles
        selected_mod = roles[0].mod
    else:
        selected_mod = None

    session = GuessSession(interaction.user.id, roles, selected_mod)
    sessions[interaction.user.id] = session
    await interaction.response.send_message(embed=session_embed(session), view=GuessView(interaction.user.id))


@role_bot.tree.command(name="quiz", description="Among Us系Modの役職クイズを出します")
@app_commands.describe(mod="出題するMOD名。未指定なら全MODから出題します")
@app_commands.autocomplete(mod=mod_autocomplete)
async def quiz(interaction: discord.Interaction, mod: str | None = None):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    selected_mod = normalize_mod_name(mod) if mod else ""
    if selected_mod:
        matched_roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
        if not matched_roles:
            mods = ", ".join(sorted({role.mod for role in roles}))
            await interaction.response.send_message(
                f"`{selected_mod}` は登録されていません。\n登録MOD: {mods or 'なし'}",
                ephemeral=True,
            )
            return
        roles = matched_roles
        selected_mod = roles[0].mod
    else:
        selected_mod = None

    unique_roles = {}
    for role in roles:
        unique_roles.setdefault((role.display_name, feature_signature(role)), role)
    quiz_roles = list(unique_roles.values())
    if len(quiz_roles) < 2:
        await interaction.response.send_message("クイズを作るには、候補役職が2件以上必要です。", ephemeral=True)
        return

    answer = random.choice(quiz_roles)
    distractors = [role for role in quiz_roles if role.name != answer.name]
    choice_count = min(4, len(quiz_roles))
    choices = random.sample(distractors, k=choice_count - 1) + [answer]
    random.shuffle(choices)

    await interaction.response.send_message(
        embed=build_quiz_embed(answer, choices, selected_mod),
        view=QuizView(interaction.user.id, answer, choices),
    )


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
