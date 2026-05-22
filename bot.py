import os
import sys
import discord
from discord.ext import commands
import asyncio
from html import escape
from aiohttp import web

from bot_instance import bot
from database.config_db import db_get_all_config, db_init, use_postgres

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
        "Features.daifugo",
        "Features.dice",
        "Features.google_search",
        "Features.omikuji",
        "Features.othello",
        "Features.poker",
        "Features.role_panel",
        "Features.sevens",
        "Features.ticket",
        "Features.uno",
        "Features.youtube_notify",
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"  ✅ loaded: {cog}")
        except Exception as e:
            print(f"  ⚠️  skipped: {cog} → {e}")


# ==========================
# 永続 View の登録
# ==========================
def register_persistent_views():
    from views.ticket_views import ClosedTicketView, TicketButtonView, TicketControlView
    from views.role_panel_views import LegacyRolePanelView, RolePanelView
    # ★ AttendanceView は attendance.py に統合したため削除
    bot.add_view(TicketButtonView(bot))
    bot.add_view(TicketControlView())
    bot.add_view(ClosedTicketView())
    bot.add_view(RolePanelView())
    bot.add_view(LegacyRolePanelView())


async def clear_global_commands():
    try:
        print("🔄 Clearing global slash commands so only guild commands remain...", flush=True)
        bot.tree.clear_commands(guild=None)
        cleared_global = await bot.tree.sync(guild=None)
        print(f"🔄 Global slash commands after cleanup: {len(cleared_global)}", flush=True)
    except Exception as e:
        print(f"⚠️ Global slash command cleanup failed: {type(e).__name__}: {e}", flush=True)


