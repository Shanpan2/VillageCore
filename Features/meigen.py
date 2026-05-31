import json
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_get_all_config, db_set
from cogs.ai_chat import QuoteCardView, make_quote_card


MAX_MEIGEN_PER_USER = 100
JST = timezone(timedelta(hours=9))


def meigen_key(guild_id: int, user_id: int) -> str:
    return f"meigen:{guild_id}:{user_id}"


def meigen_quote_mode_key(guild_id: int) -> str:
    return f"meigen_quote_mode:{guild_id}"


async def is_meigen_quote_mode_enabled(guild_id: int) -> bool:
    raw = await db_get(meigen_quote_mode_key(guild_id))
    return raw != "off"


async def load_meigen(guild_id: int, user_id: int) -> list[dict]:
    raw = await db_get(meigen_key(guild_id, user_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


async def save_meigen(guild_id: int, user_id: int, items: list[dict]):
    await db_set(meigen_key(guild_id, user_id), json.dumps(items[-MAX_MEIGEN_PER_USER:], ensure_ascii=False))


async def load_all_meigen(guild: discord.Guild) -> list[dict]:
    prefix = f"meigen:{guild.id}:"
    config = await db_get_all_config()
    all_items: list[dict] = []
    for key, raw in config.items():
        if not key.startswith(prefix):
            continue
        try:
            user_id = int(key.removeprefix(prefix))
            items = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        member = guild.get_member(user_id)
        for item in items:
            if not isinstance(item, dict):
                continue
            copied = item.copy()
            copied["user_id"] = user_id
            copied["user_name"] = member.display_name if member else f"Unknown User ({user_id})"
            copied["user_mention"] = member.mention if member else f"`{user_id}`"
            all_items.append(copied)
    return all_items


def sort_meigen_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def ensure_meigen_ids(items: list[dict], guild_id: int, user_id: int) -> tuple[list[dict], bool]:
    changed = False
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if not item.get("id"):
            item["id"] = f"{guild_id}-{user_id}-{int(time.time() * 1000)}-{index}"
            changed = True
    return items, changed


def meigen_embed(items: list[dict], index: int, title: str = "名言集") -> discord.Embed:
    total = len(items)
    item = items[index]
    embed = discord.Embed(title=title, color=0xF1C40F)
    embed.description = item.get("text", "内容なし")
    user_mention = item.get("user_mention", "不明")
    user_name = item.get("user_name", "不明")
    embed.add_field(name="登録ユーザー", value=f"{user_mention} ({user_name})", inline=False)
    embed.set_footer(text=f"{index + 1}/{total}")
    created_at = item.get("created_at")
    if created_at:
        embed.add_field(name="登録日時", value=created_at, inline=False)
    embed.add_field(name="削除番号", value=str(index + 1), inline=True)
    return embed


class MeigenQuoteMessage:
    def __init__(self, author: discord.User | discord.Member, text: str):
        self.author = author
        self.content = text
        self.attachments = []


class MeigenListView(discord.ui.View):
    def __init__(self, items: list[dict], title: str = "名言集", index: int = 0):
        super().__init__(timeout=180)
        self.items = items
        self.title = title
        self.index = index
        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.items) - 1

    @discord.ui.button(label="前へ", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=meigen_embed(self.items, self.index, self.title), view=self)

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.items) - 1, self.index + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=meigen_embed(self.items, self.index, self.title), view=self)


