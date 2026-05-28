import json
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


def titles_key(guild_id: int, user_id: int) -> str:
    return f"community_titles:{guild_id}:{user_id}"


def badges_key(guild_id: int, user_id: int) -> str:
    return f"community_badges:{guild_id}:{user_id}"


COIN_MILESTONES = [
    {"coins": 50, "kind": "badge", "name": "小銭持ち"},
    {"coins": 100, "kind": "title", "name": "村の財布"},
    {"coins": 250, "kind": "badge", "name": "コツコツ村民"},
    {"coins": 500, "kind": "title", "name": "堅実な貯金家"},
    {"coins": 1000, "kind": "title_role", "name": "村の富豪"},
    {"coins": 2000, "kind": "badge", "name": "伝説の資産家"},
]


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

    def cog_unload(self):
        self.daily_topic_loop.cancel()

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
        data = {
            "favorite": favorite[:300],
            "active_time": active_time[:200],
            "comment": comment[:500],
            "sns": sns[:300],
            "items": parse_profile_items(items),
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

        key = coin_key(interaction.guild_id, interaction.user.id)
        current = int(await db_get(key) or "0")
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
        await interaction.response.send_message(
            f"残念... {interaction.user.mention} は **{loss}** コイン失いました。"
            f"現在 **{new_balance}** コインです。"
        )

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

    @app_commands.command(name="report_channel", description="【管理者】相談/通報の送信先を現在のチャンネルに設定します")
    @app_commands.default_permissions(manage_guild=True)
    async def report_channel(self, interaction: discord.Interaction):
        await db_set(report_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"相談/通報先を {interaction.channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="report", description="管理者へ相談/通報を送ります")
    async def report(self, interaction: discord.Interaction, content: str, anonymous: bool = True):
        channel_id = int(await db_get(report_channel_key(interaction.guild_id)) or "0")
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("相談/通報先が未設定です。", ephemeral=True)
            return
        embed = discord.Embed(title="相談/通報", description=content[:1800], color=0xE74C3C, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="送信者", value="匿名" if anonymous else interaction.user.mention, inline=False)
        await channel.send(embed=embed)
        await interaction.response.send_message("管理者へ送信しました。", ephemeral=True)

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
