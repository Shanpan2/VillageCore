import os
import sys
import discord
from discord.ext import commands
import asyncio
import json
from datetime import datetime, timezone
from html import escape
from aiohttp import web

from bot_instance import bot
from database.config_db import db_get, db_get_all_config, db_init, db_set, use_postgres
from role_guesser.bot import role_bot, start_role_guesser_bot

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
LEGACY_GUILD_ID = os.getenv("LEGACY_GUILD_ID", "1405716361933754408")
PORT = int(os.getenv("PORT", "8000"))
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN")
BOT_ACTIVITY_TEXT = os.getenv("BOT_ACTIVITY_TEXT", "/help | むらびと君")
COMMANDS_SYNCED = False
PERSISTENT_VIEWS_REGISTERED = False


def parse_discord_id(value: str | None, name: str) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value.isdigit():
        print(
            f"⚠️ {name} must be a numeric Discord ID, not an invite URL or text: {value!r}",
            flush=True,
        )
        return None
    return int(value)


TARGET_GUILD_ID = parse_discord_id(GUILD_ID, "GUILD_ID")
TARGET_LEGACY_GUILD_ID = parse_discord_id(LEGACY_GUILD_ID, "LEGACY_GUILD_ID")
DEFAULT_DISABLED_EXTENSIONS = {
    "cogs.backup",
    "cogs.bot_status",
    "cogs.permission_check",
    "cogs.setup_guide",
}
DEFAULT_HIDDEN_SLASH_COMMANDS = {
    "uno_join",
    "uno_begin",
    "uno_start",
    "sevens_join",
    "sevens_begin",
    "sevens_start",
    "daifugo_join",
    "daifugo_begin",
    "daifugo_start",
    "poker_join",
    "poker_begin",
    "poker_start",
    "game_cancel",
    "join",
    "leave",
    "play",
    "skip",
    "stop",
    "pause",
    "resume",
    "queue",
    "nowplaying",
    "loop",
    "shuffle",
    "remove",
    "youtube_check",
    "youtube_notify_channel",
    "youtube_notify_keyword",
    "youtube_notify_keywords",
    "youtube_notify_status",
    "attend_set_channel",
    "attend_add_members_bulk",
    "attend_record",
    "attend_record_all",
    "attend_status",
    "attend_warnings",
    "attend_notify",
    "setup_wizard",
    "error_log_channel",
    "command_log_channel",
    "permission_audit",
    "maintenance_on",
    "maintenance_off",
    "maintenance_status",
    "data_cleanup",
}


def disabled_extensions() -> set[str]:
    raw = os.getenv("DISABLED_EXTENSIONS")
    extra = {item.strip() for item in raw.split(",") if item.strip()} if raw else set()
    return DEFAULT_DISABLED_EXTENSIONS | extra


def hidden_slash_commands() -> set[str]:
    raw = os.getenv("HIDDEN_SLASH_COMMANDS")
    extra = {item.strip() for item in raw.split(",") if item.strip()} if raw else set()
    return DEFAULT_HIDDEN_SLASH_COMMANDS | extra


def prune_hidden_slash_commands() -> None:
    for name in hidden_slash_commands():
        bot.tree.remove_command(name, guild=None)


# ==========================
# Cog ロード
# ==========================
async def load_cogs():
    cogs = [
        # cogs/
        "cogs.backup",
        "cogs.birthday",
        "cogs.clean",
        "cogs.community",
        "cogs.reminder",
        "cogs.bot_status",
        "cogs.permission_check",
        "cogs.quick",
        "cogs.server_logs",
        "cogs.setup_guide",
        "cogs.vote",
        "cogs.janken",
        "cogs.welcome",
        "cogs.music",
        "cogs.ng_words",
        "cogs.ops",
        "cogs.ai_chat",
        "cogs.help",
        # Features/
        "Features.attendance",
        "Features.codenames",
        "Features.daifugo",
        "Features.dice",
        "Features.google_search",
        "Features.gomoku",
        "Features.ito",
        "Features.meigen",
        "Features.omikuji",
        "Features.othello",
        "Features.poker",
        "Features.role_panel",
        "Features.sevens",
        "Features.shogi",
        "Features.shogi_puzzle",
        "Features.ticket",
        "Features.uno",
        "Features.werewolf",
        "Features.youtube_notify",
        "cogs.panels",
    ]
    disabled = disabled_extensions()
    for cog in cogs:
        if cog in disabled:
            print(f"  skipped by config: {cog}", flush=True)
            continue
        try:
            await bot.load_extension(cog)
            prune_hidden_slash_commands()
            print(f"  ✅ loaded: {cog}")
        except Exception as e:
            print(f"  ⚠️  skipped: {cog} → {e}")


# ==========================
# 永続 View の登録
# ==========================
def register_persistent_views():
    from views.ticket_views import ClosedTicketView, TicketButtonView, TicketControlView
    from views.role_panel_views import LegacyRolePanelView, RolePanelView
    from cogs.quick import GameControlView, GameMenuView, OthelloModeView
    from Features.gomoku import GomokuModeView
    from Features.shogi import ShogiPanelView
    from Features.shogi_puzzle import ShogiPuzzleLevelView
    # ★ AttendanceView は attendance.py に統合したため削除
    bot.add_view(TicketButtonView(bot))
    bot.add_view(TicketControlView())
    bot.add_view(ClosedTicketView())
    bot.add_view(RolePanelView())
    bot.add_view(LegacyRolePanelView())
    bot.add_view(GameMenuView())
    bot.add_view(OthelloModeView())
    bot.add_view(GomokuModeView())
    bot.add_view(ShogiPanelView())
    bot.add_view(ShogiPuzzleLevelView())
    for game in ("uno", "sevens", "daifugo", "poker", "othello", "gomoku", "ito", "codenames", "werewolf"):
        bot.add_view(GameControlView(game))


