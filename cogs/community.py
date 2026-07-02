import json
import os
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.config_db import db_get, db_get_all_config, db_set


JST = timezone(timedelta(hours=9))
EVENT_STATUSES = {
    "join": "参加",
    "maybe": "未定",
    "no": "不参加",
}
TOPICS = [
    "今日やりたいゲームは？",
    "最近いちばん笑ったことは？",
    "おすすめの動画や配信は？",
    "今週楽しみにしていることは？",
    "サーバーでやってみたい企画は？",
    "好きな食べ物を一つだけ挙げるなら？",
    "最近ハマっているものは？",
]


def jst_today() -> str:
    return datetime.now(JST).date().isoformat()


def json_get(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


async def get_json(key: str, default):
    return json_get(await db_get(key), default)


async def set_json(key: str, value):
    await db_set(key, json.dumps(value, ensure_ascii=False))


def parse_profile_items(raw: str) -> list[dict]:
    items = []
    if not raw:
        return items
    parts = []
    for line in raw.replace("；", ";").split(";"):
        parts.extend(line.splitlines())
    for part in parts:
        text = part.strip()
        if not text:
            continue
        separator = next((sep for sep in ("=", "：", ":") if sep in text), None)
        if not separator:
            continue
        name, value = text.split(separator, 1)
        name = name.strip()[:50]
        value = value.strip()[:300]
        if name and value:
            items.append({"name": name, "value": value})
        if len(items) >= 10:
            break
    return items


def profile_key(guild_id: int, user_id: int) -> str:
    return f"community_profile:{guild_id}:{user_id}"


def coin_key(guild_id: int, user_id: int) -> str:
    return f"community_coin:{guild_id}:{user_id}"


def coin_daily_key(guild_id: int, user_id: int) -> str:
    return f"community_coin_daily:{guild_id}:{user_id}"


def coin_gamble_lock_key(guild_id: int, user_id: int) -> str:
    return f"community_coin_gamble_lock:{guild_id}:{user_id}"


def coin_gamble_lock_reason_key(guild_id: int, user_id: int) -> str:
    return f"community_coin_gamble_lock_reason:{guild_id}:{user_id}"


def gamble_role_expirations_key(guild_id: int) -> str:
    return f"community_gamble_role_expirations:{guild_id}"


def titles_key(guild_id: int, user_id: int) -> str:
    return f"community_titles:{guild_id}:{user_id}"


def badges_key(guild_id: int, user_id: int) -> str:
    return f"community_badges:{guild_id}:{user_id}"


def penalty_task_key(guild_id: int, user_id: int) -> str:
    return f"community_penalty_task:{guild_id}:{user_id}"


COIN_MILESTONES = [
    {"coins": 50, "kind": "badge", "name": "小銭持ち"},
    {"coins": 100, "kind": "title", "name": "村の財布"},
    {"coins": 250, "kind": "badge", "name": "コツコツ村民"},
    {"coins": 500, "kind": "title", "name": "堅実な貯金家"},
    {"coins": 1000, "kind": "title_role", "name": "村の富豪"},
    {"coins": 2000, "kind": "badge", "name": "伝説の資産家"},
]
REPORT_COOLDOWN_SECONDS = int(os.getenv("REPORT_COOLDOWN_SECONDS", "300"))
REPORT_DEVELOPER_USER_ID = (
    os.getenv("REPORT_DEVELOPER_USER_ID")
    or os.getenv("BOT_DEVELOPER_USER_ID")
    or os.getenv("DEVELOPER_USER_ID")
)
REPORT_KIND_LABELS = {
    "bug": "バグ",
    "request": "要望",
    "abuse": "不正利用",
    "display": "表示崩れ",
    "other": "その他",
}
REAL_GAMBLER_ROLE_NAME = os.getenv("REAL_GAMBLER_ROLE_NAME", "リアルギャンブラー")
REAL_GAMBLER_ROLE_DAYS = int(os.getenv("REAL_GAMBLER_ROLE_DAYS", os.getenv("REAL_GAMBLER_LOCK_DAYS", "7")))

COIN_SHOP_ITEMS = {
    "red": {"kind": "role", "label": "赤カラー", "role_name": "カラー: 赤", "cost": 300, "days": 7, "color": 0xE74C3C},
    "blue": {"kind": "role", "label": "青カラー", "role_name": "カラー: 青", "cost": 300, "days": 7, "color": 0x3498DB},
    "green": {"kind": "role", "label": "緑カラー", "role_name": "カラー: 緑", "cost": 300, "days": 7, "color": 0x2ECC71},
    "purple": {"kind": "role", "label": "紫カラー", "role_name": "カラー: 紫", "cost": 300, "days": 7, "color": 0x9B59B6},
    "gold": {"kind": "role", "label": "金カラー", "role_name": "カラー: 金", "cost": 500, "days": 7, "color": 0xF1C40F},
    "editor": {"kind": "title", "label": "称号: 編集見習い", "name": "編集見習い", "cost": 120},
    "lucky": {"kind": "title", "label": "称号: 幸運の村民", "name": "幸運の村民", "cost": 180},
    "regular": {"kind": "badge", "label": "バッジ: ショップ常連", "name": "ショップ常連", "cost": 250},
    "sponsor": {"kind": "badge", "label": "バッジ: 村の支援者", "name": "村の支援者", "cost": 500},
}

PENALTY_GACHA_ITEMS = [
    "3分以上の動画素材を編集して、進捗を報告する",
    "7日以内に短い動画を1本投稿する",
    "30分以上、編集作業通話のVCで作業する",
    "今日中に動画企画を1つ書いて投稿する",
    "未編集素材を1つ整理して、次にやる作業を宣言する",
    "次の発言でギャンブル敗北レポートを1行提出する",
    "今日だけ慎重派を名乗り、ギャンブルを自粛する",
    "負けた理由をかっこよく言い訳する",
    "コイン復活後の健全な目標を1つ宣言する",
    "編集部屋VCに入れる時間を1つ宣言する",
    "おすすめ動画を1つ紹介して、良かった点を1行書く",
    "次のゲーム募集を1回立てる",
    "次のアモアスで強制参加したうえで初手吊りされる（1回）",
    "次のアモアス参加時に、名前を『ギャンカス〇〇〇』または『ギャンブラー〇〇』に変更する",
]


def coin_shop_expirations_key(guild_id: int) -> str:
    return f"community_coin_shop_expirations:{guild_id}"


def parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_remaining(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}時間{minutes}分"
    return f"{minutes}分"


async def get_coin_gamble_lock_until(guild_id: int, user_id: int) -> datetime | None:
    locked_until = parse_utc(await db_get(coin_gamble_lock_key(guild_id, user_id)))
    if locked_until and locked_until > utc_now():
        return locked_until
    return None


async def get_coin_gamble_lock_reason(guild_id: int, user_id: int) -> str:
    return await db_get(coin_gamble_lock_reason_key(guild_id, user_id)) or "ギャンブル制限中です"


async def lock_coin_gamble_until(guild_id: int, user_id: int, locked_until: datetime, reason: str) -> datetime:
    await db_set(coin_gamble_lock_key(guild_id, user_id), locked_until.isoformat())
    await db_set(coin_gamble_lock_reason_key(guild_id, user_id), reason)
    return locked_until


async def lock_coin_gamble_for_24h(guild_id: int, user_id: int) -> datetime:
    locked_until = utc_now() + timedelta(hours=24)
    return await lock_coin_gamble_until(guild_id, user_id, locked_until, "0コインになったため")


async def get_or_create_real_gambler_role(guild: discord.Guild) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=REAL_GAMBLER_ROLE_NAME)
    if role:
        return role
    bot_member = guild.me
    if not bot_member or not bot_member.guild_permissions.manage_roles:
        return None
    try:
        return await guild.create_role(
            name=REAL_GAMBLER_ROLE_NAME,
            color=discord.Color(0xB94F48),
            reason="Real gambler restriction role",
        )
    except discord.HTTPException:
        return None


