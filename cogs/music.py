import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp as youtube_dl

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
        self.nowplaying_message = None
        
    async def update_nowplaying(self, interaction, info):
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"**[{info['title']}]({info['webpage_url']})**",
            color=0x00ffcc
        )
        embed.set_thumbnail(url=info["thumbnail"])
        embed.add_field(name="長さ", value=f"{info.get('duration', '??')} 秒")

        if self.nowplaying_message is None:
            self.nowplaying_message = await interaction.followup.send(embed=embed)
        else:
            await self.nowplaying_message.edit(embed=embed)

    async def play_next(self, voice, interaction=None):
        if len(self.queue) == 0:
            self.playing = False
            return

        self.playing = True
        url = self.queue.pop()

        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info["url"]

        if interaction:
            await self.update_nowplaying(interaction, info)

        source = await discord.FFmpegOpusAudio.from_probe(audio_url, **FFMPEG_OPTIONS)

        voice.play(
            source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(voice, interaction),
                self.bot.loop
            )
        )

        self.current = info["title"]

    async def add_and_play(self, interaction, url):
        voice = interaction.guild.voice_client
        self.queue.add(url)

        if not self.playing:
            await self.play_next(voice, interaction)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    # ==========================
    # Slash Command: join
    # ==========================
    @app_commands.command(name="join", description="ボイスチャンネルに参加します")
    async def join(self, interaction: discord.Interaction):
        if interaction.user.voice is None:
            await interaction.response.send_message("❌ ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        await channel.connect()
        await interaction.response.send_message(f"🔊 {channel.name} に参加しました。")

    # ==========================
    # Slash Command: play
    # ==========================
    @app_commands.command(name="play", description="音楽を再生します")
    @app_commands.describe(query="曲名またはURL")
    async def play(self, interaction: discord.Interaction, query: str):
        if interaction.guild.voice_client is None:
            await self.join(interaction)

        player = self.get_player(interaction.guild)

        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        await interaction.response.defer()
        await player.add_and_play(interaction, query)

        await interaction.followup.send(f"🎵 キューに追加: **{query}**")


async def setup(bot):
    await bot.add_cog(Music(bot))
