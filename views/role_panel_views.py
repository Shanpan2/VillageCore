import json

import discord

from database.config_db import db_get


ROLE_PANEL_KEY_PREFIX = "role_panel:"
ROLE_PANEL_SELECT_ID = "role_panel_select"


def role_panel_key(message_id: int) -> str:
    return f"{ROLE_PANEL_KEY_PREFIX}{message_id}"


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
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        raw = await db_get(role_panel_key(interaction.message.id))
        if not raw:
            await interaction.response.send_message(
                "この役職パネルの設定が見つかりません。管理者に再設置してもらってください。",
                ephemeral=True,
            )
            return

        data = json.loads(raw)
        allowed_role_ids = {int(role_id) for role_id in data.get("role_ids", [])}
        selected_role_ids = [int(value) for value in self.values if int(value) in allowed_role_ids]
        if not selected_role_ids:
            await interaction.response.send_message("有効なロールが選択されていません。", ephemeral=True)
            return

        added = []
        removed = []
        failed = []

        for role_id in selected_role_ids:
            role = interaction.guild.get_role(role_id)
            if role is None:
                failed.append(f"不明なロール({role_id})")
                continue

            try:
                if role in interaction.user.roles:
                    await interaction.user.remove_roles(role, reason="Role panel toggle")
                    removed.append(role.name)
                else:
                    await interaction.user.add_roles(role, reason="Role panel toggle")
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

        await interaction.response.send_message("\n".join(lines) or "変更はありませんでした。", ephemeral=True)


class RolePanelView(discord.ui.View):
    def __init__(self, role_ids: list[int] | None = None, role_names: dict[int, str] | None = None):
        super().__init__(timeout=None)
        self.add_item(RolePanelSelect(role_ids, role_names))
