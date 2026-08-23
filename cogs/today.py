import json
import os
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.config_db import db_get, db_set


JST = timezone(timedelta(hours=9))
DEFAULT_NOTIFY_HOUR = int(os.getenv("TODAY_NOTIFY_HOUR_JST", "12"))
DEFAULT_NOTIFY_MINUTE = int(os.getenv("TODAY_NOTIFY_MINUTE_JST", "0"))


DEFAULT_TODAY_EVENTS = {
    "01-01": [{"name": "元日", "description": "新しい年の始まりの日です。"}],
    "01-07": [{"name": "七草の日", "description": "七草がゆを食べて無病息災を願う日として知られています。"}],
    "01-11": [{"name": "鏡開き", "description": "地域差はありますが、鏡餅を開いていただく日として知られています。"}],
    "02-03": [{"name": "節分", "description": "季節の分かれ目に豆まきなどを行う日です。年によって日付がずれる場合があります。"}],
    "02-14": [{"name": "バレンタインデー", "description": "チョコレートや贈り物を通して気持ちを伝える日として親しまれています。"}],
    "02-22": [{"name": "猫の日", "description": "2が並ぶ語呂合わせから、猫に親しむ日として知られています。"}],
    "03-03": [{"name": "ひな祭り", "description": "女の子の健やかな成長を願う行事の日です。"}],
    "03-14": [{"name": "ホワイトデー", "description": "バレンタインデーのお返しをする日として広まりました。"}],
    "04-01": [{"name": "エイプリルフール", "description": "軽い冗談やユーモアを楽しむ日として知られています。"}],
    "04-22": [{"name": "アースデー", "description": "地球環境について考える日です。"}],
    "05-05": [{"name": "こどもの日", "description": "子どもの人格を重んじ、幸福を願う国民の祝日です。"}],
    "05-09": [{"name": "アイスクリームの日", "description": "アイスクリームに親しむ記念日として知られています。"}],
    "06-10": [{"name": "時の記念日", "description": "時間の大切さを考える記念日です。"}],
    "06-16": [{"name": "和菓子の日", "description": "和菓子と健康招福にまつわる記念日です。"}],
    "07-07": [{"name": "七夕", "description": "短冊に願いを書き、星に思いを託す行事の日です。"}],
    "07-26": [{"name": "幽霊の日", "description": "江戸時代の怪談芝居『東海道四谷怪談』の初演日にちなむとされます。"}],
    "08-08": [{"name": "そろばんの日", "description": "そろばんを弾く音の語呂合わせから知られる記念日です。"}],
    "08-31": [{"name": "野菜の日", "description": "8・3・1の語呂合わせから、野菜に親しむ日として知られています。"}],
    "09-09": [{"name": "救急の日", "description": "9・9の語呂合わせから、救急医療への理解を深める日です。"}],
    "09-29": [{"name": "招き猫の日", "description": "来る福の語呂合わせから、招き猫にまつわる日として知られています。"}],
    "10-10": [{"name": "銭湯の日", "description": "1010を『せんとう』と読む語呂合わせの記念日です。"}],
    "10-31": [{"name": "ハロウィン", "description": "仮装やお菓子などで親しまれる行事の日です。"}],
    "11-03": [{"name": "文化の日", "description": "自由と平和を愛し、文化をすすめる国民の祝日です。"}],
    "11-11": [{"name": "ポッキー＆プリッツの日", "description": "棒状のお菓子が並ぶ形にちなんだ記念日として有名です。"}],
    "11-22": [{"name": "いい夫婦の日", "description": "11・22の語呂合わせから、夫婦にまつわる日として知られています。"}],
    "12-24": [{"name": "クリスマス・イブ", "description": "クリスマス前夜として広く親しまれています。"}],
    "12-25": [{"name": "クリスマス", "description": "日本でも贈り物や食事を楽しむ行事として親しまれています。"}],
    "12-31": [{"name": "大晦日", "description": "一年の最後の日です。年越しの準備や除夜の鐘で知られています。"}],
}

