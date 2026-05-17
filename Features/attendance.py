import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from pathlib import Path
from database.config_db import DB_PATH, use_postgres, db_get, db_set
import json


# ============================================================
# 定数
# ============================================================

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

DB_KEY = "attendance_data"
LEGACY_ATTEND_PATH = Path("attend_data.json")
ATTEND_BACKUP_PATH = Path("/data/attendance_backup.json") if use_postgres() else Path(DB_PATH).with_name("attendance_backup.json")


# ============================================================
# ポイント計算
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
    change = calc_point_change(current_pt, status)
    return min(10, current_pt + change)


def get_badge(pt: int) -> str:
    if pt <= 0:
        return "🚨 退出対象"
    elif pt <= 2:
        return "⚠️ 第2警告"
    elif pt <= 4:
        return "❗ 第1警告"
    return "✅"


# ============================================================
# データ管理（DBに JSON で保存）
# ============================================================

async def load_attend() -> dict:
    raw = await db_get(DB_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass

    for path in (ATTEND_BACKUP_PATH, LEGACY_ATTEND_PATH):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            await save_attend(data)
            return data
        except Exception:
            continue

    return {"members": {}, "notify_channel_id": None}


async def save_attend(data: dict):
    await db_set(DB_KEY, json.dumps(data, ensure_ascii=False))
    try:
        ATTEND_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        ATTEND_BACKUP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[attendance backup error] {type(e).__name__}: {e}", flush=True)


# ============================================================
# Views
# ============================================================

class AttendStatusSelect(discord.ui.Select):
    def __init__(self, uid: str, name: str, date: str, attend_data: dict):
        self.uid = uid
        self.date = date
        self.attend_data = attend_data
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=f"{name} の出席状況を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = self.values[0]
        entry = self.attend_data["members"].get(self.uid)
        if entry is None:
            await interaction.followup.send("❌ メンバーが見つかりません。", ephemeral=True)
            return
        change = calc_point_change(entry["pt"], status)
        new_pt = apply_point(entry["pt"], status)
        entry["pt"] = new_pt
        entry["records"][self.date] = status
        await save_attend(self.attend_data)
        sign = f"+{change}" if change >= 0 else str(change)
        await interaction.followup.send(
            f"✅ **{entry['name']}** | {status} → {sign}pt → **{new_pt}pt**",
            ephemeral=True,
        )


class AttendRecordView(discord.ui.View):
    def __init__(self, uid: str, name: str, date: str, attend_data: dict):
        super().__init__(timeout=300)
        self.add_item(AttendStatusSelect(uid, name, date, attend_data))


class BulkAttendSelect(discord.ui.Select):
    def __init__(self, uid: str, placeholder: str, date: str, parent_view, row: int):
        self.uid = uid
        self.parent_view = parent_view
        self.date = date
        options = [discord.SelectOption(label=s, value=s) for s in ATTEND_STATUSES]
        super().__init__(placeholder=placeholder, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selections[self.uid] = self.values[0]
        await interaction.response.defer()


class BulkAttendView(discord.ui.View):
    def __init__(self, record_date: str, member_list: list, attend_data: dict, page: int = 0, selections: dict = None):
        super().__init__(timeout=600)
        self.record_date = record_date
        self.member_list = member_list
        self.attend_data = attend_data
        self.page = page
        self.selections = selections if selections is not None else {}

        start = page * 4
        end = min(start + 4, len(member_list))
        page_members = member_list[start:end]

        for i, (uid, name, pt) in enumerate(page_members):
            already = self.selections.get(uid, "")
            ph = f"{name}（{pt}pt）" + (f" ✅{already[:6]}" if already else "")
            self.add_item(BulkAttendSelect(uid, ph[:100], record_date, self, row=i))

        if page > 0:
            prev_btn = discord.ui.Button(label="← 前へ", style=discord.ButtonStyle.secondary, row=4)
            async def prev_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, attend_data, p - 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        if end < len(member_list):
            next_btn = discord.ui.Button(label="次へ →", style=discord.ButtonStyle.primary, row=4)
            async def next_cb(inter: discord.Interaction, p=page):
                new_view = BulkAttendView(record_date, member_list, attend_data, p + 1, self.selections)
                await inter.response.edit_message(content=new_view.content(), view=new_view)
            next_btn.callback = next_cb
            self.add_item(next_btn)

        save_btn = discord.ui.Button(label="✅ 保存する", style=discord.ButtonStyle.success, row=4)
        async def save_cb(inter: discord.Interaction):
            await inter.response.defer(ephemeral=True)
            if not self.selections:
                await inter.followup.send("❌ 少なくとも1人の出席状況を選択してください。", ephemeral=True)
                return
            results = []
            for uid, status in self.selections.items():
                entry = self.attend_data["members"].get(uid)
                if entry is None:
                    continue
                change = calc_point_change(entry["pt"], status)
                new_pt = apply_point(entry["pt"], status)
                entry["pt"] = new_pt
                entry["records"][record_date] = status
                sign = f"+{change}" if change >= 0 else str(change)
                results.append(f"• **{entry['name']}** : {status} → {sign}pt → **{new_pt}pt**")
            await save_attend(self.attend_data)
            await inter.followup.send(
                f"✅ **{record_date}** の記録が完了しました！\n\n" + "\n".join(results),
                ephemeral=True,
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


# ============================================================
# Cog
# ============================================================

class Attendance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="attend_set_channel", description="【管理者】出席通知チャンネルを現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def attend_set_channel(self, interaction: discord.Interaction):
        data = await load_attend()
        data["notify_channel_id"] = interaction.channel.id
        await save_attend(data)
        await interaction.response.send_message(
            f"✅ 通知チャンネルを {interaction.channel.mention} に設定しました。", ephemeral=True
        )

    @app_commands.command(name="attend_add_member", description="【管理者】出席管理にメンバーを追加します")
    @app_commands.describe(member="追加するメンバー", initial_pt="初期ポイント（デフォルト: 10）")
    @app_commands.default_permissions(administrator=True)
    async def attend_add_member(self, interaction: discord.Interaction, member: discord.Member, initial_pt: int = 10):
        data = await load_attend()
        uid = str(member.id)
        if uid in data["members"]:
            await interaction.response.send_message(f"⚠️ {member.display_name} は既に登録されています。", ephemeral=True)
            return
        data["members"][uid] = {"name": member.display_name, "pt": initial_pt, "records": {}}
        await save_attend(data)
        await interaction.response.send_message(f"✅ {member.display_name} を追加しました（{initial_pt}pt）", ephemeral=True)

    @app_commands.command(name="attend_add_members_bulk", description="【管理者】メンバーを選択して一括追加します")
    @app_commands.describe(initial_pt="初期ポイント（デフォルト: 10）")
    @app_commands.default_permissions(administrator=True)
    async def attend_add_members_bulk(self, interaction: discord.Interaction, initial_pt: int = 10):
        data = await load_attend()
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in interaction.guild.members
            if not m.bot and str(m.id) not in data["members"]
        ]
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
                    max_values=len(options),
                )
            async def callback(self2, interaction2: discord.Interaction):
                await interaction2.response.defer(ephemeral=True)
                added = []
                for uid in self2.values:
                    m = interaction2.guild.get_member(int(uid))
                    if m is None:
                        continue
                    data["members"][uid] = {"name": m.display_name, "pt": initial_pt, "records": {}}
                    added.append(m.display_name)
                await save_attend(data)
                await interaction2.followup.send(
                    f"✅ **{len(added)}人** を追加しました！\n" + "、".join(added), ephemeral=True
                )

        view = discord.ui.View(timeout=120)
        view.add_item(MemberMultiSelect())
        await interaction.response.send_message("追加するメンバーを選んでください：", view=view, ephemeral=True)

    @app_commands.command(name="attend_remove_member", description="【管理者】出席管理からメンバーを削除します")
    @app_commands.describe(member="削除するメンバー")
    @app_commands.default_permissions(administrator=True)
    async def attend_remove_member(self, interaction: discord.Interaction, member: discord.Member):
        data = await load_attend()
        uid = str(member.id)
        if uid not in data["members"]:
            await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
            return
        del data["members"][uid]
        await save_attend(data)
        await interaction.response.send_message(f"🗑️ {member.display_name} を削除しました。", ephemeral=True)

    @app_commands.command(name="attend_record", description="【管理者】メンバーを選択して出席を記録します")
    @app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
    @app_commands.default_permissions(administrator=True)
    async def attend_record(self, interaction: discord.Interaction, date: str = ""):
        data = await load_attend()
        members = data["members"]
        if not members:
            await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
            return
        record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
        options = [
            discord.SelectOption(label=e["name"], value=uid, description=f"現在: {e['pt']}pt")
            for uid, e in members.items()
        ]

        class MemberSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(placeholder="メンバーを選択", options=options[:25])
            async def callback(self2, interaction2: discord.Interaction):
                uid = self2.values[0]
                entry = data["members"].get(uid)
                view2 = AttendRecordView(uid, entry["name"], record_date, data)
                await interaction2.response.send_message(
                    f"📋 **{entry['name']}** の出席記録（{record_date}）\n現在: **{entry['pt']}pt**",
                    view=view2, ephemeral=True,
                )

        view = discord.ui.View(timeout=120)
        view.add_item(MemberSelect())
        await interaction.response.send_message(
            f"📋 出席記録（{record_date}）\nメンバーを選んでください：", view=view, ephemeral=True
        )

    @app_commands.command(name="attend_record_all", description="【管理者】全メンバーの出席を一括で記録します")
    @app_commands.describe(date="記録日（省略すると今日）例: 2025-01-15")
    @app_commands.default_permissions(administrator=True)
    async def attend_record_all(self, interaction: discord.Interaction, date: str = ""):
        data = await load_attend()
        members = data["members"]
        if not members:
            await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
            return
        record_date = date.strip() if date.strip() else datetime.now().strftime("%Y-%m-%d")
        member_list = [(uid, e["name"], e["pt"]) for uid, e in members.items()]
        view = BulkAttendView(record_date, member_list, data, page=0)
        await interaction.response.send_message(view.content(), view=view, ephemeral=True)

    @app_commands.command(name="attend_status", description="出席ポイント一覧を表示します")
    async def attend_status(self, interaction: discord.Interaction):
        data = await load_attend()
        members = data["members"]
        if not members:
            await interaction.response.send_message("登録メンバーがいません。", ephemeral=True)
            return
        sorted_members = sorted(members.items(), key=lambda x: x[1]["pt"])
        lines = ["**📊 出席ポイント一覧**\n"]
        for uid, entry in sorted_members:
            badge = get_badge(entry["pt"])
            lines.append(f"{badge} <@{uid}> **{entry['name']}** : **{entry['pt']}pt**")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="attend_warnings", description="警告対象のメンバーを表示します")
    async def attend_warnings(self, interaction: discord.Interaction):
        data = await load_attend()
        warnings = [
            f"{get_badge(e['pt'])} <@{uid}> **{e['name']}** : **{e['pt']}pt**"
            for uid, e in sorted(data["members"].items(), key=lambda x: x[1]["pt"])
            if e["pt"] <= 4
        ]
        if warnings:
            await interaction.response.send_message("**⚠️ 警告対象メンバー一覧**\n\n" + "\n".join(warnings))
        else:
            await interaction.response.send_message("✅ 現在、警告対象のメンバーはいません。")

    @app_commands.command(name="attend_notify", description="【管理者】警告対象メンバーを通知チャンネルに送信します")
    @app_commands.default_permissions(administrator=True)
    async def attend_notify(self, interaction: discord.Interaction):
        data = await load_attend()
        ch_id = data.get("notify_channel_id")
        warnings = [
            f"{get_badge(e['pt'])} <@{uid}> **{e['name']}** : **{e['pt']}pt**"
            for uid, e in data["members"].items()
            if e["pt"] <= 4
        ]
        msg = "📢 **出席ポイント警告通知**\n"
        msg += "\n".join(warnings) if warnings else "✅ 現在、警告対象のメンバーはいません。"
        if ch_id:
            ch = self.bot.get_channel(ch_id)
            if ch:
                await ch.send(msg)
                await interaction.response.send_message("✅ 通知チャンネルに送信しました。", ephemeral=True)
                return
        await interaction.response.send_message(msg)

    @app_commands.command(name="attend_set_pt", description="【管理者】メンバーのポイントを直接設定します")
    @app_commands.describe(member="対象メンバー", pt="設定するポイント")
    @app_commands.default_permissions(administrator=True)
    async def attend_set_pt(self, interaction: discord.Interaction, member: discord.Member, pt: int):
        data = await load_attend()
        uid = str(member.id)
        if uid not in data["members"]:
            await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
            return
        new_pt = min(10, pt)
        data["members"][uid]["pt"] = new_pt
        await save_attend(data)
        await interaction.response.send_message(
            f"✅ **{member.display_name}** のポイントを **{new_pt}pt** に設定しました。{get_badge(new_pt)}",
            ephemeral=True,
        )

    @app_commands.command(name="attend_history", description="メンバーの出席履歴を表示します")
    @app_commands.describe(member="対象メンバー")
    async def attend_history(self, interaction: discord.Interaction, member: discord.Member):
        data = await load_attend()
        uid = str(member.id)
        entry = data["members"].get(uid)
        if entry is None:
            await interaction.response.send_message(f"❌ {member.display_name} は登録されていません。", ephemeral=True)
            return
        records = entry.get("records", {})
        if not records:
            await interaction.response.send_message(f"**{entry['name']}** の記録はまだありません。", ephemeral=True)
            return
        lines = [f"**📅 {entry['name']} の出席履歴** (現在: {entry['pt']}pt)\n"]
        for d in sorted(records.keys(), reverse=True)[:20]:
            lines.append(f"• {d} : {records[d]}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        data = await load_attend()
        changed = False
        for guild in self.bot.guilds:
            for uid, entry in data["members"].items():
                m = guild.get_member(int(uid))
                if m and m.display_name != entry["name"]:
                    entry["name"] = m.display_name
                    changed = True
        if changed:
            await save_attend(data)


async def setup(bot: commands.Bot):
    await bot.add_cog(Attendance(bot))
