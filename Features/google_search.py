import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


DEFAULT_RESULT_COUNT = 5
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_duckduckgo_url(value: str) -> str:
    if not value:
        return ""

    value = html.unescape(value)
    if value.startswith("//"):
        value = "https:" + value

    parsed = urlparse(value)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)

    return value


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")

        if tag == "a" and "result__a" in class_name:
            self._current = {
                "title": "",
                "link": normalize_duckduckgo_url(attrs_dict.get("href") or ""),
                "snippet": "",
            }
            self._title_parts = []
            self._capture_title = True
            return

        if self._current is not None and "result__snippet" in class_name:
            self._snippet_parts = []
            self._capture_snippet = True

    def handle_data(self, data: str):
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag == "a" and self._capture_title and self._current is not None:
            self._current["title"] = clean_text(" ".join(self._title_parts))
            if self._current["title"] and self._current["link"]:
                self.results.append(self._current)
            self._capture_title = False
            return

        if self._capture_snippet and self._current is not None:
            snippet = clean_text(" ".join(self._snippet_parts))
            if snippet:
                self._current["snippet"] = snippet
            self._capture_snippet = False
            self._current = None


class GoogleSearch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def search(self, query: str, count: int) -> list[dict[str, str]]:
        params = f"?q={quote_plus(query)}&kl=jp-jp"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        }
        timeout = aiohttp.ClientTimeout(total=12)

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(DUCKDUCKGO_HTML_URL + params) as response:
                if response.status != 200:
                    raise RuntimeError(f"DuckDuckGo returned HTTP {response.status}")
                body = await response.text()

        parser = DuckDuckGoHTMLParser()
        parser.feed(body)
        return parser.results[: max(1, min(count, 10))]

    @app_commands.command(name="google_search", description="検索結果を表示します")
    @app_commands.describe(
        query="検索したいキーワード",
        count="表示件数 1から10件",
    )
    async def google_search(
        self,
        interaction: discord.Interaction,
        query: str,
        count: app_commands.Range[int, 1, 10] = DEFAULT_RESULT_COUNT,
    ):
        await interaction.response.defer()

        try:
            items = await self.search(query, count)
        except Exception as e:
            print(f"[duckduckgo_search error] {type(e).__name__}: {e}", flush=True)
            detail = str(e)[:500] or type(e).__name__
            await interaction.followup.send(
                "❌ 検索でエラーが発生しました。\n"
                "時間をおいて再実行してください。\n"
                f"詳細: `{detail}`",
                ephemeral=True,
            )
            return

        if not items:
            await interaction.followup.send("検索結果が見つかりませんでした。")
            return

        embed = discord.Embed(
            title=f"🔎 検索: {query}",
            color=0x4C956C,
        )
        for index, item in enumerate(items, start=1):
            title = item.get("title") or "No title"
            link = item.get("link") or ""
            snippet = item.get("snippet") or "説明文はありません。"
            value = f"{snippet[:180]}{'...' if len(snippet) > 180 else ''}\n{link}"
            embed.add_field(
                name=f"{index}. {title[:240]}",
                value=value[:1024],
                inline=False,
            )
        embed.set_footer(text="Powered by DuckDuckGo")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GoogleSearch(bot))
