import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="addadmin")
    async def addadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id not in data["admins"]:
            data["admins"].append(target.id)
            save_data(data)
            await interaction.response.send_message(MESSAGES["sys_add_admin"].format(target=target.mention), ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["sys_already_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removeadmin")
    async def removeadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id in data["admins"]:
            data["admins"].remove(target.id)
            save_data(data)
            await interaction.response.send_message(MESSAGES["sys_remove_admin"].format(target=target.mention), ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["sys_not_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="addsupportadmin")
    async def addsupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id not in data["supports"]:
            data["supports"].append(target.id)
            save_data(data)
            await interaction.response.send_message(MESSAGES["sys_add_support"].format(target=target.mention), ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["sys_already_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removesupportadmin")
    async def removesupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id in data["supports"]:
            data["supports"].remove(target.id)
            save_data(data)
            await interaction.response.send_message(MESSAGES["sys_remove_support"].format(target=target.mention), ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["sys_not_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="lockdown")
    async def lockdown_cmd(self, interaction: discord.Interaction, seconds: int):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        data["lockdown_time"] = seconds
        save_data(data)
        await interaction.response.send_message(MESSAGES["sys_lockdown_set"].format(seconds=seconds), ephemeral=True)

    @app_commands.command(name="resetdata")
    async def resetdata(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        data["auction_count"] = 0
        data["ticket_count"] = 0
        save_data(data)
        await interaction.response.send_message(MESSAGES["sys_reset_done"], ephemeral=True)

    @app_commands.command(name="addpoint")
    async def addpoint(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        str_id = str(user.id)
        current = data["points"].get(str_id, 0)
        data["points"][str_id] = current + amount
        save_data(data)
        await interaction.response.send_message(f"{MESSAGES['pt_add_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=data['points'][str_id])})", ephemeral=True)

    @app_commands.command(name="removepoint")
    async def removepoint(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        str_id = str(user.id)
        current = data["points"].get(str_id, 0)
        new_bal = max(0, current - amount)
        data["points"][str_id] = new_bal
        save_data(data)
        await interaction.response.send_message(f"{MESSAGES['pt_remove_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=new_bal)})", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
