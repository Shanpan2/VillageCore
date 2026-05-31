import asyncio
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cogs.server_logs import send_server_log
from database.config_db import db_get, db_set

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    genai = None
    types = None


MENTION_RE = re.compile(r"<@!?\d+>")
MAX_HISTORY_TURNS = 10
DEFAULT_USER_COOLDOWN_SECONDS = 30
DEFAULT_GLOBAL_COOLDOWN_SECONDS = 4
DEFAULT_QUOTA_BACKOFF_SECONDS = 600
DEFAULT_SERVER_BACKOFF_SECONDS = 300
QUOTE_CARD_SIZE = (1200, 630)
QUOTE_MAX_CHARS = 180
QUOTE_THEMES = {
    "black": {
        "label": "黒",
        "top": (8, 9, 12),
        "bottom": (10, 10, 12),
        "accent": (22, 58, 45),
        "shade": 215,
    },
    "forest": {
        "label": "森",
        "top": (8, 30, 24),
        "bottom": (25, 67, 47),
        "accent": (66, 138, 92),
        "shade": 190,
    },
    "night": {
        "label": "夜空",
        "top": (6, 12, 32),
        "bottom": (24, 18, 56),
        "accent": (72, 86, 180),
        "shade": 195,
    },
    "sunset": {
        "label": "夕焼け",
        "top": (52, 23, 48),
        "bottom": (136, 67, 40),
        "accent": (230, 126, 84),
        "shade": 185,
    },
    "mono": {
        "label": "灰",
        "top": (24, 26, 30),
        "bottom": (68, 68, 72),
        "accent": (125, 125, 130),
        "shade": 200,
    },
}
QUOTE_THEME_ORDER = ("black", "forest", "night", "sunset", "mono")
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/NotoSansJP-VF.ttf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/BIZ-UDGothicR.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def sanitize_error_text(text: str, api_key: str | None = None) -> str:
    if api_key:
        text = text.replace(api_key, "***")
    return text[:700]


def user_friendly_ai_error(error: Exception, api_key: str | None = None) -> str:
    detail = sanitize_error_text(str(error), api_key)
    status = getattr(error, "code", None) or getattr(error, "status_code", None)

    if status in (401, 403):
        reason = "APIキー、Gemini APIの有効化、またはプロジェクト権限を確認してください。"
    elif status == 404:
        reason = "指定しているGeminiモデル名が使えない可能性があります。`GEMINI_MODEL` を確認してください。"
    elif status == 429:
        reason = "Gemini APIの利用制限、短時間の呼び出し過多、または無料枠上限の可能性があります。"
    elif status and 400 <= int(status) < 500:
        reason = "Gemini APIへのリクエスト内容、キー、モデル、利用制限のいずれかで拒否されています。"
    elif status and int(status) >= 500:
        reason = "Gemini API側の一時的な障害、または通信失敗の可能性があります。"
    else:
        reason = "Gemini APIへの接続または応答生成で失敗しています。Railwayログの詳細も確認してください。"

    if detail:
        return f"{reason}\n詳細: `{detail}`"
    return reason


def memory_key(guild_id: int | None, user_id: int) -> str:
    scope = guild_id if guild_id is not None else "dm"
    return f"ai_memory:{scope}:{user_id}"


def split_discord_message(text: str, limit: int = 1900) -> list[str]:
    chunks = []
    current = ""
    for line in text.splitlines() or [text]:
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
        current = f"{current}\n{line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks


