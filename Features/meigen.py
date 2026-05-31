import json
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database.config_db import db_get, db_get_all_config, db_set


MAX_MEIGEN_PER_USER = 100
JST = timezone(timedelta(hours=9))


def meigen_key(guild_id: int, user_id: int) -> str:
    return f"meigen:{guild_id}:{user_id}"


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
    return embed


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
        items.append(
            {
                "text": text,
                "created_at": datetime.now(timezone.utc).astimezone(JST).strftime("%Y-%m-%d %H:%M"),
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "message_id": interaction.id,
                "channel_id": interaction.channel_id,
            }
        )
        await save_meigen(interaction.guild_id, interaction.user.id, items)
        await interaction.response.send_message(f"名言を登録しました。現在 **{len(items)}件** です。", ephemeral=True)

    @app_commands.command(name="meigen_list", description="登録された名言を一覧表示します")
    @app_commands.describe(user="表示するユーザー。未指定なら全員です")
    async def meigen_list(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        if user:
            loaded = await load_meigen(interaction.guild.id, user.id)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Meigen(bot))
