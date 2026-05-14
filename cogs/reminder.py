import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta


# ==========================
# 時間解析ユーティリティ
# ==========================
def parse_relative(t: str) -> int:
    """'10m', '2h30m', '90s' などを秒数に変換。失敗時は -1 を返す"""
    sec = 0
    num = ""
    found = False
    for c in t:
        if c.isdigit():
            num += c
        elif c in ("s", "m", "h") and num:
            found = True
            if c == "s":
                sec += int(num)
            elif c == "m":
                sec += int(num) * 60
            elif c == "h":
                sec += int(num) * 3600
            num = ""
    return sec if found else -1


def parse_absolute(time_str: str) -> datetime | None:
    """
    以下の形式をすべて受け付ける:
      18:30
      2026-05-14
      2026-05-14_18:30
      2026-05-14-18:30
      2026-05-14 18:30
    """
    fmts = [
        "%Y-%m-%d_%H:%M",
        "%Y-%m-%d-%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%H:%M",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 日付なしなら今日/明日で補完
            if fmt == "%H:%M":
                now = datetime.now()
                dt = now.replace(
                    hour=dt.hour, minute=dt.minute, second=0, microsecond=0
                )
                if dt <= now:
                    dt += timedelta(days=1)
            return dt
        except ValueError:
            continue
    return None


# ==========================
# Cog 本体
# ==========================
class Reminder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # タスク管理: reminder_id -> asyncio.Task
        self._tasks: dict[int, asyncio.Task] = {}
        self._next_id = 0

    # -------------------------------------------------------
    # /remind
    # -------------------------------------------------------
    @app_commands.command(name="remind", description="指定した時間後またはその時刻にリマインドします")
    @app_commands.describe(
        time_str="例: 10m / 2h30m / 18:30 / 2026-05-14_18:30",
        message="リマインド内容",
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        time_str: str,
        message: str,
    ):
        now = datetime.now()

        # ① 相対時間（数字+s/m/h が含まれる）
        if any(c in time_str for c in ("s", "m", "h")) and any(c.isdigit() for c in time_str):
            seconds = parse_relative(time_str)
            if seconds <= 0:
                await interaction.response.send_message(
                    "❌ 時間指定が正しくありません。例: `10m` `2h` `90s`",
                    ephemeral=True,
                )
                return
            target = now + timedelta(seconds=seconds)

        # ② 絶対時間
        else:
            target = parse_absolute(time_str)
            if target is None:
                await interaction.response.send_message(
                    "❌ 時間形式が正しくありません。\n"
                    "使用例: `10m` / `18:30` / `2026-05-14_18:30`",
                    ephemeral=True,
                )
                return
            seconds = (target - now).total_seconds()
            if seconds <= 0:
                await interaction.response.send_message(
                    "❌ 過去の時間は指定できません。", ephemeral=True
                )
                return

        # 確認メッセージ
        reminder_id = self._next_id
        self._next_id += 1

        await interaction.response.send_message(
            f"⏰ **{target.strftime('%Y-%m-%d %H:%M')}** にリマインドします。\n"
            f"📝 内容: {message}\n"
            f"🆔 リマインダーID: `{reminder_id}`  ← キャンセルする場合は `/remind_cancel` で使用"
        )

        # タスクとして登録
        task = asyncio.create_task(
            self._fire(
                channel=interaction.channel,
                user=interaction.user,
                message=message,
                seconds=seconds,
                reminder_id=reminder_id,
            )
        )
        self._tasks[reminder_id] = task

    # -------------------------------------------------------
    # /remind_cancel
    # -------------------------------------------------------
    @app_commands.command(name="remind_cancel", description="リマインダーをキャンセルします")
    @app_commands.describe(reminder_id="キャンセルしたいリマインダーのID")
    async def remind_cancel(self, interaction: discord.Interaction, reminder_id: int):
        task = self._tasks.get(reminder_id)
        if task is None or task.done():
            await interaction.response.send_message(
                f"❌ ID `{reminder_id}` のリマインダーは見つかりません（すでに完了 or 存在しない）。",
                ephemeral=True,
            )
            return

        task.cancel()
        del self._tasks[reminder_id]
        await interaction.response.send_message(
            f"✅ リマインダー ID `{reminder_id}` をキャンセルしました。", ephemeral=True
        )

    # -------------------------------------------------------
    # /remind_list
    # -------------------------------------------------------
    @app_commands.command(name="remind_list", description="現在アクティブなリマインダー一覧を表示します")
    async def remind_list(self, interaction: discord.Interaction):
        active = {rid: t for rid, t in self._tasks.items() if not t.done()}
        if not active:
            await interaction.response.send_message(
                "📭 アクティブなリマインダーはありません。", ephemeral=True
            )
            return

        lines = [f"🆔 `{rid}`" for rid in active]
        await interaction.response.send_message(
            "⏰ **アクティブなリマインダー**\n" + "\n".join(lines),
            ephemeral=True,
        )

    # -------------------------------------------------------
    # 内部処理
    # -------------------------------------------------------
    async def _fire(
        self,
        channel: discord.TextChannel,
        user: discord.Member,
        message: str,
        seconds: float,
        reminder_id: int,
    ):
        try:
            await asyncio.sleep(seconds)
            await channel.send(f"🔔 {user.mention} リマインダー: **{message}**")
        except asyncio.CancelledError:
            pass  # キャンセル済み → 何もしない
        finally:
            self._tasks.pop(reminder_id, None)

    # Cog がアンロードされたとき全タスクをキャンセル
    async def cog_unload(self):
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminder(bot))