async def save_gamble_role_expiration(guild_id: int, user_id: int, role_id: int, expires_at: datetime):
    records = await get_json(gamble_role_expirations_key(guild_id), [])
    records = [
        record
        for record in records
        if not (int(record.get("user_id", 0)) == user_id and int(record.get("role_id", 0)) == role_id)
    ]
    records.append(
        {
            "user_id": user_id,
            "role_id": role_id,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        }
    )
    await set_json(gamble_role_expirations_key(guild_id), records[-500:])


async def apply_real_gambler_penalty(guild: discord.Guild, member: discord.Member) -> tuple[datetime, bool]:
    expires_at = utc_now() + timedelta(days=max(1, REAL_GAMBLER_ROLE_DAYS))
    role_added = False
    role = await get_or_create_real_gambler_role(guild)
    bot_member = guild.me
    if role and bot_member and role not in member.roles and role < bot_member.top_role:
        try:
            await member.add_roles(role, reason="Coin balance reached zero by gambling")
            role_added = True
        except discord.HTTPException:
            pass
    if role:
        await save_gamble_role_expiration(guild.id, member.id, role.id, expires_at)
    return expires_at, role_added


def draw_penalty_gacha() -> str:
    return random.choice(PENALTY_GACHA_ITEMS)


def format_datetime_jst(value: datetime | None) -> str:
    if not value:
        return "不明"
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M")


async def save_penalty_task(guild_id: int, user_id: int, penalty: str) -> dict:
    task = {
        "penalty": penalty,
        "assigned_at": utc_now().isoformat(),
        "deadline_at": (utc_now() + timedelta(days=7)).isoformat(),
        "completed": False,
        "completed_at": "",
    }
    await set_json(penalty_task_key(guild_id, user_id), task)
    return task


async def get_penalty_task(guild_id: int, user_id: int) -> dict | None:
    task = await get_json(penalty_task_key(guild_id, user_id), None)
    return task if isinstance(task, dict) else None


async def complete_penalty_task(guild_id: int, user_id: int) -> bool:
    task = await get_penalty_task(guild_id, user_id)
    if not task or task.get("completed"):
        return False
    task["completed"] = True
    task["completed_at"] = utc_now().isoformat()
    await set_json(penalty_task_key(guild_id, user_id), task)
    return True


def coin_shop_item_summary(data: dict) -> str:
    if data.get("kind") == "role":
        return f"{data['cost']}コイン / {data['days']}日"
    return f"{data['cost']}コイン / 永続"


async def add_unique_json_value(key: str, value: str, limit: int = 30) -> bool:
    values = await get_json(key, [])
    if value in values:
        return False
    values.append(value)
    await set_json(key, values[:limit])
    return True


async def apply_coin_rewards(guild: discord.Guild | None, member: discord.Member | None, coins: int) -> list[str]:
    if not guild or not member:
        return []

    messages = []
    for milestone in COIN_MILESTONES:
        if coins < milestone["coins"]:
            continue
        name = milestone["name"]
        kind = milestone["kind"]
        if kind in ("title", "title_role"):
            added = await add_unique_json_value(titles_key(guild.id, member.id), name)
            if added:
                messages.append(f"称号「{name}」を獲得")
        if kind == "badge":
            added = await add_unique_json_value(badges_key(guild.id, member.id), name)
            if added:
                messages.append(f"バッジ「{name}」を獲得")
        if kind == "title_role":
            role = discord.utils.get(guild.roles, name=name)
            bot_member = guild.me
            if role and bot_member and role not in member.roles and role < bot_member.top_role:
                try:
                    await member.add_roles(role, reason="Coin milestone reward")
                    messages.append(f"記念ロール「{name}」を付与")
                except discord.HTTPException:
                    pass
    return messages