async def clear_global_commands():
    try:
        print("🔄 Clearing global slash commands so only guild commands remain...", flush=True)
        bot.tree.clear_commands(guild=None)
        cleared_global = await bot.tree.sync(guild=None)
        print(f"🔄 Global slash commands after cleanup: {len(cleared_global)}", flush=True)
    except Exception as e:
        print(f"⚠️ Global slash command cleanup failed: {type(e).__name__}: {e}", flush=True)


async def clear_legacy_guild_commands():
    if not TARGET_LEGACY_GUILD_ID:
        return
    try:
        guild = discord.Object(id=TARGET_LEGACY_GUILD_ID)
        print(f"🔄 Clearing legacy guild slash commands: {LEGACY_GUILD_ID}", flush=True)
        bot.tree.clear_commands(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔄 Legacy guild slash commands after cleanup: {len(synced)}", flush=True)
    except Exception as e:
        print(f"⚠️ Legacy guild command cleanup failed: {type(e).__name__}: {e}", flush=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def guild_record_key(guild_id: int) -> str:
    return f"bot_guild:{guild_id}"


async def load_guild_record(guild_id: int) -> dict:
    raw = await db_get(guild_record_key(guild_id))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def upsert_guild_record(guild: discord.Guild, joined: bool = False) -> None:
    now = utc_now_iso()
    data = await load_guild_record(guild.id)
    data.setdefault("first_seen_at", now)
    if joined:
        data["joined_at"] = now
        data.pop("left_at", None)
    data.update(
        {
            "id": str(guild.id),
            "name": guild.name,
            "owner_id": str(guild.owner_id) if guild.owner_id else "",
            "member_count": guild.member_count,
            "last_seen_at": now,
        }
    )
    await db_set(guild_record_key(guild.id), json.dumps(data, ensure_ascii=False))


async def mark_guild_removed(guild: discord.Guild) -> None:
    data = await load_guild_record(guild.id)
    now = utc_now_iso()
    data.setdefault("first_seen_at", now)
    data.update(
        {
            "id": str(guild.id),
            "name": guild.name,
            "owner_id": str(guild.owner_id) if guild.owner_id else "",
            "member_count": guild.member_count,
            "left_at": now,
            "last_seen_at": now,
        }
    )
    await db_set(guild_record_key(guild.id), json.dumps(data, ensure_ascii=False))


async def record_current_guilds() -> None:
    for guild in bot.guilds:
        await upsert_guild_record(guild)


def format_dt(value: str | None) -> str:
    if not value:
        return "-"
    return escape(value.replace("T", " ").replace("+00:00", " UTC"))


def bot_permission_summary(guild: discord.Guild) -> tuple[str, str]:
    me = guild.me
    if not me:
        return "不明", "unknown"
    perms = me.guild_permissions
    if perms.administrator:
        return "管理者", "ok"
    important = [
        perms.manage_roles,
        perms.manage_channels,
        perms.send_messages,
        perms.embed_links,
        perms.attach_files,
        perms.read_message_history,
    ]
    if all(important):
        return "主要権限OK", "ok"
    if perms.send_messages:
        return "一部不足", "warn"
    return "送信不可の可能性", "bad"


def dashboard_env_rows(names: tuple[str, ...]) -> str:
    return "".join(
        f"<tr><td>{name}</td><td>{'設定済み' if os.getenv(name) else '未設定'}</td></tr>"
        for name in names
    )


def dashboard_guild_rows(guilds: list[discord.Guild], guild_records: dict[str, str] | None = None) -> list[str]:
    rows = []
    records = guild_records or {}
    for guild in guilds:
        record = {}
        raw_record = records.get(str(guild.id))
        if raw_record:
            try:
                record = json.loads(raw_record)
            except Exception:
                record = {}
        owner = guild.owner
        me = guild.me
        permission_text, permission_class = bot_permission_summary(guild)
        icon = guild.icon.url if guild.icon else ""
        icon_html = (
            f'<img class="guild-icon" src="{escape(icon)}" alt="">'
            if icon
            else '<span class="guild-icon placeholder">?</span>'
        )
        search_text = f"{guild.name} {guild.id} {owner.name if owner else ''}".casefold()
        rows.append(
            f'<tr data-search="{escape(search_text)}">'
            f'<td><div class="guild-cell">{icon_html}<div><strong>{escape(guild.name)}</strong>'
            f'<small>{guild.id}</small></div></div></td>'
            f'<td>{guild.member_count or "-"}</td>'
            f'<td>{escape(owner.name) if owner else escape(str(guild.owner_id or "-"))}</td>'
            f'<td>{format_dt(record.get("first_seen_at"))}</td>'
            f'<td>{format_dt(record.get("last_seen_at"))}</td>'
            f'<td><span class="pill {permission_class}">{escape(permission_text)}</span></td>'
            f'<td>{"可" if me and me.guild_permissions.create_instant_invite else "不可"}</td>'
            '</tr>'
        )
    return rows


# ==========================
# on_ready
# ==========================
@bot.event
async def on_ready():
    global COMMANDS_SYNCED, PERSISTENT_VIEWS_REGISTERED

    if BOT_ACTIVITY_TEXT:
        try:
            await bot.change_presence(activity=discord.Game(name=BOT_ACTIVITY_TEXT))
        except Exception as e:
            print(f"⚠️ presence update failed: {e}", flush=True)

    try:
        if not PERSISTENT_VIEWS_REGISTERED:
            register_persistent_views()
            PERSISTENT_VIEWS_REGISTERED = True
    except Exception as e:
        print(f"⚠️ register_persistent_views エラー: {e}")

    try:
        await record_current_guilds()
    except Exception as e:
        print(f"?? guild dashboard record failed: {type(e).__name__}: {e}", flush=True)

    if COMMANDS_SYNCED:
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        return

    if TARGET_GUILD_ID:
        guild = discord.Object(id=TARGET_GUILD_ID)
        print("🔄 Syncing global slash commands...", flush=True)
        global_synced = await bot.tree.sync()
        print("🔄 Copying slash commands to target guild for fast local updates...", flush=True)
        bot.tree.copy_global_to(guild=guild)
        print("🔄 Syncing target guild slash commands...", flush=True)
        synced = await bot.tree.sync(guild=guild)
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(global_synced)} global slash commands", flush=True)
        print(f"🔄 Synced {len(synced)} slash commands to guild {GUILD_ID}", flush=True)
    else:
        synced = await bot.tree.sync()
        asyncio.create_task(clear_legacy_guild_commands())
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(synced)} global slash commands", flush=True)