def load_font(size: int, bold: bool = False):
    candidates = FONT_CANDIDATES[:]
    if bold:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "C:/Windows/Fonts/NotoSansJP-VF.ttf",
            "C:/Windows/Fonts/meiryob.ttc",
            "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
        ] + candidates
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    lines: list[str] = []
    for paragraph in paragraphs or [text.strip()]:
        current = ""
        for char in paragraph:
            candidate = current + char
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def clean_quote_label(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category in {"So", "Sk", "Cs", "Co", "Cn"} or char in {"\ufe0f", "\ufffd"}:
            continue
        cleaned.append(char)
    return "".join(cleaned).strip()


def clean_quote_content(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category in {"So", "Cs", "Co", "Cn"} or char in {"\ufe0f", "\ufffd"}:
            continue
        cleaned.append(char)
    return "".join(cleaned).strip()


def make_gradient_background(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


def apply_quote_background(theme_key: str) -> Image.Image:
    width, height = QUOTE_CARD_SIZE
    theme = QUOTE_THEMES.get(theme_key, QUOTE_THEMES["black"])
    image = make_gradient_background(width, height, theme["top"], theme["bottom"])
    overlay = Image.new("RGBA", QUOTE_CARD_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle((0, 0, width, height), fill=(0, 0, 0, theme["shade"]))
    accent = theme["accent"]
    odraw.ellipse((-180, -150, 560, 760), fill=(*accent, 120))
    odraw.ellipse((760, -260, 1400, 380), fill=(*accent, 70))
    if theme_key == "night":
        star_draw = ImageDraw.Draw(overlay)
        for x, y, alpha in ((930, 92, 95), (1018, 156, 70), (1105, 84, 85), (858, 216, 55), (1138, 262, 50)):
            star_draw.ellipse((x, y, x + 3, y + 3), fill=(255, 255, 245, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


async def make_quote_card(message: discord.Message, theme_key: str = "black") -> BytesIO:
    text = clean_quote_content(message.content or "")
    if not text:
        raise ValueError("quote target has no text")
    if len(text) > QUOTE_MAX_CHARS:
        text = text[:QUOTE_MAX_CHARS].rstrip() + "..."

    width, height = QUOTE_CARD_SIZE
    image = apply_quote_background(theme_key)

    avatar = Image.new("RGBA", (300, 300), (40, 40, 40, 255))
    try:
        avatar_bytes = await message.author.display_avatar.replace(size=512, static_format="png").read()
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((300, 300))
    except Exception:
        pass

    mask = Image.new("L", (300, 300), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 300, 300), fill=255)
    avatar.putalpha(mask)
    avatar = avatar.filter(ImageFilter.UnsharpMask(radius=1, percent=120))
    image.alpha_composite(avatar, (90, 165))

    draw = ImageDraw.Draw(image)
    quote_font_size = 54
    while quote_font_size >= 34:
        quote_font = load_font(quote_font_size)
        lines = wrap_text(draw, text, quote_font, 660)
        line_height = quote_font_size + 14
        if len(lines) * line_height <= 320:
            break
        quote_font_size -= 4
    quote_font = load_font(quote_font_size)
    name_font = load_font(28, bold=True)
    tag_font = load_font(22)

    lines = wrap_text(draw, text, quote_font, 660)
    line_height = quote_font_size + 14
    total_height = len(lines) * line_height
    start_y = max(105, (height - total_height) // 2 - 20)
    x = 470
    for i, line in enumerate(lines):
        draw.text((x, start_y + i * line_height), line, font=quote_font, fill=(245, 245, 245))

    display_name = clean_quote_label(getattr(message.author, "display_name", message.author.name))
    user_name = clean_quote_label(getattr(message.author, "name", display_name))
    if not display_name:
        display_name = "Unknown"
    if not user_name:
        user_name = display_name
    footer_y = start_y + total_height + 34
    draw.text((x, footer_y), f"- {display_name}", font=name_font, fill=(235, 235, 235))
    draw.text((x, footer_y + 36), f"@{user_name}", font=tag_font, fill=(155, 155, 155))
    draw.text((width - 255, height - 54), "むらびと名言", font=tag_font, fill=(160, 160, 160))

    buffer = BytesIO()
    image.convert("RGB").save(buffer, "PNG", optimize=True)
    buffer.seek(0)
    return buffer


class QuoteThemeButton(discord.ui.Button):
    def __init__(self, theme_key: str):
        theme = QUOTE_THEMES[theme_key]
        super().__init__(label=theme["label"], style=discord.ButtonStyle.secondary, custom_id=f"quote_theme:{theme_key}")
        self.theme_key = theme_key

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, QuoteCardView):
            await interaction.response.send_message("名言カードの情報を取得できませんでした。", ephemeral=True)
            return
        try:
            card = await make_quote_card(view.quote_message, self.theme_key)
        except Exception as e:
            print(f"[ai_quote theme error] {type(e).__name__}: {e}", flush=True)
            await interaction.response.send_message("背景の変更に失敗しました。", ephemeral=True)
            return

        await interaction.response.defer()
        await interaction.message.edit(
            attachments=[discord.File(card, filename=f"quote_{self.theme_key}.png")],
            view=view,
        )


class QuoteDeleteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="削除", style=discord.ButtonStyle.danger, custom_id="quote_delete", row=1)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, QuoteCardView):
            await interaction.response.send_message("名言カードの情報を取得できませんでした。", ephemeral=True)
            return

        can_delete = interaction.user.id == view.requester_id
        if isinstance(interaction.user, discord.Member):
            can_delete = can_delete or interaction.user.guild_permissions.manage_messages
        if not can_delete:
            await interaction.response.send_message("この名言カードを削除できるのは、作成者またはメッセージ管理権限を持つ人だけです。", ephemeral=True)
            return

        if interaction.guild:
            quoted_author = view.quote_message.author
            embed = discord.Embed(title="コマンド削除: 名言カード", color=0xE74C3C)
            embed.add_field(name="削除者", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="引用元", value=f"{quoted_author.mention} ({quoted_author.id})", inline=False)
            embed.add_field(name="チャンネル", value=getattr(interaction.channel, "mention", "不明"), inline=True)
            quote_text = (view.quote_message.content or "内容なし").replace("\n", " ").strip()
            embed.add_field(name="引用内容", value=quote_text[:1000], inline=False)
            await send_server_log(view.bot, interaction.guild, embed, "command_delete")
        await interaction.message.delete()


class QuoteCardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, quote_message: discord.Message, requester_id: int):
        super().__init__(timeout=900)
        self.bot = bot
        self.quote_message = quote_message
        self.requester_id = requester_id
        for theme_key in QUOTE_THEME_ORDER:
            self.add_item(QuoteThemeButton(theme_key))
        self.add_item(QuoteDeleteButton())


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=self.api_key) if genai and self.api_key else None
        self.ai_bot_name = os.getenv("AI_BOT_NAME", "むらびとくん")
        self.ai_developer_name = os.getenv("AI_DEVELOPER_NAME", "シャンパン2号")
        self.user_cooldown_seconds = int(os.getenv("AI_USER_COOLDOWN_SECONDS", str(DEFAULT_USER_COOLDOWN_SECONDS)))
        self.global_cooldown_seconds = int(os.getenv("AI_GLOBAL_COOLDOWN_SECONDS", str(DEFAULT_GLOBAL_COOLDOWN_SECONDS)))
        self.quota_backoff_seconds = int(os.getenv("AI_QUOTA_BACKOFF_SECONDS", str(DEFAULT_QUOTA_BACKOFF_SECONDS)))
        self.server_backoff_seconds = int(os.getenv("AI_SERVER_BACKOFF_SECONDS", str(DEFAULT_SERVER_BACKOFF_SECONDS)))
        self.user_next_allowed: dict[tuple[int | str, int], float] = {}
        self.global_next_allowed = 0.0
        self.request_lock = asyncio.Lock()

    async def cog_load(self):
        if not self.client:
            print("AI chat disabled: GEMINI_API_KEY or GOOGLE_API_KEY is not set.", flush=True)

    async def load_memory(self, guild_id: int | None, user_id: int) -> list[dict]:
        raw = await db_get(memory_key(guild_id, user_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    async def save_memory(self, guild_id: int | None, user_id: int, history: list[dict]):
        await db_set(memory_key(guild_id, user_id), json.dumps(history[-MAX_HISTORY_TURNS:], ensure_ascii=False))

    def cooldown_remaining(self, guild_id: int | None, user_id: int) -> int:
        now = time.monotonic()
        scope = guild_id if guild_id is not None else "dm"
        user_wait = self.user_next_allowed.get((scope, user_id), 0) - now
        global_wait = self.global_next_allowed - now
        return max(0, int(max(user_wait, global_wait) + 0.999))

    def mark_cooldown(self, guild_id: int | None, user_id: int):
        now = time.monotonic()
        scope = guild_id if guild_id is not None else "dm"
        self.user_next_allowed[(scope, user_id)] = now + self.user_cooldown_seconds
        self.global_next_allowed = now + self.global_cooldown_seconds

    def mark_quota_backoff(self):
        self.global_next_allowed = max(self.global_next_allowed, time.monotonic() + self.quota_backoff_seconds)

    def mark_server_backoff(self):
        self.global_next_allowed = max(self.global_next_allowed, time.monotonic() + self.server_backoff_seconds)
        print(f"[ai_chat] Gemini server backoff active for {self.server_backoff_seconds} seconds.", flush=True)

    def build_prompt(self, message: discord.Message, question: str, history: list[dict]) -> str:
        display_name = getattr(message.author, "display_name", message.author.name)
        guild_name = message.guild.name if message.guild else "DM"
        history_lines = []
        for item in history[-MAX_HISTORY_TURNS:]:
            user_text = item.get("user", "")
            assistant_text = item.get("assistant", "")
            if user_text:
                history_lines.append(f"User: {user_text}")
            if assistant_text:
                history_lines.append(f"Assistant: {assistant_text}")

        history_text = "\n".join(history_lines) if history_lines else "No previous conversation."
        bot_identity = self.ai_bot_name or getattr(self.bot.user, "display_name", "むらびとくん")
        developer_identity = self.ai_developer_name or "シャンパン2号"
        return (
            f"Discord server: {guild_name}\n"
            f"Bot name: {bot_identity}\n"
            f"Developer name: {developer_identity}\n"
            f"User: {display_name}\n\n"
            f"Recent conversation with this user:\n{history_text}\n\n"
            f"Current question:\n{question}"
        )

    def generate_reply(self, prompt: str) -> str:
        if not self.client:
            return "AI応答が未設定です。環境変数 `GEMINI_API_KEY` を設定してください。"

        config = types.GenerateContentConfig(
            system_instruction=(
                "あなたはDiscordサーバー内で動く親切な日本語アシスタントです。"
                f"あなたのBot名は「{self.ai_bot_name}」です。"
                f"開発者名は「{self.ai_developer_name or 'シャンパン2号'}」です。"
                "Bot名や開発者名を聞かれた場合は、上記の名前をそのまま答えてください。"
                "会話履歴を参考にしつつ、簡潔で自然に答えてください。"
                "不確かなことは断定せず、確認が必要だと伝えてください。"
            ),
            temperature=0.7,
            max_output_tokens=1000,
        )
        last_error = None
        for attempt in range(2):
            try:
                response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
                break
            except Exception as e:
                last_error = e
                status = getattr(e, "code", None) or getattr(e, "status_code", None)
                if attempt == 0 and status and int(status) >= 500:
                    time.sleep(2)
                    continue
                raise
        else:
            raise last_error
        return (getattr(response, "text", None) or "").strip() or "すみません、うまく回答を生成できませんでした。"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user:
            return

        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = False
        replied_message = None
        if message.reference:
            replied_message = message.reference.resolved
            if not isinstance(replied_message, discord.Message) and message.reference.message_id:
                try:
                    replied_message = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    replied_message = None
            if isinstance(replied_message, discord.Message):
                is_reply_to_bot = replied_message.author.id == self.bot.user.id

        if not is_mentioned and not is_reply_to_bot:
            return

        question = MENTION_RE.sub("", message.content).strip()
        if is_mentioned and isinstance(replied_message, discord.Message) and not question:
            try:
                card = await make_quote_card(replied_message)
                await message.reply(
                    file=discord.File(card, filename="quote.png"),
                    view=QuoteCardView(self.bot, replied_message, message.author.id),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except ValueError:
                await message.reply(
                    "引用できるテキストがありません。テキスト付きのメッセージに返信してBotをメンションしてください。",
                    mention_author=False,
                )
            except Exception as e:
                print(f"[ai_quote error] {type(e).__name__}: {e}", flush=True)
                await message.reply("名言カードの生成に失敗しました。", mention_author=False)
            return

        if not question:
            await message.reply("質問内容も一緒に送ってください。例: `@Bot 今日の予定を整理して`")
            return

        guild_id = message.guild.id if message.guild else None
        wait_seconds = self.cooldown_remaining(guild_id, message.author.id)
        if wait_seconds > 0:
            await message.reply(f"AI応答は少しクールダウン中です。あと {wait_seconds} 秒ほど待ってから試してください。")
            return
        self.mark_cooldown(guild_id, message.author.id)

        async with message.channel.typing():
            try:
                history = await self.load_memory(guild_id, message.author.id)
                prompt = self.build_prompt(message, question, history)
                async with self.request_lock:
                    reply = await asyncio.to_thread(self.generate_reply, prompt)
                history.append(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "user": question[:1000],
                        "assistant": reply[:1500],
                    }
                )
                await self.save_memory(guild_id, message.author.id, history)
            except Exception as e:
                detail = sanitize_error_text(str(e), self.api_key)
                print(f"[ai_chat error] {type(e).__name__}: {detail}", flush=True)
                status = getattr(e, "code", None) or getattr(e, "status_code", None)
                if status == 429:
                    self.mark_quota_backoff()
                elif status and int(status) >= 500:
                    self.mark_server_backoff()
                await message.reply(f"AI応答中にエラーが発生しました: {type(e).__name__}\n{user_friendly_ai_error(e, self.api_key)}")
                return

        chunks = split_discord_message(reply)
        if chunks:
            await message.reply(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)

    @app_commands.command(name="ai_memory_clear", description="自分のAI会話履歴を削除します")
    async def ai_memory_clear(self, interaction: discord.Interaction):
        await db_set(memory_key(interaction.guild_id, interaction.user.id), "[]")
        await interaction.response.send_message("AI会話履歴を削除しました。", ephemeral=True)

    @app_commands.command(name="ai_memory_status", description="自分のAI会話履歴の保存件数を表示します")
    async def ai_memory_status(self, interaction: discord.Interaction):
        history = await self.load_memory(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"保存されている会話履歴: {len(history)}件", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