async def get_or_create_shop_role(guild: discord.Guild, item: dict) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=item["role_name"])
    if role:
        return role
    bot_member = guild.me
    if not bot_member or not bot_member.guild_permissions.manage_roles:
        return None
    try:
        return await guild.create_role(
            name=item["role_name"],
            color=discord.Color(item["color"]),
            reason="Coin shop color role",
        )
    except discord.HTTPException:
        return None


async def save_shop_expiration(guild_id: int, user_id: int, role_id: int, item_key: str, expires_at: datetime):
    records = await get_json(coin_shop_expirations_key(guild_id), [])
    records = [
        record
        for record in records
        if not (int(record.get("user_id", 0)) == user_id and int(record.get("role_id", 0)) == role_id)
    ]
    records.append(
        {
            "user_id": user_id,
            "role_id": role_id,
            "item": item_key,
            "expires_at": expires_at.isoformat(),
        }
    )
    await set_json(coin_shop_expirations_key(guild_id), records[-500:])


def event_key(message_id: int) -> str:
    return f"community_event:{message_id}"


def event_index_key(guild_id: int) -> str:
    return f"community_event_index:{guild_id}"


def topic_settings_key(guild_id: int) -> str:
    return f"community_topic:{guild_id}"


def faq_key(guild_id: int, name: str) -> str:
    return f"community_faq:{guild_id}:{name.lower()}"


def faq_index_key(guild_id: int) -> str:
    return f"community_faq_index:{guild_id}"


def rule_key(guild_id: int) -> str:
    return f"community_rule:{guild_id}"


def report_channel_key(guild_id: int) -> str:
    return f"community_report_channel:{guild_id}"


def report_cooldown_key(guild_id: int, user_id: int) -> str:
    return f"community_report_cooldown:{guild_id}:{user_id}"