class Meigen(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="meigen", description="名言を登録します")
    @app_commands.describe(text="登録する名言")
    async def meigen(self, interaction: discord.Interaction, text: str):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        text = text.strip()
        if not text:
            await interaction.response.send_message("登録する文言を入力してください。", ephemeral=True)
            return
        if len(text) > 500:
            await interaction.response.send_message("名言は500文字以内で登録してください。", ephemeral=True)
            return

        items = await load_meigen(interaction.guild_id, interaction.user.id)
        item = {
            "id": f"{interaction.guild_id}-{interaction.user.id}-{int(time.time() * 1000)}",
            "text": text,
            "created_at": datetime.now(timezone.utc).astimezone(JST).strftime("%Y-%m-%d %H:%M"),
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name,
            "message_id": interaction.id,
            "channel_id": interaction.channel_id,
        }
        items.append(item)
        await save_meigen(interaction.guild_id, interaction.user.id, items)
        if await is_meigen_quote_mode_enabled(interaction.guild_id):
            quote_message = MeigenQuoteMessage(interaction.user, text)
            card = await make_quote_card(quote_message)
            await interaction.response.send_message(
                f"名言を登録しました。現在 **{len(items)}件** です。",
                file=discord.File(card, filename="meigen.png"),
                view=QuoteCardView(self.bot, quote_message, interaction.user.id),
            )
        else:
            await interaction.response.send_message(f"名言を登録しました。現在 **{len(items)}件** です。", ephemeral=True)

    @app_commands.command(name="meigen_list", description="登録された名言を一覧表示します")
    @app_commands.describe(user="表示するユーザー。未指定なら全員です")
    async def meigen_list(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        if user:
            loaded = await load_meigen(interaction.guild.id, user.id)
            loaded, changed = ensure_meigen_ids(loaded, interaction.guild.id, user.id)
            if changed:
                await save_meigen(interaction.guild.id, user.id, loaded)
            items = []
            for item in loaded:
                copied = item.copy()
                copied["user_id"] = user.id
                copied["user_name"] = user.display_name
                copied["user_mention"] = user.mention
                items.append(copied)
            title = f"{user.display_name} の名言集"
        else:
            items = await load_all_meigen(interaction.guild)
            title = "みんなの名言集"

        items = sort_meigen_items(items)
        if not items:
            target_text = f"{user.display_name} の" if user else ""
            await interaction.response.send_message(f"{target_text}名言はまだ登録されていません。", ephemeral=True)
            return

        view = MeigenListView(items, title)
        await interaction.response.send_message(embed=meigen_embed(items, 0, title), view=view)

    @app_commands.command(name="meigen_delete", description="登録した名言を削除します")
    @app_commands.describe(number="削除番号。/meigen_list の表示番号です", user="このユーザーの一覧番号から削除する場合に指定します")
    async def meigen_delete(self, interaction: discord.Interaction, number: int, user: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        if user:
            source_items = await load_meigen(interaction.guild.id, user.id)
            source_items, changed = ensure_meigen_ids(source_items, interaction.guild.id, user.id)
            if changed:
                await save_meigen(interaction.guild.id, user.id, source_items)
            display_items = []
            for item in source_items:
                copied = item.copy()
                copied["user_id"] = user.id
                copied["user_name"] = user.display_name
                copied["user_mention"] = user.mention
                display_items.append(copied)
        else:
            display_items = await load_all_meigen(interaction.guild)

        sorted_items = sort_meigen_items(display_items)
        if not sorted_items:
            await interaction.response.send_message("削除できる名言がありません。", ephemeral=True)
            return
        if number < 1 or number > len(sorted_items):
            await interaction.response.send_message(f"削除番号は 1 から {len(sorted_items)} の間で指定してください。", ephemeral=True)
            return

        target_item = sorted_items[number - 1]
        target_id = target_item.get("id")
        target_user_id = int(target_item.get("user_id") or 0)
        target = interaction.guild.get_member(target_user_id) or user or interaction.user

        if target_user_id != interaction.user.id:
            if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message("他ユーザーの名言を削除するにはメッセージ管理権限が必要です。", ephemeral=True)
                return

        items = await load_meigen(interaction.guild.id, target_user_id)
        if target_id:
            new_items = [item for item in items if item.get("id") != target_id]
        else:
            removed = False
            new_items = []
            for item in items:
                same_text = item.get("text") == target_item.get("text")
                same_time = item.get("created_at") == target_item.get("created_at")
                if not removed and same_text and same_time:
                    removed = True
                    continue
                new_items.append(item)
        await save_meigen(interaction.guild.id, target_user_id, new_items)
        deleted_text = target_item.get("text", "内容なし")
        await interaction.response.send_message(
            f"{getattr(target, 'display_name', target_user_id)} の名言を削除しました。\n削除内容: {deleted_text[:200]}",
            ephemeral=True,
        )

    @app_commands.command(name="meigen_quote_mode", description="【管理者】名言登録時に名言カード画像を表示するか設定します")
    @app_commands.describe(enabled="ONなら登録時に名言カード画像を表示します")
    @app_commands.default_permissions(manage_guild=True)
    async def meigen_quote_mode(self, interaction: discord.Interaction, enabled: bool):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        await db_set(meigen_quote_mode_key(interaction.guild_id), "on" if enabled else "off")
        await interaction.response.send_message(
            f"名言登録時のカード表示を **{'ON' if enabled else 'OFF'}** にしました。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
