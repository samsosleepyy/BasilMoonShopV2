import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin, init_guild_data

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="anti-raid", description=MESSAGES["desc_antiraid"])
    @app_commands.describe(status="เปิด (True) หรือ ปิด (False) ระบบป้องกัน", log_channel="ช่องสำหรับแจ้งเตือน")
    async def antiraid(self, interaction: discord.Interaction, status: bool, log_channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): 
            return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        
        data["guilds"][str(interaction.guild_id)]["antiraid"] = {
            "status": status,
            "log_channel": log_channel.id
        }
        save_data(data)
        
        if status:
            msg = MESSAGES["ar_enabled"].format(channel=log_channel.mention)
        else:
            msg = MESSAGES["ar_disabled"]
            
        await interaction.followup.send(msg, ephemeral=True)

    # Anti-Raid Logic
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        guild = channel.guild
        data = load_data()
        guild_id = str(guild.id)
        
        if "guilds" not in data or guild_id not in data["guilds"]: return
        ar_config = data["guilds"][guild_id].get("antiraid", {"status": False})
        
        if not ar_config["status"]: return
        
        try:
            # Check audit log for webhook creation
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
                if (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds() > 10: return

                user = entry.user
                if user.bot: return 
                
                # Check if user is admin/support
                is_authorized = False
                if user.guild_permissions.administrator: is_authorized = True
                if user.id in data["admins"]: is_authorized = True
                for role in user.roles:
                    if role.id in data["admins"]: is_authorized = True
                
                log_chan_id = ar_config.get("log_channel")
                log_chan = guild.get_channel(log_chan_id) if log_chan_id else None

                if is_authorized:
                    # Authorized: Just Log (Safe)
                    if log_chan:
                        embed = discord.Embed(title=MESSAGES["ar_log_title_safe"], description=MESSAGES["ar_log_desc_safe"], color=discord.Color.green())
                        embed.add_field(name=MESSAGES["ar_field_user"], value=MESSAGES["ar_val_user"].format(mention=user.mention, id=user.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_webhook"], value=MESSAGES["ar_val_webhook"].format(name=entry.target.name, id=entry.target.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_action"], value=MESSAGES["ar_action_safe"], inline=False)
                        embed.timestamp = datetime.datetime.now()
                        await log_chan.send(embed=embed)

                else:
                    # Unauthorized: Delete & Ban & Alert
                    webhook = entry.target
                    try: await webhook.delete(reason="Anti-Raid: Unauthorized creation")
                    except: pass
                    
                    try:
                        await channel.set_permissions(user, manage_webhooks=False, reason="Anti-Raid: Blocked user")
                    except: pass
                    
                    if log_chan:
                        # Construct Pings
                        pings = []
                        for admin_id in data["admins"]:
                            # Try to resolve if role or user
                            if guild.get_role(admin_id): pings.append(f"<@&{admin_id}>")
                            else: pings.append(f"<@{admin_id}>")
                        
                        for sup_id in data["supports"]:
                            if guild.get_role(sup_id): pings.append(f"<@&{sup_id}>")
                            else: pings.append(f"<@{sup_id}>")
                            
                        ping_str = " ".join(pings) if pings else "@here"
                        
                        embed = discord.Embed(title=MESSAGES["ar_log_title"], description=MESSAGES["ar_log_desc"], color=discord.Color.red())
                        embed.add_field(name=MESSAGES["ar_field_user"], value=MESSAGES["ar_val_user"].format(mention=user.mention, id=user.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_webhook"], value=MESSAGES["ar_val_webhook"].format(name=webhook.name, id=webhook.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_action"], value=MESSAGES["ar_action_taken"], inline=False)
                        embed.timestamp = datetime.datetime.now()
                        
                        # Send with pings
                        await log_chan.send(content=MESSAGES["ar_ping_msg"].format(mentions=ping_str), embed=embed)
                    
                    return 
        except Exception as e:
            print(f"Anti-Raid Error: {e}")

    # ... (คำสั่งอื่นๆ คงเดิม) ...
    @app_commands.command(name="addadmin", description=MESSAGES["desc_addadmin"])
    async def addadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id not in data["admins"]:
            data["admins"].append(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_add_admin"].format(target=target.mention), ephemeral=True)
        else: await interaction.followup.send(MESSAGES["sys_already_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removeadmin", description=MESSAGES["desc_removeadmin"])
    async def removeadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id in data["admins"]:
            data["admins"].remove(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_remove_admin"].format(target=target.mention), ephemeral=True)
        else: await interaction.followup.send(MESSAGES["sys_not_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="addsupportadmin", description=MESSAGES["desc_addsupport"])
    async def addsupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id not in data["supports"]:
            data["supports"].append(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_add_support"].format(target=target.mention), ephemeral=True)
        else: await interaction.followup.send(MESSAGES["sys_already_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removesupportadmin", description=MESSAGES["desc_removesupport"])
    async def removesupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        if target.id in data["supports"]:
            data["supports"].remove(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_remove_support"].format(target=target.mention), ephemeral=True)
        else: await interaction.followup.send(MESSAGES["sys_not_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="lockdown", description=MESSAGES["desc_lockdown"])
    async def lockdown_cmd(self, interaction: discord.Interaction, seconds: int):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["lockdown_time"] = seconds
        save_data(data)
        await interaction.followup.send(MESSAGES["sys_lockdown_set"].format(seconds=seconds), ephemeral=True)

    @app_commands.command(name="resetdata", description=MESSAGES["desc_resetdata"])
    async def resetdata(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        
        guild_data = data["guilds"][str(interaction.guild_id)]
        guild_data["auction_count"] = 0
        guild_data["ticket_count"] = 0
        
        save_data(data)
        await interaction.followup.send(MESSAGES["sys_reset_done"], ephemeral=True)

    @app_commands.command(name="addpoint", description=MESSAGES["desc_addpoint"])
    async def addpoint(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not is_support_or_admin(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        str_id = str(user.id)
        current = data["points"].get(str_id, 0)
        data["points"][str_id] = current + amount
        save_data(data)
        await interaction.followup.send(f"{MESSAGES['pt_add_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=data['points'][str_id])})", ephemeral=True)

    @app_commands.command(name="removepoint", description=MESSAGES["desc_removepoint"])
    async def removepoint(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not is_support_or_admin(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        str_id = str(user.id)
        current = data["points"].get(str_id, 0)
        new_bal = max(0, current - amount)
        data["points"][str_id] = new_bal
        save_data(data)
        await interaction.followup.send(f"{MESSAGES['pt_remove_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=new_bal)})", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
