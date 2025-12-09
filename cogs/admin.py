import discord
from discord import app_commands
from discord.ext import commands, tasks
import sys
import os
import datetime
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin, init_guild_data, DATA_FILE

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # เริ่มการทำงานของ Auto Backup Loop
        self.autobackup_task.start()

    def cog_unload(self):
        # หยุด Loop เมื่อมีการปิดบอทหรือโหลดโค้ดใหม่
        self.autobackup_task.cancel()

    # =========================================
    # 🔄 AUTO BACKUP LOOP (ทุก 1 ชั่วโมง)
    # =========================================
    @tasks.loop(hours=1)
    async def autobackup_task(self):
        # รอให้บอทพร้อมก่อนทำงาน
        await self.bot.wait_until_ready()
        
        try:
            if not os.path.exists(DATA_FILE): return

            data = load_data()
            
            # วนลูปเช็คทุก Guild ใน Database
            if "guilds" in data:
                for guild_id_str, guild_data in data["guilds"].items():
                    # เช็คว่า Guild นี้ตั้งค่าช่อง Backup ไว้ไหม
                    channel_id = guild_data.get("autobackup_channel")
                    
                    if channel_id:
                        try:
                            # พยายามหาช่อง
                            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                            
                            if channel:
                                # [UPDATED] ดึงชื่อเซิฟเวอร์มาทำชื่อไฟล์
                                guild = self.bot.get_guild(int(guild_id_str))
                                guild_name = guild.name if guild else f"Guild-{guild_id_str}"
                                
                                # ล้างอักขระพิเศษออกจากชื่อไฟล์ (กัน Error)
                                safe_name = "".join([c for c in guild_name if c.isalnum() or c in " -_"]).strip()
                                if not safe_name: safe_name = "ServerData"
                                
                                # ตั้งชื่อไฟล์: ชื่อเซิฟ-data-วันเวลา.json
                                timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
                                filename = f"{safe_name}-data-{timestamp}.json"
                                
                                file = discord.File(DATA_FILE, filename=filename)
                                await channel.send(content=f"⏰ **Auto Backup** ({datetime.datetime.now().strftime('%H:%M')})", file=file)
                                print(f"Auto-backup sent to guild {guild_name} ({guild_id_str})")
                                
                        except Exception as e:
                            print(f"Failed to send backup to guild {guild_id_str}: {e}")
                            
        except Exception as e:
            print(f"Auto-backup loop error: {e}")

    # =========================================
    # COMMANDS
    # =========================================

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
        
        msg = MESSAGES["ar_enabled"].format(channel=log_channel.mention) if status else MESSAGES["ar_disabled"]
        await interaction.followup.send(msg, ephemeral=True)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        guild = channel.guild
        data = load_data()
        guild_id = str(guild.id)
        
        if "guilds" not in data or guild_id not in data["guilds"]: return
        ar_config = data["guilds"][guild_id].get("antiraid", {"status": False})
        
        if not ar_config["status"]: return
        
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
                if (datetime.datetime.now(datetime.timezone.utc) - entry.created_at).total_seconds() > 10: return

                user = entry.user
                if user.bot: return 
                
                is_authorized = False
                if user.guild_permissions.administrator: is_authorized = True
                if user.id in data["admins"]: is_authorized = True
                for role in user.roles:
                    if role.id in data["admins"]: is_authorized = True
                
                log_chan_id = ar_config.get("log_channel")
                log_chan = guild.get_channel(log_chan_id) if log_chan_id else None

                if is_authorized:
                    if log_chan:
                        embed = discord.Embed(title=MESSAGES["ar_log_title_safe"], description=MESSAGES["ar_log_desc_safe"], color=discord.Color.green())
                        embed.add_field(name=MESSAGES["ar_field_user"], value=MESSAGES["ar_val_user"].format(mention=user.mention, id=user.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_webhook"], value=MESSAGES["ar_val_webhook"].format(name=entry.target.name, id=entry.target.id), inline=True)
                        embed.add_field(name=MESSAGES["ar_field_action"], value=MESSAGES["ar_action_safe"], inline=False)
                        embed.timestamp = datetime.datetime.now()
                        await log_chan.send(embed=embed)
                else:
                    webhook = entry.target
                    try: await webhook.delete(reason="Anti-Raid: Unauthorized creation")
                    except: pass
                    try: await channel.set_permissions(user, manage_webhooks=False, reason="Anti-Raid: Blocked user")
                    except: pass
                    
                    if log_chan:
                        pings = []
                        for admin_id in data["admins"]:
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
                        await log_chan.send(content=MESSAGES["ar_ping_msg"].format(mentions=ping_str), embed=embed)
                    return 
        except Exception as e:
            print(f"Anti-Raid Error: {e}")

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

    # =========================================
    # 📥 ระบบ BACKUP & RESTORE
    # =========================================
    
    @app_commands.command(name="backup", description="สำรองข้อมูล data.json")
    @app_commands.describe(autobackup_log="[Optional] ช่องสำหรับส่ง Auto Backup ทุก 1 ชม.")
    async def backup(self, interaction: discord.Interaction, autobackup_log: discord.TextChannel = None):
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        if not os.path.exists(DATA_FILE):
            return await interaction.followup.send("❌ ไม่พบไฟล์ข้อมูล (Database ยังไม่ถูกสร้าง)", ephemeral=True)

        # เตรียมชื่อไฟล์: ชื่อเซิฟ-data-วันเวลา.json
        safe_name = "".join([c for c in interaction.guild.name if c.isalnum() or c in " -_"]).strip()
        if not safe_name: safe_name = "ServerData"
        timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
        filename = f"{safe_name}-data-{timestamp}.json"

        # กรณีเลือกช่อง Auto Backup (แยกตาม Guild)
        if autobackup_log:
            data = load_data()
            init_guild_data(data, interaction.guild_id)
            
            # บันทึกแยกเป็นราย Guild
            data["guilds"][str(interaction.guild_id)]["autobackup_channel"] = autobackup_log.id
            save_data(data)
            
            await interaction.followup.send(f"✅ **ตั้งค่า Auto Backup เรียบร้อย!**\nจะส่งไฟล์ Backup เข้าห้อง {autobackup_log.mention} ของเซิร์ฟเวอร์นี้ ทุก 1 ชั่วโมง\n(เริ่มส่งไฟล์แรกทันที...)", ephemeral=True)
            
            # ส่งไฟล์แรกทันที
            file = discord.File(DATA_FILE, filename=filename)
            await autobackup_log.send(f"📦 **Backup เริ่มต้น**", file=file)
        
        # กรณีไม่เลือกช่อง (Manual Download)
        else:
            file = discord.File(DATA_FILE, filename=filename)
            await interaction.followup.send("📦 **ไฟล์ Backup ข้อมูลปัจจุบัน**", file=file, ephemeral=True)

    @app_commands.command(name="restore", description="กู้คืนข้อมูลจากไฟล์ data.json")
    @app_commands.describe(file="ไฟล์ data.json ที่ต้องการกู้คืน")
    async def restore(self, interaction: discord.Interaction, file: discord.Attachment):
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        if not file.filename.endswith(".json"):
            return await interaction.response.send_message("❌ โปรดอัปโหลดไฟล์ .json เท่านั้น", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            await file.save(DATA_FILE)
            load_data() 
            await interaction.followup.send(f"✅ **กู้คืนข้อมูลสำเร็จ!**\nขนาดไฟล์: {file.size} bytes\nข้อมูลถูกบันทึกลงระบบแล้ว", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการกู้คืน: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
