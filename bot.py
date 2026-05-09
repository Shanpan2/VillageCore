import discord
from discord.ext import commands
import json
import os
from datetime import datetime

# ============================================================
# トークン読み込み
# ============================================================
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN環境変数が設定されていません")

# ============================================================
# データファイルパス
# ============================================================
POLL_DATA_FILE   = "poll_data.json"
ATTEND_DATA_FILE = "attend_data.json"

# ============================================================
# データ読み書きユーティリティ
# ============================================================
def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============================================================
# インメモリデータ
# ============================================================
poll_data: dict   = load_json(POLL_DATA_FILE, {})
attend_data: dict = load_json(ATTEND_DATA_FILE, {"members": {}, "notify_channel_id": None})

# ============================================================
# Bot 初期化
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.polls = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
# ポイント計算ロジック（マイナスあり・上限10）
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
    """マイナスも許容（下限なし）、上限10"""
    change = calc_point_change(current_pt, status)
    return min(10, current_pt + change)  # マイナスも許容

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

def save_attend():
    save_json(ATTEND_DATA_FILE, attend_data)

def get_badge(pt: int) -> str:
    if pt <= 0:
        return "🚨 退出対象"
    elif pt <= 2:
        return "⚠️ 第2警告"
    elif pt <= 4:
        return "❗ 第1警告"
    return "✅"

# ============================================================
# 起動・名前同期
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ ログイン成功: {bot.user} (ID: {bot.user.id})")

    # 登録済みメンバーの名前をDiscordの最新表示名に同期
    for guild in bot.guilds:
        for uid, entry in attend_data["members"].items():
            member = guild.get_member(int(uid))
            if member and member.display_name != entry["name"]:
                print(f"🔄 名前同期: {entry['name']} → {member.display_name}")
                entry["name"] = member.display_name
    save_attend()

    await bot.tree.sync()
    print("✅ スラッシュコマンド同期完了")