EXTRA_FIXED_TODAY_EVENTS = {
    "01-10": [{"name": "110番の日", "description": "110番通報の適切な利用を呼びかける日です。"}],
    "01-15": [{"name": "いちごの日", "description": "1・15の語呂合わせから、いちごに親しむ日として知られています。"}],
    "02-02": [{"name": "夫婦の日", "description": "2・2の語呂合わせから、夫婦にまつわる日として知られています。"}],
    "02-09": [{"name": "肉の日", "description": "2・9の語呂合わせから、肉に親しむ日として知られています。"}],
    "03-09": [{"name": "ありがとうの日", "description": "3・9の語呂合わせから、感謝を伝える日として知られています。"}],
    "03-15": [{"name": "靴の記念日", "description": "日本で西洋式の靴工場が開かれたことにちなむ記念日です。"}],
    "04-06": [{"name": "城の日", "description": "4・6の語呂合わせから、城にまつわる日として知られています。"}],
    "04-10": [{"name": "駅弁の日", "description": "駅弁文化に親しむ記念日として知られています。"}],
    "05-02": [{"name": "えんぴつ記念日", "description": "鉛筆にまつわる記念日として知られています。"}],
    "05-10": [{"name": "メイドの日", "description": "5・10の語呂合わせから、ネット文化でも親しまれている日です。"}],
    "05-23": [{"name": "キスの日", "description": "日本映画でキスシーンが話題になった日にちなむとされます。"}],
    "06-06": [{"name": "楽器の日", "description": "芸事は6歳の6月6日から始めると上達するという言い伝えにちなむ日です。"}],
    "07-22": [{"name": "ナッツの日", "description": "7・22の語呂合わせから、ナッツに親しむ日として知られています。"}],
    "08-07": [{"name": "花の日", "description": "8・7の語呂合わせから、花にまつわる日として知られています。"}],
    "08-10": [{"name": "ハートの日", "description": "8・10の語呂合わせから、心や気持ちにまつわる日として知られています。"}],
    "09-06": [{"name": "黒の日", "description": "9・6の語呂合わせから、黒色にまつわる日として知られています。"}],
    "09-10": [{"name": "牛タンの日", "description": "9・10の語呂合わせから、牛タンに親しむ日として知られています。"}],
    "10-01": [{"name": "コーヒーの日", "description": "国際的にもコーヒーに親しむ日として知られています。"}],
    "10-04": [{"name": "天使の日", "description": "10・4の語呂合わせから、天使にまつわる日として知られています。"}],
    "10-30": [{"name": "たまごかけごはんの日", "description": "たまごかけごはんに親しむ記念日として知られています。"}],
    "11-01": [{"name": "犬の日", "description": "犬の鳴き声の語呂合わせから、犬に親しむ日として知られています。"}],
    "11-05": [{"name": "いいりんごの日", "description": "11・5の語呂合わせから、りんごに親しむ日として知られています。"}],
    "11-29": [{"name": "いい肉の日", "description": "11・29の語呂合わせから、肉に親しむ日として有名です。"}],
    "12-12": [{"name": "漢字の日", "description": "いい字一字の語呂合わせから、漢字にまつわる日として知られています。"}],
}


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> int:
    day = 1
    while datetime(year, month, day).weekday() != weekday:
        day += 1
    return day + (nth - 1) * 7


