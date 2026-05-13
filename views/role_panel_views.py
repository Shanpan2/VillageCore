# views/role_panel_views.py

import discord

# ============================================================
# 🎛️ ロール付与ボタン（パネル側）
# ============================================================

class RolePanelView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="🎫 ロールを付与 / 削除", style=discord.ButtonStyle.primary, custom_id="role_toggle")
    async def toggle_role(self, inter: discord.Interaction, button: discord.ui.Button):

        role = inter.guild.get_role(self.role_id)
        if role is None:
            await inter.response.send_message("❌ ロールが見つかりません。", ephemeral=True)
            return

        if role in inter.user.roles:
            await inter.user.remove_roles(role)
            await inter.response.send_message(f"🗑️ {role.name} を削除しました。", ephemeral=True)
        else:
            await inter.user.add_roles(role)
            await inter.response.send_message(f"🎉 {role.name} を付与しました。", ephemeral=True)
