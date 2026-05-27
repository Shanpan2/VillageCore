import calendar
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.config_db import db_get, db_set


JST = ZoneInfo("Asia/Tokyo")


def birthday_key(guild_id: int) -> str:
    return f"birthday_settings:{guild_id}"


def default_settings() -> dict:
    return {
        "channel_id": None,
        "birthdays": {},
        "last_sent": {},
    }


def validate_month_day(month: int, day: int):
    if month < 1 or month > 12:
        raise ValueError("月は1から12で指定してください。")
    max_day = calendar.monthrange(2024, month)[1]
    if day < 1 or day > max_day:
        raise ValueError(f"{month}月は1から{max_day}日までです。")


def zodiac_sign(month: int, day: int) -> str:
    signs = [
        ((1, 20), (2, 18), "水瓶座"),
        ((2, 19), (3, 20), "魚座"),
        ((3, 21), (4, 19), "牡羊座"),
        ((4, 20), (5, 20), "牡牛座"),
        ((5, 21), (6, 21), "双子座"),
        ((6, 22), (7, 22), "蟹座"),
        ((7, 23), (8, 22), "獅子座"),
        ((8, 23), (9, 22), "乙女座"),
        ((9, 23), (10, 23), "天秤座"),
        ((10, 24), (11, 22), "蠍座"),
        ((11, 23), (12, 21), "射手座"),
        ((12, 22), (12, 31), "山羊座"),
        ((1, 1), (1, 19), "山羊座"),
    ]
    for start, end, sign in signs:
        if (month, day) >= start and (month, day) <= end:
            return sign
    return "不明"


class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.birthday_loop.start()

    def cog_unload(self):
        self.birthday_loop.cancel()

    async def load_settings(self, guild_id: int) -> dict:
        raw = await db_get(birthday_key(guild_id))
        if not raw:
            return default_settings()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return default_settings()
        base = default_settings()
        base.update(data)
        base["birthdays"] = base.get("birthdays") or {}
        base["last_sent"] = base.get("last_sent") or {}
        return base

    async def save_settings(self, guild_id: int, data: dict):
        await db_set(birthday_key(guild_id), json.dumps(data, ensure_ascii=False))

    @tasks.loop(hours=1)
    async def birthday_loop(self):
        today = datetime.now(JST)
        for guild in self.bot.guilds:
            await self.notify_for_guild(guild, today, manual=False)

    @birthday_loop.before_loop
    async def before_birthday_loop(self):
        await self.bot.wait_until_ready()

    async def notify_for_guild(self, guild: discord.Guild, now: datetime, manual: bool = False) -> int:
        settings = await self.load_settings(guild.id)
        channel_id = settings.get("channel_id")
        if not channel_id:
            return 0

        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return 0

        today_key = now.strftime("%Y-%m-%d")
        sent_count = 0
        changed = False

        for user_id, entry in settings["birthdays"].items():
            if int(entry.get("month", 0)) != now.month or int(entry.get("day", 0)) != now.day:
                continue
            if settings["last_sent"].get(user_id) == today_key and not manual:
                continue

            member = guild.get_member(int(user_id))
            mention = member.mention if member else f"<@{user_id}>"
            name = member.display_name if member else entry.get("name", "member")
            embed = discord.Embed(
                title="誕生日おめでとうございます！",
                description=f"{mention} さん、素敵な一年になりますように。\n星座: **{zodiac_sign(now.month, now.day)}**",
                color=0xF7B731,
            )
            embed.set_footer(text=f"{name} / {now.month}月{now.day}日")
            await channel.send(content=f"今日は {mention} さんの誕生日です！", embed=embed)
            settings["last_sent"][user_id] = today_key
            sent_count += 1
            changed = True

        if changed:
            await self.save_settings(guild.id, settings)
        return sent_count

    @app_commands.command(name="birthday_channel", description="【管理者】誕生日通知先を現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.load_settings(interaction.guild_id)
        settings["channel_id"] = interaction.channel_id
        await self.save_settings(interaction.guild_id, settings)
        await interaction.response.send_message(f"誕生日通知先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="birthday_add", description="【管理者】メンバーの誕生日を登録します")
    @app_commands.describe(member="対象メンバー", month="月", day="日")
    @app_commands.default_permissions(administrator=True)
    async def add_birthday(self, interaction: discord.Interaction, member: discord.Member, month: int, day: int):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        try:
            validate_month_day(month, day)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        settings = await self.load_settings(interaction.guild_id)
        settings["birthdays"][str(member.id)] = {
            "month": month,
            "day": day,
            "name": member.display_name,
            "zodiac": zodiac_sign(month, day),
        }
        await self.save_settings(interaction.guild_id, settings)
        await interaction.response.send_message(
            f"{member.mention} の誕生日を **{month}月{day}日** に登録しました。\n星座: **{zodiac_sign(month, day)}**",
            ephemeral=True,
        )

    @app_commands.command(name="birthday_remove", description="【管理者】メンバーの誕生日登録を削除します")
    @app_commands.describe(member="対象メンバー")
    @app_commands.default_permissions(administrator=True)
    async def remove_birthday(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.load_settings(interaction.guild_id)
        removed = settings["birthdays"].pop(str(member.id), None)
        settings["last_sent"].pop(str(member.id), None)
        await self.save_settings(interaction.guild_id, settings)
        message = "削除しました。" if removed else "登録が見つかりませんでした。"
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="birthday_list", description="登録済みの誕生日一覧を表示します")
    async def list_birthdays(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.load_settings(interaction.guild_id)
        birthdays = settings["birthdays"]
        if not birthdays:
            await interaction.response.send_message("誕生日はまだ登録されていません。", ephemeral=True)
            return

        rows = []
        for user_id, entry in sorted(birthdays.items(), key=lambda item: (item[1]["month"], item[1]["day"])):
            member = interaction.guild.get_member(int(user_id))
            name = member.display_name if member else entry.get("name", user_id)
            sign = entry.get("zodiac") or zodiac_sign(int(entry["month"]), int(entry["day"]))
            rows.append(f"{entry['month']:02d}/{entry['day']:02d} - {name}（{sign}）")

        embed = discord.Embed(title="誕生日一覧", description="\n".join(rows[:60]), color=0xF7B731)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="birthday_check", description="【管理者】今日の誕生日通知を手動実行します")
    @app_commands.default_permissions(administrator=True)
    async def check_birthdays(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = await self.notify_for_guild(interaction.guild, datetime.now(JST), manual=True)
        await interaction.followup.send(f"誕生日通知を確認しました。送信件数: {count}", ephemeral=True)

    @app_commands.command(name="birthday_zodiac", description="誕生日から星座を計算します")
    @app_commands.describe(month="月", day="日")
    async def birthday_zodiac(self, interaction: discord.Interaction, month: int, day: int):
        try:
            validate_month_day(month, day)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(f"**{month}月{day}日** の星座は **{zodiac_sign(month, day)}** です。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