# ============================================================
# /help コマンド
# ============================================================
@bot.tree.command(name="help", description="使えるコマンドの一覧と説明を表示します")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 コマンド一覧",
        color=0x534AB7
    )

    embed.add_field(name="\u200b", value="**🗳️ Poll・ロール機能**", inline=False)
    embed.add_field(
        name="/setup_poll_role 【村長権限用】",
        value="Pollの選択肢に投票したユーザーへ自動でロールを付与する設定をします。\n`message_id` `answer_text` `role_name` `assign_role`",
        inline=False
    )
    embed.add_field(
        name="/list_poll_roles",
        value="現在登録されているPoll→ロールの紐付け一覧を表示します。",
        inline=False
    )

    embed.add_field(name="\u200b", value="**📋 出席管理機能（村長権限用）**", inline=False)
    embed.add_field(
        name="/attend_add_member 【村長権限用】",
        value="メンバーを1人出席管理に追加します。初期ポイントは10pt。",
        inline=False
    )
    embed.add_field(
        name="/attend_add_members_bulk 【村長権限用】",
        value="複数のメンバーをまとめて出席管理に追加します（選択式）。",
        inline=False
    )
    embed.add_field(
        name="/attend_remove_member 【村長権限用】",
        value="メンバーを出席管理から削除します。",
        inline=False
    )
    embed.add_field(
        name="/attend_record 【村長権限用】",
        value="メンバーを1人選んで出席状況を記録します。",
        inline=False
    )
    embed.add_field(
        name="/attend_record_all 【村長権限用】",
        value="全メンバーの出席状況を一括で記録します。4人ずつページを移動して全員選択し「保存する」を押してください。",
        inline=False
    )
    embed.add_field(
        name="/attend_set_pt 【村長権限用】",
        value="メンバーのポイントを直接指定して修正します（ミス修正用）。",
        inline=False
    )
    embed.add_field(
        name="/attend_set_channel 【村長権限用】",
        value="警告通知を送るチャンネルを現在のチャンネルに設定します。",
        inline=False
    )
    embed.add_field(
        name="/attend_notify 【村長権限用】",
        value="警告対象メンバーを通知チャンネルに送信します。",
        inline=False
    )

    embed.add_field(name="\u200b", value="**📊 確認コマンド（誰でも使用可）**", inline=False)
    embed.add_field(
        name="/attend_status",
        value="全メンバーの出席ポイント一覧を表示します。",
        inline=False
    )
    embed.add_field(
        name="/attend_warnings",
        value="警告対象（4pt以下）のメンバーだけを表示します。",
        inline=False
    )
    embed.add_field(
        name="/attend_history",
        value="指定メンバーの出席履歴（直近20件）を表示します。",
        inline=False
    )

    embed.add_field(name="\u200b", value="**📈 ポイント基準**", inline=False)
    embed.add_field(
        name="付与・減算ルール",
        value=(
            "✅ 投票して出席：+2pt（4pt以下なら+3pt）\n"
            "✅ 生存確認(DM回答済み)：+3pt\n"
            "➖ 欠席系（投票あり）：-1pt\n"
            "➖ 無断遅刻：-1pt\n"
            "❌ 無断欠席：-3pt\n"
            "⚠️ 4pt以下：第1警告 / 2pt以下：第2警告 / 0pt以下：退出対象"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================
#  POLL ROLE 機能
# ============================================================

@bot.tree.command(
    name="setup_poll_role",
    description="【村長権限用】Pollの選択肢にロールを紐付けます（ロールは自動作成）"
)
@discord.app_commands.describe(
    message_id="PollのメッセージID",
    answer_text="投票選択肢のテキスト（完全一致）",
    role_name="作成するロール名（省略すると選択肢名と同じ）",
    assign_role="投票したらロールを付与するか（デフォルト: True）",
)
async def setup_poll_role(
    interaction: discord.Interaction,
    message_id: str,
    answer_text: str,
    role_name: str = "",
    assign_role: bool = True,
):
    if not await check_admin(interaction):
        return
    await interaction.response.defer(ephemeral=True)

    try:
        msg = await interaction.channel.fetch_message(int(message_id))
    except (discord.NotFound, ValueError):
        await interaction.followup.send("❌ メッセージが見つかりません。同じチャンネルで実行してください。", ephemeral=True)
        return

    if msg.poll is None:
        await interaction.followup.send("❌ そのメッセージにはPollがありません。", ephemeral=True)
        return

    answer_id = None
    for ans in msg.poll.answers:
        if ans.text == answer_text:
            answer_id = str(ans.id)
            break

    if answer_id is None:
        choices = "\n".join(f"• {a.text}" for a in msg.poll.answers)
        await interaction.followup.send(f"❌ 選択肢が見つかりません。以下から選んでください：\n{choices}", ephemeral=True)
        return

    final_role_name = role_name.strip() if role_name.strip() else answer_text

    role = discord.utils.get(interaction.guild.roles, name=final_role_name)
    if role is None:
        role = await interaction.guild.create_role(
            name=final_role_name,
            mentionable=True,
            reason=f"Poll投票ロール自動作成 by {interaction.user}"
        )
        created_msg = f"✨ ロール **{final_role_name}** を新規作成しました（メンション可能）"
    else:
        if not role.mentionable:
            await role.edit(mentionable=True)
        created_msg = f"ℹ️ 既存ロール **{final_role_name}** を使用します（メンション可能に設定済み）"

    if message_id not in poll_data:
        poll_data[message_id] = {}
    poll_data[message_id][answer_id] = {
        "role_id": role.id,
        "assign_role": assign_role,
    }
    save_json(POLL_DATA_FILE, poll_data)

    assign_str = "✅ ロール付与: あり" if assign_role else "⛔ ロール付与: なし（記録のみ）"
    await interaction.followup.send(
        f"{created_msg}\n「{answer_text}」への投票と **{final_role_name}** を紐付けました\n{assign_str}",
        ephemeral=True
    )


@bot.tree.command(name="list_poll_roles", description="登録済みのPoll→ロール一覧を表示")
async def list_poll_roles(interaction: discord.Interaction):
    if not poll_data:
        await interaction.response.send_message("登録されているPollロール紐付けはありません。", ephemeral=True)
        return

    lines = []
    for msg_id, answers in poll_data.items():
        lines.append(f"📋 メッセージID: `{msg_id}`")
        for ans_id, info in answers.items():
            role = interaction.guild.get_role(info["role_id"])
            role_name = role.name if role else f"ID:{info['role_id']}(削除済み)"
            assign_str = "付与あり" if info.get("assign_role", True) else "付与なし"
            lines.append(f"  └ 選択肢ID `{ans_id}` → **{role_name}** ({assign_str})")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ── Poll投票イベント ──────────────────────────────────────────
@bot.event
async def on_raw_poll_vote_add(payload: discord.RawPollVoteActionEvent):
    msg_id = str(payload.message_id)
    ans_id = str(payload.answer_id)

    info = poll_data.get(msg_id, {}).get(ans_id)
    if info is None or not info.get("assign_role", True):
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    role = guild.get_role(info["role_id"])
    if role is None:
        print(f"⚠️ ロールID {info['role_id']} が見つかりません")
        return

    try:
        await member.add_roles(role, reason="Poll投票によるロール付与")
        print(f"✅ {member.display_name} に {role.name} を付与")
    except discord.Forbidden:
        print(f"❌ ロール付与権限なし: {member.display_name}")


@bot.event
async def on_raw_poll_vote_remove(payload: discord.RawPollVoteActionEvent):
    msg_id = str(payload.message_id)
    ans_id = str(payload.answer_id)

    info = poll_data.get(msg_id, {}).get(ans_id)
    if info is None or not info.get("assign_role", True):
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    role = guild.get_role(info["role_id"])
    if role is None:
        return

    try:
        await member.remove_roles(role, reason="Poll投票取り消しによるロール削除")
        print(f"🗑️ {member.display_name} から {role.name} を削除")
    except discord.Forbidden:
        print(f"❌ ロール削除権限なし: {member.display_name}")


@bot.event
async def on_poll_finish(poll: discord.Poll):
    try:
        message = await poll.channel.fetch_message(poll.message.id)
        msg_id = str(message.id)
    except Exception:
        return

    if msg_id not in poll_data:
        return

    guild = poll.message.guild
    deleted_roles = []

    for ans_id, info in poll_data[msg_id].items():
        role = guild.get_role(info["role_id"])
        if role is not None:
            try:
                await role.delete(reason="Poll終了によるロール自動削除")
                deleted_roles.append(role.name)
                print(f"🗑️ Poll終了: ロール {role.name} を削除")
            except discord.Forbidden:
                print(f"❌ ロール削除権限なし: {role.name}")

    del poll_data[msg_id]
    save_json(POLL_DATA_FILE, poll_data)

    if deleted_roles:
        try:
            await poll.channel.send(
                f"📢 Pollが終了しました。以下のロールを削除しました：{', '.join(f'**{r}**' for r in deleted_roles)}"
            )
        except Exception:
            pass


# ============================================================
#  出席管理機能
# ============================================================

@bot.tree.command(name="attend_set_channel", description="【村長権限用】出席管理の通知チャンネルを現在のチャンネルに設定します")
async def attend_set_channel(interaction: discord.Interaction):
    if not await check_admin(interaction):
        return
    attend_data["notify_channel_id"] = interaction.channel.id
    save_attend()
    await interaction.response.send_message(f"✅ 通知チャンネルを {interaction.channel.mention} に設定しました。", ephemeral=True)


@bot.tree.command(name="attend_add_member", description="【村長権限用】出席管理にメンバーを1人追加します")
@discord.app_commands.describe(member="追加するメンバー", initial_pt="初期ポイント（デフォルト: 10）")
async def attend_add_member(interaction: discord.Interaction, member: discord.Member, initial_pt: int = 10):
    if not await check_admin(interaction):
        return
    uid = str(member.id)
    if uid in attend_data["members"]:
        await interaction.response.send_message(f"⚠️ {member.display_name} は既に登録されています。", ephemeral=True)
        return
    attend_data["members"][uid] = {
        "name": member.display_name,
        "pt": initial_pt,
        "records": {}
    }
    save_attend()
    await interaction.response.send_message(f"✅ {member.display_name} を追加しました（{initial_pt}pt）", ephemeral=True)


@bot.tree.command(name="attend_add_members_bulk", description="【村長権限用】メンバーを選択して一括で出席管理に追加します")
@discord.app_commands.describe(initial_pt="初期ポイント（デフォルト: 10）")
async def attend_add_members_bulk(interaction: discord.Interaction, initial_pt: int = 10):
    if not await check_admin(interaction):
        return

    options = []
    for member in interaction.guild.members:
        if member.bot:
            continue
        if str(member.id) in attend_data["members"]:
            continue
        options.append(discord.SelectOption(
            label=member.display_name,
            value=str(member.id),
        ))

    if not options:
        await interaction.response.send_message("✅ 全員すでに登録済みです。", ephemeral=True)
        return

    options = options[:25]

    class MemberMultiSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="追加するメンバーを選択（複数可）",
                options=options,
                min_values=1,
                max_values=len(options)
            )

        async def callback(self, interaction2: discord.Interaction):
            added = []
            for uid in self.values:
                member = interaction2.guild.get_member(int(uid))
                if member is None:
                    continue
                attend_data["members"][uid] = {
                    "name": member.display_name,
                    "pt": initial_pt,
                    "records": {}
                }
                added.append(member.display_name)
            save_attend()
            await interaction2.response.send_message(
                f"✅ **{len(added)}人** を追加しました！\n" + "、".join(added),
                ephemeral=True
            )

    view = discord.ui.View(timeout=120)
    view.add_item(MemberMultiSelect())
    await interaction.response.send_message(
        "追加するメンバーを選んでください（複数選択可）：",
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="attend_remove_member", description="【村長権限用】出席管理からメンバーを削除します")
@discord.app_commands.describe(member="削除するメンバー")
async def attend_remove_member(interaction: discord.Interaction, member: discord.Member):
    if not await check_admin(interaction):
        return
    uid = str(member.id)
    if uid not in attend_data["members"]:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
        return
    del attend_data["members"][uid]
    save_attend()
    await interaction.response.send_message(f"🗑️ {member.display_name} を削除しました。", ephemeral=True)


# ── 個別出席記録 ──────────────────────────────────────────────

class AttendStatusSelect(discord.ui.Select):
    def __init__(self, uid: str, name: str, date: str):
        self.uid  = uid
        self.date = date
        options   = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=f"{name} の出席状況を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        status = self.values[0]
        entry  = attend_data["members"].get(self.uid)
        if entry is None:
            await interaction.response.send_message("❌ メンバーが見つかりません。", ephemeral=True)
            return
        change = calc_point_change(entry["pt"], status)
        new_pt = apply_point(entry["pt"], status)
        entry["pt"] = new_pt
        entry["records"][self.date] = status
        save_attend()
        sign = f"+{change}" if change >= 0 else str(change)
        await interaction.response.send_message(
            f"✅ **{entry['name']}** | {status} → {sign}pt → **{new_pt}pt**",
            ephemeral=True
        )


class AttendRecordView(discord.ui.View):
    def __init__(self, uid: str, name: str, date: str):
        super().__init__(timeout=300)
        self.add_item(AttendStatusSelect(uid, name, date))


@bot.tree.command(name="attend_record", description="【村長権限用】メンバーを選択して出席を記録します")
@discord.app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
async def attend_record(interaction: discord.Interaction, date: str = ""):
    if not await check_admin(interaction):
        return
    members = attend_data["members"]
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
        return
    record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")

    options = [
        discord.SelectOption(label=entry["name"], value=uid, description=f"現在: {entry['pt']}pt")
        for uid, entry in members.items()
    ]

    class MemberSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="メンバーを選択", options=options[:25])

        async def callback(self, interaction2: discord.Interaction):
            uid   = self.values[0]
            entry = attend_data["members"].get(uid)
            view2 = AttendRecordView(uid, entry["name"], record_date)
            await interaction2.response.send_message(
                f"📋 **{entry['name']}** の出席記録（{record_date}）\n現在: **{entry['pt']}pt**",
                view=view2, ephemeral=True
            )

    view = discord.ui.View(timeout=120)
    view.add_item(MemberSelect())
    await interaction.response.send_message(
        f"📋 出席記録（{record_date}）\nメンバーを選んでください：",
        view=view, ephemeral=True
    )


