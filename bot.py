import discord
from discord.ext import commands, tasks
import os
from datetime import datetime
import asyncpg
import json

# ============================================================
# トークン読み込み
# ============================================================
TOKEN        = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN環境変数が設定されていません")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL環境変数が設定されていません")

# ============================================================
# Bot 初期化
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.polls = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
db: asyncpg.Pool = None  # DBコネクションプール

# ============================================================
# 管理者ロールチェック
# ============================================================
ADMIN_ROLE_NAME = "村長権限用"

def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id == interaction.guild.owner_id:
        return True
    return any(role.name == ADMIN_ROLE_NAME for role in interaction.user.roles)

async def check_admin(interaction: discord.Interaction) -> bool:
    if not is_admin(interaction):
        await interaction.response.send_message(
            f"❌ このコマンドは **{ADMIN_ROLE_NAME}** ロールを持つ人のみ使用できます。",
            ephemeral=True
        )
        return False
    return True

# ============================================================
# ポイント計算ロジック
# ============================================================
def calc_point_change(current_pt: int, status: str) -> int:
    if status == "投票して出席":
        return 3 if current_pt <= 4 else 2
    if status == "生存確認(DM回答済み)":
        return 3
    if status in ("欠席に投票して欠席", "投票して不参加", "投票しなくて欠席", "投票して無断遅刻"):
        return -1
    if status == "投票して無断欠席":
        return -3
    return 0

def apply_point(current_pt: int, status: str) -> int:
    return min(10, current_pt + calc_point_change(current_pt, status))

ATTEND_STATUSES = [
    "投票して出席",
    "生存確認(DM回答済み)",
    "欠席に投票して欠席",
    "投票して不参加",
    "投票しなくて欠席",
    "投票して遅刻(要件あり)",
    "投票して無断遅刻",
    "投票して無断欠席",
]

WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]

def get_badge(pt: int) -> str:
    if pt <= 0:   return "🚨 退出対象"
    if pt <= 2:   return "⚠️ 第2警告"
    if pt <= 4:   return "❗ 第1警告"
    return "✅"

# ============================================================
# DB初期化・テーブル作成
# ============================================================
async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)
    async with db.acquire() as conn:
        # メンバーテーブル
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                discord_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                pt         INTEGER NOT NULL DEFAULT 10
            )
        """)
        # 出席記録テーブル
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                discord_id TEXT NOT NULL,
                date       TEXT NOT NULL,
                status     TEXT NOT NULL,
                PRIMARY KEY (discord_id, date)
            )
        """)
        # Poll設定テーブル
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_roles (
                message_id TEXT NOT NULL,
                answer_id  TEXT NOT NULL,
                role_id    BIGINT NOT NULL,
                assign_role BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (message_id, answer_id)
            )
        """)
        # Bot設定テーブル
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
    print("✅ DB初期化完了")


# ============================================================
# DBヘルパー関数
# ============================================================
async def db_get_members() -> list[asyncpg.Record]:
    async with db.acquire() as conn:
        return await conn.fetch("SELECT * FROM members ORDER BY pt ASC")

async def db_get_member(discord_id: str) -> asyncpg.Record | None:
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM members WHERE discord_id=$1", discord_id)

async def db_upsert_member(discord_id: str, name: str, pt: int):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO members (discord_id, name, pt)
            VALUES ($1, $2, $3)
            ON CONFLICT (discord_id) DO UPDATE SET name=$2, pt=$3
        """, discord_id, name, pt)

async def db_delete_member(discord_id: str):
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM members WHERE discord_id=$1", discord_id)
        await conn.execute("DELETE FROM records WHERE discord_id=$1", discord_id)

async def db_get_records(discord_id: str) -> list[asyncpg.Record]:
    async with db.acquire() as conn:
        return await conn.fetch("SELECT * FROM records WHERE discord_id=$1 ORDER BY date DESC", discord_id)

async def db_get_record_on_date(discord_id: str, date: str) -> asyncpg.Record | None:
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM records WHERE discord_id=$1 AND date=$2", discord_id, date)

