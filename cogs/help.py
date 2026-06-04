import discord
from discord import app_commands
from discord.ext import commands


CATEGORIES = {
    "music": {
        "label": "音楽",
        "emoji": "🎵",
        "prefixes": ("music",),
    },
    "admin": {
        "label": "管理",
        "emoji": "🛠️",
        "prefixes": (
            "admin",
            "bot_status",
            "backup",
            "birthday",
            "clean",
            "archive",
            "command_log",
            "data_cleanup",
            "error_log",
            "maintenance",
            "ng_word",
            "permission_check",
            "permission_audit",
            "report_channel",
            "role_panel",
            "rule_set",
            "server_log",
            "settings_status",
            "setup_guide",
            "setup_wizard",
            "topic_channel",
            "ticket",
            "welcome",
            "youtube",
            "youtube_notify",
        ),
    },
    "attendance": {
        "label": "出席管理",
        "emoji": "📋",
        "prefixes": ("attendance", "attend"),
    },
    "games": {
        "label": "ゲーム",
        "emoji": "🎮",
        "prefixes": ("game", "janken", "dice", "omikuji", "othello", "uno", "sevens", "daifugo", "poker", "werewolf", "ito", "codenames"),
    },
    "utility": {
        "label": "便利機能",
        "emoji": "📌",
        "prefixes": ("coin", "event", "faq", "google_search", "penalty", "profile", "quick", "reminder", "report", "rule", "title", "topic", "vote"),
    },
    "ai": {
        "label": "AI",
        "emoji": "🤖",
        "prefixes": ("ai",),
    },
}


def command_category(command: app_commands.Command) -> str:
    for category, data in CATEGORIES.items():
        if command.name.startswith(data["prefixes"]):
            return category
    return "utility"


def build_category_embed(bot: commands.Bot, category: str) -> discord.Embed:
    data = CATEGORIES[category]
    if category == "games":
        embed = discord.Embed(
            title="🎮 ゲーム",
            description=(
                "ゲームは **`/game`** から遊ぶのがおすすめです。\n"
                "ゲームを選ぶと、募集作成・参加・抜ける・開始・中止・ルール確認をボタンで操作できます。\n\n"
                "**対応ゲーム**\n"
                "UNO / 7並べ / 大富豪 / ポーカー / オセロ / 詰将棋\n\n"
                "**オセロ**\n"
                "`/game` からオセロを選ぶと、対人戦またはAI対戦の難易度を選べます。\n\n"
                "**詰将棋**\n"
                "`/game` から詰将棋を選ぶと、初級/中級/上級の問題に挑戦できます。"
                "正解するとコイン報酬があります。\n\n"
                "**すぐ遊ぶ**\n"
                "`/quick` からゲーム作成、おみくじ、1d100、じゃんけんをすぐ実行できます。\n\n"
                "**補助コマンド**\n"
                "`/game_cancel` は募集を中止する予備コマンドです。\n"
                "個別のゲーム開始コマンドは、パネルが使えない時の予備として残しています。"
            ),
            color=0x00BFFF,
        )
        embed.set_footer(text="普段は /game と /quick を使えば大丈夫です。")
        return embed

    commands_list = sorted(
        [
            command
            for command in bot.tree.walk_commands()
            if command.parent is None and command_category(command) == category
        ],
        key=lambda command: command.name,
    )

    embed = discord.Embed(
        title=f"{data['emoji']} {data['label']}コマンド",
        color=0x00BFFF,
    )

    if not commands_list:
        embed.description = "このカテゴリのコマンドはありません。"
        return embed

    lines = []
    for command in commands_list:
        description = command.description or "説明なし"
        lines.append(f"`/{command.name}`\n{description}")
    embed.description = "\n\n".join(lines)[:4000]
    embed.set_footer(text="メニューからカテゴリを切り替えられます。")
    return embed


def build_overview_embed(bot: commands.Bot) -> discord.Embed:
    counts = {category: 0 for category in CATEGORIES}
    for command in bot.tree.walk_commands():
        if command.parent is None:
            counts[command_category(command)] += 1

    embed = discord.Embed(
        title="📘 コマンドヘルプ",
        description="カテゴリを選ぶと、その種類のコマンドだけ表示します。よく使う機能はパネル系コマンドにまとめています。",
        color=0x00BFFF,
    )
    for category, data in CATEGORIES.items():
        embed.add_field(
            name=f"{data['emoji']} {data['label']}",
            value=f"{counts[category]}件",
            inline=True,
        )
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label=data["label"],
                value=category,
                emoji=data["emoji"],
            )
            for category, data in CATEGORIES.items()
        ]
        super().__init__(
            placeholder="表示するカテゴリを選んでください",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_category_embed(self.bot, self.values[0]),
            view=HelpView(self.bot),
        )


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.add_item(HelpCategorySelect(bot))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="コマンドをカテゴリ別に表示します")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_overview_embed(self.bot),
            view=HelpView(self.bot),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