# ── 一括出席記録 ──────────────────────────────────────────────

class BulkAttendSelect(discord.ui.Select):
    def __init__(self, uid: str, placeholder: str, date: str, parent_view, row: int):
        self.uid         = uid
        self.parent_view = parent_view
        self.date        = date
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=placeholder, options=options, row=row)

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
        page_members = member_list[start:end]

        for i, (uid, name, pt) in enumerate(page_members):
            already = self.selections.get(uid, "")
            ph = f"{name}（{pt}pt）" + (f" ✅{already[:6]}" if already else "")
            self.add_item(BulkAttendSelect(uid, ph[:100], record_date, self, row=i))

        # 前へボタン
        if page > 0:
            prev_btn = discord.ui.Button(label="← 前へ", style=discord.ButtonStyle.secondary, row=4)
            async def prev_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, p - 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        # 次へボタン
        if end < len(member_list):
            next_btn = discord.ui.Button(label="次へ →", style=discord.ButtonStyle.primary, row=4)
            async def next_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, p + 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            next_btn.callback = next_cb
            self.add_item(next_btn)

        # 保存ボタン（常に表示）
        save_btn = discord.ui.Button(label="✅ 保存する", style=discord.ButtonStyle.success, row=4)
        async def save_cb(inter: discord.Interaction):
            if not self.selections:
                await inter.response.send_message("❌ 少なくとも1人の出席状況を選択してください。", ephemeral=True)
                return
            results = []
            for uid, status in self.selections.items():
                entry = attend_data["members"].get(uid)
                if entry is None:
                    continue
                change = calc_point_change(entry["pt"], status)
                new_pt = apply_point(entry["pt"], status)
                entry["pt"] = new_pt
                entry["records"][record_date] = status
                sign = f"+{change}" if change >= 0 else str(change)
                results.append(f"• **{entry['name']}** : {status} → {sign}pt → **{new_pt}pt**")
            save_attend()
            await inter.response.send_message(
                f"✅ **{record_date}** の記録が完了しました！\n\n" + "\n".join(results),
                ephemeral=True
            )
        save_btn.callback = save_cb
        self.add_item(save_btn)

    def content(self) -> str:
        total_pages = max(1, (len(self.member_list) - 1) // 4 + 1)
        return (
            f"📋 **{self.record_date}** の一括出席記録 "
            f"（{self.page + 1}/{total_pages}ページ）\n"
            f"選択済み: {len(self.selections)}人 ／ 全{len(self.member_list)}人\n"
            f"各メンバーの出席状況を選んで「✅ 保存する」を押してください："
        )


@bot.tree.command(name="attend_record_all", description="【村長権限用】全メンバーの出席を一括で記録します")
@discord.app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
async def attend_record_all(interaction: discord.Interaction, date: str = ""):
    if not await check_admin(interaction):
        return
    members = attend_data["members"]
    if not members:
        await interaction.response.send_message(
            "登録メンバーがいません。先に /attend_add_members_bulk でメンバーを登録してください。",
            ephemeral=True
        )
        return
    record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
    member_list = [(uid, entry["name"], entry["pt"]) for uid, entry in members.items()]
    view = BulkAttendView(record_date, member_list, page=0)
    await interaction.response.send_message(view.content(), view=view, ephemeral=True)


# ── ポイント確認・通知 ────────────────────────────────────────

@bot.tree.command(name="attend_status", description="出席ポイント一覧を表示します")
async def attend_status(interaction: discord.Interaction):
    members = attend_data["members"]
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
        return

    sorted_members = sorted(members.items(), key=lambda x: x[1]["pt"])
    lines = ["**📊 出席ポイント一覧**\n"]
    for uid, entry in sorted_members:
        pt    = entry["pt"]
        badge = get_badge(pt)
        lines.append(f"{badge} <@{uid}> **{entry['name']}** : **{pt}pt**")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_warnings", description="警告対象のメンバーだけを表示します")
async def attend_warnings(interaction: discord.Interaction):
    members = attend_data["members"]
    if not members:
        await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
        return

    warnings = []
    for uid, entry in sorted(members.items(), key=lambda x: x[1]["pt"]):
        pt = entry["pt"]
        if pt > 4:
            continue
        badge = get_badge(pt)
        warnings.append(f"{badge} <@{uid}> **{entry['name']}** : **{pt}pt**")

    if warnings:
        lines = ["**⚠️ 警告対象メンバー一覧**\n"] + warnings
    else:
        lines = ["✅ 現在、警告対象のメンバーはいません。"]

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="attend_notify", description="【村長権限用】警告対象メンバーを通知チャンネルに送信します")
async def attend_notify(interaction: discord.Interaction):
    if not await check_admin(interaction):
        return
    members = attend_data["members"]
    ch_id   = attend_data.get("notify_channel_id")

    warnings = []
    for uid, entry in members.items():
        pt = entry["pt"]
        if pt > 4:
            continue
        badge = get_badge(pt)
        warnings.append(f"{badge} <@{uid}> **{entry['name']}** : **{pt}pt**")

    msg = "📢 **出席ポイント警告通知**\n"
    msg += "\n".join(warnings) if warnings else "✅ 現在、警告対象のメンバーはいません。"

    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(msg)
            await interaction.response.send_message("✅ 通知チャンネルに送信しました。", ephemeral=True)
            return

    await interaction.response.send_message(msg)


