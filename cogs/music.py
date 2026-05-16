import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import random

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicPlayer:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = []
        self.current = None
        self.current_info = None
        self.loop_mode = "off"
        self.playing = False

    async def play_next(self, channel=None):
        voice = self.guild.voice_client
        if voice is None:
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

        loop = self.bot.loop

        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(item["url"], download=False)
                audio_url = info["url"]
            self.current_info = info
        except Exception as e:
            if channel:
                await channel.send(f"❌ 再生エラー: {e}")
            await self.play_next(channel)
            return

        source = discord.FFmpegOpusAudio.from_probe(audio_url, **FFMPEG_OPTIONS)

        def after_play(err):
            asyncio.run_coroutine_threadsafe(self.play_next(channel), loop)

        voice.play(source, after=after_play)

        if channel:
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"[{info['title']}]({info['webpage_url']})",
                color=0x00FFCC,
            )
            embed.set_thumbnail(url=info.get("thumbnail"))
            await channel.send(embed=embed)

    async def add_to_queue(self, channel, query: str):
        if query.startswith("spotify:"):
            query = query.replace("spotify:", "https://open.spotify.com/")

        if not query.startswith("http"):
            query = f"ytsearch:{query}"

        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
                if "entries" in info:
                    entries = info["entries"]
                    if not entries:
                        await channel.send("❌ 検索結果が見つかりませんでした。")
                        return
                    entry = entries[0]
                else:
                    entry = info
                url = entry.get("webpage_url") or entry.get("url")
                title = entry.get("title", "Unknown title")
                if not url:
                    await channel.send("❌ 再生用URLが取得できませんでした。")
                    return
        except Exception as e:
            await channel.send(f"❌ 取得エラー: {e}")
            return

        item = {"url": url, "title": title}
        self.queue.append(item)

        if not self.playing:
            await self.play_next(channel)
        else:
            await channel.send(f"🎵 キューに追加しました: **{title}**")


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    # -------------------------
    # /join
    # -------------------------
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
            await interaction.followup.send(f"🔊 {vc_channel.name} に参加しました。")
        except Exception as e:
            print(f"[join error] {e}")
            await interaction.followup.send(f"❌ エラー: {e}")

    # -------------------------
    # /leave
    # -------------------------
    @app_commands.command(name="leave", description="ボイスチャンネルから退出します")
    async def leave(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if not voice:
            await interaction.response.send_message("❌ 接続していません。", ephemeral=True)
            return
        player = self.get_player(interaction.guild)
        player.queue.clear()
        player.playing = False
        await voice.disconnect()
        await interaction.response.send_message("👋 退出しました。")

    # -------------------------
    # /play  ★「考え中」を出さない版
    # -------------------------
    @app_commands.command(name="play", description="音楽を再生します")
    @app_commands.describe(query="曲名またはURL")
    async def play(self, interaction: discord.Interaction, query: str):
        # VCチェックは即座に実施（3秒以内）
        if interaction.user.voice is None:
            await interaction.response.send_message(
                "❌ ボイスチャンネルに参加してから実行してください。", ephemeral=True
            )
            return

        # ★ 即座に応答して「考え中」を出さない
        await interaction.response.send_message(f"🔍 `{query}` を検索中…")

        # VC接続
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

        # バックグラウンドで検索・再生（時間がかかってもタイムアウトしない）
        asyncio.create_task(
            self._play_task(interaction, query)
        )

    async def _play_task(self, interaction: discord.Interaction, query: str):
        """バックグラウンドで曲を検索してキューに追加する"""
        try:
            player = self.get_player(interaction.guild)
            await player.add_to_queue(interaction.channel, query)
            # 「検索中…」メッセージを削除
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
        except Exception as e:
            print(f"[play error] {e}")
            try:
                await interaction.edit_original_response(content=f"❌ エラー: {e}")
            except Exception:
                pass

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
            await interaction.response.send_message("❌ 再生中の曲がありません。", ephemeral=True)

    # -------------------------
    # /stop
    # -------------------------
    @app_commands.command(name="stop", description="再生を停止してキューをクリアします")
    async def stop(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        player = self.get_player(interaction.guild)
        player.queue.clear()
        player.playing = False
        if voice:
            voice.stop()
            await interaction.response.send_message("⏹️ 停止しました。")
        else:
            await interaction.response.send_message("❌ 再生していません。", ephemeral=True)

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
            await interaction.response.send_message("❌ 再生中ではありません。", ephemeral=True)

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
            await interaction.response.send_message("❌ 一時停止されていません。", ephemeral=True)

    # -------------------------
    # /queue
    # -------------------------
    @app_commands.command(name="queue", description="キューを表示します")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.queue:
            await interaction.response.send_message("📭 キューは空です。")
            return
        lines = [f"{i+1}. {item['title']}" for i, item in enumerate(player.queue)]
        embed = discord.Embed(
            title="📜 キュー一覧",
            description="\n".join(lines),
            color=0x00FFCC,
        )
        await interaction.response.send_message(embed=embed)

    # -------------------------
    # /nowplaying
    # -------------------------
    @app_commands.command(name="nowplaying", description="現在再生中の曲を表示します")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if not player.current_info:
            await interaction.response.send_message("❌ 再生中の曲はありません。", ephemeral=True)
            return
        info = player.current_info
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"[{info['title']}]({info['webpage_url']})",
            color=0x00FFCC,
        )
        embed.set_thumbnail(url=info.get("thumbnail"))
        await interaction.response.send_message(embed=embed)

    # -------------------------
    # /loop
    # -------------------------
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

    # -------------------------
    # /shuffle
    # -------------------------
    @app_commands.command(name="shuffle", description="キューをシャッフルします")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if len(player.queue) < 2:
            await interaction.response.send_message("❌ シャッフルできる曲が足りません。", ephemeral=True)
            return
        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 シャッフルしました。")

    # -------------------------
    # /remove
    # -------------------------
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
