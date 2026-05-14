import discord
from discord.ext import commands
import asyncio
import yt_dlp as youtube_dl


# youtube-dl の警告を無効化
youtube_dl.utils.bug_reports_message = lambda: ""

YDL_OPTIONS = {
    "format": "bestaudio",
    "noplaylist": True,
    "quiet": True,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}


class MusicQueue:
    def __init__(self):
        self.queue = []

    def add(self, item):
        self.queue.append(item)

    def pop(self):
        return self.queue.pop(0) if self.queue else None

    def clear(self):
        self.queue = []

    def __len__(self):
        return len(self.queue)


class MusicPlayer:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()
        self.current = None
        self.playing = False
        self.nowplaying_message = None  # ★追加
        
    
    async def update_nowplaying(self, ctx, info):
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"**[{info['title']}]({info['webpage_url']})**",
            color=0x00ffcc
        )
        embed.set_thumbnail(url=info["thumbnail"])
        embed.add_field(name="長さ", value=f"{info.get('duration', '??')} 秒")

        if self.nowplaying_message is None:
            self.nowplaying_message = await ctx.send(embed=embed)
        else:
            await self.nowplaying_message.edit(embed=embed)


    async def play_next(self, voice, ctx=None):
        if len(self.queue) == 0:
            self.playing = False
            return

        self.playing = True
        url = self.queue.pop()

        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info["url"]

        # NowPlaying 更新
        if ctx:
            await self.update_nowplaying(ctx, info)

        source = await discord.FFmpegOpusAudio.from_probe(audio_url, **FFMPEG_OPTIONS)

        voice.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(voice, ctx),
                self.bot.loop
            )
        )

        # ★ここ修正
        self.current = info["title"]


    async def add_and_play(self, ctx, url):
        voice = ctx.voice_client
        self.queue.add(url)

        if not self.playing:
            await self.play_next(voice, ctx)



class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # guild_id: MusicPlayer

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    # -------------------------
    # VC 参加
    # -------------------------
    @commands.command(name="join")
    async def join(self, ctx):
        if ctx.author.voice is None:
            await ctx.send("❌ ボイスチャンネルに参加してから実行してください。")
            return

        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"🔊 {channel.name} に参加しました。")

    # -------------------------
    # 再生
    # -------------------------
    @commands.command(name="play")
    async def play(self, ctx, *, query):
        if ctx.voice_client is None:
            await ctx.invoke(self.join)

        player = self.get_player(ctx.guild)

        # YouTube 検索対応
        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        await player.add_and_play(ctx, query)
        await ctx.send(f"🎵 キューに追加: **{query}**")
    
    # -------------------------
    # 再生中のキューを表示
    # -------------------------
    @commands.command(name="nowplaying")
    async def nowplaying(self, ctx):
        player = self.get_player(ctx.guild)

        if player.current is None:
            await ctx.send("🎵 現在再生中の曲はありません。")
            return

        await ctx.send(f"🎶 再生中: **{player.current}**")

    # -------------------------
    # スキップ
    # -------------------------
    @commands.command(name="skip")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ スキップしました。")

    # -------------------------
    # 停止
    # -------------------------
    @commands.command(name="stop")
    async def stop(self, ctx):
        player = self.get_player(ctx.guild)
        player.queue.clear()

        if ctx.voice_client:
            ctx.voice_client.stop()

        await ctx.send("⏹️ 停止しました。")

    # -------------------------
    # 一時停止
    # -------------------------
    @commands.command(name="pause")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ 一時停止しました。")

    # -------------------------
    # 再開
    # -------------------------
    @commands.command(name="resume")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 再開しました。")

    # -------------------------
    # キュー表示
    # -------------------------
    @commands.command(name="queue")
    async def queue(self, ctx):
        player = self.get_player(ctx.guild)

        if len(player.queue) == 0:
            await ctx.send("📭 キューは空です。")
            return

        msg = "\n".join([f"{i+1}. {url}" for i, url in enumerate(player.queue.queue)])
        await ctx.send(f"📜 **キュー一覧:**\n{msg}")

    # -------------------------
    # VC 退出
    # -------------------------
    @commands.command(name="leave")
    async def leave(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("👋 VC から退出しました。")



async def setup(bot):
    await bot.add_cog(Music(bot))

