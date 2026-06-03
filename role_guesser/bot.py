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
    "can_kill": "その役職はキルできますか？",
    "uses_vent": "その役職はベントを使えますか？",
    "can_win_alone": "その役職は単独勝利できますか？",
    "can_protect": "その役職は誰かを守る能力がありますか？",
    "can_investigate": "その役職は情報を調べる能力がありますか？",
    "meeting_ability": "その役職は会議中に強い能力を発揮しますか？",
}


@dataclass(frozen=True)
class Role:
    name: str
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
            team = (row.get("team") or "").strip().lower()
            features = {
                key: parse_bool(row.get(key))
                for key in FEATURE_QUESTIONS
                if not key.startswith("team_")
            }
            features["team_crewmate"] = team == "crewmate"
            features["team_impostor"] = team == "impostor"
            features["team_neutral"] = team == "neutral"
            roles.append(Role(name=name, mod=(row.get("mod") or "Unknown").strip(), features=features))
    return roles


def best_question(candidates: list[Role], asked: set[str]) -> str | None:
    best_key = None
    best_score = -1
    total = len(candidates)
    for key in FEATURE_QUESTIONS:
        if key in asked:
            continue
        yes_count = sum(1 for role in candidates if role.features.get(key) is True)
        no_count = sum(1 for role in candidates if role.features.get(key) is False)
        if yes_count == 0 or no_count == 0:
            continue
        score = min(yes_count, no_count) - abs((total / 2) - yes_count) * 0.01
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
        if answer is None or not self.current_question:
            return
        key = self.current_question
        self.candidates = [
            role
            for role in self.candidates
            if role.features.get(key) is None or role.features.get(key) == answer
        ]

    def next_question(self) -> str | None:
        key = best_question(self.candidates, self.asked)
        self.current_question = key
        if key:
            self.asked.add(key)
        return key


sessions: dict[int, GuessSession] = {}


def session_embed(session: GuessSession) -> discord.Embed:
    if len(session.candidates) == 0:
        return discord.Embed(
            title="役職当て",
            description="候補がなくなりました。役職データが足りないか、どこかの回答が違うかもしれません。",
            color=0xE74C3C,
        )

    if len(session.candidates) == 1:
        role = session.candidates[0]
        return discord.Embed(
            title="役職当て",
            description=f"あなたが思い浮かべた役職は **{role.name}** ですか？\nMOD: `{role.mod}`",
            color=0x2ECC71,
        )

    key = session.current_question or session.next_question()
    if not key:
        preview = "\n".join(f"- {role.name} ({role.mod})" for role in session.candidates[:10])
        more = "" if len(session.candidates) <= 10 else f"\nほか {len(session.candidates) - 10} 件"
        return discord.Embed(
            title="役職当て",
            description=f"これ以上うまく絞れませんでした。候補はこのあたりです。\n{preview}{more}",
            color=0xF1C40F,
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
        finished = len(session.candidates) <= 1 or "候補がなくなりました" in embed.description or "これ以上" in embed.description
        if finished:
            sessions.pop(self.user_id, None)
        await interaction.response.edit_message(embed=embed, view=None if finished else self)

    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, True)

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, False)

    @discord.ui.button(label="わからない", style=discord.ButtonStyle.secondary)
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
