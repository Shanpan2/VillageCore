"""
YouTube通知 Cog
「#おちゃめ村」が含まれる動画タイトル/概要を定期チェックし、
指定チャンネルに投稿します。

必要なもの:
  pip install google-api-python-client

環境変数:
  YOUTUBE_API_KEY  ← Google Cloud Console で取得した APIキー
"""

import os
import asyncio
import discord
from discord.ext import commands, tasks
from googleapiclient.discovery import build
from database.config_db import db_get, db_set

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = 1405736791339696289  # 投稿先チャンネルID
CHECK_KEYWORD = "#おちゃめ村"
CHECK_INTERVAL_MINUTES = 10  # チェック間隔（分）
POSTED_KEY = "youtube_posted_ids"  # 投稿済みIDをDBに保存するキー


class YoutubeNotify(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.posted_ids: set[str] = set()
        self.check_youtube.start()

    async def cog_load(self):
        # 起動時にDB から投稿済みIDを復元
        saved = await db_get(POSTED_KEY)
        if saved:
            self.posted_ids = set(saved.split(","))

    def cog_unload(self):
        self.check_youtube.cancel()

    # -------------------------------------------------------
    # 定期タスク
    # -------------------------------------------------------
    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check_youtube(self):
        if not YOUTUBE_API_KEY:
            return

        channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
        if channel is None:
            return

        videos = self._search_videos(CHECK_KEYWORD)

        for video in videos:
            vid_id = video["id"]
            if vid_id in self.posted_ids:
                continue

            self.posted_ids.add(vid_id)

            embed = discord.Embed(
                title=video["title"],
                url=f"https://www.youtube.com/watch?v={vid_id}",
                description=video["description"][:200] + ("..." if len(video["description"]) > 200 else ""),
                color=0xFF0000,
            )
            embed.set_thumbnail(url=video["thumbnail"])
            embed.set_footer(text=f"📺 {video['channel']}")

            await channel.send(
                content=f"🎬 **{CHECK_KEYWORD}** の新着動画です！",
                embed=embed,
            )

        # 投稿済みIDをDBに保存（最大500件に絞る）
        trimmed = list(self.posted_ids)[-500:]
        await db_set(POSTED_KEY, ",".join(trimmed))

    @check_youtube.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # -------------------------------------------------------
    # YouTube Data API 検索
    # -------------------------------------------------------
    def _search_videos(self, keyword: str) -> list[dict]:
        try:
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
            request = youtube.search().list(
                part="snippet",
                q=keyword,
                type="video",
                order="date",
                maxResults=10,
            )
            response = request.execute()
        except Exception as e:
            print(f"[YoutubeNotify] API エラー: {e}")
            return []

        results = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            title = snippet.get("title", "")
            description = snippet.get("description", "")

            # タイトルまたは概要にキーワードが含まれるか確認
            if keyword not in title and keyword not in description:
                continue

            results.append({
                "id": item["id"]["videoId"],
                "title": title,
                "description": description,
                "channel": snippet.get("channelTitle", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            })

        return results

    # -------------------------------------------------------
    # /youtube_check（手動チェックコマンド）
    # -------------------------------------------------------
    from discord import app_commands

    @app_commands.command(name="youtube_check", description="【管理者】YouTube通知を今すぐチェックします")
    @app_commands.default_permissions(administrator=True)
    async def youtube_check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.check_youtube()
        await interaction.followup.send("✅ YouTube チェックを実行しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(YoutubeNotify(bot))