@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        await upsert_guild_record(guild, joined=True)
    except Exception as e:
        print(f"?? guild join record failed: {guild.id} {type(e).__name__}: {e}", flush=True)


@bot.event
async def on_guild_remove(guild: discord.Guild):
    try:
        await mark_guild_removed(guild)
    except Exception as e:
        print(f"?? guild remove record failed: {guild.id} {type(e).__name__}: {e}", flush=True)

async def handle_ping(request):
    return web.Response(text="OK")


def command_list(prefixes: tuple[str, ...]) -> str:
    commands = []
    try:
        for command in bot.tree.walk_commands():
            name = str(getattr(command, "name", ""))
            parent = getattr(command, "parent", None)
            if parent is None and name.startswith(prefixes):
                commands.append(command)
    except Exception as e:
        print(f"[help site] command list failed: {type(e).__name__}: {e}", flush=True)
        return "<p class='muted'>コマンド一覧を読み込めませんでした。Bot起動後にもう一度開いてください。</p>"
    commands = sorted(commands, key=lambda command: str(getattr(command, "name", "")))
    if not commands:
        return "<p class='muted'>起動後にコマンド一覧が表示されます。</p>"
    return "<ul class='command-list'>" + "".join(
        f"<li><code>/{escape(str(getattr(command, 'name', '')))}</code><span>{escape(str(getattr(command, 'description', '') or ''))}</span></li>"
        for command in commands
    ) + "</ul>"