def parse_user_id(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    return int(value) if value.isdigit() else None


async def get_report_developer_user(bot: commands.Bot) -> discord.User | None:
    developer_id = parse_user_id(REPORT_DEVELOPER_USER_ID)
    if developer_id:
        user = bot.get_user(developer_id)
        if user:
            return user
        try:
            return await bot.fetch_user(developer_id)
        except discord.HTTPException:
            return None
    try:
        app_info = await bot.application_info()
        owner = app_info.owner
        if isinstance(owner, discord.Team):
            return None
        return owner
    except discord.HTTPException:
        return None


def build_report_embed(
    interaction: discord.Interaction,
    kind_label: str,
    content: str,
    *,
    anonymous: bool,
    for_developer: bool,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Bot報告 / {kind_label}",
        description=content[:1800],
        color=0xE74C3C,
        timestamp=datetime.now(timezone.utc),
    )
    sender_value = "匿名" if anonymous and not for_developer else f"{interaction.user.mention}\nID: `{interaction.user.id}`"
    embed.add_field(name="送信者", value=sender_value, inline=False)
    if interaction.guild:
        embed.add_field(name="サーバー", value=f"{interaction.guild.name}\nID: `{interaction.guild.id}`", inline=False)
    if interaction.channel:
        channel_name = getattr(interaction.channel, "mention", None) or getattr(interaction.channel, "name", "不明")
        embed.add_field(name="チャンネル", value=f"{channel_name}\nID: `{interaction.channel_id}`", inline=False)
    embed.set_footer(text="VillageCore / report")
    return embed


def event_embed(data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=data["title"],
        description=data.get("description") or "詳細なし",
        color=0x2ECC71,
    )
    if data.get("when"):
        embed.add_field(name="日時", value=data["when"], inline=False)
    for status, label in EVENT_STATUSES.items():
        users = data["responses"].get(status, [])
        value = "\n".join(f"<@{uid}>" for uid in users) if users else "なし"
        embed.add_field(name=f"{label} {len(users)}人", value=value[:1024], inline=True)
    embed.set_footer(text="ボタンで回答を変更できます")
    return embed


class EventRsvpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def update_response(self, interaction: discord.Interaction, status: str):
        if not interaction.message:
            await interaction.response.send_message("イベントメッセージが見つかりません。", ephemeral=True)
            return
        data = await get_json(event_key(interaction.message.id), None)
        if not data:
            await interaction.response.send_message("このイベント情報は見つかりませんでした。", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        for users in data["responses"].values():
            if user_id in users:
                users.remove(user_id)
        data["responses"].setdefault(status, []).append(user_id)
        await set_json(event_key(interaction.message.id), data)
        await interaction.response.edit_message(embed=event_embed(data), view=self)

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success, custom_id="community_event_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_response(interaction, "join")

    @discord.ui.button(label="未定", style=discord.ButtonStyle.secondary, custom_id="community_event_maybe")
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_response(interaction, "maybe")

    @discord.ui.button(label="不参加", style=discord.ButtonStyle.danger, custom_id="community_event_no")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_response(interaction, "no")


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(EventRsvpView())
        self.daily_topic_loop.start()
        self.coin_shop_cleanup_loop.start()

    def cog_unload(self):
        self.daily_topic_loop.cancel()
        self.coin_shop_cleanup_loop.cancel()

    @app_commands.command(name="event_create", description="参加/未定/不参加ボタン付きイベントを作成します")
    @app_commands.describe(title="イベント名", description="内容", when="日時や集合時間")
    async def event_create(self, interaction: discord.Interaction, title: str, description: str, when: str = ""):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        data = {
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "title": title[:200],
            "description": description[:1000],
            "when": when[:200],
            "creator_id": interaction.user.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "responses": {"join": [], "maybe": [], "no": []},
        }
        await interaction.response.send_message(embed=event_embed(data), view=EventRsvpView())
        msg = await interaction.original_response()
        await set_json(event_key(msg.id), data)
        index = await get_json(event_index_key(interaction.guild_id), [])
        if msg.id not in index:
            index.append(msg.id)
            await set_json(event_index_key(interaction.guild_id), index[-200:])

    @app_commands.command(name="event_cancel", description="イベント募集を中止します")
    @app_commands.describe(message_id="募集メッセージID", reason="中止理由")
    async def event_cancel(self, interaction: discord.Interaction, message_id: str, reason: str = ""):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        try:
            event_message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("メッセージIDは数字で入力してください。", ephemeral=True)
            return

        data = await get_json(event_key(event_message_id), None)
        if not data:
            await interaction.response.send_message("そのイベント募集は見つかりませんでした。", ephemeral=True)
            return
        is_owner = data.get("creator_id") == interaction.user.id
        is_manager = interaction.user.guild_permissions.manage_guild
        if not is_owner and not is_manager:
            await interaction.response.send_message("募集を中止できるのは作成者または管理者です。", ephemeral=True)
            return

        data["canceled"] = True
        data["cancel_reason"] = reason[:500]
        await set_json(event_key(event_message_id), data)

        channel = self.bot.get_channel(data.get("channel_id", 0))
        embed = event_embed(data)
        embed.title = f"【中止】{data['title']}"
        embed.color = 0xE74C3C
        if reason:
            embed.add_field(name="中止理由", value=reason[:1024], inline=False)
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(event_message_id)
                await message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        await interaction.response.send_message("イベント募集を中止しました。", ephemeral=True)

    @app_commands.command(name="profile_set", description="自己紹介プロフィールを登録します")
    @app_commands.describe(
        favorite="好きなもの",
        active_time="活動時間",
        comment="ひとこと",
        sns="SNSやリンク",
        items="追加項目。例: 好きなゲーム=Among Us; 推し=むらびと君",
    )
    async def profile_set(
        self,
        interaction: discord.Interaction,
        favorite: str = "",
        active_time: str = "",
        comment: str = "",
        sns: str = "",
        items: str = "",
    ):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        current = await get_json(profile_key(interaction.guild_id, interaction.user.id), {})
        parsed_items = parse_profile_items(items)
        data = {
            "favorite": favorite[:300] if favorite else current.get("favorite", ""),
            "active_time": active_time[:200] if active_time else current.get("active_time", ""),
            "comment": comment[:500] if comment else current.get("comment", ""),
            "sns": sns[:300] if sns else current.get("sns", ""),
            "items": parsed_items if items else current.get("items", []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await set_json(profile_key(interaction.guild_id, interaction.user.id), data)
        extra = f"\n追加項目: {len(data['items'])}件" if data["items"] else ""
        await interaction.response.send_message(f"プロフィールを保存しました。{extra}", ephemeral=True)

    @app_commands.command(name="profile", description="プロフィールを表示します")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        member = member or interaction.user
        data = await get_json(profile_key(interaction.guild_id, member.id), {})
        titles = await get_json(titles_key(interaction.guild_id, member.id), [])
        badges = await get_json(badges_key(interaction.guild_id, member.id), [])
        coins = int(await db_get(coin_key(interaction.guild_id, member.id)) or "0")
        if isinstance(member, discord.Member):
            reward_messages = await apply_coin_rewards(interaction.guild, member, coins)
            if reward_messages:
                titles = await get_json(titles_key(interaction.guild_id, member.id), [])
                badges = await get_json(badges_key(interaction.guild_id, member.id), [])
        embed = discord.Embed(title=f"{member.display_name} のプロフィール", color=0x00BFFF)
        embed.add_field(name="称号", value=", ".join(titles) if titles else "なし", inline=False)
        embed.add_field(name="バッジ", value=", ".join(badges) if badges else "なし", inline=False)
        embed.add_field(name="コイン", value=f"{coins}", inline=True)
        embed.add_field(name="好きなもの", value=data.get("favorite") or "未設定", inline=False)
        embed.add_field(name="活動時間", value=data.get("active_time") or "未設定", inline=False)
        embed.add_field(name="ひとこと", value=data.get("comment") or "未設定", inline=False)
        embed.add_field(name="SNS/リンク", value=data.get("sns") or "未設定", inline=False)
        for item in data.get("items", [])[:10]:
            embed.add_field(name=str(item.get("name", "項目"))[:256], value=str(item.get("value", "未設定"))[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coin_balance", description="サーバー内通貨の残高を表示します")
    async def coin_balance(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        member = member or interaction.user
        coins = int(await db_get(coin_key(interaction.guild_id, member.id)) or "0")
        await interaction.response.send_message(f"{member.mention} のコイン: **{coins}**")

    @app_commands.command(name="coin_shop", description="コインでロール、称号、バッジを交換します")
    @app_commands.describe(item="交換する商品。未指定なら一覧を表示します")
    @app_commands.choices(
        item=[
            app_commands.Choice(name="赤カラー 300コイン / 7日", value="red"),
            app_commands.Choice(name="青カラー 300コイン / 7日", value="blue"),
            app_commands.Choice(name="緑カラー 300コイン / 7日", value="green"),
            app_commands.Choice(name="紫カラー 300コイン / 7日", value="purple"),
            app_commands.Choice(name="金カラー 500コイン / 7日", value="gold"),
            app_commands.Choice(name="称号: 編集見習い 120コイン", value="editor"),
            app_commands.Choice(name="称号: 幸運の村民 180コイン", value="lucky"),
            app_commands.Choice(name="バッジ: ショップ常連 250コイン", value="regular"),
            app_commands.Choice(name="バッジ: 村の支援者 500コイン", value="sponsor"),
        ]
    )
    async def coin_shop(self, interaction: discord.Interaction, item: app_commands.Choice[str] | None = None):
        if not interaction.guild_id or not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        owned_titles = await get_json(titles_key(interaction.guild_id, interaction.user.id), [])
        owned_badges = await get_json(badges_key(interaction.guild_id, interaction.user.id), [])
        if item is None:
            lines = []
            for data in COIN_SHOP_ITEMS.values():
                if data.get("kind") == "title" and data.get("name") in owned_titles:
                    continue
                if data.get("kind") == "badge" and data.get("name") in owned_badges:
                    continue
                lines.append(f"- **{data['label']}**: {coin_shop_item_summary(data)}")
            embed = discord.Embed(
                title="コインショップ",
                description="期間限定ロール、称号、バッジを交換できます。\n獲得済みの称号・バッジは一覧から非表示になります。\n\n"
                + ("\n".join(lines) if lines else "現在交換できる未獲得の称号・バッジはありません。"),
                color=0xF1C40F,
            )
            embed.set_footer(text="/coin_shop item:商品名 で交換できます。")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        item_key = item.value
        data = COIN_SHOP_ITEMS.get(item_key)
        if not data:
            await interaction.response.send_message("その商品は見つかりませんでした。", ephemeral=True)
            return

        balance_key = coin_key(interaction.guild_id, interaction.user.id)
        balance = int(await db_get(balance_key) or "0")
        if balance < data["cost"]:
            await interaction.response.send_message(
                f"コインが足りません。必要: **{data['cost']}** / 現在: **{balance}**",
                ephemeral=True,
            )
            return

        kind = data.get("kind", "role")
        result_text = ""
        if kind == "role":
            role = await get_or_create_shop_role(interaction.guild, data)
            bot_member = interaction.guild.me
            if not role or not bot_member or role >= bot_member.top_role:
                await interaction.response.send_message(
                    "カラー役職を作成/付与できませんでした。Botに「ロールの管理」権限があるか、Botのロール位置を確認してください。",
                    ephemeral=True,
                )
                return

            shop_role_names = {
                shop_item["role_name"]
                for shop_item in COIN_SHOP_ITEMS.values()
                if shop_item.get("kind") == "role"
            }
            removable_roles = [
                member_role
                for member_role in interaction.user.roles
                if member_role.name in shop_role_names and member_role != role and member_role < bot_member.top_role
            ]
            if removable_roles:
                try:
                    await interaction.user.remove_roles(*removable_roles, reason="Coin shop color role replaced")
                except discord.HTTPException:
                    pass

            await interaction.user.add_roles(role, reason="Coin shop purchase")
            expires_at = datetime.now(timezone.utc) + timedelta(days=data["days"])
            await save_shop_expiration(interaction.guild_id, interaction.user.id, role.id, item_key, expires_at)
            result_text = f"期限: **{data['days']}日間**"
        elif kind == "title":
            if data["name"] in owned_titles:
                await interaction.response.send_message(
                    f"称号 **{data['name']}** はすでに獲得済みです。コインは消費していません。",
                    ephemeral=True,
                )
                return
            await add_unique_json_value(titles_key(interaction.guild_id, interaction.user.id), data["name"])
            result_text = "称号はプロフィールに永続保存されます。"
        elif kind == "badge":
            if data["name"] in owned_badges:
                await interaction.response.send_message(
                    f"バッジ **{data['name']}** はすでに獲得済みです。コインは消費していません。",
                    ephemeral=True,
                )
                return
            await add_unique_json_value(badges_key(interaction.guild_id, interaction.user.id), data["name"])
            result_text = "バッジはプロフィールに永続保存されます。"
        else:
            await interaction.response.send_message("その商品種別はまだ対応していません。", ephemeral=True)
            return

        await db_set(balance_key, str(balance - data["cost"]))

        await interaction.response.send_message(
            f"{interaction.user.mention} が **{data['label']}** を交換しました。\n"
            f"消費: **{data['cost']}** コイン / 残高: **{balance - data['cost']}** コイン\n"
            f"{result_text}",
        )

    @app_commands.command(name="coin_ranking", description="所持コインのランキングを表示します")
    async def coin_ranking(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        all_config = await db_get_all_config()
        prefix = f"community_coin:{interaction.guild_id}:"
        ranking = []
        for key, value in all_config.items():
            if not key.startswith(prefix):
                continue
            try:
                user_id = int(key.removeprefix(prefix))
                coins = int(value or "0")
            except ValueError:
                continue
            member = interaction.guild.get_member(user_id) if interaction.guild else None
            if member and member.bot:
                continue
            ranking.append((coins, user_id, member))

        ranking.sort(reverse=True, key=lambda item: item[0])
        if not ranking:
            await interaction.response.send_message("まだコインランキングに表示できるデータがありません。", ephemeral=True)
            return

        lines = []
        for index, (coins, user_id, member) in enumerate(ranking[:10], start=1):
            name = member.mention if member else f"<@{user_id}>"
            lines.append(f"{index}. {name} - **{coins}** コイン")
        own_rank = next((index for index, (_, user_id, _) in enumerate(ranking, start=1) if user_id == interaction.user.id), None)
        footer = f"あなたの順位: {own_rank}位" if own_rank else "あなたはまだランキングに入っていません。"
        embed = discord.Embed(title="コインランキング", description="\n".join(lines), color=0xF1C40F)
        embed.set_footer(text=footer)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coin_daily", description="1日1回コインを受け取ります")
    async def coin_daily(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        key = coin_daily_key(interaction.guild_id, interaction.user.id)
        today = jst_today()
        if await db_get(key) == today:
            await interaction.response.send_message("今日のコインは受け取り済みです。", ephemeral=True)
            return
        amount = random.randint(5, 15)
        balance_key = coin_key(interaction.guild_id, interaction.user.id)
        current = int(await db_get(balance_key) or "0")
        new_balance = current + amount
        await db_set(balance_key, str(new_balance))
        await db_set(key, today)
        rewards = await apply_coin_rewards(interaction.guild, interaction.user, new_balance)
        reward_text = "\n" + "\n".join(f"🎖 {message}" for message in rewards) if rewards else ""
        await interaction.response.send_message(f"{interaction.user.mention} は **{amount}** コインを受け取りました。現在 **{new_balance}** コインです。{reward_text}")

    @app_commands.command(name="coin_gamble", description="コインを賭けてギャンブルします")
    @app_commands.describe(amount="賭けるコイン数")
    async def coin_gamble(self, interaction: discord.Interaction, amount: int):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("賭けるコイン数は1以上にしてください。", ephemeral=True)
            return

        locked_until = await get_coin_gamble_lock_until(interaction.guild_id, interaction.user.id)
        if locked_until:
            remaining = format_remaining(locked_until - utc_now())
            reason = await get_coin_gamble_lock_reason(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"{reason}。ギャンブルはあと **{remaining}** できません。\n"
                "コイン集めや別のゲームで少し休憩しましょう。",
                ephemeral=True,
            )
            return

        key = coin_key(interaction.guild_id, interaction.user.id)
        current = int(await db_get(key) or "0")
        if current <= 0:
            await interaction.response.send_message(
                "現在の所持コインは **0** です。ギャンブルはできません。\n"
                "まずは `/coin_daily` やおみくじでコインを集めてください。",
                ephemeral=True,
            )
            return
        if current < amount:
            await interaction.response.send_message(
                f"コインが足りません。現在の所持コインは **{current}** です。",
                ephemeral=True,
            )
            return
        if random.random() < 0.45:
            bonus_percent = random.randint(10, 100)
            profit = max(1, amount * bonus_percent // 100)
            new_balance = current + profit
            await db_set(key, str(new_balance))
            rewards = await apply_coin_rewards(interaction.guild, interaction.user, new_balance)
            reward_text = "\n" + "\n".join(f"🎖 {message}" for message in rewards) if rewards else ""
            await interaction.response.send_message(
                f"当たり！ {interaction.user.mention} は **{amount}** コインを賭けて "
                f"**+{profit}** コイン獲得しました。現在 **{new_balance}** コインです。{reward_text}"
            )
            return

        loss = amount if random.random() < 0.65 else max(1, amount // 2)
        new_balance = max(0, current - loss)
        await db_set(key, str(new_balance))
        zero_lock_text = ""
        if new_balance == 0:
            locked_until = await lock_coin_gamble_for_24h(interaction.guild_id, interaction.user.id)
            remaining = format_remaining(locked_until - utc_now())
            penalty = draw_penalty_gacha()
            active_task = await get_penalty_task(interaction.guild_id, interaction.user.id)
            if not active_task or active_task.get("completed"):
                active_task = await save_penalty_task(interaction.guild_id, interaction.user.id, penalty)
                penalty_text = (
                    f"\n強化罰ゲームが発生: **{penalty}**"
                    f"\n期限: **{format_datetime_jst(parse_utc(active_task.get('deadline_at', '')))}**"
                )
            else:
                penalty_text = (
                    f"\n未完了の強化罰ゲームがあります: **{active_task.get('penalty', '不明')}**"
                    "\n新しい罰ゲームは追加しませんでした。"
                )
            role_text = ""
            if isinstance(interaction.user, discord.Member) and interaction.guild:
                role_expires_at, role_added = await apply_real_gambler_penalty(interaction.guild, interaction.user)
                role_remaining = format_remaining(role_expires_at - utc_now())
                if role_added:
                    role_text = f"\nロール **{REAL_GAMBLER_ROLE_NAME}** を **{role_remaining}** 付与しました。"
                else:
                    role_text = f"\nロール **{REAL_GAMBLER_ROLE_NAME}** は付与済み、または権限不足で付与できませんでした。"
            zero_lock_text = (
                f"\n0コインになったため、ギャンブルは **{remaining}** できません。"
                f"{role_text}"
                f"{penalty_text}"
                "\n`/penalty_status` で状態を確認できます。"
            )
        await interaction.response.send_message(
            f"残念... {interaction.user.mention} は **{loss}** コイン失いました。"
            f"現在 **{new_balance}** コインです。{zero_lock_text}"
        )

    @app_commands.command(name="penalty_gacha", description="罰ゲームをランダムで引きます")
    @app_commands.describe(member="【管理者のみ】別のメンバーの代わりに引く場合は指定してください")
    @app_commands.default_permissions(manage_guild=True)
    async def penalty_gacha(self, interaction: discord.Interaction, member: discord.Member | None = None):
        # メンバーが指定されていない場合は、管理者は誰でも実行可能、非管理者は自分自身のみ
        if member is None:
            target_member = interaction.user
        else:
            # メンバーが指定されている場合は、管理者のみ実行可能
            is_admin = interaction.user.guild_permissions.manage_guild
            if not is_admin:
                await interaction.response.send_message(
                    "他のメンバーの代わりに罰ゲームを引けるのは管理者だけです。",
                    ephemeral=True,
                )
                return
            target_member = member

        penalty = draw_penalty_gacha()
        if member is None:
            await interaction.response.send_message(f"罰ゲームガチャ: **{penalty}**")
        else:
            await interaction.response.send_message(f"{target_member.mention} の罰ゲームガチャ: **{penalty}**")

    @app_commands.command(name="penalty_status", description="現在の強化罰ゲームを確認します")
    async def penalty_status(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        member = member or interaction.user
        task = await get_penalty_task(interaction.guild_id, member.id)
        if not task:
            await interaction.response.send_message(f"{member.mention} に強化罰ゲームはありません。", ephemeral=True)
            return

        completed = bool(task.get("completed"))
        deadline_at = parse_utc(task.get("deadline_at", ""))
        completed_at = parse_utc(task.get("completed_at", ""))
        status = "完了済み" if completed else "未完了"
        embed = discord.Embed(
            title=f"{member.display_name} の強化罰ゲーム",
            color=0x2ECC71 if completed else 0xE67E22,
        )
        embed.add_field(name="内容", value=str(task.get("penalty") or "不明"), inline=False)
        embed.add_field(name="状態", value=status, inline=True)
        embed.add_field(name="期限", value=format_datetime_jst(deadline_at), inline=True)
        if completed_at:
            embed.add_field(name="完了日時", value=format_datetime_jst(completed_at), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="penalty_complete", description="【管理者】メンバーの強化罰ゲームを完了にします")
    @app_commands.default_permissions(manage_guild=True)
    async def penalty_complete(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        completed = await complete_penalty_task(interaction.guild_id, member.id)
        if not completed:
            await interaction.response.send_message(
                f"{member.mention} に未完了の強化罰ゲームはありません。",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(f"{member.mention} の強化罰ゲームを完了にしました。", ephemeral=True)

    @app_commands.command(name="coin_give", description="【管理者】メンバーにコインを付与します")
    @app_commands.default_permissions(manage_guild=True)
    async def coin_give(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        key = coin_key(interaction.guild_id, member.id)
        current = int(await db_get(key) or "0")
        new_balance = max(0, current + amount)
        await db_set(key, str(new_balance))
        rewards = await apply_coin_rewards(interaction.guild, member, new_balance)
        reward_text = "\n" + "\n".join(f"🎖 {message}" for message in rewards) if rewards else ""
        await interaction.response.send_message(f"{member.mention} のコインを **{new_balance}** に更新しました。{reward_text}", ephemeral=True)

    @app_commands.command(name="title_give", description="【管理者】メンバーに称号を付与します")
    @app_commands.default_permissions(manage_guild=True)
    async def title_give(self, interaction: discord.Interaction, member: discord.Member, title: str):
        titles = await get_json(titles_key(interaction.guild_id, member.id), [])
        title = title.strip()[:50]
        if title and title not in titles:
            titles.append(title)
        await set_json(titles_key(interaction.guild_id, member.id), titles[:20])
        await interaction.response.send_message(f"{member.mention} に称号 **{title}** を付与しました。", ephemeral=True)

    @app_commands.command(name="title_remove", description="【管理者】メンバーの称号を削除します")
    @app_commands.default_permissions(manage_guild=True)
    async def title_remove(self, interaction: discord.Interaction, member: discord.Member, title: str):
        titles = await get_json(titles_key(interaction.guild_id, member.id), [])
        titles = [item for item in titles if item != title]
        await set_json(titles_key(interaction.guild_id, member.id), titles)
        await interaction.response.send_message(f"{member.mention} から称号 **{title}** を削除しました。", ephemeral=True)

    @app_commands.command(name="title_list", description="メンバーの称号一覧を表示します")
    async def title_list(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        titles = await get_json(titles_key(interaction.guild_id, member.id), [])
        await interaction.response.send_message(f"{member.mention} の称号: " + (", ".join(titles) if titles else "なし"))

    @app_commands.command(name="topic_channel", description="【管理者】今日のお題の投稿先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def topic_channel(self, interaction: discord.Interaction):
        await set_json(topic_settings_key(interaction.guild_id), {"channel_id": interaction.channel_id, "last_date": ""})
        await interaction.response.send_message(f"今日のお題の投稿先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="topic_now", description="今日のお題を投稿します")
    async def topic_now(self, interaction: discord.Interaction):
        topic = random.choice(TOPICS)
        await interaction.response.send_message(f"**今日のお題**\n{topic}")

    @tasks.loop(hours=1)
    async def daily_topic_loop(self):
        await self.bot.wait_until_ready()
        now = datetime.now(JST)
        if now.hour != 9:
            return
        for guild in self.bot.guilds:
            settings = await get_json(topic_settings_key(guild.id), {})
            if not settings or settings.get("last_date") == now.date().isoformat():
                continue
            channel = self.bot.get_channel(settings.get("channel_id", 0))
            if not isinstance(channel, discord.TextChannel):
                continue
            await channel.send(f"**今日のお題**\n{random.choice(TOPICS)}")
            settings["last_date"] = now.date().isoformat()
            await set_json(topic_settings_key(guild.id), settings)

    @tasks.loop(hours=1)
    async def coin_shop_cleanup_loop(self):
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            records = await get_json(coin_shop_expirations_key(guild.id), [])
            if records:
                remaining = []
                changed = False
                for record in records:
                    expires_at = parse_utc(record.get("expires_at", ""))
                    if not expires_at or expires_at > now:
                        remaining.append(record)
                        continue
                    changed = True
                    member = guild.get_member(int(record.get("user_id", 0)))
                    role = guild.get_role(int(record.get("role_id", 0)))
                    bot_member = guild.me
                    if member and role and bot_member and role in member.roles and role < bot_member.top_role:
                        try:
                            await member.remove_roles(role, reason="Coin shop color role expired")
                        except discord.HTTPException:
                            pass
                if changed:
                    await set_json(coin_shop_expirations_key(guild.id), remaining)

            gamble_records = await get_json(gamble_role_expirations_key(guild.id), [])
            if not gamble_records:
                continue
            gamble_remaining = []
            gamble_changed = False
            for record in gamble_records:
                expires_at = parse_utc(record.get("expires_at", ""))
                if not expires_at or expires_at > now:
                    gamble_remaining.append(record)
                    continue
                gamble_changed = True
                member = guild.get_member(int(record.get("user_id", 0)))
                role = guild.get_role(int(record.get("role_id", 0)))
                bot_member = guild.me
                if member and role and bot_member and role in member.roles and role < bot_member.top_role:
                    try:
                        await member.remove_roles(role, reason="Real gambler restriction expired")
                    except discord.HTTPException:
                        pass
            if gamble_changed:
                await set_json(gamble_role_expirations_key(guild.id), gamble_remaining)

    @app_commands.command(name="faq_set", description="【管理者】FAQを登録します")
    @app_commands.default_permissions(manage_guild=True)
    async def faq_set(self, interaction: discord.Interaction, name: str, answer: str):
        name = name.strip().lower()[:50]
        await db_set(faq_key(interaction.guild_id, name), answer[:1800])
        index = await get_json(faq_index_key(interaction.guild_id), [])
        if name not in index:
            index.append(name)
            await set_json(faq_index_key(interaction.guild_id), index[:100])
        await interaction.response.send_message(f"FAQ `{name}` を保存しました。", ephemeral=True)

    @app_commands.command(name="faq", description="FAQを表示します")
    async def faq(self, interaction: discord.Interaction, name: str):
        answer = await db_get(faq_key(interaction.guild_id, name.strip().lower()))
        await interaction.response.send_message(answer or "そのFAQは見つかりませんでした。", ephemeral=not bool(answer))

    @app_commands.command(name="faq_list", description="FAQ一覧を表示します")
    async def faq_list(self, interaction: discord.Interaction):
        index = await get_json(faq_index_key(interaction.guild_id), [])
        await interaction.response.send_message("FAQ一覧:\n" + ("\n".join(f"- {name}" for name in index) if index else "なし"), ephemeral=True)

    @app_commands.command(name="rule_set", description="【管理者】サーバールールを登録します")
    @app_commands.default_permissions(manage_guild=True)
    async def rule_set(self, interaction: discord.Interaction, text: str):
        await db_set(rule_key(interaction.guild_id), text[:1800])
        await interaction.response.send_message("サーバールールを保存しました。", ephemeral=True)

    @app_commands.command(name="rule", description="サーバールールを表示します")
    async def rule(self, interaction: discord.Interaction):
        text = await db_get(rule_key(interaction.guild_id))
        await interaction.response.send_message(text or "サーバールールはまだ登録されていません。", ephemeral=not bool(text))

    @app_commands.command(name="report_channel", description="【管理者】Bot報告の控え送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def report_channel(self, interaction: discord.Interaction):
        await db_set(report_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"Bot報告の控え送信先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="report", description="Bot開発者へバグ報告・要望・通報を送ります")
    @app_commands.describe(
        kind="報告の種類",
        content="報告内容。発生したコマンド、状況、表示されたエラーなどを書くと助かります",
        anonymous="サーバー内の控えチャンネルでは匿名にします。開発者には確認用に送信者IDが届きます",
    )
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="バグ", value="bug"),
            app_commands.Choice(name="要望", value="request"),
            app_commands.Choice(name="不正利用", value="abuse"),
            app_commands.Choice(name="表示崩れ", value="display"),
            app_commands.Choice(name="その他", value="other"),
        ]
    )
    async def report(
        self,
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        content: str,
        anonymous: bool = False,
    ):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        text = content.strip()
        if len(text) < 5:
            await interaction.response.send_message("報告内容は5文字以上で入力してください。", ephemeral=True)
            return

        cooldown_key = report_cooldown_key(interaction.guild_id, interaction.user.id)
        locked_until = parse_utc(await db_get(cooldown_key))
        now = datetime.now(timezone.utc)
        if locked_until and locked_until > now:
            await interaction.response.send_message(
                f"連続送信防止のため、あと **{format_remaining(locked_until - now)}** 待ってから送信してください。",
                ephemeral=True,
            )
            return

        kind_label = REPORT_KIND_LABELS.get(kind.value, "その他")
        developer_embed = build_report_embed(
            interaction,
            kind_label,
            text,
            anonymous=anonymous,
            for_developer=True,
        )
        channel_embed = build_report_embed(
            interaction,
            kind_label,
            text,
            anonymous=anonymous,
            for_developer=False,
        )

        sent_to = []
        developer = await get_report_developer_user(self.bot)
        if developer:
            try:
                await developer.send(embed=developer_embed)
                sent_to.append("開発者DM")
            except discord.HTTPException:
                pass

        channel_id = int(await db_get(report_channel_key(interaction.guild_id)) or "0")
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=channel_embed)
                sent_to.append("報告チャンネル")
            except discord.HTTPException:
                pass

        if not sent_to:
            await interaction.response.send_message(
                "報告を送信できませんでした。開発者DMが閉じている、または `/report_channel` が未設定の可能性があります。",
                ephemeral=True,
            )
            return

        await db_set(cooldown_key, (now + timedelta(seconds=REPORT_COOLDOWN_SECONDS)).isoformat())
        await interaction.response.send_message(
            f"報告を送信しました。送信先: **{', '.join(sent_to)}**",
            ephemeral=True,
        )

    @app_commands.command(name="archive_old_events", description="【管理者】古いイベント記録を整理します")
    @app_commands.default_permissions(manage_guild=True)
    async def archive_old_events(self, interaction: discord.Interaction, days: int = 30):
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        index = await get_json(event_index_key(interaction.guild_id), [])
        kept = []
        removed = 0
        for message_id in index:
            data = await get_json(event_key(message_id), None)
            if not data:
                removed += 1
                continue
            created = datetime.fromisoformat(data.get("created_at", datetime.now(timezone.utc).isoformat()))
            if created < cutoff:
                await db_set(event_key(message_id), "")
                removed += 1
            else:
                kept.append(message_id)
        await set_json(event_index_key(interaction.guild_id), kept)
        await interaction.response.send_message(f"古いイベント記録を **{removed}件** 整理しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