def vernal_equinox_day(year: int) -> int:
    if 1900 <= year <= 2099:
        return int(20.8431 + 0.242194 * (year - 1980) - ((year - 1980) // 4))
    return 20


def autumnal_equinox_day(year: int) -> int:
    if 1900 <= year <= 2099:
        return int(23.2488 + 0.242194 * (year - 1980) - ((year - 1980) // 4))
    return 23


def add_holiday(holidays: dict[tuple[int, int], list[dict]], month: int, day: int, name: str, description: str):
    holidays.setdefault((month, day), []).append({"name": name, "description": description})


def japanese_holiday_events(year: int) -> dict[tuple[int, int], list[dict]]:
    holidays: dict[tuple[int, int], list[dict]] = {}
    add_holiday(holidays, 1, 1, "元日", "新しい年の始まりを祝う国民の祝日です。")
    add_holiday(holidays, 1, nth_weekday(year, 1, 0, 2), "成人の日", "大人になったことを自覚し、自ら生き抜こうとする青年を祝い励ます祝日です。")
    add_holiday(holidays, 2, 11, "建国記念の日", "建国をしのび、国を愛する心を養う国民の祝日です。")
    if year >= 2020:
        add_holiday(holidays, 2, 23, "天皇誕生日", "天皇の誕生日を祝う国民の祝日です。")
    add_holiday(holidays, 3, vernal_equinox_day(year), "春分の日", "自然をたたえ、生物をいつくしむ国民の祝日です。")
    add_holiday(holidays, 4, 29, "昭和の日", "激動の日々を経て復興を遂げた昭和の時代を顧みる祝日です。")
    add_holiday(holidays, 5, 3, "憲法記念日", "日本国憲法の施行を記念する国民の祝日です。")
    add_holiday(holidays, 5, 4, "みどりの日", "自然に親しみ、その恩恵に感謝する国民の祝日です。")
    add_holiday(holidays, 5, 5, "こどもの日", "子どもの人格を重んじ、幸福を願う国民の祝日です。")
    add_holiday(holidays, 7, nth_weekday(year, 7, 0, 3), "海の日", "海の恩恵に感謝し、海洋国日本の繁栄を願う国民の祝日です。")
    if year >= 2016:
        add_holiday(holidays, 8, 11, "山の日", "山に親しむ機会を得て、山の恩恵に感謝する国民の祝日です。")
    add_holiday(holidays, 9, nth_weekday(year, 9, 0, 3), "敬老の日", "多年にわたり社会につくしてきた老人を敬愛し、長寿を祝う祝日です。")
    add_holiday(holidays, 9, autumnal_equinox_day(year), "秋分の日", "祖先をうやまい、なくなった人々をしのぶ国民の祝日です。")
    add_holiday(holidays, 10, nth_weekday(year, 10, 0, 2), "スポーツの日", "スポーツを楽しみ、他者を尊重する精神を培う祝日です。")
    add_holiday(holidays, 11, 3, "文化の日", "自由と平和を愛し、文化をすすめる国民の祝日です。")
    add_holiday(holidays, 11, 23, "勤労感謝の日", "勤労をたっとび、生産を祝い、国民が互いに感謝しあう祝日です。")

    base_days = sorted(holidays)
    for month, day in base_days:
        date = datetime(year, month, day)
        if date.weekday() != 6:
            continue
        substitute = date + timedelta(days=1)
        while (substitute.month, substitute.day) in holidays:
            substitute += timedelta(days=1)
        add_holiday(holidays, substitute.month, substitute.day, "振替休日", "国民の祝日が日曜日にあたる場合の振替休日です。")

    current = datetime(year, 1, 2)
    end = datetime(year, 12, 30)
    while current <= end:
        previous_day = current - timedelta(days=1)
        next_day = current + timedelta(days=1)
        if (
            (current.month, current.day) not in holidays
            and (previous_day.month, previous_day.day) in holidays
            and (next_day.month, next_day.day) in holidays
        ):
            add_holiday(holidays, current.month, current.day, "国民の休日", "祝日と祝日に挟まれた休日です。")
        current += timedelta(days=1)
    return holidays


def summer_doyo_no_ushi_events(year: int) -> dict[tuple[int, int], list[dict]]:
    events: dict[tuple[int, int], list[dict]] = {}
    anchor = datetime(2026, 7, 26)
    current = datetime(year, 7, 19)
    end = datetime(year, 8, 7)
    while current <= end:
        if (current - anchor).days % 12 == 0:
            add_holiday(
                events,
                current.month,
                current.day,
                "土用の丑の日",
                "夏の土用期間中の丑の日です。うなぎを食べる日としてよく知られています。",
            )
        current += timedelta(days=1)
    return events


def dynamic_today_events(year: int, month: int, day: int) -> list[dict]:
    events = []
    events.extend(japanese_holiday_events(year).get((month, day), []))
    events.extend(summer_doyo_no_ushi_events(year).get((month, day), []))
    return events


DAILY_FOOD_THEMES = [
    "おにぎり", "味噌汁", "カレー", "うどん", "そば", "ラーメン", "たこ焼き", "お好み焼き",
    "寿司", "天ぷら", "唐揚げ", "焼き鳥", "ハンバーグ", "オムライス", "ナポリタン", "餃子",
    "焼きそば", "親子丼", "牛丼", "お茶漬け", "卵かけご飯", "おでん", "鍋", "豚汁",
    "コロッケ", "サンドイッチ", "ホットケーキ", "プリン", "団子", "たい焼き", "アイス",
]

DAILY_NATURE_THEMES = [
    "朝日", "夕焼け", "星空", "月", "雲", "雨音", "虹", "風", "海", "川", "湖", "山",
    "森", "草原", "花", "桜", "新緑", "紅葉", "雪", "霜", "雷", "木漏れ日", "野鳥",
    "虫の声", "潮風", "青空", "夕立", "霧", "小川", "砂浜", "流れ星",
]

DAILY_FUN_THEMES = [
    "カードゲーム", "ボードゲーム", "クイズ", "謎解き", "映画", "アニメ", "漫画", "読書",
    "音楽", "カラオケ", "散歩", "写真", "料理", "お絵描き", "雑談", "ゲーム募集",
    "Among Us", "作業通話", "動画編集", "短歌", "川柳", "しりとり", "心理テスト", "大喜利",
    "おすすめ紹介", "ランキング作り", "思い出話", "豆知識", "ミニ企画", "今日の目標", "反省会",
]


def daily_theme_events(year: int, month: int, day: int) -> list[dict]:
    day_index = datetime(year, month, day).timetuple().tm_yday - 1
    food = DAILY_FOOD_THEMES[day_index % len(DAILY_FOOD_THEMES)]
    nature = DAILY_NATURE_THEMES[(day_index * 3 + month) % len(DAILY_NATURE_THEMES)]
    fun = DAILY_FUN_THEMES[(day_index * 5 + day) % len(DAILY_FUN_THEMES)]
    return [
        {
            "name": f"今日の食べ物テーマ: {food}",
            "description": f"今日は {food} を話題にしてみる日です。好きな食べ方や思い出を話すきっかけにできます。",
        },
        {
            "name": f"今日の自然テーマ: {nature}",
            "description": f"今日は {nature} に少し目を向ける日です。写真、天気、季節の話題にも使えます。",
        },
        {
            "name": f"今日の娯楽テーマ: {fun}",
            "description": f"今日は {fun} を楽しむきっかけの日です。サーバー内の雑談や募集ネタにどうぞ。",
        },
    ]


def today_settings_key(guild_id: int) -> str:
    return f"today_settings:{guild_id}"


def today_custom_key(guild_id: int) -> str:
    return f"today_custom_events:{guild_id}"


def date_key(month: int, day: int) -> str:
    return f"{month:02d}-{day:02d}"


def read_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


async def get_json(key: str, default):
    return read_json(await db_get(key), default)


async def set_json(key: str, value):
    await db_set(key, json.dumps(value, ensure_ascii=False))


def default_settings() -> dict:
    return {
        "channel_id": 0,
        "enabled": True,
        "hour": max(0, min(23, DEFAULT_NOTIFY_HOUR)),
        "minute": max(0, min(59, DEFAULT_NOTIFY_MINUTE)),
        "last_date": "",
    }


def setting_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def validate_date(month: int, day: int) -> bool:
    try:
        datetime(2024, month, day)
        return True
    except ValueError:
        return False


class Today(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.today_loop.start()

    def cog_unload(self):
        if self.today_loop.is_running():
            self.today_loop.cancel()

    async def get_settings(self, guild_id: int) -> dict:
        settings = await get_json(today_settings_key(guild_id), {})
        merged = default_settings()
        if isinstance(settings, dict):
            merged.update(settings)
        return merged

    async def save_settings(self, guild_id: int, settings: dict):
        await set_json(today_settings_key(guild_id), settings)

    async def get_custom_events(self, guild_id: int) -> dict:
        data = await get_json(today_custom_key(guild_id), {})
        return data if isinstance(data, dict) else {}

    async def save_custom_events(self, guild_id: int, data: dict):
        await set_json(today_custom_key(guild_id), data)

    async def custom_events_for(self, guild_id: int, month: int, day: int) -> list[dict]:
        custom = await self.get_custom_events(guild_id)
        items = custom.get(date_key(month, day), [])
        return [item for item in items if isinstance(item, dict)]

    async def events_for(self, guild_id: int, month: int, day: int, year: int | None = None) -> list[dict]:
        year = year or datetime.now(JST).year
        key = date_key(month, day)
        events = [dict(item) for item in DEFAULT_TODAY_EVENTS.get(key, [])]
        events.extend(dict(item) for item in EXTRA_FIXED_TODAY_EVENTS.get(key, []))
        events.extend(dynamic_today_events(year, month, day))
        events.extend(await self.custom_events_for(guild_id, month, day))
        if not events:
            events.extend(daily_theme_events(year, month, day))
        unique_events = []
        seen = set()
        for event in events:
            name = str(event.get("name") or "")
            marker = name
            if marker in seen:
                continue
            seen.add(marker)
            unique_events.append(event)
        return unique_events

    def build_embed(self, guild: discord.Guild, events: list[dict], now: datetime) -> discord.Embed:
        title = f"今日はなんの日？ {now.month}月{now.day}日"
        embed = discord.Embed(title=title, color=0x6EC6FF, timestamp=now.astimezone(timezone.utc))
        if events:
            selected = events[:5]
            lines = []
            for event in selected:
                name = str(event.get("name") or "記念日")
                description = str(event.get("description") or "").strip()
                lines.append(f"**{name}**\n{description or '今日はこの記念日として知られています。'}")
            embed.description = "\n\n".join(lines)
            if len(events) > len(selected):
                embed.set_footer(text=f"ほか {len(events) - len(selected)} 件あります。/today_list で確認できます。")
        else:
            embed.description = "登録されている記念日はまだありません。管理者は `/today_add` で追加できます。"
        embed.set_author(name=guild.name)
        return embed

    async def send_today(self, guild: discord.Guild, channel: discord.TextChannel):
        now = datetime.now(JST)
        events = await self.events_for(guild.id, now.month, now.day, now.year)
        await channel.send(
            embed=self.build_embed(guild, events, now),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def resolve_channel(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel | None:
        channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            return None
        return fetched if isinstance(fetched, discord.TextChannel) and fetched.guild.id == guild.id else None

    @tasks.loop(minutes=1)
    async def today_loop(self):
        await self.bot.wait_until_ready()
        now = datetime.now(JST)
        for guild in self.bot.guilds:
            try:
                await self.send_today_if_due(guild, now)
            except Exception as exc:
                print(
                    f"[today] guild check failed: guild={guild.id} {type(exc).__name__}: {exc}",
                    flush=True,
                )

    async def send_today_if_due(self, guild: discord.Guild, now: datetime) -> bool:
        settings = await self.get_settings(guild.id)
        if not settings.get("enabled", True):
            return False
        scheduled_at = now.replace(
            hour=setting_int(settings.get("hour"), 12, 0, 23),
            minute=setting_int(settings.get("minute"), 0, 0, 59),
            second=0,
            microsecond=0,
        )
        today = now.date().isoformat()
        if now < scheduled_at or settings.get("last_date") == today:
            return False

        channel_id = setting_int(settings.get("channel_id"), 0, 0, 2**63 - 1)
        if not channel_id:
            return False
        channel = await self.resolve_channel(guild, channel_id)
        if channel is None:
            print(f"[today] configured channel not found: guild={guild.id} channel={channel_id}", flush=True)
            return False

        await self.send_today(guild, channel)
        settings["last_date"] = today
        await self.save_settings(guild.id, settings)
        return True

    @today_loop.before_loop
    async def before_today_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="today_channel", description="【管理者】今日はなんの日の通知先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def today_channel(self, interaction: discord.Interaction, hour: int = 12, minute: int = 0):
        if not interaction.guild_id or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            await interaction.response.send_message("時刻は `hour: 0-23`、`minute: 0-59` で指定してください。", ephemeral=True)
            return
        settings = await self.get_settings(interaction.guild_id)
        settings.update({"channel_id": interaction.channel_id, "hour": hour, "minute": minute, "enabled": True})
        await self.save_settings(interaction.guild_id, settings)
        await interaction.response.send_message(
            f"今日はなんの日の通知先を {interaction.channel.mention} に設定しました。\n"
            f"通知時刻: **毎日 JST {hour:02d}:{minute:02d}**",
            ephemeral=True,
        )

    @app_commands.command(name="today_now", description="今日の『今日はなんの日』を今すぐ投稿します")
    async def today_now(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return
        now = datetime.now(JST)
        events = await self.events_for(interaction.guild.id, now.month, now.day, now.year)
        await interaction.response.send_message(embed=self.build_embed(interaction.guild, events, now))

    @app_commands.command(name="today_status", description="今日はなんの日通知の設定を確認します")
    async def today_status(self, interaction: discord.Interaction):
        if not interaction.guild_id or not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.get_settings(interaction.guild_id)
        channel = interaction.guild.get_channel(int(settings.get("channel_id") or 0))
        channel_text = channel.mention if isinstance(channel, discord.TextChannel) else "未設定"
        enabled = "ON" if settings.get("enabled", True) else "OFF"
        await interaction.response.send_message(
            f"今日はなんの日通知: **{enabled}**\n"
            f"通知先: {channel_text}\n"
            f"通知時刻: **JST {int(settings.get('hour', 12)):02d}:{int(settings.get('minute', 0)):02d}**",
            ephemeral=True,
        )

    @app_commands.command(name="today_enable", description="【管理者】今日はなんの日通知のON/OFFを切り替えます")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(mode=[
        app_commands.Choice(name="ON", value="on"),
        app_commands.Choice(name="OFF", value="off"),
    ])
    async def today_enable(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.get_settings(interaction.guild_id)
        settings["enabled"] = mode.value == "on"
        await self.save_settings(interaction.guild_id, settings)
        await interaction.response.send_message(f"今日はなんの日通知を **{mode.name}** にしました。", ephemeral=True)

    @app_commands.command(name="today_add", description="【管理者】独自の記念日を追加します")
    @app_commands.default_permissions(manage_guild=True)
    async def today_add(self, interaction: discord.Interaction, month: int, day: int, name: str, description: str = ""):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not validate_date(month, day):
            await interaction.response.send_message("存在する日付を指定してください。", ephemeral=True)
            return
        key = date_key(month, day)
        data = await self.get_custom_events(interaction.guild_id)
        items = data.setdefault(key, [])
        item = {"name": name.strip()[:80], "description": description.strip()[:300]}
        items.append(item)
        data[key] = items[:20]
        await self.save_custom_events(interaction.guild_id, data)
        await interaction.response.send_message(f"{month}月{day}日に **{item['name']}** を追加しました。", ephemeral=True)

    @app_commands.command(name="today_edit", description="【管理者】独自の記念日を番号で編集します")
    @app_commands.default_permissions(manage_guild=True)
    async def today_edit(
        self,
        interaction: discord.Interaction,
        month: int,
        day: int,
        index: int,
        name: str | None = None,
        description: str | None = None,
    ):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if not validate_date(month, day):
            await interaction.response.send_message("存在する日付を指定してください。", ephemeral=True)
            return
        if name is None and description is None:
            await interaction.response.send_message("変更後の名前か内容を指定してください。", ephemeral=True)
            return
        key = date_key(month, day)
        data = await self.get_custom_events(interaction.guild_id)
        items = data.get(key, [])
        if index < 1 or index > len(items):
            await interaction.response.send_message("番号が範囲外です。`/today_list` で独自登録番号を確認してください。", ephemeral=True)
            return

        item = items[index - 1]
        if name is not None:
            new_name = name.strip()[:80]
            if new_name:
                item["name"] = new_name
        if description is not None:
            item["description"] = description.strip()[:300]
        data[key] = items
        await self.save_custom_events(interaction.guild_id, data)
        await interaction.response.send_message(
            f"{month}月{day}日の独自登録 {index} 番を **{item.get('name', '記念日')}** に更新しました。",
            ephemeral=True,
        )

    @app_commands.command(name="today_remove", description="【管理者】独自の記念日を番号で削除します")
    @app_commands.default_permissions(manage_guild=True)
    async def today_remove(self, interaction: discord.Interaction, month: int, day: int, index: int):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        key = date_key(month, day)
        data = await self.get_custom_events(interaction.guild_id)
        items = data.get(key, [])
        if index < 1 or index > len(items):
            await interaction.response.send_message("番号が範囲外です。`/today_list` で確認してください。", ephemeral=True)
            return
        removed = items.pop(index - 1)
        data[key] = items
        await self.save_custom_events(interaction.guild_id, data)
        await interaction.response.send_message(f"**{removed.get('name', '記念日')}** を削除しました。", ephemeral=True)

    @app_commands.command(name="today_list", description="指定日の登録済み記念日を確認します")
    async def today_list(self, interaction: discord.Interaction, month: int | None = None, day: int | None = None):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        now = datetime.now(JST)
        month = month or now.month
        day = day or now.day
        if not validate_date(month, day):
            await interaction.response.send_message("存在する日付を指定してください。", ephemeral=True)
            return
        events = await self.events_for(interaction.guild_id, month, day, now.year)
        if not events:
            await interaction.response.send_message(f"{month}月{day}日の登録はありません。", ephemeral=True)
            return
        lines = []
        custom_items = await self.custom_events_for(interaction.guild_id, month, day)
        if custom_items:
            lines.append("**独自登録（編集・削除用番号）**")
            for index, event in enumerate(custom_items, start=1):
                lines.append(f"{index}. **{event.get('name', '記念日')}** - {event.get('description', '')}")
            lines.append("")
            lines.append("**実際に表示される内容**")
        for index, event in enumerate(events, start=1):
            lines.append(f"{index}. **{event.get('name', '記念日')}** - {event.get('description', '')}")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Today(bot))