async def db_upsert_record(discord_id: str, date: str, status: str):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO records (discord_id, date, status)
            VALUES ($1, $2, $3)
            ON CONFLICT (discord_id, date) DO UPDATE SET status=$3
        """, discord_id, date, status)

async def db_get_poll_roles(message_id: str) -> list[asyncpg.Record]:
    async with db.acquire() as conn:
        return await conn.fetch("SELECT * FROM poll_roles WHERE message_id=$1", message_id)

async def db_upsert_poll_role(message_id: str, answer_id: str, role_id: int, assign_role: bool):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO poll_roles (message_id, answer_id, role_id, assign_role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (message_id, answer_id) DO UPDATE SET role_id=$3, assign_role=$4
        """, message_id, answer_id, role_id, assign_role)

async def db_delete_poll_roles(message_id: str):
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM poll_roles WHERE message_id=$1", message_id)

async def db_get_config(key: str) -> str | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM bot_config WHERE key=$1", key)
        return row["value"] if row else None

async def db_set_config(key: str, value):
    val = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_config (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value=$2
        """, key, val)


# ============================================================
# 起動
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ ログイン成功: {bot.user} (ID: {bot.user.id})")
    await init_db()

    # 登録済みメンバーの名前をDiscordの最新表示名に同期
    members = await db_get_members()
    for row in members:
        for guild in bot.guilds:
            member = guild.get_member(int(row["discord_id"]))
            if member and member.display_name != row["name"]:
                print(f"🔄 名前同期: {row['name']} → {member.display_name}")
                await db_upsert_member(row["discord_id"], member.display_name, row["pt"])

    weekly_reminder.start()
    await bot.tree.sync()
    print("✅ スラッシュコマンド同期完了")


# ============================================================
# 毎週定期リマインド
# ============================================================
@tasks.loop(minutes=1)
async def weekly_reminder():
    cfg_str = await db_get_config("reminder")
    if not cfg_str:
        return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"):
        return
    now = datetime.now()
    if now.weekday() != cfg.get("weekday", 0): return
    if now.hour    != cfg.get("hour", 20):     return
    if now.minute  != cfg.get("minute", 0):    return
    ch_id = cfg.get("channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        await ch.send(cfg.get("message", "📢 活動日です！Pollに投票して出席を記録してください！"))
        print("✅ 週次リマインド送信完了")


# ============================================================
# 新規メンバー歓迎
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    cfg_str = await db_get_config("welcome")
    if not cfg_str:
        return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"):
        return
    ch_id = cfg.get("channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if ch:
        msg = cfg.get("message", "🎉 {mention} さん、ようこそ！").replace("{mention}", member.mention)
        await ch.send(msg)


# ============================================================
# ボイスチャンネル入退室ロール
# ============================================================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    cfg_str = await db_get_config("voice_role")
    if not cfg_str:
        return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"):
        return
    role_id = cfg.get("role_id")
    if not role_id:
        return
    role = member.guild.get_role(role_id)
    if not role:
        return
    if before.channel is None and after.channel is not None:
        try:
            await member.add_roles(role, reason="VC入室")
        except discord.Forbidden:
            pass
    elif before.channel is not None and after.channel is None:
        try:
            await member.remove_roles(role, reason="VC退室")
        except discord.Forbidden:
            pass


# ============================================================
# /help
# ============================================================
@bot.tree.command(name="help", description="使えるコマンドの一覧と説明を表示します")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 コマンド一覧", color=0x534AB7)
    embed.add_field(name="\u200b", value="**🗳️ Poll・ロール機能**", inline=False)
    embed.add_field(name="/setup_poll_role 【村長権限用】", value="Pollの選択肢に投票したユーザーへ自動でロールを付与する設定をします。", inline=False)
    embed.add_field(name="/list_poll_roles", value="現在登録されているPoll→ロールの紐付け一覧を表示します。", inline=False)
    embed.add_field(name="\u200b", value="**📋 出席管理【村長権限用】**", inline=False)
    embed.add_field(name="/attend_add_member", value="メンバーを1人出席管理に追加します。", inline=False)
    embed.add_field(name="/attend_add_members_bulk", value="複数のメンバーをまとめて追加します（選択式）。", inline=False)
    embed.add_field(name="/attend_remove_member", value="メンバーを出席管理から削除します。", inline=False)
    embed.add_field(name="/attend_record", value="メンバーを1人選んで出席状況を記録します。", inline=False)
    embed.add_field(name="/attend_record_all", value="全メンバーの出席を一括記録します。", inline=False)
    embed.add_field(name="/attend_set_pt", value="ポイントを直接修正します（ミス修正用）。マイナスも可。", inline=False)
    embed.add_field(name="/attend_set_channel", value="警告通知チャンネルを設定します。", inline=False)
    embed.add_field(name="/attend_notify", value="警告対象メンバーを通知チャンネルに送信します。", inline=False)
    embed.add_field(name="/attend_kick_targets", value="退出対象（0pt以下）を表示してキックを確認します。", inline=False)
    embed.add_field(name="\u200b", value="**📊 確認コマンド（誰でも使用可）**", inline=False)
    embed.add_field(name="/attend_status", value="全メンバーの出席ポイント一覧を表示します。", inline=False)
    embed.add_field(name="/attend_warnings", value="警告対象（4pt以下）のメンバーだけを表示します。", inline=False)
    embed.add_field(name="/attend_history", value="指定メンバーの出席履歴（直近20件）を表示します。", inline=False)
    embed.add_field(name="/attend_stats", value="メンバーの出席率・欠席回数を集計して表示します。", inline=False)
    embed.add_field(name="\u200b", value="**⚙️ Bot設定【村長権限用】**", inline=False)
    embed.add_field(name="/config_reminder", value="定期リマインドの曜日・時間・メッセージを設定します。", inline=False)
    embed.add_field(name="/config_welcome", value="新規メンバー歓迎メッセージを設定します。", inline=False)
    embed.add_field(name="/config_voice_role", value="VC入室時に付与するロールを設定します。", inline=False)
    embed.add_field(name="\u200b", value="**📈 ポイント基準**", inline=False)
    embed.add_field(name="付与・減算ルール", value=(
        "✅ 投票して出席：+2pt（4pt以下なら+3pt）\n"
        "✅ 生存確認(DM回答済み)：+3pt\n"
        "➖ 欠席系（投票あり）：-1pt / 無断遅刻：-1pt\n"
        "❌ 無断欠席：-3pt\n"
        "❗ 4pt以下：第1警告 / ⚠️ 2pt以下：第2警告 / 🚨 0pt以下：退出対象"
    ), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================
# POLL ROLE 機能
# ============================================================

@bot.tree.command(name="setup_poll_role", description="【村長権限用】Pollの選択肢にロールを紐付けます（ロールは自動作成）")
@discord.app_commands.describe(
    message_id="PollのメッセージID", answer_text="投票選択肢のテキスト（完全一致）",
    role_name="作成するロール名（省略すると選択肢名と同じ）", assign_role="投票したらロールを付与するか",
)
async def setup_poll_role(interaction: discord.Interaction, message_id: str, answer_text: str, role_name: str = "", assign_role: bool = True):
    if not await check_admin(interaction): return
    await interaction.response.defer(ephemeral=True)
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
    except (discord.NotFound, ValueError):
        await interaction.followup.send("❌ メッセージが見つかりません。", ephemeral=True); return
    if msg.poll is None:
        await interaction.followup.send("❌ そのメッセージにはPollがありません。", ephemeral=True); return

    answer_id = None
    for ans in msg.poll.answers:
        if ans.text == answer_text:
            answer_id = str(ans.id); break
    if answer_id is None:
        choices = "\n".join(f"• {a.text}" for a in msg.poll.answers)
        await interaction.followup.send(f"❌ 選択肢が見つかりません：\n{choices}", ephemeral=True); return

    final_role_name = role_name.strip() if role_name.strip() else answer_text
    role = discord.utils.get(interaction.guild.roles, name=final_role_name)
    if role is None:
        role = await interaction.guild.create_role(name=final_role_name, mentionable=True, reason=f"Poll投票ロール自動作成")
        created_msg = f"✨ ロール **{final_role_name}** を新規作成しました"
    else:
        if not role.mentionable: await role.edit(mentionable=True)
        created_msg = f"ℹ️ 既存ロール **{final_role_name}** を使用します"

    await db_upsert_poll_role(message_id, answer_id, role.id, assign_role)
    assign_str = "✅ ロール付与: あり" if assign_role else "⛔ ロール付与: なし"
    await interaction.followup.send(f"{created_msg}\n「{answer_text}」→ **{final_role_name}** を紐付けました\n{assign_str}", ephemeral=True)


@bot.tree.command(name="list_poll_roles", description="登録済みのPoll→ロール一覧を表示")
async def list_poll_roles(interaction: discord.Interaction):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM poll_roles")
    if not rows:
        await interaction.response.send_message("登録されているPollロール紐付けはありません。", ephemeral=True); return
    lines = []
    from itertools import groupby
    msg_ids = {}
    for row in rows:
        msg_ids.setdefault(row["message_id"], []).append(row)
    for msg_id, items in msg_ids.items():
        lines.append(f"📋 メッセージID: `{msg_id}`")
        for item in items:
            role = interaction.guild.get_role(item["role_id"])
            role_name = role.name if role else f"ID:{item['role_id']}(削除済み)"
            lines.append(f"  └ 選択肢ID `{item['answer_id']}` → **{role_name}** ({'付与あり' if item['assign_role'] else '付与なし'})")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.event
async def on_raw_poll_vote_add(payload: discord.RawPollVoteActionEvent):
    msg_id = str(payload.message_id)
    ans_id = str(payload.answer_id)
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM poll_roles WHERE message_id=$1 AND answer_id=$2", msg_id, ans_id)
    if row is None or not row["assign_role"]: return
    guild = bot.get_guild(payload.guild_id)
    if guild is None: return
    member = guild.get_member(payload.user_id)
    if member is None or member.bot: return
    role = guild.get_role(row["role_id"])
    if role is None: print(f"⚠️ ロールID {row['role_id']} が見つかりません"); return
    try:
        await member.add_roles(role, reason="Poll投票によるロール付与")
        print(f"✅ {member.display_name} に {role.name} を付与")
    except discord.Forbidden:
        print(f"❌ ロール付与権限なし")


@bot.event
async def on_raw_poll_vote_remove(payload: discord.RawPollVoteActionEvent):
    msg_id = str(payload.message_id)
    ans_id = str(payload.answer_id)
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM poll_roles WHERE message_id=$1 AND answer_id=$2", msg_id, ans_id)
    if row is None or not row["assign_role"]: return
    guild = bot.get_guild(payload.guild_id)
    if guild is None: return
    member = guild.get_member(payload.user_id)
    if member is None or member.bot: return
    role = guild.get_role(row["role_id"])
    if role is None: return
    try:
        await member.remove_roles(role, reason="Poll投票取り消しによるロール削除")
        print(f"🗑️ {member.display_name} から {role.name} を削除")
    except discord.Forbidden:
        print(f"❌ ロール削除権限なし")


@bot.event
async def on_poll_finish(poll: discord.Poll):
    try:
        message = await poll.channel.fetch_message(poll.message.id)
        msg_id = str(message.id)
    except Exception: return
    rows = await db_get_poll_roles(msg_id)
    if not rows: return
    deleted_roles = []
    for row in rows:
        role = poll.message.guild.get_role(row["role_id"])
        if role:
            try:
                await role.delete(reason="Poll終了によるロール自動削除")
                deleted_roles.append(role.name)
            except discord.Forbidden: pass
    await db_delete_poll_roles(msg_id)
    if deleted_roles:
        try:
            await poll.channel.send(f"📢 Pollが終了しました。以下のロールを削除しました：{', '.join(f'**{r}**' for r in deleted_roles)}")
        except Exception: pass


# ============================================================
# 出席管理機能
# ============================================================

@bot.tree.command(name="attend_set_channel", description="【村長権限用】出席管理の通知チャンネルを現在のチャンネルに設定します")
async def attend_set_channel(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    await db_set_config("notify_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(f"✅ 通知チャンネルを {interaction.channel.mention} に設定しました。", ephemeral=True)


@bot.tree.command(name="attend_add_member", description="【村長権限用】出席管理にメンバーを1人追加します")
@discord.app_commands.describe(member="追加するメンバー", initial_pt="初期ポイント（デフォルト: 10）")
async def attend_add_member(interaction: discord.Interaction, member: discord.Member, initial_pt: int = 10):
    if not await check_admin(interaction): return
    uid = str(member.id)
    existing = await db_get_member(uid)
    if existing:
        await interaction.response.send_message(f"⚠️ {member.display_name} は既に登録されています。", ephemeral=True); return
    await db_upsert_member(uid, member.display_name, initial_pt)
    await interaction.response.send_message(f"✅ {member.display_name} を追加しました（{initial_pt}pt）", ephemeral=True)


@bot.tree.command(name="attend_add_members_bulk", description="【村長権限用】メンバーを選択して一括で出席管理に追加します")
@discord.app_commands.describe(initial_pt="初期ポイント（デフォルト: 10）")
async def attend_add_members_bulk(interaction: discord.Interaction, initial_pt: int = 10):
    if not await check_admin(interaction): return
    existing_ids = {row["discord_id"] for row in await db_get_members()}
    options = [
        discord.SelectOption(label=m.display_name, value=str(m.id))
        for m in interaction.guild.members if not m.bot and str(m.id) not in existing_ids
    ]
    if not options:
        await interaction.response.send_message("✅ 全員すでに登録済みです。", ephemeral=True); return
    options = options[:25]

    class MemberMultiSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="追加するメンバーを選択（複数可）", options=options, min_values=1, max_values=len(options))
        async def callback(self, interaction2: discord.Interaction):
            added = []
            for uid in self.values:
                m = interaction2.guild.get_member(int(uid))
                if m is None: continue
                await db_upsert_member(uid, m.display_name, initial_pt)
                added.append(m.display_name)
            await interaction2.response.send_message(f"✅ **{len(added)}人** を追加しました！\n" + "、".join(added), ephemeral=True)

    view = discord.ui.View(timeout=120)
    view.add_item(MemberMultiSelect())
    await interaction.response.send_message("追加するメンバーを選んでください（複数選択可）：", view=view, ephemeral=True)


@bot.tree.command(name="attend_remove_member", description="【村長権限用】出席管理からメンバーを削除します")
@discord.app_commands.describe(member="削除するメンバー")
async def attend_remove_member(interaction: discord.Interaction, member: discord.Member):
    if not await check_admin(interaction): return
    uid = str(member.id)
    existing = await db_get_member(uid)
    if not existing:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True); return
    await db_delete_member(uid)
    await interaction.response.send_message(f"🗑️ {member.display_name} を削除しました。", ephemeral=True)


# ── 個別出席記録 ──────────────────────────────────────────────

class AttendStatusSelect(discord.ui.Select):
    def __init__(self, uid: str, name: str, date: str, current_pt: int):
        self.uid        = uid
        self.date       = date
        self.current_pt = current_pt
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=f"{name} の出席状況を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        # 二重登録チェック
        existing_record = await db_get_record_on_date(self.uid, self.date)
        if existing_record:
            await interaction.response.send_message(
                f"⚠️ **{self.date}** の記録は既に登録されています（{existing_record['status']}）。\nミス修正は `/attend_set_pt` を使ってください。",
                ephemeral=True
            ); return

        status = self.values[0]
        row    = await db_get_member(self.uid)
        if row is None:
            await interaction.response.send_message("❌ メンバーが見つかりません。", ephemeral=True); return

        change = calc_point_change(row["pt"], status)
        new_pt = apply_point(row["pt"], status)
        await db_upsert_member(self.uid, row["name"], new_pt)
        await db_upsert_record(self.uid, self.date, status)
        sign = f"+{change}" if change >= 0 else str(change)
        await interaction.response.send_message(
            f"✅ **{row['name']}** | {status} → {sign}pt → **{new_pt}pt** {get_badge(new_pt)}",
            ephemeral=True
        )


class AttendRecordView(discord.ui.View):
    def __init__(self, uid: str, name: str, date: str, current_pt: int):
        super().__init__(timeout=300)
        self.add_item(AttendStatusSelect(uid, name, date, current_pt))


@bot.tree.command(name="attend_record", description="【村長権限用】メンバーを選択して出席を記録します")
@discord.app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
async def attend_record(interaction: discord.Interaction, date: str = ""):
    if not await check_admin(interaction): return
    members = await db_get_members()
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True); return
    record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
    options = [
        discord.SelectOption(label=row["name"], value=row["discord_id"], description=f"現在: {row['pt']}pt")
        for row in members
    ]

    class MemberSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="メンバーを選択", options=options[:25])
        async def callback(self, interaction2: discord.Interaction):
            uid = self.values[0]
            row = await db_get_member(uid)
            view2 = AttendRecordView(uid, row["name"], record_date, row["pt"])
            await interaction2.response.send_message(
                f"📋 **{row['name']}** の出席記録（{record_date}）\n現在: **{row['pt']}pt**",
                view=view2, ephemeral=True
            )

    view = discord.ui.View(timeout=120)
    view.add_item(MemberSelect())
    await interaction.response.send_message(f"📋 出席記録（{record_date}）\nメンバーを選んでください：", view=view, ephemeral=True)


# ── 一括出席記録 ──────────────────────────────────────────────

class BulkAttendSelect(discord.ui.Select):
    def __init__(self, uid: str, placeholder: str, parent_view, row_num: int):
        self.uid         = uid
        self.parent_view = parent_view
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=placeholder, options=options, row=row_num)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selections[self.uid] = self.values[0]
        await interaction.response.defer()


class BulkAttendView(discord.ui.View):
    def __init__(self, record_date: str, member_list: list, page: int = 0, selections: dict = None):
        super().__init__(timeout=600)
        self.record_date = record_date
        self.member_list = member_list
        self.page        = page
        self.selections  = selections if selections is not None else {}

        total_pages  = max(1, (len(member_list) - 1) // 4 + 1)
        start        = page * 4
        end          = min(start + 4, len(member_list))

        for i, (uid, name, pt) in enumerate(member_list[start:end]):
            already = self.selections.get(uid, "")
            ph = f"{name}（{pt}pt）" + (f" ✅{already[:6]}" if already else "")
            self.add_item(BulkAttendSelect(uid, ph[:100], self, row_num=i))

        if page > 0:
            prev_btn = discord.ui.Button(label="← 前へ", style=discord.ButtonStyle.secondary, row=4)
            async def prev_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, p - 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        if end < len(member_list):
            next_btn = discord.ui.Button(label="次へ →", style=discord.ButtonStyle.primary, row=4)
            async def next_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, p + 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            next_btn.callback = next_cb
            self.add_item(next_btn)

        save_btn = discord.ui.Button(label="✅ 保存する", style=discord.ButtonStyle.success, row=4)
        async def save_cb(inter: discord.Interaction):
            if not self.selections:
                await inter.response.send_message("❌ 少なくとも1人の出席状況を選択してください。", ephemeral=True); return
            results = []
            skipped = []
            for uid, status in self.selections.items():
                row = await db_get_member(uid)
                if row is None: continue
                # 二重登録チェック
                existing = await db_get_record_on_date(uid, record_date)
                if existing:
                    skipped.append(f"{row['name']}（登録済み）")
                    continue
                change = calc_point_change(row["pt"], status)
                new_pt = apply_point(row["pt"], status)
                await db_upsert_member(uid, row["name"], new_pt)
                await db_upsert_record(uid, record_date, status)
                sign = f"+{change}" if change >= 0 else str(change)
                results.append(f"• **{row['name']}** : {status} → {sign}pt → **{new_pt}pt**")
            msg = f"✅ **{record_date}** の記録が完了しました！\n\n" + "\n".join(results)
            if skipped:
                msg += f"\n\n⚠️ 登録済みのためスキップ: {', '.join(skipped)}"
            await inter.response.send_message(msg, ephemeral=True)
        save_btn.callback = save_cb
        self.add_item(save_btn)

    def content(self) -> str:
        total_pages = max(1, (len(self.member_list) - 1) // 4 + 1)
        return (
            f"📋 **{self.record_date}** の一括出席記録 （{self.page + 1}/{total_pages}ページ）\n"
            f"選択済み: {len(self.selections)}人 ／ 全{len(self.member_list)}人\n"
            f"※同じ日付はスキップされます\n"
            f"各メンバーの出席状況を選んで「✅ 保存する」を押してください："
        )


@bot.tree.command(name="attend_record_all", description="【村長権限用】全メンバーの出席を一括で記録します")
@discord.app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
async def attend_record_all(interaction: discord.Interaction, date: str = ""):
    if not await check_admin(interaction): return
    members = await db_get_members()
    if not members:
        await interaction.response.send_message("登録メンバーがいません。先に /attend_add_members_bulk でメンバーを登録してください。", ephemeral=True); return
    record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
    member_list = [(row["discord_id"], row["name"], row["pt"]) for row in members]
    view = BulkAttendView(record_date, member_list, page=0)
    await interaction.response.send_message(view.content(), view=view, ephemeral=True)


# ── ポイント確認・通知 ────────────────────────────────────────

@bot.tree.command(name="attend_status", description="出席ポイント一覧を表示します")
async def attend_status(interaction: discord.Interaction):
    members = await db_get_members()
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True); return
    lines = ["**📊 出席ポイント一覧**\n"]
    for row in members:
        lines.append(f"{get_badge(row['pt'])} <@{row['discord_id']}> **{row['name']}** : **{row['pt']}pt**")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_warnings", description="警告対象のメンバーだけを表示します")
async def attend_warnings(interaction: discord.Interaction):
    members = await db_get_members()
    warnings = [
        f"{get_badge(row['pt'])} <@{row['discord_id']}> **{row['name']}** : **{row['pt']}pt**"
        for row in members if row["pt"] <= 4
    ]
    lines = ["**⚠️ 警告対象メンバー一覧**\n"] + warnings if warnings else ["✅ 現在、警告対象のメンバーはいません。"]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_notify", description="【村長権限用】警告対象メンバーを通知チャンネルに送信します")
async def attend_notify(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    members  = await db_get_members()
    ch_id_str = await db_get_config("notify_channel_id")
    warnings = [
        f"{get_badge(row['pt'])} <@{row['discord_id']}> **{row['name']}** : **{row['pt']}pt**"
        for row in members if row["pt"] <= 4
    ]
    msg = "📢 **出席ポイント警告通知**\n"
    msg += "\n".join(warnings) if warnings else "✅ 現在、警告対象のメンバーはいません。"
    if ch_id_str:
        ch = bot.get_channel(int(ch_id_str))
        if ch:
            await ch.send(msg)
            await interaction.response.send_message("✅ 通知チャンネルに送信しました。", ephemeral=True); return
    await interaction.response.send_message(msg)


@bot.tree.command(name="attend_set_pt", description="【村長権限用】メンバーのポイントをミス修正などで直接設定します")
@discord.app_commands.describe(member="対象メンバー", pt="設定するポイント（マイナスも可）")
async def attend_set_pt(interaction: discord.Interaction, member: discord.Member, pt: int):
    if not await check_admin(interaction): return
    uid = str(member.id)
    row = await db_get_member(uid)
    if row is None:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True); return
    new_pt = min(10, pt)
    await db_upsert_member(uid, row["name"], new_pt)
    await interaction.response.send_message(
        f"✅ **{member.display_name}** のポイントを **{row['pt']}pt → {new_pt}pt** に変更しました。{get_badge(new_pt)}",
        ephemeral=True
    )


@bot.tree.command(name="attend_history", description="メンバーの出席履歴を表示します")
@discord.app_commands.describe(member="対象メンバー")
async def attend_history(interaction: discord.Interaction, member: discord.Member):
    uid  = str(member.id)
    row  = await db_get_member(uid)
    if row is None:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True); return
    records = await db_get_records(uid)
    if not records:
        await interaction.response.send_message(f"**{row['name']}** の記録はまだありません。", ephemeral=True); return
    lines = [f"**📅 {row['name']} の出席履歴** (現在: {row['pt']}pt)\n"]
    for rec in records[:20]:
        lines.append(f"• {rec['date']} : {rec['status']}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="attend_stats", description="メンバーの出席率・欠席回数を集計して表示します")
async def attend_stats(interaction: discord.Interaction):
    members = await db_get_members()
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True); return
    lines = ["**📈 出席率集計**\n"]
    for row in sorted(members, key=lambda r: r["pt"], reverse=True):
        records = await db_get_records(row["discord_id"])
        total   = len(records)
        if total == 0:
            lines.append(f"• **{row['name']}** : 記録なし（{row['pt']}pt）"); continue
        attend  = sum(1 for r in records if "出席" in r["status"] or "生存確認" in r["status"])
        absence = sum(1 for r in records if "欠席" in r["status"] or "不参加" in r["status"] or "無断" in r["status"])
        rate    = int(attend / total * 100)
        lines.append(f"• **{row['name']}** : 出席率 **{rate}%** （出席{attend}回 / 欠席{absence}回 / 全{total}回）{get_badge(row['pt'])}")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_kick_targets", description="【村長権限用】退出対象（0pt以下）を表示してキックを確認します")
async def attend_kick_targets(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    members = await db_get_members()
    targets = [(row["discord_id"], row["name"], row["pt"]) for row in members if row["pt"] <= 0]
    if not targets:
        await interaction.response.send_message("✅ 現在、退出対象のメンバーはいません。", ephemeral=True); return

    lines = ["**🚨 退出対象メンバー（0pt以下）**\n"]
    for uid, name, pt in targets:
        lines.append(f"• <@{uid}> **{name}** : **{pt}pt**")
    lines.append("\n以下のボタンでキックできます：")

    class KickView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            for uid, name, pt in targets[:5]:
                btn = discord.ui.Button(label=f"{name} をキック", style=discord.ButtonStyle.danger)
                async def kick_cb(inter: discord.Interaction, u=uid, n=name):
                    member = inter.guild.get_member(int(u))
                    if member is None:
                        await inter.response.send_message(f"❌ {n} はすでにサーバーにいません。", ephemeral=True); return
                    try:
                        await member.kick(reason=f"出席ポイント0pt以下 by {inter.user}")
                        await db_delete_member(u)
                        await inter.response.send_message(f"✅ **{n}** をキックしました。", ephemeral=True)
                        ch_id_str = await db_get_config("notify_channel_id")
                        if ch_id_str:
                            ch = bot.get_channel(int(ch_id_str))
                            if ch:
                                await ch.send(f"🚨 **{n}** がポイント不足によりキックされました。（実行者: {inter.user.mention}）")
                    except discord.Forbidden:
                        await inter.response.send_message(f"❌ {n} をキックする権限がありません。", ephemeral=True)
                btn.callback = kick_cb
                self.add_item(btn)

    await interaction.response.send_message("\n".join(lines), view=KickView(), ephemeral=True)


# ============================================================
# Bot設定コマンド
# ============================================================

@bot.tree.command(name="config_reminder", description="【村長権限用】定期リマインドを設定します")
@discord.app_commands.describe(enabled="リマインドを有効にするか", weekday="曜日（0=月〜6=日）", hour="時間（0〜23）", minute="分（0〜59）", message="送信するメッセージ（省略可）")
async def config_reminder(interaction: discord.Interaction, enabled: bool, weekday: int, hour: int, minute: int, message: str = ""):
    if not await check_admin(interaction): return
    cfg = {
        "enabled": enabled, "weekday": max(0, min(6, weekday)),
        "hour": max(0, min(23, hour)), "minute": max(0, min(59, minute)),
        "channel_id": interaction.channel.id,
        "message": message if message else "📢 今日は活動日です！Pollに投票して出席を記録してください！"
    }
    await db_set_config("reminder", cfg)
    status = "✅ 有効" if enabled else "⛔ 無効"
    await interaction.response.send_message(
        f"リマインド設定完了！\n状態: {status}\nタイミング: 毎週{WEEKDAY_NAMES[weekday]}曜日 {hour:02d}:{minute:02d}\nチャンネル: {interaction.channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="config_welcome", description="【村長権限用】新規メンバー歓迎メッセージを設定します")
@discord.app_commands.describe(enabled="歓迎メッセージを有効にするか", message="歓迎メッセージ（{mention}でメンションに置換）")
async def config_welcome(interaction: discord.Interaction, enabled: bool, message: str = ""):
    if not await check_admin(interaction): return
    cfg = {
        "enabled": enabled, "channel_id": interaction.channel.id,
        "message": message if message else "🎉 {mention} さん、サーバーへようこそ！"
    }
    await db_set_config("welcome", cfg)
    status = "✅ 有効" if enabled else "⛔ 無効"
    await interaction.response.send_message(f"歓迎メッセージ設定完了！\n状態: {status}\nチャンネル: {interaction.channel.mention}", ephemeral=True)


@bot.tree.command(name="config_voice_role", description="【村長権限用】VC入室時に付与するロールを設定します")
@discord.app_commands.describe(enabled="入退室ロールを有効にするか", role="入室時に付与するロール")
async def config_voice_role(interaction: discord.Interaction, enabled: bool, role: discord.Role = None):
    if not await check_admin(interaction): return
    cfg = {"enabled": enabled, "role_id": role.id if role else None}
    await db_set_config("voice_role", cfg)
    status = "✅ 有効" if enabled else "⛔ 無効"
    await interaction.response.send_message(f"VC入室ロール設定完了！\n状態: {status}\nロール: **{role.name if role else '未設定'}**", ephemeral=True)


# ============================================================
# 起動
# ============================================================
bot.run(TOKEN)