async def clear_legacy_guild_commands():
    if not LEGACY_GUILD_ID:
        return
    try:
        guild = discord.Object(id=int(LEGACY_GUILD_ID))
        print(f"🔄 Clearing legacy guild slash commands: {LEGACY_GUILD_ID}", flush=True)
        bot.tree.clear_commands(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"🔄 Legacy guild slash commands after cleanup: {len(synced)}", flush=True)
    except Exception as e:
        print(f"⚠️ Legacy guild command cleanup failed: {type(e).__name__}: {e}", flush=True)


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

    if COMMANDS_SYNCED:
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        return

    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        # Keep slash commands guild-scoped so Discord does not show global + guild duplicates.
        bot.tree.clear_commands(guild=guild)
        print("🔄 Copying slash commands to target guild...", flush=True)
        bot.tree.copy_global_to(guild=guild)

        print("🔄 Syncing current guild slash commands...", flush=True)
        synced = await bot.tree.sync(guild=guild)
        asyncio.create_task(clear_global_commands())
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(synced)} slash commands to guild {GUILD_ID}", flush=True)
    else:
        synced = await bot.tree.sync()
        asyncio.create_task(clear_legacy_guild_commands())
        COMMANDS_SYNCED = True
        print(f"✅ Bot ready: {bot.user} ({bot.user.id})", flush=True)
        print(f"🔄 Synced {len(synced)} global slash commands", flush=True)


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
          line-height: 1.7;
        }}
        header {{
          background: #274f39;
          color: #fff;
          padding: 28px 18px 22px;
          border-bottom: 5px solid #d99345;
        }}
        .wrap {{ max-width: 1080px; margin: 0 auto; }}
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
        main {{ padding: 20px 18px 42px; }}
        section {{
          margin: 18px 0;
          padding: 18px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
        }}
        h2 {{ margin: 0 0 10px; font-size: 1.35rem; }}
        h3 {{ margin: 16px 0 8px; font-size: 1.05rem; }}
        .grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 12px;
        }}
        .tile {{
          padding: 14px;
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
          padding: 12px 14px;
          border-radius: 6px;
        }}
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
          <a href="#daily">日常</a>
          <a href="#games">ゲーム</a>
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
        <section id="daily">
          <h2>日常で使う機能</h2>
          <div class="grid">
            <div class="tile"><strong>AI応答</strong>Botにメンション、またはBotの返信にリプライするとAIが答えます。</div>
            <div class="tile"><strong>音楽</strong><code>/play</code> でYouTube音楽をVC再生できます。</div>
            <div class="tile"><strong>プロフィール</strong><code>/profile_set</code> と <code>/profile</code> で自己紹介を管理できます。</div>
            <div class="tile"><strong>コイン/称号</strong><code>/coin_daily</code> で毎日コイン、称号はプロフィールに表示されます。</div>
          </div>
        </section>
        <section id="games">
          <h2>ゲーム</h2>
          <p>UNO、7並べ、大富豪、ポーカー、オセロ、じゃんけん、おみくじ、ダイスに対応しています。</p>
          <div class="grid">
            <div class="tile"><strong>UNO</strong><code>/uno_start</code> で作成、参加者は <code>/uno_join</code>、準備できたら <code>/uno_begin</code> で開始します。</div>
            <div class="tile"><strong>7並べ</strong><code>/sevens_start</code>、<code>/sevens_join</code>、<code>/sevens_begin</code> の順で進めます。手札はDM画像で届きます。</div>
            <div class="tile"><strong>大富豪</strong><code>/daifugo_start</code> でルールを選び、<code>/daifugo_begin</code> で開始します。革命や8切りも設定できます。</div>
            <div class="tile"><strong>ポーカー</strong><code>/poker_start</code> で募集、<code>/poker_begin</code> 後にDM手札を見て交換します。</div>
            <div class="tile"><strong>募集</strong><code>/event_create</code> で参加/未定/不参加ボタン付き募集を作れます。中止は <code>/event_cancel</code> です。</div>
            <div class="tile"><strong>すぐ遊ぶ</strong><code>/quick</code> からゲーム作成、おみくじ、1d100、じゃんけんを実行できます。</div>
          </div>
          <div class="notice">
            <p><strong>ゲーム募集の中止</strong><br>
              UNO、7並べ、大富豪、ポーカーの募集は <code>/game_cancel</code> で中止できます。
              募集作成者または管理者が実行できます。開始済みのゲームを終了する場合は管理者権限が必要です。
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
              先に手札をなくした人が上がりです。革命、8切り、階段、しばり、都落ちは <code>/daifugo_start</code> のオプションで切り替えできます。
            </p>
            <p><strong>ポーカーのルール</strong><br>
              5枚の手札がDMで届きます。交換したいカードを選び、全員の交換が終わると役の強さで勝敗が決まります。
              強い順は、ストレートフラッシュ、フォーカード、フルハウス、フラッシュ、ストレート、スリーカード、ツーペア、ワンペア、ハイカードです。
            </p>
          </div>
          {command_list(("uno", "sevens", "daifugo", "poker", "game", "othello", "janken", "omikuji", "dice"))}
        </section>
        <section id="admin">
          <h2>管理者向け</h2>
          <div class="grid">
            <div class="tile"><strong>初期設定</strong><code>/setup_wizard</code> で導入時に必要な設定を確認できます。</div>
            <div class="tile"><strong>チケット</strong><code>/ticket_setup</code> と <code>/ticket_log_channel</code> を設定します。</div>
            <div class="tile"><strong>役職パネル</strong><code>/role_panel_setup</code> で複数ロール対応のパネルを作れます。</div>
            <div class="tile"><strong>YouTube通知</strong><code>/youtube_notify_channel</code> と <code>/youtube_notify_keywords</code> を設定します。</div>
            <div class="tile"><strong>ログ</strong><code>/server_log_channel</code>、<code>/error_log_channel</code>、<code>/command_log_channel</code> を設定できます。</div>
            <div class="tile"><strong>メンテナンス</strong><code>/maintenance_on</code> で一時的に一般利用を止められます。</div>
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
          {command_list(("quick", "play", "profile", "coin", "title", "topic", "event", "faq", "rule", "report"))}
          <h3>管理</h3>
          {command_list(("settings", "setup", "permission", "maintenance", "data_cleanup", "server_log", "error_log", "command_log", "ticket", "role_panel", "youtube_notify", "birthday", "welcome", "ng_word", "backup"))}
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
                "<h1>VillageCore ダッシュボード</h1>"
                "<p>ダッシュボードは無効です。<code>DASHBOARD_TOKEN</code> を設定してください。</p>"
            ),
            content_type="text/html",
        )

    if not dashboard_auth_ok(request):
        return web.Response(status=401, text="認証に失敗しました")

    try:
        config = await db_get_all_config()
        db_status = "OK"
    except Exception as e:
        config = {}
        db_status = f"NG: {type(e).__name__}"

    command_count = len([c for c in bot.tree.walk_commands() if c.parent is None])
    guild_rows = "".join(
        f"<tr><td>{escape(guild.name)}</td><td>{guild.id}</td><td>{guild.member_count or '-'}</td></tr>"
        for guild in bot.guilds
    )
    env_rows = "".join(
        f"<tr><td>{name}</td><td>{'設定済み' if os.getenv(name) else '未設定'}</td></tr>"
        for name in ("DISCORD_TOKEN", "DATABASE_URL", "GEMINI_API_KEY", "YOUTUBE_API_KEY")
    )

    html = f"""
    <!doctype html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>VillageCore ダッシュボード</title>
      <style>
        body {{ font-family: system-ui, sans-serif; margin: 32px; background: #f6f7f9; color: #20242a; }}
        main {{ max-width: 960px; margin: auto; }}
        section {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; margin: 16px 0; }}
        h1, h2 {{ margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; border-bottom: 1px solid #edf0f2; padding: 8px; }}
        .ok {{ color: #16794c; font-weight: 700; }}
      </style>
    </head>
    <body>
      <main>
        <h1>VillageCore ダッシュボード</h1>
        <section>
          <h2>状態</h2>
          <p>Bot: <span class="ok">{escape(str(bot.user)) if bot.user else "起動中"}</span></p>
          <p>データベース: {escape("PostgreSQL" if use_postgres() else "SQLite")} / {escape(db_status)}</p>
          <p>参加サーバー数: {len(bot.guilds)}</p>
          <p>スラッシュコマンド数: {command_count}</p>
          <p>保存済み設定キー数: {len(config)}</p>
        </section>
        <section>
          <h2>環境変数</h2>
          <table><tbody>{env_rows}</tbody></table>
        </section>
        <section>
          <h2>参加サーバー</h2>
          <table>
            <thead><tr><th>サーバー名</th><th>ID</th><th>メンバー数</th></tr></thead>
            <tbody>{guild_rows or "<tr><td colspan='3'>参加サーバーがありません</td></tr>"}</tbody>
          </table>
        </section>
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

    print(f"🌐 Starting health server on port {PORT}", flush=True)
    asyncio.create_task(start_health_server())

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {type(e).__name__}: {e}", flush=True)
        raise


asyncio.run(main())