@bot.tree.command(name="attend_set_pt", description="【村長権限用】メンバーのポイントをミス修正などで直接設定します")
@discord.app_commands.describe(member="対象メンバー", pt="設定するポイント（マイナスも可）")
async def attend_set_pt(interaction: discord.Interaction, member: discord.Member, pt: int):
    if not await check_admin(interaction):
        return
    uid = str(member.id)
    if uid not in attend_data["members"]:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
        return
    new_pt = min(10, pt)  # 上限10、下限なし（マイナスも可）
    attend_data["members"][uid]["pt"] = new_pt
    save_attend()
    badge = get_badge(new_pt)
    await interaction.response.send_message(
        f"✅ **{member.display_name}** のポイントを **{new_pt}pt** に設定しました。{badge}",
        ephemeral=True
    )


@bot.tree.command(name="attend_history", description="メンバーの出席履歴を表示します")
@discord.app_commands.describe(member="対象メンバー")
async def attend_history(interaction: discord.Interaction, member: discord.Member):
    uid   = str(member.id)
    entry = attend_data["members"].get(uid)
    if entry is None:
        await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
        return

    records = entry.get("records", {})
    if not records:
        await interaction.response.send_message(f"**{entry['name']}** の記録はまだありません。", ephemeral=True)
        return

    lines = [f"**📅 {entry['name']} の出席履歴** (現在: {entry['pt']}pt)\n"]
    for date in sorted(records.keys(), reverse=True)[:20]:
        lines.append(f"• {date} : {records[date]}")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ============================================================
# 起動
# ============================================================
bot.run(TOKEN)
