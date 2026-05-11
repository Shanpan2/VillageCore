import discord
from discord.ext import commands, tasks
import os
from datetime import datetime
import asyncpg
import json
import random
import re
import asyncio
import google.genai as genai
import aiohttp

TOKEN        = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN環境変数が設定されていません")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL環境変数が設定されていません")

if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    ai_client = None

# ============================================================
# Bot 初期化
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.polls = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
db: asyncpg.Pool = None

# ============================================================
# 管理者ロールチェック
# ============================================================
DEFAULT_ADMIN_ROLE = "村長権限用"

async def get_admin_role_name(guild_id: int) -> str:
    cfg_str = await db_get_config(f"admin_role_{guild_id}")
    return cfg_str if cfg_str else DEFAULT_ADMIN_ROLE

async def is_admin(interaction: discord.Interaction) -> bool:
    # サーバーオーナーは常に管理者
    if interaction.user.id == interaction.guild.owner_id:
        return True
    # DBが初期化されていない場合のフォールバック
    if db is None:
        return False
    role_name = await get_admin_role_name(interaction.guild.id)
    return any(role.name == role_name for role in interaction.user.roles)

async def check_admin(interaction: discord.Interaction) -> bool:
    if not await is_admin(interaction):
        role_name = await get_admin_role_name(interaction.guild.id)
        await interaction.response.send_message(
            f"❌ このコマンドは **{role_name}** ロールを持つ人のみ使用できます。",
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                discord_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                pt         INTEGER NOT NULL DEFAULT 10
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                discord_id TEXT NOT NULL,
                date       TEXT NOT NULL,
                status     TEXT NOT NULL,
                PRIMARY KEY (discord_id, date)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_roles (
                message_id  TEXT NOT NULL,
                answer_id   TEXT NOT NULL,
                role_id     BIGINT NOT NULL,
                assign_role BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (message_id, answer_id)
            )
        """)
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
async def db_get_members():
    async with db.acquire() as conn:
        return await conn.fetch("SELECT * FROM members ORDER BY pt ASC")

async def db_get_member(discord_id: str):
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

async def db_get_records(discord_id: str):
    async with db.acquire() as conn:
        return await conn.fetch("SELECT * FROM records WHERE discord_id=$1 ORDER BY date DESC", discord_id)

async def db_get_record_on_date(discord_id: str, date: str):
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM records WHERE discord_id=$1 AND date=$2", discord_id, date)

async def db_upsert_record(discord_id: str, date: str, status: str):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO records (discord_id, date, status)
            VALUES ($1, $2, $3)
            ON CONFLICT (discord_id, date) DO UPDATE SET status=$3
        """, discord_id, date, status)

async def db_get_poll_roles(message_id: str):
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

async def db_get_config(key: str):
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
    for guild in bot.guilds:
        for row in await db_get_members():
            member = guild.get_member(int(row["discord_id"]))
            if member and member.display_name != row["name"]:
                print(f"🔄 名前同期: {row['name']} → {member.display_name}")
                await db_upsert_member(row["discord_id"], member.display_name, row["pt"])
    weekly_reminder.start()
    await bot.tree.sync()
    print("✅ スラッシュコマンド同期完了")

# ============================================================
# メッセージイベント（ダイスロール・AIメンション）
# ============================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Botメンションでアドバイス
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        content = re.sub(r"<@!?\d+>", "", message.content).strip()
        if content:
            await message.reply(
                "🤖 現在AI機能は準備中です。\n"
                "他のコマンドは `/help` で確認できます！"
            )
        return

    # xdy 形式のダイスロール
    dice_match = re.search(r"\b(\d+)d(\d+)\b", message.content.lower())
    if dice_match:
        count = int(dice_match.group(1))
        sides = int(dice_match.group(2))
        if 1 <= count <= 100 and 2 <= sides <= 1000:
            results = [random.randint(1, sides) for _ in range(count)]
            total   = sum(results)
            max_val = sides * count
            min_val = count
            if total == max_val:         comment = "🌟 **クリティカル！！** 最高の出目！"
            elif total == min_val:       comment = "💀 **ファンブル...** 最低の出目..."
            elif total >= max_val * 0.8: comment = "✨ かなりいい出目！"
            elif total <= max_val * 0.2: comment = "😰 かなり低い出目..."
            else:                        comment = "🎲 普通の出目。"
            dice_str = " + ".join(str(r) for r in results) if count > 1 else str(results[0])
            await message.reply(
                f"🎲 `{count}d{sides}` を振りました！\n"
                f"出目: {dice_str}\n"
                f"合計: **{total}** / {max_val}\n"
                f"{comment}"
            )

# #おちゃめ村タグ付きYouTubeリンクを自動転送
    if ("youtube.com" in message.content or "youtu.be" in message.content) and "#おちゃめ村" in message.content:
        target_channel = bot.get_channel(1405736791339696289)
        if target_channel and message.channel.id != target_channel.id:
            words = message.content.split()
            urls = [w for w in words if "youtube.com" in w or "youtu.be" in w]
            if urls:
                url = urls[0]
                # YouTube動画IDを抽出
                video_id = None
                if "youtube.com/watch?v=" in url:
                    video_id = url.split("v=")[1].split("&")[0]
                elif "youtu.be/" in url:
                    video_id = url.split("youtu.be/")[1].split("?")[0]

                youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
                embed = discord.Embed(color=0xFF0000)

                if video_id and youtube_api_key:
                    data = {}  # 事前に空で宣言
                    try:
                        api_url = (
                            f"https://www.googleapis.com/youtube/v3/videos"
                            f"?id={video_id}&key={youtube_api_key}"
                            f"&part=snippet"
                        )
                        async with aiohttp.ClientSession() as session:
                            async with session.get(api_url) as resp:
                                data = await resp.json()
                    except Exception as e:
                        print(f"YouTube API エラー: {e}")

                    if data.get("items"):
                        snippet = data["items"][0]["snippet"]
                        title        = snippet.get("title", "タイトル不明")
                        channel_name = snippet.get("channelTitle", "不明")
                        description  = snippet.get("description", "")
                        tags         = [w for w in description.split() if w.startswith("#")]
                        tags_str     = " ".join(tags[:10]) if tags else "なし"
                        thumbnail    = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                        embed.title  = f"🎬 {title}"
                        embed.url    = url
                        embed.add_field(name="👤 チャンネル", value=channel_name, inline=True)
                        embed.add_field(name="🏷️ 概要欄のタグ", value=tags_str, inline=False)
                        embed.set_footer(text=f"📤 {message.author.display_name} が {message.channel.name} で共有")
                        if thumbnail:
                            embed.set_image(url=thumbnail)
                    else:
                        embed.title = "📺 YouTube動画"
                        embed.url   = url
                        embed.set_footer(text=f"📤 {message.author.display_name} が共有")

                await target_channel.send(embed=embed)
                
    await bot.process_commands(message)

