from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from googleapiclient.discovery import build

from database.config_db import db_get, db_set


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DEFAULT_NOTIFY_CHANNEL_ID = int(os.getenv("YOUTUBE_NOTIFY_CHANNEL_ID", "0") or "0")
DEFAULT_CHECK_KEYWORD = os.getenv("YOUTUBE_NOTIFY_KEYWORD", "#おちゃめ村")
CHECK_INTERVAL_MINUTES = int(os.getenv("YOUTUBE_CHECK_INTERVAL_MINUTES", "10"))
YOUTUBE_QUOTA_BACKOFF_MINUTES = int(os.getenv("YOUTUBE_QUOTA_BACKOFF_MINUTES", "360"))

LEGACY_CHANNEL_KEY = "youtube_notify_channel_id"
LEGACY_KEYWORD_KEY = "youtube_notify_keyword"
LEGACY_POSTED_KEY = "youtube_posted_ids"


def guild_channel_key(guild_id: int) -> str:
    return f"youtube_notify_channel_id:{guild_id}"


def guild_keywords_key(guild_id: int) -> str:
    return f"youtube_notify_keywords:{guild_id}"


def posted_key(guild_id: int, keyword: str) -> str:
    return f"youtube_posted_ids:{guild_id}:{keyword}"


def parse_keywords(value: str) -> list[str]:
    keywords = []
    seen = set()
    for part in value.replace("\n", ",").split(","):
        keyword = part.strip()
        if not keyword or keyword in seen:
            continue
        keywords.append(keyword)
        seen.add(keyword)
    return keywords[:10]


def parse_youtube_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def safe_error(error: Exception) -> str:
    text = str(error)
    if YOUTUBE_API_KEY:
        text = text.replace(YOUTUBE_API_KEY, "***")
    return text


def is_quota_error(error: Exception) -> bool:
    text = str(error)
    return "quotaExceeded" in text or "youtube.quota" in text or "exceeded your" in text