async def handle_help_site(request):
    try:
        command_count = len([c for c in bot.tree.walk_commands() if getattr(c, "parent", None) is None])
    except Exception as e:
        print(f"[help site] command count failed: {type(e).__name__}: {e}", flush=True)
        command_count = 0
    html = f"""
    <!doctype html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>むらびと君 ヘルプ</title>
      <style>
        :root {{
          color-scheme: light;
          --bg: #f5f7f3;
          --ink: #1d2b24;
          --muted: #607065;
          --line: #d9e2d7;
          --panel: #ffffff;
          --accent: #2d7a52;
          --accent-2: #b66b2d;
          --soft: #eaf3e6;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: var(--bg);
          color: var(--ink);
          line-height: 1.72;
        }}
        header {{
          background: #274f39;
          color: #fff;
          padding: 28px 18px 22px;
          border-bottom: 5px solid #d99345;
        }}
        .wrap {{ max-width: 1120px; margin: 0 auto; }}
        .brand {{ display: flex; gap: 16px; align-items: center; }}
        .badge {{
          width: 62px; height: 62px; border-radius: 8px;
          display: grid; place-items: center;
          background: #f7d89e; color: #274f39;
          font-size: 30px; font-weight: 800;
          border: 2px solid rgba(255,255,255,.55);
        }}
        h1 {{ margin: 0; font-size: clamp(1.75rem, 4vw, 2.7rem); letter-spacing: 0; }}
        header p {{ margin: 8px 0 0; color: #e7f4ea; max-width: 760px; }}
        nav {{
          position: sticky; top: 0; z-index: 2;
          background: rgba(245,247,243,.96);
          border-bottom: 1px solid var(--line);
          backdrop-filter: blur(8px);
        }}
        nav .wrap {{
          display: flex; gap: 10px; overflow-x: auto;
          padding: 10px 18px;
        }}
        nav a {{
          flex: 0 0 auto;
          color: var(--ink); text-decoration: none;
          padding: 8px 10px; border-radius: 6px;
          font-weight: 650; font-size: .94rem;
        }}
        nav a:hover {{ background: var(--soft); }}
        main {{ padding: 24px 18px 46px; }}
        section {{
          margin: 20px 0;
          padding: 22px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
        }}
        h2 {{ margin: 0 0 12px; font-size: 1.42rem; }}
        h3 {{ margin: 16px 0 8px; font-size: 1.05rem; }}
        .grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
          gap: 14px;
        }}
        .tile {{
          padding: 15px 16px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: #fbfcfa;
        }}
        .tile strong {{ display: block; margin-bottom: 4px; color: var(--accent); }}
        code {{
          background: #edf3eb;
          color: #18472f;
          border: 1px solid #d7e4d4;
          border-radius: 5px;
          padding: 1px 6px;
          white-space: nowrap;
        }}
        .command-list {{ list-style: none; margin: 0; padding: 0; }}
        .command-list li {{
          display: grid;
          grid-template-columns: minmax(130px, 210px) 1fr;
          gap: 10px;
          padding: 9px 0;
          border-bottom: 1px solid #eef2ec;
        }}
        .command-list li:last-child {{ border-bottom: 0; }}
        .muted {{ color: var(--muted); }}
        .notice {{
          border-left: 4px solid var(--accent-2);
          background: #fff8ed;
          padding: 13px 15px;
          border-radius: 6px;
        }}
        .notice p {{ margin: 0 0 10px; }}
        .notice p:last-child {{ margin-bottom: 0; }}
        .compact-list {{ margin: 8px 0 0; padding-left: 1.2rem; }}
        .compact-list li {{ margin: 3px 0; }}
        footer {{ color: var(--muted); padding: 24px 18px 42px; text-align: center; }}
        @media (max-width: 640px) {{
          .brand {{ align-items: flex-start; }}
          .badge {{ width: 52px; height: 52px; font-size: 24px; }}
          section {{ padding: 14px; }}
          .command-list li {{ grid-template-columns: 1fr; gap: 3px; }}
        }}
      </style>
    </head>
    <body>
      <header>
        <div class="wrap brand">
          <div class="badge">村</div>
          <div>
            <h1>むらびと君 ヘルプ</h1>
            <p>Discordサーバーの運営と交流を支える多機能Botです。音楽、チケット、出席、通知、AI、ゲーム、コミュニティ機能をまとめて使えます。</p>
          </div>
        </div>
      </header>
      <nav>
        <div class="wrap">
          <a href="#start">はじめに</a>
          <a href="#roles-guesser">Roles Guesser</a>
          <a href="#daily">日常</a>
          <a href="#games">ゲーム</a>
          <a href="#coin-note">コイン遊び</a>
          <a href="#admin">管理者</a>
          <a href="#trouble">困った時</a>
          <a href="#commands">コマンド</a>
        </div>
      </nav>
      <main class="wrap">
        <section id="start">
          <h2>はじめに</h2>
          <div class="grid">
            <div class="tile"><strong>まず使う</strong><code>/quick</code> で日常用メニューを開けます。</div>
            <div class="tile"><strong>設定確認</strong><code>/settings_status</code> で通知先やログ先を確認できます。</div>
            <div class="tile"><strong>権限確認</strong><code>/permission_audit</code> でBot権限を診断できます。</div>
          </div>
        </section>
        <section id="roles-guesser">
          <h2>Roles Guesser</h2>
          <div class="notice">
            <p><strong>Among Us MOD役職向けのアキネーター・クイズBOT</strong><br>
              Roles Guesserは、Among Us MODの役職を推測したり、特徴から役職を覚えたりするための補助BOTです。
              Wiki本文をそのまま掲載するのではなく、役職の挙動を特徴タグに分解し、BOT用の独自質問・ヒントとして扱います。
              著作権リスクを抑えるため、Wiki本文、表、Tips、Q&A、画像などは転載しません。
            </p>
          </div>
          <div class="grid">
            <div class="tile"><strong>役職アキネーター</strong><code>/guess</code> 質問に答えて候補の役職を絞り込みます。MODでの絞り込みにも対応しています。</div>
            <div class="tile"><strong>役職クイズ</strong><code>/quiz</code> 表示された特徴ヒントから、該当する役職を選ぶクイズです。</div>
            <div class="tile"><strong>データ方針</strong> 役職説明文は転載せず、<code>roles.csv</code> には役職名、MOD名、陣営、特徴タグを中心に保存します。</div>
          </div>
        </section>
        <section id="daily">
          <h2>日常で使う機能</h2>
          <div class="grid">
            <div class="tile"><strong>AI応答</strong>Botにメンション、またはBotの返信にリプライするとAIが答えます。</div>
            <div class="tile"><strong>音楽</strong><code>/music</code> で音楽パネルを開き、再生、停止、スキップ、キュー確認をボタンで操作できます。</div>
            <div class="tile"><strong>プロフィール</strong><code>/profile_set</code> と <code>/profile</code> で自己紹介を管理できます。</div>
            <div class="tile"><strong>コイン/称号</strong><code>/coin_daily</code> で毎日コイン、<code>/coin_gamble</code> でコインを賭けられます。</div>
          </div>
        </section>
        <section id="games">
          <h2>ゲーム</h2>
          <div class="notice">
            <p><strong>おすすめの使い方</strong><br>
              ゲームは <code>/game</code> から選ぶのがおすすめです。
              UNO、7並べ、大富豪、ポーカー、オセロ、Ito、コードネーム、人狼の募集作成、参加、抜ける、開始、中止、ルール確認をボタンで操作できます。
              今後は個別コマンドより <code>/game</code> をメイン導線にしていきます。
            </p>
          </div>
          <p>UNO、7並べ、大富豪、ポーカー、オセロ、将棋、詰将棋、Ito、コードネーム、人狼、じゃんけん、おみくじ、ダイスに対応しています。</p>
          <div class="grid">
            <div class="tile"><strong>ゲームパネル</strong><code>/game</code> からUNO、7並べ、大富豪、ポーカー、オセロ、将棋、詰将棋、Ito、コードネーム、人狼を選べます。募集作成、参加、抜ける、開始、中止、ルール確認をボタンで操作できます。</div>
            <div class="tile"><strong>UNO</strong><code>/game</code> でUNOを選びます。手札と操作はDM、公開チャンネルは1つの進行メッセージを編集して場札だけを表示します。</div>
            <div class="tile"><strong>7並べ</strong><code>/game</code> で7並べを選びます。7を中心に同じマークのカードを順番につなげます。手札はDM画像で届き、公開パネルにはカード名を表示しません。</div>
            <div class="tile"><strong>大富豪</strong><code>/game</code> で大富豪を選びます。前の人より強いカードを出し、先に手札をなくした人が上がりです。出せる候補はDMで確認できます。</div>
            <div class="tile"><strong>ポーカー</strong><code>/game</code> でポーカーを選びます。DMで届いた5枚の手札から交換し、役の強さで勝負します。最終結果はトランプ画像付きで表示されます。</div>
            <div class="tile"><strong>オセロ</strong><code>/game</code> でオセロを選びます。対人戦またはAI対戦の難易度を選んで開始できます。</div>
            <div class="tile"><strong>詰将棋</strong><code>/game</code> で詰将棋を選びます。初級/中級/上級から選び、正解するとコインを獲得できます。</div>
            <div class="tile"><strong>Ito</strong><code>/game</code> でItoを選びます。主催者がお題を入力でき、空欄ならランダムお題で始められます。</div>
            <div class="tile"><strong>コードネーム</strong><code>/game</code> でコードネームを選びます。赤/青チーム参加とスパイマスター設定をボタンで行えます。</div>
            <div class="tile"><strong>人狼</strong><code>/game</code> で人狼を選びます。募集、参加、開始、ルール確認をボタンで行い、夜行動や投票は対象指定コマンドで進めます。</div>
            <div class="tile"><strong>募集</strong><code>/event_create</code> で参加/未定/不参加ボタン付き募集を作れます。中止は <code>/event_cancel</code> です。</div>
            <div class="tile"><strong>すぐ遊ぶ</strong><code>/quick</code> からゲームパネル、おみくじ、1d100、じゃんけんを実行できます。</div>
          </div>
          <div class="notice">
            <p><strong>ゲーム募集の中止</strong><br>
              UNO、7並べ、大富豪、ポーカー、オセロ、Ito、コードネーム、人狼の募集中止は <code>/game</code> の「中止」ボタンから行えます。
              募集作成者または管理者が実行できます。開始済みのゲームを終了する場合は管理者権限が必要です。
            </p>
            <p><strong>ゲームの保存</strong><br>
              多くのゲームはデータベースに状態を保存します。再デプロイ後も続きから操作できるようにしています。
              ただし、古い操作パネルや終了済みゲームは復元できない場合があります。
            </p>
            <p><strong>UNOのルール</strong><br>
              手札を先になくした人が勝ちです。場のカードと同じ色、同じ数字、同じ記号のカードを出せます。
              出せない時は山札から引きます。残り1枚になったらUNO宣言を忘れないようにしてください。
            </p>
            <p><strong>7並べのルール</strong><br>
              7を中心に、同じマークの6、8、5、9のように順番につなげて出します。
              出せるカードがない時はパスできます。手札を早くなくした人から順位が決まります。
            </p>
            <p><strong>大富豪のルール</strong><br>
              前の人より強いカード、または同じ枚数の組み合わせを出していきます。
              先に手札をなくした人が上がりです。革命、8切り、階段、しばり、都落ちなどの追加ルールに対応しています。
            </p>
            <p><strong>ポーカーのルール</strong><br>
              5枚の手札がDMで届きます。交換したいカードを選び、全員の交換が終わると役の強さで勝敗が決まります。
              強い順は、ストレートフラッシュ、フォーカード、フルハウス、フラッシュ、ストレート、スリーカード、ツーペア、ワンペア、ハイカードです。
            </p>
            <p><strong>Itoのルール</strong><br>
              1から100の数字がDMで配られます。数字を直接言わず、お題に沿った例えで表現し、最後に小さい順へ並べます。
            </p>
            <p><strong>コードネームのルール</strong><br>
              赤青チームに分かれ、スパイマスターのヒントから味方の単語を当てます。暗殺者を選ぶと即敗北です。
            </p>
            <p><strong>人狼のルール</strong><br>
              村人陣営は人狼を全員追放すれば勝ち、人狼陣営は人狼の数が村人陣営以上になれば勝ちです。
            </p>
          </div>
          {command_list(("uno", "sevens", "daifugo", "poker", "game", "othello", "ito", "codenames", "werewolf", "janken", "omikuji", "dice"))}
        </section>
        <section id="coin-note">
          <h2>コイン遊びのメモ</h2>
          <div class="notice">
            <p><strong>遊び方の目安</strong><br>
              コインはサーバー内の遊び用ポイントです。勝ち負けが続く時は、少し休憩して別の話題やゲームに切り替えるのがおすすめです。
            </p>
          </div>
          <div class="grid">
            <div class="tile"><strong>ほどほどに遊ぶ</strong>連続で賭け続けず、区切りを決めて遊ぶと長く楽しめます。</div>
            <div class="tile"><strong>休憩を入れる</strong>大きく負けた時や連敗した時は10分休憩。熱くなりすぎる前に止めるのが安心です。</div>
            <div class="tile"><strong>煽りすぎない</strong>「今日はここまで」と言った人には追加で煽らないようにしましょう。</div>
            <div class="tile"><strong>0コイン時</strong>ギャンブルで0コインになった場合、その時点から24時間はギャンブルできません。</div>
          </div>
          <div class="notice">
            <p><strong>軽い罰ゲームにするなら</strong><br>
              安全で短く、笑って終われる内容にしてください。<code>/penalty_gacha</code> で軽い罰ゲームをランダムに引けます。
            </p>
            <ul class="compact-list">
              <li>その日だけ軽い語尾を付ける</li>
              <li>今日の反省を1行で書く</li>
              <li>好きな食べ物や最近のおすすめを発表する</li>
              <li>今の気持ちを五七五っぽく書く</li>
            </ul>
          </div>
        </section>
        <section id="admin">
          <h2>管理者向け</h2>
          <div class="grid">
            <div class="tile"><strong>管理パネル</strong><code>/admin</code> で設定確認、権限診断、ログ設定、メンテナンス操作をまとめて実行できます。</div>
            <div class="tile"><strong>チケット</strong><code>/ticket_setup</code> と <code>/ticket_log_channel</code> を設定します。</div>
            <div class="tile"><strong>役職パネル</strong><code>/role_panel_setup</code> で複数ロール対応のパネルを作れます。</div>
            <div class="tile"><strong>YouTube通知</strong><code>/youtube</code> で通知先、キーワード、状態確認、手動チェックを操作できます。</div>
            <div class="tile"><strong>出席管理</strong><code>/attendance</code> で出席記録、ポイント一覧、警告確認を操作できます。</div>
            <div class="tile"><strong>ログ/メンテナンス</strong><code>/admin</code> からエラーログ先、利用ログ先、メンテナンス状態を設定できます。</div>
          </div>
        </section>
        <section id="trouble">
          <h2>困った時</h2>
          <div class="notice">
            <p><strong>AIが429/503になる</strong><br>Gemini APIの無料枠上限や混雑です。時間を置くか、モデル/クールダウン設定を調整してください。</p>
            <p><strong>YouTube通知が止まる</strong><br>YouTube Data APIのクォータ上限です。Botは一定時間チェックを休止します。</p>
            <p><strong>音楽が再生されない</strong><br>cookie、yt-dlp、Deno、動画側の制限を確認してください。</p>
            <p><strong>ロール付与できない</strong><br>Botのロールを付与対象ロールより上に置いてください。</p>
          </div>
        </section>
        <section id="commands">
          <h2>コマンド一覧</h2>
          <p class="muted">現在読み込まれているトップレベルコマンド数: {command_count}</p>
          <h3>よく使う</h3>
          {command_list(("quick", "music", "youtube", "attendance", "admin", "profile", "coin", "penalty", "title", "topic", "event", "faq", "rule", "report"))}
          <h3>管理</h3>
          {command_list(("admin", "server_log", "ticket", "role_panel", "youtube", "attendance", "birthday", "welcome", "ng_word", "backup"))}
        </section>
      </main>
      <footer>むらびと君 / VillageCore Help</footer>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


def dashboard_auth_ok(request: web.Request) -> bool:
    return bool(DASHBOARD_TOKEN and request.query.get("token") == DASHBOARD_TOKEN)


async def handle_dashboard(request: web.Request):
    if not DASHBOARD_TOKEN:
        return web.Response(
            text=(
                "<h1>むらびと君ダッシュボード</h1>"
                "<p>ダッシュボードは無効です。<code>DASHBOARD_TOKEN</code> を設定してください。</p>"
            ),
            content_type="text/html",
        )

    if not dashboard_auth_ok(request):
        return web.Response(status=401, text="認証できませんでした。")

    try:
        config = await db_get_all_config()
        db_status = "OK"
    except Exception as e:
        config = {}
        db_status = f"NG: {type(e).__name__}"

    guild_records = {
        key.removeprefix("bot_guild:"): value
        for key, value in config.items()
        if key.startswith("bot_guild:")
    }
    command_count = len([c for c in bot.tree.walk_commands() if c.parent is None])
    sorted_guilds = sorted(bot.guilds, key=lambda item: item.name.casefold())
    total_members = sum(guild.member_count or 0 for guild in sorted_guilds)
    role_guilds = sorted(role_bot.guilds, key=lambda item: item.name.casefold())
    guild_rows = dashboard_guild_rows(sorted_guilds, guild_records)

    env_rows = dashboard_env_rows(
        ("DISCORD_TOKEN", "ROLE_GUESSER_TOKEN", "DATABASE_URL", "GEMINI_API_KEY", "YOUTUBE_API_KEY")
    )

    html = f"""
    <!doctype html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>むらびと君ダッシュボード</title>
      <style>
        body {{ font-family: system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #20242a; }}
        main {{ max-width: 1180px; margin: auto; padding: 28px; }}
        section {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; margin: 16px 0; }}
        h1, h2 {{ margin-top: 0; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
        .metric {{ background: #f9fafb; border: 1px solid #edf0f2; border-radius: 8px; padding: 12px; }}
        .metric strong {{ display: block; font-size: 1.7rem; }}
        .toolbar {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }}
        input[type="search"] {{ min-width: 260px; flex: 1; padding: 10px 12px; border: 1px solid #cfd6dd; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; border-bottom: 1px solid #edf0f2; padding: 10px 8px; vertical-align: middle; }}
        th {{ font-size: .86rem; color: #53606b; background: #fbfcfd; position: sticky; top: 0; }}
        small {{ display: block; color: #66727f; }}
        .ok {{ color: #16794c; font-weight: 700; }}
        .pill {{ border-radius: 999px; padding: 3px 8px; font-size: .82rem; font-weight: 700; white-space: nowrap; }}
        .pill.ok {{ color: #16794c; background: #eaf7f0; }}
        .pill.warn {{ color: #8a5a00; background: #fff4d8; }}
        .pill.bad, .pill.unknown {{ color: #9a2f22; background: #fdecea; }}
        .guild-cell {{ display: flex; align-items: center; gap: 10px; }}
        .guild-icon {{ width: 34px; height: 34px; border-radius: 8px; object-fit: cover; background: #e8edf2; display: inline-grid; place-items: center; color: #6b7785; font-weight: 800; }}
        .table-wrap {{ overflow-x: auto; max-height: 70vh; }}
      </style>
    </head>
    <body>
      <main>
        <h1>むらびと君ダッシュボード</h1>
        <section>
          <h2>状態</h2>
          <div class="summary">
            <div class="metric"><span>むらびと君</span><strong>{escape(str(bot.user)) if bot.user else "起動中"}</strong></div>
            <div class="metric"><span>導入サーバー数</span><strong>{len(sorted_guilds)}</strong></div>
            <div class="metric"><span>合計メンバー数</span><strong>{total_members}</strong></div>
            <div class="metric"><span>Slashコマンド数</span><strong>{command_count}</strong></div>
          </div>
          <p>データベース: {escape("PostgreSQL" if use_postgres() else "SQLite")} / {escape(db_status)}</p>
          <p>保存済み設定キー数: {len(config)}</p>
        </section>
        <section>
          <h2>Roles Guesser</h2>
          <div class="summary">
            <div class="metric"><span>BOT</span><strong>{escape(str(role_bot.user)) if role_bot.user else "未起動または起動中"}</strong></div>
            <div class="metric"><span>導入サーバー数</span><strong>{len(role_guilds)}</strong></div>
            <div class="metric"><span>Slashコマンド数</span><strong>{len([c for c in role_bot.tree.walk_commands() if c.parent is None])}</strong></div>
          </div>
          <p><a href="/roles-dashboard?token={escape(request.query.get('token', ''))}">Roles Guesser専用ダッシュボードを開く</a></p>
        </section>
        <section>
          <h2>環境変数</h2>
          <table><tbody>{env_rows}</tbody></table>
        </section>
        <section>
          <h2>むらびと君の導入サーバー</h2>
          <div class="toolbar">
            <input id="guildSearch" type="search" placeholder="サーバー名 / ID / オーナーで検索">
            <span id="guildCount">{len(sorted_guilds)} 件</span>
          </div>
          <div class="table-wrap">
          <table id="guildTable">
            <thead>
              <tr>
                <th>サーバー</th>
                <th>人数</th>
                <th>オーナー</th>
                <th>初回確認</th>
                <th>最終確認</th>
                <th>BOT権限</th>
                <th>招待作成</th>
              </tr>
            </thead>
            <tbody>{''.join(guild_rows) or "<tr><td colspan='7'>導入中のサーバーはありません</td></tr>"}</tbody>
          </table>
          </div>
        </section>
        <script>
          const input = document.getElementById('guildSearch');
          const rows = Array.from(document.querySelectorAll('#guildTable tbody tr'));
          const count = document.getElementById('guildCount');
          input?.addEventListener('input', () => {{
            const q = input.value.trim().toLowerCase();
            let visible = 0;
            for (const row of rows) {{
              const ok = !q || (row.dataset.search || '').includes(q);
              row.style.display = ok ? '' : 'none';
              if (ok) visible += 1;
            }}
            count.textContent = `${{visible}} 件`;
          }});
        </script>
      </main>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def handle_roles_dashboard(request: web.Request):
    if not DASHBOARD_TOKEN:
        return web.Response(
            text=(
                "<h1>Roles Guesserダッシュボード</h1>"
                "<p>ダッシュボードは無効です。<code>DASHBOARD_TOKEN</code> を設定してください。</p>"
            ),
            content_type="text/html",
        )

    if not dashboard_auth_ok(request):
        return web.Response(status=401, text="認証できませんでした。")

    try:
        config = await db_get_all_config()
        db_status = "OK"
    except Exception as e:
        config = {}
        db_status = f"NG: {type(e).__name__}"

    sorted_guilds = sorted(role_bot.guilds, key=lambda item: item.name.casefold())
    total_members = sum(guild.member_count or 0 for guild in sorted_guilds)
    command_count = len([c for c in role_bot.tree.walk_commands() if c.parent is None])
    guild_rows = dashboard_guild_rows(sorted_guilds)
    env_rows = dashboard_env_rows(("ROLE_GUESSER_TOKEN", "GUILD_ID", "DASHBOARD_TOKEN"))

    html = f"""
    <!doctype html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Roles Guesserダッシュボード</title>
      <style>
        body {{ font-family: system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #20242a; }}
        main {{ max-width: 1180px; margin: auto; padding: 28px; }}
        section {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; margin: 16px 0; }}
        h1, h2 {{ margin-top: 0; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
        .metric {{ background: #f9fafb; border: 1px solid #edf0f2; border-radius: 8px; padding: 12px; }}
        .metric strong {{ display: block; font-size: 1.7rem; }}
        .toolbar {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }}
        input[type="search"] {{ min-width: 260px; flex: 1; padding: 10px 12px; border: 1px solid #cfd6dd; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; border-bottom: 1px solid #edf0f2; padding: 10px 8px; vertical-align: middle; }}
        th {{ font-size: .86rem; color: #53606b; background: #fbfcfd; position: sticky; top: 0; }}
        small {{ display: block; color: #66727f; }}
        .pill {{ border-radius: 999px; padding: 3px 8px; font-size: .82rem; font-weight: 700; white-space: nowrap; }}
        .pill.ok {{ color: #16794c; background: #eaf7f0; }}
        .pill.warn {{ color: #8a5a00; background: #fff4d8; }}
        .pill.bad, .pill.unknown {{ color: #9a2f22; background: #fdecea; }}
        .guild-cell {{ display: flex; align-items: center; gap: 10px; }}
        .guild-icon {{ width: 34px; height: 34px; border-radius: 8px; object-fit: cover; background: #e8edf2; display: inline-grid; place-items: center; color: #6b7785; font-weight: 800; }}
        .table-wrap {{ overflow-x: auto; max-height: 70vh; }}
      </style>
    </head>
    <body>
      <main>
        <h1>Roles Guesserダッシュボード</h1>
        <section>
          <h2>状態</h2>
          <div class="summary">
            <div class="metric"><span>BOT</span><strong>{escape(str(role_bot.user)) if role_bot.user else "未起動または起動中"}</strong></div>
            <div class="metric"><span>導入サーバー数</span><strong>{len(sorted_guilds)}</strong></div>
            <div class="metric"><span>合計メンバー数</span><strong>{total_members}</strong></div>
            <div class="metric"><span>Slashコマンド数</span><strong>{command_count}</strong></div>
          </div>
          <p>データベース: {escape("PostgreSQL" if use_postgres() else "SQLite")} / {escape(db_status)}</p>
          <p>保存済み設定キー数: {len(config)}</p>
          <p><a href="/dashboard?token={escape(request.query.get('token', ''))}">むらびと君ダッシュボードへ戻る</a></p>
        </section>
        <section>
          <h2>環境変数</h2>
          <table><tbody>{env_rows}</tbody></table>
        </section>
        <section>
          <h2>Roles Guesserの導入サーバー</h2>
          <div class="toolbar">
            <input id="guildSearch" type="search" placeholder="サーバー名 / ID / オーナーで検索">
            <span id="guildCount">{len(sorted_guilds)} 件</span>
          </div>
          <div class="table-wrap">
          <table id="guildTable">
            <thead>
              <tr>
                <th>サーバー</th>
                <th>人数</th>
                <th>オーナー</th>
                <th>初回確認</th>
                <th>最終確認</th>
                <th>BOT権限</th>
                <th>招待作成</th>
              </tr>
            </thead>
            <tbody>{''.join(guild_rows) or "<tr><td colspan='7'>導入中のサーバーはありません</td></tr>"}</tbody>
          </table>
          </div>
        </section>
        <script>
          const input = document.getElementById('guildSearch');
          const rows = Array.from(document.querySelectorAll('#guildTable tbody tr'));
          const count = document.getElementById('guildCount');
          input?.addEventListener('input', () => {{
            const q = input.value.trim().toLowerCase();
            let visible = 0;
            for (const row of rows) {{
              const ok = !q || (row.dataset.search || '').includes(q);
              row.style.display = ok ? '' : 'none';
              if (ok) visible += 1;
            }}
            count.textContent = `${{visible}} 件`;
          }});
        </script>
      </main>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/help", handle_help_site)
    app.router.add_get("/dashboard", handle_dashboard)
    app.router.add_get("/roles-dashboard", handle_roles_dashboard)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"🌐 Health server running on port {PORT}", flush=True)


# ==========================
# エントリポイント
# ==========================
async def main():
    print("🚀 Starting bot process", flush=True)
    print(f"🔑 DISCORD_TOKEN set: {TOKEN is not None}", flush=True)
    print(f"🌐 PORT={PORT}", flush=True)
    print(f"🛡️ GUILD_ID={GUILD_ID or '(global sync)'}", flush=True)

    if TOKEN is None:
        print("❌ DISCORD_TOKEN が設定されていません", flush=True)
        return

    await db_init()
    await load_cogs()

    asyncio.create_task(start_role_guesser_bot())

    print(f"🌐 Starting health server on port {PORT}", flush=True)
    asyncio.create_task(start_health_server())

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {type(e).__name__}: {e}", flush=True)
        raise


asyncio.run(main())