# ============================================================
# 毎週定期リマインド
# ============================================================
@tasks.loop(minutes=1)
async def weekly_reminder():
    cfg_str = await db_get_config("reminder")
    if not cfg_str: return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"): return
    now = datetime.now()
    if now.weekday() != cfg.get("weekday", 0): return
    if now.hour    != cfg.get("hour", 20):     return
    if now.minute  != cfg.get("minute", 0):    return
    ch_id = cfg.get("channel_id")
    if not ch_id: return
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
    if not cfg_str: return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"): return
    ch_id = cfg.get("channel_id")
    if not ch_id: return
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
    if not cfg_str: return
    cfg = json.loads(cfg_str)
    if not cfg.get("enabled"): return
    role_id = cfg.get("role_id")
    if not role_id: return
    role = member.guild.get_role(role_id)
    if not role: return
    if before.channel is None and after.channel is not None:
        try: await member.add_roles(role, reason="VC入室")
        except discord.Forbidden: pass
    elif before.channel is not None and after.channel is None:
        try: await member.remove_roles(role, reason="VC退室")
        except discord.Forbidden: pass

# ============================================================
# /help
# ============================================================
@bot.tree.command(name="help", description="使えるコマンドの一覧と説明を表示します")
async def help_command(interaction: discord.Interaction):
    role_name = await get_admin_role_name(interaction.guild.id)
    embed = discord.Embed(title="📖 コマンド一覧", color=0x534AB7)
    embed.add_field(name="\u200b", value=f"**現在の管理者ロール: `{role_name}`**", inline=False)
    embed.add_field(name="\u200b", value="**🗳️ Poll・ロール機能**", inline=False)
    embed.add_field(name="/setup_poll_role 【管理者】", value="Pollの選択肢に投票したユーザーへ自動でロールを付与する設定をします。", inline=False)
    embed.add_field(name="/list_poll_roles", value="現在登録されているPoll→ロールの紐付け一覧を表示します。", inline=False)
    embed.add_field(name="\u200b", value="**📋 出席管理【管理者】**", inline=False)
    embed.add_field(name="/attend_add_member", value="メンバーを1人出席管理に追加します。", inline=False)
    embed.add_field(name="/attend_add_members_bulk", value="複数のメンバーをまとめて追加します（選択式）。", inline=False)
    embed.add_field(name="/attend_remove_member", value="メンバーを出席管理から削除します。", inline=False)
    embed.add_field(name="/attend_record", value="メンバーを1人選んで出席状況を記録します。", inline=False)
    embed.add_field(name="/attend_record_all", value="全メンバーの出席を一括記録します。", inline=False)
    embed.add_field(name="/attend_set_pt", value="ポイントを直接修正します（ミス修正用・マイナスも可）。", inline=False)
    embed.add_field(name="/attend_set_channel", value="警告通知チャンネルを設定します。", inline=False)
    embed.add_field(name="/attend_notify", value="警告対象メンバーを通知チャンネルに送信します。", inline=False)
    embed.add_field(name="/attend_kick_targets", value="退出対象（0pt以下）を表示してキックを確認します。", inline=False)
    embed.add_field(name="\u200b", value="**📊 確認コマンド（誰でも使用可）**", inline=False)
    embed.add_field(name="/attend_status", value="全メンバーの出席ポイント一覧を表示します。", inline=False)
    embed.add_field(name="/attend_warnings", value="警告対象（4pt以下）のメンバーだけを表示します。", inline=False)
    embed.add_field(name="/attend_history", value="指定メンバーの出席履歴（直近20件）を表示します。", inline=False)
    embed.add_field(name="/attend_stats", value="メンバーの出席率・欠席回数を集計して表示します。", inline=False)
    embed.add_field(name="\u200b", value="**🎮 楽しいコマンド**", inline=False)
    embed.add_field(name="xdy（例: 2d6）", value="メッセージに打つだけでダイスロール！", inline=False)
    embed.add_field(name="/roll 2d6", value="スラッシュコマンドでダイスロール。", inline=False)
    embed.add_field(name="/omikuji", value="おみくじを引きます！大吉〜大凶。", inline=False)
    embed.add_field(name="/janken", value="Botとじゃんけん対決！", inline=False)
    embed.add_field(name="/choose A B C", value="選択肢からランダムに1つ選びます。", inline=False)
    embed.add_field(name="/timer 60", value="カウントダウンタイマー（最大300秒）。終了時にあなたをメンション。", inline=False)
    embed.add_field(name="/meigen", value="村の名言をランダム表示。", inline=False)
    embed.add_field(name="/meigen_add 【管理者】", value="オリジナル名言を追加します。", inline=False)
    embed.add_field(name="@Bot名 質問", value="BotをメンションするとAIが回答します！", inline=False)
    embed.add_field(name="\u200b", value="**⚙️ Bot設定【管理者】**", inline=False)
    embed.add_field(name="/config_admin_role", value="管理者ロール名を変更します。", inline=False)
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
# 管理者ロール設定
# ============================================================
@bot.tree.command(name="config_admin_role", description="管理者ロールを設定します（サーバーオーナーまたは現在の管理者ロールを持つ人）")
@discord.app_commands.describe(role="管理者として設定するロール")
async def config_admin_role(interaction: discord.Interaction, role: discord.Role):
    # サーバーオーナーまたは現在の管理者ロールを持つ人が設定可能
    is_owner = interaction.user.id == interaction.guild.owner_id
    current_role_name = await get_admin_role_name(interaction.guild.id)
    has_admin_role = any(r.name == current_role_name for r in interaction.user.roles)
    # Discordのサーバー管理権限を持つ人も設定可能
    has_manage_guild = interaction.user.guild_permissions.manage_guild

    if not (is_owner or has_admin_role or has_manage_guild):
        await interaction.response.send_message(
            "❌ このコマンドはサーバーオーナー・管理者ロール・サーバー管理権限を持つ人のみ使用できます。",
            ephemeral=True
        )
        return
    await db_set_config(f"admin_role_{interaction.guild.id}", role.name)
    await interaction.response.send_message(
        f"✅ 管理者ロールを **{role.name}** に設定しました！\nこのロールを持つ人が管理者コマンドを使えます。",
        ephemeral=True
    )

