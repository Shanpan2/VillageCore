import json

import discord

from database.config_db import db_get


ROLE_PANEL_KEY_PREFIX = "role_panel:"
ROLE_PANEL_SELECT_ID = "role_panel_select"
LEGACY_ROLE_PANEL_BUTTON_ID = "role_toggle"


def role_panel_key(message_id: int) -> str:
    return f"{ROLE_PANEL_KEY_PREFIX}{message_id}"


def panel_roles_from_data(data: dict) -> tuple[list[int], dict[int, str]]:
    role_ids = [int(role_id) for role_id in data.get("role_ids", [])]
    raw_names = data.get("role_names", {})
    role_names = {int(role_id): name for role_id, name in raw_names.items()}
    return role_ids, role_names


async def get_fresh_member(interaction: discord.Interaction) -> discord.Member | None:
    if not interaction.guild:
        return None
    try:
        return await interaction.guild.fetch_member(interaction.user.id)
    except discord.HTTPException:
        member = interaction.guild.get_member(interaction.user.id)
        return member if isinstance(member, discord.Member) else None


async def reset_role_panel_message(interaction: discord.Interaction, role_ids: list[int], role_names: dict[int, str]):
    if interaction.message:
        try:
            await interaction.message.edit(view=RolePanelView(role_ids, role_names))
        except discord.HTTPException as e:
            print(f"[RolePanel] message reset failed: {type(e).__name__}: {e}", flush=True)


async def toggle_roles(interaction: discord.Interaction, selected_role_ids: list[int]) -> str:
    if not interaction.guild:
        return "サーバー内で実行してください。"

    member = await get_fresh_member(interaction)
    if member is None:
        return "メンバー情報を取得できませんでした。"

    bot_member = interaction.guild.me
    added = []
    removed = []
    failed = []

    for role_id in selected_role_ids:
        role = interaction.guild.get_role(role_id)
        if role is None:
            failed.append(f"不明なロール({role_id})")
            continue

        if bot_member and role >= bot_member.top_role:
            failed.append(f"{role.name}(Botのロール位置が低い)")
            continue

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Role panel toggle")
                removed.append(role.name)
            else:
                await member.add_roles(role, reason="Role panel toggle")
                added.append(role.name)
        except discord.Forbidden:
            failed.append(f"{role.name}(権限不足)")
        except discord.HTTPException:
            failed.append(f"{role.name}(処理失敗)")

    lines = []
    if added:
        lines.append("付与: " + ", ".join(added))
    if removed:
        lines.append("解除: " + ", ".join(removed))
    if failed:
        lines.append("失敗: " + ", ".join(failed))

    return "\n".join(lines) or "変更はありませんでした。"


class RolePanelSelect(discord.ui.Select):
    def __init__(self, role_ids: list[int] | None = None, role_names: dict[int, str] | None = None):
        role_ids = role_ids or [0]
        role_names = role_names or {}
        options = [
            discord.SelectOption(
                label=role_names.get(role_id, f"Role {role_id}")[:100],
                value=str(role_id),
            )
            for role_id in role_ids[:25]
        ]
        super().__init__(
            placeholder="付け外ししたいロールを選んでください",
            min_values=1,
            max_values=max(1, len(options)),
            options=options,
            custom_id=ROLE_PANEL_SELECT_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        raw = await db_get(role_panel_key(interaction.message.id))
        if not raw:
            await interaction.response.send_message(
                "この役職パネルの設定が見つかりません。管理者に再設置または変換してもらってください。",
                ephemeral=True,
            )
            return

        data = json.loads(raw)
        role_ids, role_names = panel_roles_from_data(data)
        allowed_role_ids = set(role_ids)
        selected_role_ids = [int(value) for value in self.values if int(value) in allowed_role_ids]
        if not selected_role_ids:
            await interaction.response.send_message("有効なロールが選択されていません。", ephemeral=True)
            await reset_role_panel_message(interaction, role_ids, role_names)
            return

        result = await toggle_roles(interaction, selected_role_ids)
        await interaction.response.send_message(result, ephemeral=True)
        await reset_role_panel_message(interaction, role_ids, role_names)


class RolePanelView(discord.ui.View):
    def __init__(self, role_ids: list[int] | None = None, role_names: dict[int, str] | None = None):
        super().__init__(timeout=None)
        self.add_item(RolePanelSelect(role_ids, role_names))


class LegacyRolePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(LegacyRoleToggleButton())


class LegacyRoleToggleButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ロール付与 / 解除",
            style=discord.ButtonStyle.primary,
            custom_id=LEGACY_ROLE_PANEL_BUTTON_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        raw = await db_get(role_panel_key(interaction.message.id))
        if not raw:
            await interaction.response.send_message(
                "この古い役職パネルはロール情報を復元できていません。"
                "管理者に `/role_panel_migrate` で変換してもらってください。",
                ephemeral=True,
            )
            return

        data = json.loads(raw)
        role_ids, role_names = panel_roles_from_data(data)
        if len(role_ids) != 1:
            await interaction.response.send_message(
                "このパネルは複数ロール設定です。新しい選択メニューからロールを選んでください。",
                ephemeral=True,
            )
            await reset_role_panel_message(interaction, role_ids, role_names)
            return

        result = await toggle_roles(interaction, role_ids)
        await interaction.response.send_message(result, ephemeral=True)
