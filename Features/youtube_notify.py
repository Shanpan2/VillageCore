"""
YouTube notification Cog.

Searches for videos containing "#おちゃめ村" and posts them to the configured
promotion channel only after their publish/scheduled time has arrived.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from googleapiclient.discovery import build

from database.config_db import db_get, db_set


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
DEFAULT_NOTIFY_CHANNEL_ID = int(os.getenv("YOUTUBE_NOTIFY_CHANNEL_ID", "1405736791339696289"))
CHECK_KEYWORD = os.getenv("YOUTUBE_NOTIFY_KEYWORD", "#おちゃめ村")
CHECK_INTERVAL_MINUTES = int(os.getenv("YOUTUBE_CHECK_INTERVAL_MINUTES", "10"))
POSTED_KEY = "youtube_posted_ids"
CHANNEL_KEY = "youtube_notify_channel_id"


def parse_youtube_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class YoutubeNotify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.posted_ids: set[str] = set()
        self.notify_channel_id = DEFAULT_NOTIFY_CHANNEL_ID

    async def cog_load(self):
        saved = await db_get(POSTED_KEY)
        if saved:
            self.posted_ids = {video_id for video_id in saved.split(",") if video_id}

        saved_channel = await db_get(CHANNEL_KEY)
        if saved_channel:
            try:
                self.notify_channel_id = int(saved_channel)
            except ValueError:
                pass

        self.check_youtube.start()

    def cog_unload(self):
        self.check_youtube.cancel()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_youtube(self):
        await self.post_due_videos()

    @check_youtube.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def post_due_videos(self) -> int:
        if not YOUTUBE_API_KEY:
            return 0

        channel = self.bot.get_channel(self.notify_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.notify_channel_id)
            except Exception:
                return 0

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return 0

        videos = await self.bot.loop.run_in_executor(None, self._search_videos, CHECK_KEYWORD)
        now = datetime.now(timezone.utc)
        posted_count = 0

        for video in sorted(videos, key=lambda item: item["post_at"] or datetime.min.replace(tzinfo=timezone.utc)):
            vid_id = video["id"]
            if vid_id in self.posted_ids:
                continue

            post_at = video["post_at"]
            if post_at and post_at > now:
                continue

            embed = discord.Embed(
                title=video["title"],
                url=f"https://www.youtube.com/watch?v={vid_id}",
                description=video["description"][:200] + ("..." if len(video["description"]) > 200 else ""),
                color=0xFF0000,
                timestamp=post_at,
            )
            if video["thumbnail"]:
                embed.set_thumbnail(url=video["thumbnail"])
            embed.set_footer(text=f"📺 {video['channel']}")

            await channel.send(
                content=f"🎬 **{CHECK_KEYWORD}** の動画が公開されました！",
                embed=embed,
            )
            self.posted_ids.add(vid_id)
            posted_count += 1

        trimmed = list(self.posted_ids)[-500:]
        await db_set(POSTED_KEY, ",".join(trimmed))
        return posted_count

    def _search_videos(self, keyword: str) -> list[dict]:
        try:
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
            search_request = youtube.search().list(
                part="snippet",
                q=keyword,
                type="video",
                order="date",
                maxResults=10,
            )
            search_response = search_request.execute()
        except Exception as e:
            print(f"[YoutubeNotify] search API error: {e}", flush=True)
            return []

        video_ids = [
            item.get("id", {}).get("videoId")
            for item in search_response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        try:
            details_request = youtube.videos().list(
                part="snippet,liveStreamingDetails",
                id=",".join(video_ids),
                maxResults=len(video_ids),
            )
            details_response = details_request.execute()
        except Exception as e:
            print(f"[YoutubeNotify] videos API error: {e}", flush=True)
            return []

        results = []
        for item in details_response.get("items", []):
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            if keyword not in title and keyword not in description:
                continue

            live_details = item.get("liveStreamingDetails", {})
            scheduled_at = parse_youtube_time(live_details.get("scheduledStartTime"))
            actual_start = parse_youtube_time(live_details.get("actualStartTime"))
            published_at = parse_youtube_time(snippet.get("publishedAt"))
            post_at = actual_start or scheduled_at or published_at

            results.append({
                "id": item["id"],
                "title": title,
                "description": description,
                "channel": snippet.get("channelTitle", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "post_at": post_at,
            })

        return results

    @app_commands.command(name="youtube_check", description="【管理者】YouTube通知を今すぐチェックします")
    @app_commands.default_permissions(administrator=True)
    async def youtube_check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        posted_count = await self.post_due_videos()
        await interaction.followup.send(
            f"✅ YouTube チェックを実行しました。投稿件数: {posted_count}",
            ephemeral=True,
        )

    @app_commands.command(name="youtube_notify_channel", description="【管理者】YouTube通知先を現在のチャンネルに設定します")
    @app_commands.default_permissions(administrator=True)
    async def youtube_notify_channel(self, interaction: discord.Interaction):
        self.notify_channel_id = interaction.channel_id
        await db_set(CHANNEL_KEY, str(interaction.channel_id))
        await interaction.response.send_message(
            f"✅ YouTube通知先を {interaction.channel.mention} に設定しました。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(YoutubeNotify(bot))
