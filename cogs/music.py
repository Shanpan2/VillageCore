import asyncio
import os
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_COOKIE_FILE = BASE_DIR / "cookies.txt"


class QuietYtdlpLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        print(f"[yt-dlp warning] {msg}", flush=True)

    def error(self, msg):
        pass


YDL_OPTIONS = {
    "format": "bestaudio*/best*",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "logger": QuietYtdlpLogger(),
    "js_runtimes": {
        "deno": {},
    },
    "default_search": "ytsearch1",
    "extract_flat": False,
    "cachedir": False,
    "socket_timeout": 20,
    "retries": 3,
    "fragment_retries": 3,
    "extractor_args": {
        "youtube": {
            "player_client": ["default", "mweb", "web_embedded"],
            "formats": ["missing_pot", "incomplete"],
        },
    },
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    },
}
YDL_PLAY_FORMATS = (
    "bestaudio*[protocol^=http]/bestaudio*/best*[protocol^=http]/best*",
    "251/250/249/140/bestaudio*/best*",
    "best*[acodec!=none]/best*",
    "best*/worst*",
    None,
)

cookie_file = os.getenv("YTDLP_COOKIE_FILE") or str(DEFAULT_COOKIE_FILE)
if cookie_file and os.path.exists(cookie_file):
    YDL_OPTIONS["cookiefile"] = cookie_file
    print(f"YTDLP cookie file loaded: {cookie_file}", flush=True)
elif os.getenv("YTDLP_COOKIE_FILE"):
    print(f"YTDLP cookie file path set but not found: {cookie_file}", flush=True)


FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def format_yt_dlp_error(error: Exception, prefix: str = "エラー") -> str:
    raw = str(error).strip()
    if raw.startswith("ERROR:"):
        raw = raw[len("ERROR:"):].strip()
    raw = raw.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    raw_lower = raw.lower()

    cookie_keywords = [
        "sign in to confirm you",
        "cookies-from-browser",
        "cookies for the authentication",
        "use --cookies",
        "extractors#exporting-youtube-cookies",
        "confirm your age",
        "not a bot",
    ]
    if any(keyword in raw_lower for keyword in cookie_keywords):
        return (
            "❌ この動画は YouTube 側の制限で再生できませんでした。\n"
            "リポジトリ直下の `cookies.txt`、または `YTDLP_COOKIE_FILE` に設定したcookieを確認してください。"
        )

    return f"❌ {prefix}: {raw[:1500]}"


def _extract_info(query: str):
    last_error = None
    for requested_format in YDL_PLAY_FORMATS:
        options = YDL_OPTIONS.copy()
        if requested_format:
            options["format"] = requested_format
        else:
            options.pop("format", None)
            options["ignore_no_formats_error"] = True
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(query, download=False)
        except Exception as e:
            last_error = e
            if "requested format is not available" not in str(e).lower():
                raise

    raise last_error


def _extract_metadata(query: str):
    options = YDL_OPTIONS.copy()
    options.pop("format", None)
    options["extract_flat"] = "in_playlist"
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(query, download=False, process=False)


def _youtube_url_from_entry(entry: dict) -> str | None:
    for key in ("webpage_url", "original_url"):
        url = entry.get(key)
        if url:
            return url

    url = entry.get("url")
    if url and url.startswith(("http://", "https://")):
        return url

    video_id = entry.get("id") or url
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return None


def _pick_audio_url(info: dict) -> str | None:
    if info.get("url") and info.get("acodec") != "none":
        return info["url"]

    formats = info.get("formats") or []
    audio_formats = [
        fmt
        for fmt in formats
        if fmt.get("url")
        and fmt.get("acodec") not in (None, "none")
        and fmt.get("vcodec") in (None, "none")
    ]
    if not audio_formats:
        audio_formats = [
            fmt
            for fmt in formats
            if fmt.get("url") and fmt.get("acodec") not in (None, "none")
        ]

    if not audio_formats:
        return None

    audio_formats.sort(
        key=lambda fmt: (
            fmt.get("abr") or 0,
            fmt.get("asr") or 0,
            fmt.get("filesize") or fmt.get("filesize_approx") or 0,
        ),
        reverse=True,
    )
    return audio_formats[0]["url"]


class MusicPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = []
        self.current = None
        self.current_info = None
        self.loop_mode = "off"
        self.playing = False

    def reset(self):
        self.queue.clear()
        self.current = None
        self.current_info = None
        self.playing = False

    async def play_next(self, channel=None):
        voice = self.guild.voice_client
        if voice is None or not voice.is_connected():
            self.playing = False
            return

        if not self.queue:
            self.playing = False
            self.current = None
            self.current_info = None
            return

        if self.loop_mode == "single" and self.current:
            item = self.current
        else:
            item = self.queue.pop(0)
            if self.loop_mode == "all":
                self.queue.append(item)

        self.current = item
        self.playing = True

        try:
            info = await asyncio.to_thread(_extract_info, item["url"])
            if "entries" in info:
                entries = [entry for entry in info["entries"] if entry]
                if not entries:
                    raise RuntimeError("検索結果が見つかりませんでした。")
                info = entries[0]

            audio_url = _pick_audio_url(info)
            if not audio_url:
                raise RuntimeError("音声URLを取得できませんでした。")

            self.current_info = info
            source = await discord.FFmpegOpusAudio.from_probe(audio_url, **FFMPEG_OPTIONS)
        except Exception as e:
            if channel:
                await channel.send(format_yt_dlp_error(e, prefix="再生エラー"))
            await self.play_next(channel)
            return

        def after_play(err):
            if err:
                print(f"[music after_play] {err}", flush=True)
            asyncio.run_coroutine_threadsafe(self.play_next(channel), self.bot.loop)

        voice.play(source, after=after_play)

        if channel:
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"[{info.get('title', item['title'])}]({info.get('webpage_url', item['url'])})",
                color=0x00FFCC,
            )
            if info.get("thumbnail"):
                embed.set_thumbnail(url=info["thumbnail"])
            await channel.send(embed=embed)

    async def add_to_queue(self, channel, query: str):
        if query.startswith("spotify:"):
            query = query.replace("spotify:", "https://open.spotify.com/")

        if query.startswith(("http://", "https://")):
            item = {"url": query, "title": query}
            self.queue.append(item)
            if not self.playing:
                await self.play_next(channel)
            else:
                await channel.send(f"🎶 キューに追加しました: **{query}**")
            return

        query = f"ytsearch1:{query}"

        try:
            info = await asyncio.to_thread(_extract_metadata, query)
            if "entries" in info:
                entries = [entry for entry in info["entries"] if entry]
                if not entries:
                    await channel.send("❌ 検索結果が見つかりませんでした。")
                    return
                entry = entries[0]
            else:
                entry = info

            url = _youtube_url_from_entry(entry)
            title = entry.get("title", "Unknown title")
            if not url:
                await channel.send("❌ 再生用URLを取得できませんでした。")
                return
        except Exception as e:
            await channel.send(format_yt_dlp_error(e, prefix="取得エラー"))
            return

        item = {"url": url, "title": title}
        self.queue.append(item)

        if not self.playing:
            await self.play_next(channel)
        else:
            await channel.send(f"🎶 キューに追加しました: **{title}**")


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.leave_tasks: dict[int, asyncio.Task] = {}
        self.monitor_tasks: dict[int, asyncio.Task] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    def cancel_leave_task(self, guild_id: int):
        task = self.leave_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    def cancel_monitor_task(self, guild_id: int):
        task = self.monitor_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    def start_monitor_task(self, guild: discord.Guild):
        task = self.monitor_tasks.get(guild.id)
        if task and not task.done():
            return
        self.monitor_tasks[guild.id] = asyncio.create_task(self.monitor_voice_channel(guild))

    async def disconnect_if_alone(self, guild: discord.Guild) -> bool:
        voice = guild.voice_client
        if not voice or not voice.channel:
            return True

        humans = [member for member in voice.channel.members if not member.bot]
        if humans:
            return False

        player = self.get_player(guild)
        player.reset()
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await voice.disconnect()
        return True

    async def leave_if_alone(self, guild: discord.Guild, delay: int = 30):
        await asyncio.sleep(delay)
        if await self.disconnect_if_alone(guild):
            self.cancel_monitor_task(guild.id)

    async def monitor_voice_channel(self, guild: discord.Guild):
        try:
            while True:
                await asyncio.sleep(30)
                voice = guild.voice_client
                if not voice or not voice.channel:
                    return
                if await self.disconnect_if_alone(guild):
                    return
        finally:
            self.monitor_tasks.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild is None:
            return

        voice = member.guild.voice_client
        if not voice or not voice.channel:
            self.cancel_leave_task(member.guild.id)
            self.cancel_monitor_task(member.guild.id)
            return

        if after.channel and after.channel.id == voice.channel.id and not member.bot:
            self.cancel_leave_task(member.guild.id)
            self.start_monitor_task(member.guild)
            return

        if not before.channel or before.channel.id != voice.channel.id:
            return

        humans = [vc_member for vc_member in voice.channel.members if not vc_member.bot]
        if humans:
            self.cancel_leave_task(member.guild.id)
            self.start_monitor_task(member.guild)
            return

        self.cancel_leave_task(member.guild.id)
        self.leave_tasks[member.guild.id] = asyncio.create_task(
            self.leave_if_alone(member.guild)
        )

    @app_commands.command(name="join", description="ボイスチャンネルに参加します")
    async def join(self, interaction: discord.Interaction):
        if interaction.user.voice is None:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに参加してから実行してください。", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            vc_channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(vc_channel)
            else:
                await vc_channel.connect()
            self.cancel_leave_task(interaction.guild.id)
            self.start_monitor_task(interaction.guild)
            await interaction.followup.send(f"🔊 {vc_channel.name} に参加しました。")
        except Exception as e:
            print(f"[join error] {e}", flush=True)
            await interaction.followup.send(f"❌ エラー: {e}")

    @app_commands.command(name="leave", description="ボイスチャンネルから退出します")
    async def leave(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if not voice:
            await interaction.response.send_message("❌ 接続していません。", ephemeral=True)
            return
        self.cancel_leave_task(interaction.guild.id)
        self.cancel_monitor_task(interaction.guild.id)
        player = self.get_player(interaction.guild)
        player.reset()
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await voice.disconnect()
        await interaction.response.send_message("👋 退出しました。")

    @app_commands.command(name="play", description="音楽を再生します")
    @app_commands.describe(query="曲名またはURL")
    async def play(self, interaction: discord.Interaction, query: str):
        if interaction.user.voice is None:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに参加してから実行してください。", ephemeral=True
            )
            return

        await interaction.response.send_message(f"🔎 `{query}` を検索中...")

        if not interaction.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect()
            except Exception as e:
                await interaction.edit_original_response(content=f"❌ VC接続エラー: {e}")
                return
        else:
            voice = interaction.guild.voice_client
            if voice.channel != interaction.user.voice.channel:
                try:
                    await voice.move_to(interaction.user.voice.channel)
                except Exception as e:
                    await interaction.edit_original_response(content=f"❌ VC移動エラー: {e}")
                    return

        self.cancel_leave_task(interaction.guild.id)
        self.start_monitor_task(interaction.guild)
        asyncio.create_task(self._play_task(interaction, query))

    async def _play_task(self, interaction: discord.Interaction, query: str):
        try:
            player = self.get_player(interaction.guild)
            await player.add_to_queue(interaction.channel, query)
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
        except Exception as e:
            print(f"[play error] {e}", flush=True)
            try:
                await interaction.edit_original_response(content=f"❌ エラー: {e}")
            except Exception:
                pass

    @app_commands.command(name="skip", description="次の曲へスキップします")
    async def skip(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.stop()
            await interaction.response.send_message("⏭️ スキップしました。")
        else:
            await interaction.response.send_message("❌ 再生中の曲がありません。", ephemeral=True)

    @app_commands.command(name="stop", description="再生を停止してキューをクリアします")
    async def stop(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        player = self.get_player(interaction.guild)
        player.reset()
        if voice:
            voice.stop()
            await interaction.response.send_message("⏹️ 停止しました。")
        else:
            await interaction.response.send_message("❌ 再生していません。", ephemeral=True)

    @app_commands.command(name="pause", description="一時停止します")
    async def pause(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸️ 一時停止しました。")
        else:
            await interaction.response.send_message("❌ 再生中ではありません。", ephemeral=True)

    @app_commands.command(name="resume", description="再開します")
    async def resume(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ 再開しました。")
        else:
            await interaction.response.send_message("❌ 一時停止されていません。", ephemeral=True)

    @app_commands.command(name="queue", description="キューを表示します")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.queue:
            await interaction.response.send_message("📭 キューは空です。")
            return
        lines = [f"{i + 1}. {item['title']}" for i, item in enumerate(player.queue)]
        embed = discord.Embed(
            title="📜 キュー一覧",
            description="\n".join(lines),
            color=0x00FFCC,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="現在再生中の曲を表示します")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.current_info:
            await interaction.response.send_message("❌ 再生中の曲はありません。", ephemeral=True)
            return
        info = player.current_info
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{info.get('title', 'Unknown title')}]({info.get('webpage_url', '')})",
            color=0x00FFCC,
        )
        if info.get("thumbnail"):
            embed.set_thumbnail(url=info["thumbnail"])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="loop", description="ループモードを設定します（off / single / all）")
    @app_commands.describe(mode="off / single / all")
    async def loop(self, interaction: discord.Interaction, mode: str):
        if mode not in ("off", "single", "all"):
            await interaction.response.send_message(
                "❌ `off` / `single` / `all` のいずれかを指定してください。", ephemeral=True
            )
            return
        player = self.get_player(interaction.guild)
        player.loop_mode = mode
        await interaction.response.send_message(f"🔁 ループモード: **{mode}**")

    @app_commands.command(name="shuffle", description="キューをシャッフルします")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if len(player.queue) < 2:
            await interaction.response.send_message(
                "❌ シャッフルできる曲が足りません。", ephemeral=True
            )
            return
        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 シャッフルしました。")

    @app_commands.command(name="remove", description="キューから指定番号の曲を削除します")
    @app_commands.describe(index="削除する曲番号")
    async def remove(self, interaction: discord.Interaction, index: int):
        player = self.get_player(interaction.guild)
        if index < 1 or index > len(player.queue):
            await interaction.response.send_message("❌ 正しい番号を指定してください。", ephemeral=True)
            return
        removed = player.queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ 削除しました: **{removed['title']}**")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