class YoutubeNotify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: dict[int, dict] = {}
        self.quota_backoff_until: datetime | None = None
        self.last_backoff_log_at: datetime | None = None

    async def cog_load(self):
        self.check_youtube.start()

    def cog_unload(self):
        self.check_youtube.cancel()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_youtube(self):
        await self.post_due_videos()

    @check_youtube.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def get_settings(self, guild_id: int) -> dict:
        if guild_id in self.settings:
            return self.settings[guild_id]

        raw_keywords = await db_get(guild_keywords_key(guild_id))
        if raw_keywords:
            try:
                keywords = json.loads(raw_keywords)
            except json.JSONDecodeError:
                keywords = parse_keywords(raw_keywords)
        else:
            legacy_keyword = await db_get(LEGACY_KEYWORD_KEY)
            keywords = [legacy_keyword or DEFAULT_CHECK_KEYWORD]
            await db_set(guild_keywords_key(guild_id), json.dumps(keywords, ensure_ascii=False))

        saved_channel = await db_get(guild_channel_key(guild_id)) or await db_get(LEGACY_CHANNEL_KEY)
        channel_id = DEFAULT_NOTIFY_CHANNEL_ID
        if saved_channel:
            try:
                channel_id = int(saved_channel)
            except ValueError:
                channel_id = DEFAULT_NOTIFY_CHANNEL_ID
        if channel_id:
            await db_set(guild_channel_key(guild_id), str(channel_id))

        posted_ids = {}
        skip_first = {}
        for keyword in keywords:
            saved_posted = await db_get(posted_key(guild_id, keyword)) or await db_get(LEGACY_POSTED_KEY)
            ids = {video_id for video_id in saved_posted.split(",") if video_id} if saved_posted else set()
            posted_ids[keyword] = ids
            skip_first[keyword] = not bool(ids)

        self.settings[guild_id] = {
            "channel_id": channel_id,
            "keywords": keywords,
            "posted_ids": posted_ids,
            "skip_first": skip_first,
        }
        return self.settings[guild_id]

    async def save_posted_ids(self, guild_id: int, keyword: str, posted_ids: set[str]):
        await db_set(posted_key(guild_id, keyword), ",".join(list(posted_ids)[-500:]))

    async def post_due_videos(self, guild_id: int | None = None) -> int:
        if not YOUTUBE_API_KEY:
            print("[YoutubeNotify] YOUTUBE_API_KEY is not set.", flush=True)
            return 0
        if self.is_in_quota_backoff():
            self.log_quota_backoff_skip()
            return 0

        guilds = [self.bot.get_guild(guild_id)] if guild_id else list(self.bot.guilds)
        guilds = [guild for guild in guilds if guild is not None]
        posted_total = 0
        search_cache: dict[str, list[dict]] = {}

        for guild in guilds:
            settings = await self.get_settings(guild.id)
            channel_id = settings.get("channel_id")
            if not channel_id:
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue

            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue

            for keyword in settings["keywords"]:
                if keyword not in search_cache:
                    search_cache[keyword] = await self.bot.loop.run_in_executor(None, self._search_videos, keyword)
                posted_total += await self.post_videos_for_channel(guild.id, channel, keyword, search_cache[keyword])

        return posted_total

    def is_in_quota_backoff(self) -> bool:
        return bool(self.quota_backoff_until and datetime.now(timezone.utc) < self.quota_backoff_until)

    def quota_backoff_remaining_minutes(self) -> int:
        if not self.quota_backoff_until:
            return 0
        remaining = self.quota_backoff_until - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds() // 60) + 1)

    def mark_quota_backoff(self):
        self.quota_backoff_until = datetime.now(timezone.utc) + timedelta(minutes=YOUTUBE_QUOTA_BACKOFF_MINUTES)
        print(
            f"[YoutubeNotify] YouTube API quota exceeded. "
            f"Skipping checks for {YOUTUBE_QUOTA_BACKOFF_MINUTES} minutes.",
            flush=True,
        )

    def log_quota_backoff_skip(self):
        now = datetime.now(timezone.utc)
        if self.last_backoff_log_at and (now - self.last_backoff_log_at).total_seconds() < 1800:
            return
        self.last_backoff_log_at = now
        print(
            f"[YoutubeNotify] quota backoff active. "
            f"Next check in about {self.quota_backoff_remaining_minutes()} minutes.",
            flush=True,
        )

    async def post_videos_for_channel(
        self,
        guild_id: int,
        channel: discord.TextChannel | discord.Thread,
        keyword: str,
        videos: list[dict],
    ) -> int:
        settings = await self.get_settings(guild_id)
        posted_ids: set[str] = settings["posted_ids"].setdefault(keyword, set())
        settings["skip_first"].setdefault(keyword, not bool(posted_ids))
        now = datetime.now(timezone.utc)
        due_unposted = []

        for video in sorted(videos, key=lambda item: item["post_at"] or datetime.min.replace(tzinfo=timezone.utc)):
            video_id = video["id"]
            if video_id in posted_ids:
                continue
            post_at = video["post_at"]
            if post_at and post_at > now:
                continue
            due_unposted.append(video)

        if settings["skip_first"][keyword]:
            for video in due_unposted:
                posted_ids.add(video["id"])
            settings["skip_first"][keyword] = False
            await self.save_posted_ids(guild_id, keyword, posted_ids)
            print(f"[YoutubeNotify] Guild {guild_id}: marked {len(due_unposted)} existing videos for {keyword}.", flush=True)
            return 0

        posted_count = 0
        for video in due_unposted:
            video_id = video["id"]
            embed = discord.Embed(
                title=video["title"],
                url=f"https://www.youtube.com/watch?v={video_id}",
                description=video["description"][:200] + ("..." if len(video["description"]) > 200 else ""),
                color=0xFF0000,
                timestamp=video["post_at"],
            )
            if video["thumbnail"]:
                embed.set_thumbnail(url=video["thumbnail"])
            embed.set_footer(text=f"動画投稿者: {video['channel']}")
            await channel.send(content=f"**{keyword}** の動画が公開されました！", embed=embed)
            posted_ids.add(video_id)
            posted_count += 1

        await self.save_posted_ids(guild_id, keyword, posted_ids)
        return posted_count

    def _search_videos(self, keyword: str) -> list[dict]:
        try:
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
            search_response = (
                youtube.search()
                .list(part="snippet", q=keyword, type="video", order="date", maxResults=10)
                .execute()
            )
        except Exception as e:
            print(f"[YoutubeNotify] search API error: {safe_error(e)}", flush=True)
            if is_quota_error(e):
                self.mark_quota_backoff()
            return []

        video_ids = [
            item.get("id", {}).get("videoId")
            for item in search_response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        try:
            details_response = (
                youtube.videos()
                .list(part="snippet,liveStreamingDetails", id=",".join(video_ids), maxResults=len(video_ids))
                .execute()
            )
        except Exception as e:
            print(f"[YoutubeNotify] videos API error: {safe_error(e)}", flush=True)
            if is_quota_error(e):
                self.mark_quota_backoff()
            return []

        results = []
        for item in details_response.get("items", []):
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            if keyword not in title and keyword not in description:
                continue
            live_details = item.get("liveStreamingDetails", {})
            post_at = (
                parse_youtube_time(live_details.get("actualStartTime"))
                or parse_youtube_time(live_details.get("scheduledStartTime"))
                or parse_youtube_time(snippet.get("publishedAt"))
            )
            results.append(
                {
                    "id": item["id"],
                    "title": title,
                    "description": description,
                    "channel": snippet.get("channelTitle", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    "post_at": post_at,
                }
            )
        return results

    @app_commands.command(name="youtube_check", description="【管理者】YouTube通知を今すぐチェックします")
    @app_commands.default_permissions(administrator=True)
    async def youtube_check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.is_in_quota_backoff():
            await interaction.followup.send(
                f"YouTube APIのクォータ上限に達しているため、現在チェックを停止中です。"
                f"約 {self.quota_backoff_remaining_minutes()} 分後に再開します。",
                ephemeral=True,
            )
            return
        posted_count = await self.post_due_videos(interaction.guild_id)
        await interaction.followup.send(f"YouTubeチェックを実行しました。投稿件数: {posted_count}", ephemeral=True)

    @app_commands.command(name="youtube_notify_channel", description="【管理者】YouTube通知先を現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def youtube_notify_channel(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.get_settings(interaction.guild_id)
        settings["channel_id"] = interaction.channel_id
        await db_set(guild_channel_key(interaction.guild_id), str(interaction.channel_id))
        await interaction.response.send_message(f"YouTube通知先を {interaction.channel.mention} に記憶しました。", ephemeral=True)

    @app_commands.command(name="youtube_notify_keyword", description="YouTube通知で検索するハッシュタグを1つ設定します")
    @app_commands.describe(keyword="例: #おちゃめ村")
    @app_commands.default_permissions(manage_guild=True)
    async def youtube_notify_keyword(self, interaction: discord.Interaction, keyword: str):
        await self.set_keywords(interaction, [keyword.strip()])

    @app_commands.command(name="youtube_notify_keywords", description="YouTube通知で検索するハッシュタグを複数設定します")
    @app_commands.describe(keywords="例: #おちゃめ村,#告知,#切り抜き")
    @app_commands.default_permissions(manage_guild=True)
    async def youtube_notify_keywords(self, interaction: discord.Interaction, keywords: str):
        await self.set_keywords(interaction, parse_keywords(keywords))

    async def set_keywords(self, interaction: discord.Interaction, keywords: list[str]):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        keywords = [keyword for keyword in keywords if keyword]
        if not keywords:
            await interaction.response.send_message("キーワードを入力してください。", ephemeral=True)
            return

        settings = await self.get_settings(interaction.guild_id)
        settings["keywords"] = keywords
        settings["posted_ids"] = {keyword: set() for keyword in keywords}
        settings["skip_first"] = {keyword: True for keyword in keywords}
        await db_set(guild_keywords_key(interaction.guild_id), json.dumps(keywords, ensure_ascii=False))
        for keyword in keywords:
            await db_set(posted_key(interaction.guild_id, keyword), "")

        await interaction.response.send_message(
            "YouTube通知キーワードを記憶しました。\n"
            + "\n".join(f"- {keyword}" for keyword in keywords)
            + "\n次回チェック時、既存動画は重複通知防止のため既読扱いになります。",
            ephemeral=True,
        )

    @app_commands.command(name="youtube_notify_status", description="YouTube通知設定を表示します")
    async def youtube_notify_status(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        settings = await self.get_settings(interaction.guild_id)
        channel = self.bot.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        channel_text = channel.mention if isinstance(channel, discord.TextChannel) else "未設定"
        posted_total = sum(len(ids) for ids in settings["posted_ids"].values())
        await interaction.response.send_message(
            f"通知先: {channel_text}\n"
            f"検索キーワード:\n" + "\n".join(f"- {keyword}" for keyword in settings["keywords"]) + "\n"
            f"記憶済み動画数: **{posted_total}**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(YoutubeNotify(bot))
