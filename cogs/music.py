import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import random

YDL_OPTIONS = {
    "format": "bestaudio",
    "noplaylist": True,
    "quiet": True
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}


class MusicPlayer:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = []
        self.current = None
        self.loop_mode = "off"  # off / single / all
        self.playing = False

    async def play_next(self, interaction=None):
        voice = self.guild.voice_client
        if voice is None:
            return

        # キューが空の場合
        if not self.queue:
            self.playing = False
            self.current = None
            return

        # ループモード処理
        if self.loop_mode == "single" and self.current:
            url = self.current
        else:
            url = self.queue.pop(0)
            if self.loop_mode == "all":
                self.queue.append(url)

        self.current = url
        self.playing = True

        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info["url"]

        source = await discord.FFmpegOpusAudio.from_probe(audio_url, **FFMPEG_OPTIONS)

        def after_play(err):
            asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

        voice.play(source, after=after_play)

        if interaction:
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"[{info['title']}]({info['webpage_url']})",
                color=0x00ffcc
            )
            embed.set_thumbnail(url=info.get("thumbnail"))
            await interaction.followup.send(embed=embed)

    async def add_to_queue(self, interaction, query):
        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            url = info["entries"][0]["webpage_url"] if "entries" in info else info["webpage_url"]

        self.queue.append(url)

        if not self.playing:
            await self.play_next(interaction)
        else:
            await interaction.followup.send(f"🎵 キューに追加しました: {url}")


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    # -------------------------
    # /join
    # -------------------------
    @app_commands.command(name="join", description="ボイスチャンネルに参加します")
    async def join(self, interaction: discord.Interaction):
        if interaction.user.voice is None:
            await interaction.response.send_message("❌ ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        await channel.connect()
        await interaction.response.send_message(f"🔊 {channel.name} に参加しました。")

    # -------------------------
    # /leave
    # -------------------------
    @app_commands.command(name="leave", description="ボイスチャンネルから退出します")
    async def leave(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice:
            await voice.disconnect()
            await interaction.response.send_message("👋 ボイスチャンネルから退出しました。")
        else:
            await interaction.response.send_message("❌ ボイスチャンネルに接続していません。")

    # -------------------------
    # /play
    # -------------------------
    @app_commands.command(name="play", description="音楽を再生します")
    @app_commands.describe(query="曲名またはURL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if interaction.guild.voice_client is None:
            await self.join(interaction)

        player = self.get_player(interaction.guild)
        await player.add_to_queue(interaction, query)

    # -------------------------
    # /skip
    # -------------------------
    @app_commands.command(name="skip", description="次の曲へスキップします")
    async def skip(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.stop()
            await interaction.response.send_message("⏭️ スキップしました。")
        else:
            await interaction.response.send_message("❌ 再生中の曲がありません。")

    # -------------------------
    # /stop
    # -------------------------
    @app_commands.command(name="stop", description="再生を停止します")
    async def stop(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice:
            voice.stop()
            await interaction.response.send_message("⏹️ 停止しました。")
        else:
            await interaction.response.send_message("❌ 再生していません。")

    # -------------------------
    # /pause
    # -------------------------
    @app_commands.command(name="pause", description="一時停止します")
    async def pause(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸️ 一時停止しました。")
        else:
            await interaction.response.send_message("❌ 再生中ではありません。")

    # -------------------------
    # /resume
    # -------------------------
    @app_commands.command(name="resume", description="再開します")
    async def resume(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ 再開しました。")
        else:
            await interaction.response.send_message("❌ 一時停止されていません。")

    # -------------------------
    # /queue
    # -------------------------
    @app_commands.command(name="queue", description="キューを表示します")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)

        if not player.queue:
            await interaction.response.send_message("📭 キューは空です。")
            return

        text = "\n".join([f"{i+1}. {url}" for i, url in enumerate(player.queue)])
        await interaction.response.send_message(f"📜 **キュー一覧**\n{text}")

    # -------------------------
    # /nowplaying
    # -------------------------
    @app_commands.command(name="nowplaying", description="現在再生中の曲を表示します")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)

        if not player.current:
            await interaction.response.send_message("❌ 再生中の曲はありません。")
            return

        await interaction.response.send_message(f"🎶 **Now Playing:** {player.current}")

    # -------------------------
    # /loop
    # -------------------------
    @app_commands.command(name="loop", description="ループモードを設定します")
    @app_commands.describe(mode="single / all / off")
    async def loop(self, interaction: discord.Interaction, mode: str):
        if mode not in ["single", "all", "off"]:
            await interaction.response.send_message("❌ single / all / off のいずれかを指定してください。")
            return

        player = self.get_player(interaction.guild)
        player.loop_mode = mode

        await interaction.response.send_message(f"🔁 ループモードを **{mode}** に設定しました。")

    # -------------------------
    # /shuffle
    # -------------------------
    @app_commands.command(name="shuffle", description="キューをシャッフルします")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)

        if len(player.queue) < 2:
            await interaction.response.send_message("❌ シャッフルできる曲が足りません。")
            return

        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 キューをシャッフルしました。")

    # -------------------------
    # /remove
    # -------------------------
    @app_commands.command(name="remove", description="キューから指定番号の曲を削除します")
    @app_commands.describe(index="削除する曲番号")
    async def remove(self, interaction: discord.Interaction, index: int):
        player = self.get_player(interaction.guild)

        if index < 1 or index > len(player.queue):
            await interaction.response.send_message("❌ 正しい番号を指定してください。")
            return

        removed = player.queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ 削除しました: {removed}")


async def setup(bot):
    await bot.add_cog(Music(bot))