# ============================================================
# POLL ROLE 機能
# ============================================================
@bot.tree.command(name="setup_poll_role", description="【管理者】Pollの選択肢にロールを紐付けます（ロールは自動作成）")
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
        role = await interaction.guild.create_role(name=final_role_name, mentionable=True, reason="Poll投票ロール自動作成")
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
@bot.tree.command(name="attend_set_channel", description="【管理者】出席管理の通知チャンネルを現在のチャンネルに設定します")
async def attend_set_channel(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    await db_set_config("notify_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(f"✅ 通知チャンネルを {interaction.channel.mention} に設定しました。", ephemeral=True)


@bot.tree.command(name="attend_add_member", description="【管理者】出席管理にメンバーを1人追加します")
@discord.app_commands.describe(member="追加するメンバー", initial_pt="初期ポイント（デフォルト: 10）")
async def attend_add_member(interaction: discord.Interaction, member: discord.Member, initial_pt: int = 10):
    if not await check_admin(interaction): return
    uid = str(member.id)
    if await db_get_member(uid):
        await interaction.response.send_message(f"⚠️ {member.display_name} は既に登録されています。", ephemeral=True); return
    await db_upsert_member(uid, member.display_name, initial_pt)
    await interaction.response.send_message(f"✅ {member.display_name} を追加しました（{initial_pt}pt）", ephemeral=True)


@bot.tree.command(name="attend_add_members_bulk", description="【管理者】メンバーを選択して一括で出席管理に追加します")
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


@bot.tree.command(name="attend_remove_member", description="【管理者】出席管理からメンバーを削除します")
@discord.app_commands.describe(member="削除するメンバー")
async def attend_remove_member(interaction: discord.Interaction, member: discord.Member):
    if not await check_admin(interaction): return
    uid = str(member.id)
    if not await db_get_member(uid):
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True); return
    await db_delete_member(uid)
    await interaction.response.send_message(f"🗑️ {member.display_name} を削除しました。", ephemeral=True)


class AttendStatusSelect(discord.ui.Select):
    def __init__(self, uid: str, name: str, date: str, current_pt: int):
        self.uid = uid
        self.date = date
        self.current_pt = current_pt
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=f"{name} の出席状況を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        existing = await db_get_record_on_date(self.uid, self.date)
        if existing:
            await interaction.response.send_message(
                f"⚠️ **{self.date}** の記録は既に登録されています（{existing['status']}）。\nミス修正は `/attend_set_pt` を使ってください。",
                ephemeral=True
            ); return
        status = self.values[0]
        row = await db_get_member(self.uid)
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


@bot.tree.command(name="attend_record", description="【管理者】メンバーを選択して出席を記録します")
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


class BulkAttendSelect(discord.ui.Select):
    def __init__(self, uid: str, placeholder: str, parent_view, row_num: int):
        self.uid = uid
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
        self.page = page
        self.selections = selections if selections is not None else {}

        total_pages = max(1, (len(member_list) - 1) // 4 + 1)
        start = page * 4
        end   = min(start + 4, len(member_list))

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
                existing = await db_get_record_on_date(uid, record_date)
                if existing:
                    skipped.append(f"{row['name']}（登録済み）"); continue
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


@bot.tree.command(name="attend_record_all", description="【管理者】全メンバーの出席を一括で記録します")
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


@bot.tree.command(name="attend_status", description="出席ポイント一覧を表示します")
async def attend_status(interaction: discord.Interaction):
    members = await db_get_members()
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True); return
    lines = ["**📊 出席ポイント一覧**\n"]
    for row in members:
        # メンションのみ表示（名前の重複なし）
        lines.append(f"{get_badge(row['pt'])} <@{row['discord_id']}> : **{row['pt']}pt**")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_warnings", description="警告対象のメンバーだけを表示します")
async def attend_warnings(interaction: discord.Interaction):
    members  = await db_get_members()
    warnings = [
        f"{get_badge(row['pt'])} <@{row['discord_id']}> : **{row['pt']}pt**"
        for row in members if row["pt"] <= 4
    ]
    lines = ["**⚠️ 警告対象メンバー一覧**\n"] + warnings if warnings else ["✅ 現在、警告対象のメンバーはいません。"]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_notify", description="【管理者】警告対象メンバーを通知チャンネルに送信します")
async def attend_notify(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    members   = await db_get_members()
    ch_id_str = await db_get_config("notify_channel_id")
    warnings  = [
        f"{get_badge(row['pt'])} <@{row['discord_id']}> : **{row['pt']}pt**"
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


@bot.tree.command(name="attend_set_pt", description="【管理者】メンバーのポイントをミス修正などで直接設定します")
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
    uid     = str(member.id)
    row     = await db_get_member(uid)
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
            lines.append(f"• <@{row['discord_id']}> : 記録なし（{row['pt']}pt）"); continue
        attend  = sum(1 for r in records if "出席" in r["status"] or "生存確認" in r["status"])
        absence = sum(1 for r in records if "欠席" in r["status"] or "不参加" in r["status"] or "無断" in r["status"])
        rate    = int(attend / total * 100)
        lines.append(f"• <@{row['discord_id']}> : 出席率 **{rate}%** （出席{attend}回 / 欠席{absence}回）{get_badge(row['pt'])}")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_kick_targets", description="【管理者】退出対象（0pt以下）を表示してキックを確認します")
async def attend_kick_targets(interaction: discord.Interaction):
    if not await check_admin(interaction): return
    members = await db_get_members()
    targets = [(row["discord_id"], row["name"], row["pt"]) for row in members if row["pt"] <= 0]
    if not targets:
        await interaction.response.send_message("✅ 現在、退出対象のメンバーはいません。", ephemeral=True); return
    lines = ["**🚨 退出対象メンバー（0pt以下）**\n"]
    for uid, name, pt in targets:
        lines.append(f"• <@{uid}> : **{pt}pt**")
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
@bot.tree.command(name="config_reminder", description="【管理者】定期リマインドを設定します")
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


@bot.tree.command(name="config_welcome", description="【管理者】新規メンバー歓迎メッセージを設定します")
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


@bot.tree.command(name="config_voice_role", description="【管理者】VC入室時に付与するロールを設定します")
@discord.app_commands.describe(enabled="入退室ロールを有効にするか", role="入室時に付与するロール")
async def config_voice_role(interaction: discord.Interaction, enabled: bool, role: discord.Role = None):
    if not await check_admin(interaction): return
    cfg = {"enabled": enabled, "role_id": role.id if role else None}
    await db_set_config("voice_role", cfg)
    status = "✅ 有効" if enabled else "⛔ 無効"
    await interaction.response.send_message(f"VC入室ロール設定完了！\n状態: {status}\nロール: **{role.name if role else '未設定'}**", ephemeral=True)

# ============================================================
# 🎲 ダイスロール（スラッシュコマンド版）
# ============================================================
@bot.tree.command(name="roll", description="ダイスを振ります。例: /roll 2d6 → 6面ダイスを2個")
@discord.app_commands.describe(dice="ダイスの形式（例: 2d6, 1d20, 3d8）")
async def roll_dice(interaction: discord.Interaction, dice: str):
    match = re.fullmatch(r"(\d+)d(\d+)", dice.strip().lower())
    if not match:
        await interaction.response.send_message("❌ 形式が正しくありません。例: `2d6`、`1d20`", ephemeral=True); return
    count = int(match.group(1))
    sides = int(match.group(2))
    if count < 1 or count > 100:
        await interaction.response.send_message("❌ ダイスの数は1〜100にしてください。", ephemeral=True); return
    if sides < 2 or sides > 1000:
        await interaction.response.send_message("❌ 面数は2〜1000にしてください。", ephemeral=True); return
    results = [random.randint(1, sides) for _ in range(count)]
    total   = sum(results)
    max_val = sides * count
    min_val = count
    if total == max_val:         comment = "🌟 **クリティカル！！** 最高の出目！"
    elif total == min_val:       comment = "💀 **ファンブル...** 最低の出目..."
    elif total >= max_val * 0.8: comment = "✨ かなりいい出目！"
    elif total <= max_val * 0.2: comment = "😰 かなり低い出目..."
    else:                        comment = "🎲 普通の出目。"
    dice_str = " + ".join(str(r) for r in results) if count > 1 else str(results[0])
    await interaction.response.send_message(
        f"🎲 **{interaction.user.display_name}** が `{dice}` を振りました！\n"
        f"出目: {dice_str}\n合計: **{total}** / {max_val}\n{comment}"
    )

# ============================================================
# 🎋 おみくじ
# ============================================================
OMIKUJI_LIST = [
    ("大吉", "🌟", "最高の運勢です！何事も積極的に挑戦しましょう！村の活動も絶好調になるでしょう！"),
    ("中吉", "✨", "良い運勢です。努力が実を結ぶ時期。今日も元気に活動しましょう！"),
    ("小吉", "🌸", "まずまずの運勢。地道な努力が大切。村人との絆を大切に！"),
    ("吉",   "🍀", "平穏な一日になりそう。焦らずゆっくり進みましょう。"),
    ("末吉", "🌿", "運勢は後から上向きに。今は準備期間と考えて！"),
    ("凶",   "⚠️", "少し注意が必要な日。慎重に行動しましょう。無断欠席には気をつけて！"),
    ("大凶", "💀", "今日は慎重に！でも大丈夫、明日はきっと良くなります。出席だけは忘れずに！"),
]
OMIKUJI_WEIGHTS = [10, 20, 20, 25, 15, 7, 3]

@bot.tree.command(name="omikuji", description="おみくじを引きます！今日の運勢は？（1日1回）")
async def omikuji(interaction: discord.Interaction):
    # 1日1回チェック
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"omikuji_{interaction.user.id}_{today}"
    already = await db_get_config(key)
    if already:
        result, emoji, _ = next((o for o in OMIKUJI_LIST if o[0] == already), ("？", "🎋", ""))
        await interaction.response.send_message(
            f"⚠️ 今日はもうおみくじを引いています！\n今日の結果: **{emoji} {already}**\nまた明日引いてね！",
            ephemeral=True
        )
        return

    result, emoji, message = random.choices(OMIKUJI_LIST, weights=OMIKUJI_WEIGHTS, k=1)[0]
    await db_set_config(key, result)

    color_map = {
        "大吉": 0xFFD700, "中吉": 0xFF69B4, "小吉": 0x98FB98,
        "吉": 0x87CEEB, "末吉": 0xDDA0DD, "凶": 0xFFA500, "大凶": 0xFF4500
    }
    embed = discord.Embed(title=f"{emoji} {result}", description=message, color=color_map.get(result, 0x534AB7))
    embed.set_author(name=f"{interaction.user.display_name} のおみくじ結果")
    embed.set_footer(text="また明日も引いてみてね！")
    await interaction.response.send_message(embed=embed)

# ============================================================
# ✊ じゃんけん
# ============================================================
JANKEN_HANDS = {"グー": "✊", "チョキ": "✌️", "パー": "🖐️"}
JANKEN_WINS  = {"グー": "チョキ", "チョキ": "パー", "パー": "グー"}

class JankenView(discord.ui.View):
    def __init__(self, challenger: discord.Member):
        super().__init__(timeout=30)
        self.challenger = challenger

    async def resolve(self, interaction: discord.Interaction, user_hand: str):
        bot_hand   = random.choice(list(JANKEN_HANDS.keys()))
        user_emoji = JANKEN_HANDS[user_hand]
        bot_emoji  = JANKEN_HANDS[bot_hand]
        if user_hand == bot_hand:
            result = "🤝 **あいこ！** もう一度！"; color = 0x87CEEB
        elif JANKEN_WINS[user_hand] == bot_hand:
            result = "🎉 **あなたの勝ち！** やったね！"; color = 0x00C851
        else:
            result = "😈 **Botの勝ち！** 残念！"; color = 0xFF4444
        embed = discord.Embed(title="✊ じゃんけん結果", color=color)
        embed.add_field(name=f"{interaction.user.display_name}", value=f"{user_emoji} {user_hand}", inline=True)
        embed.add_field(name="Bot", value=f"{bot_emoji} {bot_hand}", inline=True)
        embed.add_field(name="結果", value=result, inline=False)
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✊ グー", style=discord.ButtonStyle.primary)
    async def goo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("他の人のじゃんけんです！", ephemeral=True); return
        await self.resolve(interaction, "グー")

    @discord.ui.button(label="✌️ チョキ", style=discord.ButtonStyle.primary)
    async def choki(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("他の人のじゃんけんです！", ephemeral=True); return
        await self.resolve(interaction, "チョキ")

    @discord.ui.button(label="🖐️ パー", style=discord.ButtonStyle.primary)
    async def paa(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("他の人のじゃんけんです！", ephemeral=True); return
        await self.resolve(interaction, "パー")


@bot.tree.command(name="janken", description="Botとじゃんけんで勝負！")
async def janken(interaction: discord.Interaction):
    embed = discord.Embed(title="✊ じゃんけん！", description="グー・チョキ・パーを選んでください！", color=0x534AB7)
    await interaction.response.send_message(embed=embed, view=JankenView(interaction.user))

# ============================================================
# 🎯 ランダム選択
# ============================================================
@bot.tree.command(name="choose", description="選択肢からランダムに1つ選びます。例: /choose ラーメン カレー 寿司")
@discord.app_commands.describe(choices="スペース区切りで選択肢を入力（例: A B C）")
async def choose(interaction: discord.Interaction, choices: str):
    items = [c.strip() for c in choices.split() if c.strip()]
    if len(items) < 2:
        await interaction.response.send_message("❌ 選択肢を2つ以上スペースで区切って入力してください。", ephemeral=True); return
    if len(items) > 20:
        await interaction.response.send_message("❌ 選択肢は20個までです。", ephemeral=True); return
    chosen = random.choice(items)
    embed  = discord.Embed(title="🎯 ランダム選択", color=0x534AB7)
    embed.add_field(name="選択肢", value=" / ".join(items), inline=False)
    embed.add_field(name="選ばれたのは...", value=f"# **{chosen}** 🎉", inline=False)
    embed.set_footer(text=f"選んだ人: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

# ============================================================
# ⏱️ カウントダウンタイマー
# ============================================================
@bot.tree.command(name="timer", description="カウントダウンタイマーを開始します")
@discord.app_commands.describe(seconds="秒数（最大300秒）", message="終了時のメッセージ（省略可）")
async def timer(interaction: discord.Interaction, seconds: int, message: str = ""):
    if seconds < 1 or seconds > 300:
        await interaction.response.send_message("❌ 秒数は1〜300で指定してください。", ephemeral=True); return
    end_msg = message if message else "時間です！"
    embed   = discord.Embed(
        title="⏱️ タイマースタート！",
        description=f"**{seconds}秒**後に {interaction.user.mention} に通知します\n終了メッセージ: {end_msg}",
        color=0x534AB7
    )
    embed.set_footer(text=f"開始: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(seconds)
    finish_embed = discord.Embed(
        title="⏰ タイマー終了！",
        description=f"⏱️ **{seconds}秒**が経過しました！\n\n{end_msg}",
        color=0xFF4444
    )
    finish_embed.set_footer(text=f"セットした人: {interaction.user.display_name}")
    await interaction.followup.send(content=interaction.user.mention, embed=finish_embed)

# ============================================================
# 💬 村の名言Bot
# ============================================================
DEFAULT_MEIGEN = [
    "「出席は義務ではなく、愛情だ。」― 村の古老",
    "「無断欠席は村の心を傷つける。」― 村長語録",
    "「ポイントは信頼の証。」― 村の憲法第一条",
    "「今日の出席が、明日の村を作る。」― 初代村長",
    "「遅刻するくらいなら、一言声をかけよ。」― 村の教え",
]

@bot.tree.command(name="meigen", description="村の名言をランダムに表示します")
async def meigen(interaction: discord.Interaction):
    cfg_str  = await db_get_config("meigen_list")
    all_list = json.loads(cfg_str) if cfg_str else []
    combined = DEFAULT_MEIGEN + all_list
    quote    = random.choice(combined)
    embed    = discord.Embed(title="💬 村の名言", description=f"*{quote}*", color=0xF0A500)
    embed.set_footer(text="/meigen_add で名言を追加できます（管理者）")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="meigen_add", description="【管理者】村の名言を追加します")
@discord.app_commands.describe(quote="追加する名言（作者も書くと味が出ます）")
async def meigen_add(interaction: discord.Interaction, quote: str):
    if not await check_admin(interaction): return
    cfg_str  = await db_get_config("meigen_list")
    all_list = json.loads(cfg_str) if cfg_str else []
    all_list.append(quote)
    await db_set_config("meigen_list", all_list)
    await interaction.response.send_message(f"✅ 名言を追加しました！\n*{quote}*", ephemeral=True)


@bot.tree.command(name="meigen_list", description="登録されている村の名言一覧を表示します")
async def meigen_list_cmd(interaction: discord.Interaction):
    cfg_str  = await db_get_config("meigen_list")
    all_list = json.loads(cfg_str) if cfg_str else []
    if not all_list:
        await interaction.response.send_message("まだオリジナル名言は登録されていません。`/meigen_add` で追加してください！", ephemeral=True); return
    lines = [f"{i+1}. *{q}*" for i, q in enumerate(all_list)]
    await interaction.response.send_message("**💬 登録済み名言一覧**\n\n" + "\n".join(lines), ephemeral=True)

# ============================================================
# 以下を bot.py の bot.run(TOKEN) の直前に追加してください
# （既存のオセロ・UNO・自動削除コードがあれば全部削除してから追加）
# ============================================================

# ============================================================
# 🗑️ メッセージ一括削除
# ============================================================
@bot.tree.command(name="purge", description="【管理者】直近のメッセージを指定した件数削除します")
@discord.app_commands.describe(count="削除するメッセージ数（1〜100）")
async def purge(interaction: discord.Interaction, count: int):
    if not await check_admin(interaction): return
    if count < 1 or count > 100:
        await interaction.response.send_message("❌ 1〜100の範囲で指定してください。", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=count)
    await interaction.followup.send(f"🗑️ **{len(deleted)}件** のメッセージを削除しました。", ephemeral=True)


# ============================================================
# ♟️ オセロ（修正版）
# ============================================================
OTHELLO_EMPTY = "⬜"
OTHELLO_BLACK = "⚫"
OTHELLO_WHITE = "⚪"
OTHELLO_HINT  = "🟩"
COL_LABELS    = "ABCDEFGH"

class OthelloGame:
    def __init__(self, player_black: discord.Member, player_white: discord.Member):
        self.player_black = player_black
        self.player_white = player_white
        self.board = [[0]*8 for _ in range(8)]
        self.board[3][3] = 2; self.board[4][4] = 2
        self.board[3][4] = 1; self.board[4][3] = 1
        self.current = 1  # 1=黒, 2=白

    @property
    def current_player(self):
        return self.player_black if self.current == 1 else self.player_white

    @property
    def current_emoji(self):
        return "⚫" if self.current == 1 else "⚪"

    def get_valid_moves(self, color):
        return [(r, c) for r in range(8) for c in range(8)
                if self.board[r][c] == 0 and self._can_place(r, c, color)]

    def _can_place(self, row, col, color):
        opp = 3 - color
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            r, c = row+dr, col+dc
            found_opp = False
            while 0 <= r < 8 and 0 <= c < 8:
                if self.board[r][c] == opp:
                    found_opp = True
                elif self.board[r][c] == color and found_opp:
                    return True
                else:
                    break
                r += dr; c += dc
        return False

    def place(self, row, col, color):
        opp = 3 - color
        self.board[row][col] = color
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            r, c = row+dr, col+dc
            to_flip = []
            while 0 <= r < 8 and 0 <= c < 8:
                if self.board[r][c] == opp:
                    to_flip.append((r, c))
                elif self.board[r][c] == color:
                    for fr, fc in to_flip:
                        self.board[fr][fc] = color
                    break
                else:
                    break
                r += dr; c += dc

    def count(self):
        b = sum(row.count(1) for row in self.board)
        w = sum(row.count(2) for row in self.board)
        return b, w

    def render(self, valid_moves=None):
        vm_set = set(valid_moves) if valid_moves else set()
        lines = ["```"]
        lines.append("┌───┬─A─┬─B─┬─C─┬─D─┬─E─┬─F─┬─G─┬─H─┐")
        for r in range(8):
            row_str = f"│ {r+1} │"
            for c in range(8):
                if self.board[r][c] == 1:   row_str += " ● │"
                elif self.board[r][c] == 2: row_str += " ○ │"
                elif (r, c) in vm_set:      row_str += " * │"
                else:                        row_str += "   │"
            lines.append(row_str)
            if r < 7:
                lines.append("├───┼───┼───┼───┼───┼───┼───┼───┼───┤")
        lines.append("└───┴───┴───┴───┴───┴───┴───┴───┴───┘")
        lines.append("```")
        lines.append("● = 黒  ○ = 白  \\* = 置ける場所")
        return "\n".join(lines)


othello_games: dict = {}  # channel_id -> OthelloGame


def make_othello_view(game: OthelloGame, valid_moves: list, channel_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=300)

    # 座標選択（行を選ぶSelect）
    row_options = []
    valid_rows = sorted(set(r for r, c in valid_moves))
    for r in valid_rows:
        row_options.append(discord.SelectOption(
            label=f"{r+1}行目",
            value=str(r),
            description=f"置ける列: {', '.join(COL_LABELS[c] for _, c in valid_moves if _ == r)}"
        ))

    class RowSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="① 行を選択（1〜8）", options=row_options, row=0)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != game.current_player.id:
                await interaction.response.send_message("❌ あなたの番ではありません！", ephemeral=True); return
            selected_row = int(self.values[0])
            col_options = [
                discord.SelectOption(label=f"{COL_LABELS[c]}列", value=f"{selected_row},{c}")
                for r, c in valid_moves if r == selected_row
            ]
            new_view = discord.ui.View(timeout=300)
            new_view.add_item(ColSelect(col_options))
            new_view.add_item(SurrenderButton())
            await interaction.response.edit_message(
                content=game.render(valid_moves) + f"\n\n{game.current_emoji} {game.current_player.mention} の番\n② 列を選択してください：",
                view=new_view
            )

    class ColSelect(discord.ui.Select):
        def __init__(self, col_options):
            super().__init__(placeholder="② 列を選択（A〜H）", options=col_options, row=0)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != game.current_player.id:
                await interaction.response.send_message("❌ あなたの番ではありません！", ephemeral=True); return
            r, c = map(int, self.values[0].split(","))
            color = game.current
            game.place(r, c, color)
            game.current = 3 - color

            next_moves = game.get_valid_moves(game.current)
            skip_msg = ""
            if not next_moves:
                game.current = 3 - game.current
                skip_moves = game.get_valid_moves(game.current)
                if not skip_moves:
                    # ゲーム終了
                    b, w = game.count()
                    if b > w:   result = f"🎉 {game.player_black.mention} の勝ち！（⚫{b} vs ⚪{w}）"
                    elif w > b: result = f"🎉 {game.player_white.mention} の勝ち！（⚫{b} vs ⚪{w}）"
                    else:       result = f"🤝 引き分け！（⚫{b} vs ⚪{w}）"
                    del othello_games[interaction.channel.id]
                    await interaction.response.edit_message(
                        content=f"{game.render()}\n\n**ゲーム終了！**\n{result}", view=None
                    )
                    return
                next_moves = skip_moves
                skipped_emoji = "⚫" if game.current == 2 else "⚪"
                skip_msg = f"\n⏭️ {skipped_emoji} は置ける場所がないためスキップ！"

            b, w = game.count()
            new_view = make_othello_view(game, next_moves, interaction.channel.id)
            await interaction.response.edit_message(
                content=f"{game.render(next_moves)}{skip_msg}\n⚫{b} vs ⚪{w}\n{game.current_emoji} {game.current_player.mention} の番！（🟩 = 置ける場所）",
                view=new_view
            )

    class SurrenderButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="🏳️ 降参する", style=discord.ButtonStyle.danger, row=1)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id not in [game.player_black.id, game.player_white.id]:
                await interaction.response.send_message("❌ このゲームの参加者ではありません。", ephemeral=True); return
            winner = game.player_white if interaction.user.id == game.player_black.id else game.player_black
            del othello_games[interaction.channel.id]
            await interaction.response.edit_message(
                content=f"🏳️ **{interaction.user.display_name}** が降参しました！\n🎉 {winner.mention} の勝ち！",
                view=None
            )

    view.add_item(RowSelect())
    view.add_item(SurrenderButton())
    return view


@bot.tree.command(name="othello", description="オセロで対戦します！")
@discord.app_commands.describe(opponent="対戦相手")
async def othello_cmd(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.bot or opponent.id == interaction.user.id:
        await interaction.response.send_message("❌ その相手とは対戦できません。", ephemeral=True); return
    if interaction.channel.id in othello_games:
        await interaction.response.send_message("❌ このチャンネルでは既にオセロが進行中です。`/othello_cancel` でキャンセルできます。", ephemeral=True); return

    game = OthelloGame(interaction.user, opponent)
    othello_games[interaction.channel.id] = game
    valid_moves = game.get_valid_moves(1)
    b, w = game.count()
    view = make_othello_view(game, valid_moves, interaction.channel.id)
    await interaction.response.send_message(
    f"♟️ **オセロ開始！**\n⚫ {interaction.user.mention} vs ⚪ {opponent.mention}\n\n"
    f"{game.render(valid_moves)}\n⚫{b} vs ⚪{w}\n⚫ {interaction.user.mention} の番！（* = 置ける場所）",
    view=view
    )


@bot.tree.command(name="othello_cancel", description="進行中のオセロをキャンセルします")
async def othello_cancel(interaction: discord.Interaction):
    game = othello_games.get(interaction.channel.id)
    if not game:
        await interaction.response.send_message("このチャンネルでオセロは進行していません。", ephemeral=True); return
    if interaction.user.id not in [game.player_black.id, game.player_white.id] and not await is_admin(interaction):
        await interaction.response.send_message("❌ 参加者か管理者のみキャンセルできます。", ephemeral=True); return
    del othello_games[interaction.channel.id]
    await interaction.response.send_message(f"🏳️ オセロをキャンセルしました。")


# ============================================================
# 🃏 UNO（修正版）
# ============================================================
UNO_COLORS  = ["🔴", "🔵", "🟢", "🟡"]
UNO_NUMBERS = ["0","1","2","3","4","5","6","7","8","9","Skip","Reverse","Draw2"]
UNO_WILDS   = ["Wild", "Wild4"]

def make_uno_deck():
    deck = []
    for color in UNO_COLORS:
        for num in UNO_NUMBERS:
            deck.append(f"{color}{num}")
            if num != "0": deck.append(f"{color}{num}")
    for wild in UNO_WILDS:
        for _ in range(4): deck.append(wild)
    random.shuffle(deck)
    return deck

def uno_display(card: str) -> str:
    if card == "Wild":   return "🌈ワイルド"
    if card == "Wild4":  return "🌈+4ワイルド"
    color = card[:2]
    num   = card[2:]
    num_map = {"Skip":"スキップ","Reverse":"リバース","Draw2":"+2"}
    return f"{color}{num_map.get(num, num)}"


class UNOGame:
    def __init__(self, players: list):
        self.players    = players
        self.hands      = {p.id: [] for p in players}
        self.deck       = make_uno_deck()
        self.discard    = []
        self.current_idx = 0
        self.direction  = 1
        for _ in range(7):
            for p in players:
                self.hands[p.id].append(self.deck.pop())
        while True:
            card = self.deck.pop()
            if not card.startswith("Wild"):
                self.discard.append(card); break
            self.deck.insert(0, card)

    @property
    def current_player(self): return self.players[self.current_idx]
    @property
    def top_card(self): return self.discard[-1]

    def can_play(self, card: str) -> bool:
        top = self.top_card
        if card.startswith("Wild"): return True
        if top.startswith("Wild"):  return False
        return card[:2] == top[:2] or card[2:] == top[2:]

    def play_card(self, pid: int, card: str):
        self.hands[pid].remove(card)
        self.discard.append(card)

    def draw_card(self, pid: int, count: int = 1) -> list:
        drawn = []
        for _ in range(count):
            if not self.deck:
                self.deck = self.discard[:-1]
                random.shuffle(self.deck)
                self.discard = [self.discard[-1]]
            if self.deck:
                c = self.deck.pop()
                self.hands[pid].append(c)
                drawn.append(c)
        return drawn

    def next_turn(self):
        self.current_idx = (self.current_idx + self.direction) % len(self.players)

    def skip_next(self):
        self.next_turn()
        self.next_turn()

    def hand_summary(self) -> str:
        return " | ".join(f"{p.display_name}:{len(self.hands[p.id])}枚" for p in self.players)


uno_games:   dict = {}  # channel_id -> UNOGame
uno_lobbies: dict = {}  # channel_id -> [members]


async def send_uno_turn(channel: discord.TextChannel, game: UNOGame, channel_id: int, extra_msg: str = ""):
    player  = game.current_player
    hand    = game.hands[player.id]
    playable = [c for c in hand if game.can_play(c)]

    # 手札をDMに送信
    hand_str = "  ".join(uno_display(c) for c in hand)
    dm_msg = (
        f"🃏 **あなたの手札（{len(hand)}枚）**\n{hand_str}\n\n"
        f"▶️ 場のカード: **{uno_display(game.top_card)}**\n"
        f"出せるカード: {', '.join(uno_display(c) for c in playable) if playable else 'なし（カードを引いてください）'}\n\n"
        f"⚠️ **操作はDiscordのチャンネルで行ってください！**"
    )
    try:
        await player.send(dm_msg)
    except Exception:
        pass

    # チャンネルに操作UIを送信
    options = [discord.SelectOption(label=uno_display(c), value=c, description="✅ 出せる" if game.can_play(c) else "❌ 出せない") for c in hand[:25]]

    class CardSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="出すカードを選択してください", options=options)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != game.current_player.id:
                await interaction.response.send_message("❌ あなたの番ではありません！", ephemeral=True); return
            card = self.values[0]
            if not game.can_play(card):
                await interaction.response.send_message(f"❌ **{uno_display(card)}** は今出せません！", ephemeral=True); return

            game.play_card(interaction.user.id, card)
            msg = f"🃏 {interaction.user.display_name} が **{uno_display(card)}** を出しました！"

            # 勝利チェック
            if not game.hands[interaction.user.id]:
                del uno_games[channel_id]
                await interaction.response.edit_message(content=msg + f"\n\n🎉 **{interaction.user.mention} の勝利！！** 🎊", view=None)
                return

            if len(game.hands[interaction.user.id]) == 1:
                msg += f"\n🔔 **UNO！** {interaction.user.display_name} 残り1枚！"

            # 特殊カード処理
            num = card[2:] if not card.startswith("Wild") else card
            if num == "Skip":
                game.next_turn()
                msg += f"\n⏭️ {game.current_player.display_name} はスキップ！"
                game.next_turn()
            elif num == "Reverse":
                game.direction *= -1
                msg += "\n🔄 順番が逆転！"
                game.next_turn()
            elif num == "Draw2":
                game.next_turn()
                victim = game.current_player
                game.draw_card(victim.id, 2)
                msg += f"\n+2！ {victim.display_name} が2枚引きます！"
                game.next_turn()
            elif num == "Wild4":
                game.next_turn()
                victim = game.current_player
                game.draw_card(victim.id, 4)
                msg += f"\n+4！ {victim.display_name} が4枚引きます！"
                game.next_turn()
            else:
                game.next_turn()

            await interaction.response.edit_message(content=msg, view=None)
            await send_uno_turn(interaction.channel, game, channel_id)

    class DrawButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="🎴 カードを引く", style=discord.ButtonStyle.secondary, row=1)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != game.current_player.id:
                await interaction.response.send_message("❌ あなたの番ではありません！", ephemeral=True); return
            drawn = game.draw_card(interaction.user.id, 1)
            msg = f"🎴 {interaction.user.display_name} が **{uno_display(drawn[0])}** を引きました。"
            game.next_turn()
            await interaction.response.edit_message(content=msg, view=None)
            await send_uno_turn(interaction.channel, game, channel_id)

    class SurrenderButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="🏳️ 降参", style=discord.ButtonStyle.danger, row=1)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id not in game.hands:
                await interaction.response.send_message("❌ このゲームの参加者ではありません。", ephemeral=True); return
            del uno_games[channel_id]
            await interaction.response.edit_message(
                content=f"🏳️ **{interaction.user.display_name}** が降参しました！ゲームを終了します。",
                view=None
            )

    view = discord.ui.View(timeout=300)
    view.add_item(CardSelect())
    view.add_item(DrawButton())
    view.add_item(SurrenderButton())

    status = (
        f"{extra_msg}\n" if extra_msg else ""
        f"**🃏 UNO** | 場: **{uno_display(game.top_card)}**\n"
        f"手札枚数: {game.hand_summary()}\n\n"
        f"➡️ **{player.display_name}** の番！\n"
        f"手札はDMを確認してください 📩"
    )
    await channel.send(status, view=view)


@bot.tree.command(name="uno_start", description="UNOのロビーを作成します（2〜6人）")
async def uno_start(interaction: discord.Interaction):
    if interaction.channel.id in uno_games:
        await interaction.response.send_message("❌ UNOが既に進行中です。", ephemeral=True); return
    if interaction.channel.id in uno_lobbies:
        await interaction.response.send_message("❌ ロビーが既にあります。", ephemeral=True); return
    uno_lobbies[interaction.channel.id] = [interaction.user]

    class LobbyView(discord.ui.View):
        def __init__(self): super().__init__(timeout=120)

        @discord.ui.button(label="✋ 参加する", style=discord.ButtonStyle.success)
        async def join_btn(self, inter: discord.Interaction, button: discord.ui.Button):
            lobby = uno_lobbies.get(inter.channel.id, [])
            if inter.user in lobby:
                await inter.response.send_message("既に参加しています！", ephemeral=True); return
            if len(lobby) >= 6:
                await inter.response.send_message("満員です！（最大6人）", ephemeral=True); return
            lobby.append(inter.user)
            names = ", ".join(p.display_name for p in lobby)
            await inter.response.send_message(f"✅ {inter.user.display_name} が参加！\n現在の参加者（{len(lobby)}人）: {names}")

        @discord.ui.button(label="🎮 ゲーム開始", style=discord.ButtonStyle.primary)
        async def start_btn(self, inter: discord.Interaction, button: discord.ui.Button):
            lobby = uno_lobbies.get(inter.channel.id, [])
            if inter.user.id != lobby[0].id:
                await inter.response.send_message("❌ ホストのみ開始できます！", ephemeral=True); return
            if len(lobby) < 2:
                await inter.response.send_message("❌ 2人以上必要です！", ephemeral=True); return
            game = UNOGame(lobby)
            uno_games[inter.channel.id] = game
            del uno_lobbies[inter.channel.id]
            names = ", ".join(p.display_name for p in lobby)
            await inter.response.send_message(
                f"🃏 **UNO開始！**\n参加者（{len(lobby)}人）: {names}\n"
                f"各自DMに手札を送ります。DMが受け取れるか確認してください！"
            )
            await send_uno_turn(inter.channel, game, inter.channel.id)

        @discord.ui.button(label="❌ キャンセル", style=discord.ButtonStyle.danger)
        async def cancel_btn(self, inter: discord.Interaction, button: discord.ui.Button):
            lobby = uno_lobbies.get(inter.channel.id, [])
            if inter.user.id != lobby[0].id:
                await inter.response.send_message("❌ ホストのみキャンセルできます！", ephemeral=True); return
            del uno_lobbies[inter.channel.id]
            await inter.response.send_message("❌ ロビーをキャンセルしました。")

    await interaction.response.send_message(
        f"🃏 **UNOロビー作成！**\nホスト: {interaction.user.display_name}\n\n"
        f"「✋ 参加する」で参加 → 2人以上集まったら「🎮 ゲーム開始」を押してください！\n"
        f"（最大6人）",
        view=LobbyView()
    )


@bot.tree.command(name="uno_hand", description="自分の手札をDMで再送します")
async def uno_hand(interaction: discord.Interaction):
    game = uno_games.get(interaction.channel.id)
    if not game:
        await interaction.response.send_message("現在UNOは進行していません。", ephemeral=True); return
    hand = game.hands.get(interaction.user.id)
    if hand is None:
        await interaction.response.send_message("このゲームに参加していません。", ephemeral=True); return
    hand_str = "  ".join(uno_display(c) for c in hand)
    playable = [c for c in hand if game.can_play(c)]
    try:
        await interaction.user.send(
            f"🃏 **手札（{len(hand)}枚）**\n{hand_str}\n\n"
            f"▶️ 場のカード: **{uno_display(game.top_card)}**\n"
            f"出せるカード: {', '.join(uno_display(c) for c in playable) if playable else 'なし'}\n\n"
            f"⚠️ **操作はDiscordのチャンネルで行ってください！**"
        )
        await interaction.response.send_message("✅ DMに手札を送りました！チャンネルで操作してください。", ephemeral=True)
    except Exception:
        await interaction.response.send_message(f"🃏 手札（{len(hand)}枚）:\n{hand_str}", ephemeral=True)


@bot.tree.command(name="uno_cancel", description="【管理者または参加者】進行中のUNOをキャンセルします")
async def uno_cancel(interaction: discord.Interaction):
    game = uno_games.get(interaction.channel.id)
    if not game:
        await interaction.response.send_message("UNOは進行していません。", ephemeral=True); return
    if interaction.user.id not in game.hands and not await is_admin(interaction):
        await interaction.response.send_message("❌ 参加者か管理者のみキャンセルできます。", ephemeral=True); return
    del uno_games[interaction.channel.id]
    await interaction.response.send_message("❌ UNOをキャンセルしました。")
        
# ============================================================
# 起動
# ============================================================
bot.run(TOKEN)
