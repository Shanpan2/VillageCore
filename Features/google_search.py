import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build


GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID") or os.getenv("GOOGLE_CSE_ID")
DEFAULT_RESULT_COUNT = 5


class GoogleSearch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def search(self, query: str, count: int) -> list[dict]:
        if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
            raise RuntimeError(
                "GOOGLE_SEARCH_API_KEY と GOOGLE_SEARCH_ENGINE_ID を設定してください。"
            )

        service = build("customsearch", "v1", developerKey=GOOGLE_SEARCH_API_KEY)
        response = (
            service.cse()
            .list(
                q=query,
                cx=GOOGLE_SEARCH_ENGINE_ID,
                num=max(1, min(count, 10)),
                safe="active",
                lr="lang_ja",
            )
            .execute()
        )
        return response.get("items", [])

    @app_commands.command(name="google_search", description="Google検索結果を表示します")
    @app_commands.describe(
        query="検索したいキーワード",
        count="表示件数 1〜10件",
    )
    async def google_search(
        self,
        interaction: discord.Interaction,
        query: str,
        count: app_commands.Range[int, 1, 10] = DEFAULT_RESULT_COUNT,
    ):
        await interaction.response.defer()

        try:
            items = await asyncio.to_thread(self.search, query, count)
        except Exception as e:
            print(f"[google_search error] {type(e).__name__}: {e}", flush=True)
            await interaction.followup.send(
                "❌ Google検索でエラーが発生しました。\n"
                "`GOOGLE_SEARCH_API_KEY` と `GOOGLE_SEARCH_ENGINE_ID`、"
                "Custom Search JSON API の有効化を確認してください。",
                ephemeral=True,
            )
            return

        if not items:
            await interaction.followup.send("検索結果が見つかりませんでした。")
            return

        embed = discord.Embed(
            title=f"🔎 Google検索: {query}",
            color=0x4285F4,
        )
        for index, item in enumerate(items[:count], start=1):
            title = item.get("title", "No title")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            value = f"{snippet[:180]}{'...' if len(snippet) > 180 else ''}\n{link}"
            embed.add_field(
                name=f"{index}. {title[:240]}",
                value=value[:1024],
                inline=False,
            )
        embed.set_footer(text="Powered by Google Custom Search JSON API")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GoogleSearch(bot))
