import discord
from discord import app_commands
from discord.ext import commands, tasks
import sys
import os
import datetime
import asyncio
import io
import resource
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin, init_guild_data, DATA_FILE, is_owner, OWNER_IDS

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autobackup_task.start()

    def cog_unload(self):
        self.autobackup_task.cancel()

    # =========================================
    # 🔔 STARTUP NOTIFICATION
    # =========================================
    @commands.Cog.listener()
    async def on_ready(self):
        if hasattr(self.bot, "startup_notified") and self.bot.startup_notified:
            return
        
        self.bot.startup_notified = True
        print(f"✅ Bot is ready! Logged in as {self.bot.user}")

        # [REMOVED] DM to Owner to prevent Rate Limit
        # timestamp = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        # ram_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        # ... (DM logic removed) ...

    # =========================================
    # 🔄 AUTO BACKUP LOOP
    # =========================================
    @tasks.loop(hours=1)
    async def autobackup_task(self):
        await self.bot.wait_until_ready()
        try:
            if not os.path.exists(DATA_FILE): return
            data = load_data()
            
            if "guilds" in data:
                count_sent = 0
                for guild_id_str, guild_data in data["guilds"].items():
                    channel_id = guild_data.get("autobackup_channel")
                    if channel_id:
                        try:
                            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                            if channel:
                                ram_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                                file_size_kb = os.path.getsize(DATA_FILE) / 1024
                                
                                report_msg = (
                                    f"📦 **Auto Backup**\n"
                                    f"⏰ `{datetime.datetime.now().strftime('%H:%M:%S')}` | "
                                    f"🧠 RAM: `{ram_usage:.2f} MB` | "
                                    f"💾 Size: `{file_size_kb:.2f} KB`"
                                )
                                
                                guild = self.bot.get_guild(int(guild_id_str))
                                safe_name = "".join([c for c in guild.name if c.isalnum() or c in " -_"]).strip() if guild else "ServerData"
                                timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
                                filename = f"{safe_name}-backup-{timestamp}.json"
                                
                                file = discord.File(DATA_FILE, filename=filename)
                                await channel.send(content=report_msg, file=file)
                                count_sent += 1
                                await asyncio.sleep(2) 
                        except Exception as e:
                            print(f"Auto-backup fail for {guild_id_str}: {e}")
        except Exception as e:
            print(f"Auto-backup loop error: {e}")

    # =========================================
    # 👑 OWNER PANEL COMMAND
    # =========================================
    @app_commands.command(name="owner-panel", description="[Owner Only] แผงควบคุมบอทและการจัดการข้อมูล")
    async def owner_panel(self, interaction: discord.Interaction):
        if not is_owner(interaction):
            return await interaction.response.send_message(MESSAGES["owner_only"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=False)
        view = OwnerPanelView(self.bot, interaction.user.id)
        embed = view.get_status_embed()
        await interaction.followup.send(embed=embed, view=view)

    # =========================================
    # ⚙️ LOCAL ADMIN MANAGEMENT (UPDATED)
    # =========================================
    @app_commands.command(name="addadmin", description=MESSAGES["desc_addadmin"])
    async def addadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        guild_id = str(interaction.guild_id)
        
        if target.id not in data["guilds"][guild_id]["admins"]:
            data["guilds"][guild_id]["admins"].append(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_add_admin"].format(target=target.mention), ephemeral=True)
        else: 
            await interaction.followup.send(MESSAGES["sys_already_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removeadmin", description=MESSAGES["desc_removeadmin"])
    async def removeadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        guild_id = str(interaction.guild_id)
        
        if target.id in data["guilds"][guild_id]["admins"]:
            data["guilds"][guild_id]["admins"].remove(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_remove_admin"].format(target=target.mention), ephemeral=True)
        else: 
            await interaction.followup.send(MESSAGES["sys_not_admin"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="addsupportadmin", description=MESSAGES["desc_addsupport"])
    async def addsupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        guild_id = str(interaction.guild_id)
        
        if target.id not in data["guilds"][guild_id]["supports"]:
            data["guilds"][guild_id]["supports"].append(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_add_support"].format(target=target.mention), ephemeral=True)
        else: 
            await interaction.followup.send(MESSAGES["sys_already_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="removesupportadmin", description=MESSAGES["desc_removesupport"])
    async def removesupportadmin(self, interaction: discord.Interaction, target: discord.User | discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        guild_id = str(interaction.guild_id)
        
        if target.id in data["guilds"][guild_id]["supports"]:
            data["guilds"][guild_id]["supports"].remove(target.id)
            save_data(data)
            await interaction.followup.send(MESSAGES["sys_remove_support"].format(target=target.mention), ephemeral=True)
        else: 
            await interaction.followup.send(MESSAGES["sys_not_support"].format(target=target.mention), ephemeral=True)

    @app_commands.command(name="lockdown", description=MESSAGES["desc_lockdown"])
    async def lockdown_cmd(self, interaction: discord.Interaction, seconds: int):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["lockdown_time"] = seconds
        save_data(data)
        await interaction.followup.send(MESSAGES["sys_lockdown_set"].format(seconds=seconds), ephemeral=True)

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

    @app_commands.command(name="anti-raid", description=MESSAGES["desc_antiraid"])
    async def antiraid(self, interaction: discord.Interaction, status: bool, log_channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_has_permission(interaction): return await interaction.followup.send(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["antiraid"] = {"status": status, "log_channel": log_channel.id}
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
                
                # Check Local Admins
                local_admins = data["guilds"][guild_id].get("admins", [])
                if user.id in local_admins: is_authorized = True
                for role in user.roles:
                    if role.id in local_admins: is_authorized = True
                
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
                        for admin_id in local_admins:
                            if guild.get_role(admin_id): pings.append(f"<@&{admin_id}>")
                            else: pings.append(f"<@{admin_id}>")
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

# =========================================
# 🖥️ OWNER PANEL VIEW
# =========================================

class OwnerPanelView(discord.ui.View):
    def __init__(self, bot, owner_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id
        self.current_page = 0
        self.items_per_page = 5
        self.setup_main_menu()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("🔒 เฉพาะ Owner เท่านั้น", ephemeral=True)
            return False
        return True

    def setup_main_menu(self):
        self.clear_items()
        # Row 0
        b_info = discord.ui.Button(label="ℹ️ Info & Servers", style=discord.ButtonStyle.primary, row=0)
        b_info.callback = self.to_info_mode
        self.add_item(b_info)

        b_wl = discord.ui.Button(label="🛡️ Whitelist", style=discord.ButtonStyle.success, row=0)
        b_wl.callback = self.to_whitelist_mode
        self.add_item(b_wl)

        b_reset = discord.ui.Button(label="🗑️ Reset Data", style=discord.ButtonStyle.danger, row=0)
        b_reset.callback = self.to_reset_mode
        self.add_item(b_reset)

        # Row 1
        b_backup = discord.ui.Button(label="📦 Backup Data", style=discord.ButtonStyle.secondary, row=1)
        b_backup.callback = self.do_backup_logic
        self.add_item(b_backup)

        b_stop = discord.ui.Button(label="⛔ Stop Auto-Backup", style=discord.ButtonStyle.secondary, row=1)
        b_stop.callback = self.stop_autobackup
        self.add_item(b_stop)

        b_restore = discord.ui.Button(label="📥 Restore Data", style=discord.ButtonStyle.primary, row=1)
        b_restore.callback = self.do_restore_flow
        self.add_item(b_restore)

    # --- ACTION CALLBACKS ---
    async def to_info_mode(self, interaction: discord.Interaction):
        self.current_page = 0
        await self.update_info_view(interaction)

    async def to_whitelist_mode(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(ServerSelectMenu(self.bot, "whitelist"))
        b_cancel = discord.ui.Button(label="ยกเลิก", style=discord.ButtonStyle.danger, row=1)
        b_cancel.callback = self.return_to_main
        self.add_item(b_cancel)
        
        embed = discord.Embed(title="🛡️ Whitelist Management", description="เลือกเซิฟเวอร์ที่ต้องการ **อนุญาต (Whitelist)**\n(เลือกได้หลายอัน)", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=self)

    async def to_reset_mode(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(ServerSelectMenu(self.bot, "reset"))
        b_cancel = discord.ui.Button(label="ยกเลิก", style=discord.ButtonStyle.danger, row=1)
        b_cancel.callback = self.return_to_main
        self.add_item(b_cancel)
        
        embed = discord.Embed(title="🗑️ Reset Data Management", description="⚠️ เลือกเซิฟเวอร์ที่ต้องการ **ลบข้อมูลทั้งหมด**\n(เลือกได้หลายอัน - ลบทันที!)", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=self)

    async def do_backup_logic(self, interaction: discord.Interaction):
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        current_channel_id = data["guilds"][str(interaction.guild_id)].get("autobackup_channel")
        
        if not current_channel_id:
            view = AutoBackupSetupView(self.bot)
            await interaction.response.send_message("⚠️ **ยังไม่ได้ตั้งค่า Auto Backup**\nกรุณาเลือกห้องที่จะให้บอทส่งไฟล์ Backup อัตโนมัติทุก 1 ชั่วโมง:", view=view, ephemeral=True)
        else:
            await self.send_manual_backup(interaction)

    async def send_manual_backup(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
            
        if os.path.exists(DATA_FILE):
            timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
            file = discord.File(DATA_FILE, filename=f"manual-backup-{timestamp}.json")
            await interaction.followup.send("📦 **Manual Backup:**", file=file, ephemeral=True)
        else:
            await interaction.followup.send("❌ ไม่พบไฟล์ข้อมูล", ephemeral=True)

    async def stop_autobackup(self, interaction: discord.Interaction):
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["autobackup_channel"] = None
        save_data(data)
        await interaction.response.send_message("✅ **ยกเลิก Auto Backup** ของเซิฟเวอร์นี้แล้ว", ephemeral=True)

    async def do_restore_flow(self, interaction: discord.Interaction):
        await interaction.response.send_message("📂 **กรุณาส่งไฟล์ `data.json` ลงในช่องนี้**\n(ระบบจะรอรับไฟล์จาก Owner เท่านั้น ภายใน 60 วินาที...)", ephemeral=True)
        
        def check(m):
            return m.author.id in OWNER_IDS and m.channel.id == interaction.channel.id and m.attachments

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            
            attachment = msg.attachments[0]
            if not attachment.filename.endswith('.json'):
                return await interaction.followup.send("❌ โปรดส่งไฟล์นามสกุล `.json` เท่านั้น", ephemeral=True)
            
            await attachment.save(DATA_FILE)
            load_data()
            cogs = ["QueueSystem", "SelectSystem", "TicketSystem", "TicketSystemV2", "GambleSystem", "AuctionSystem"]
            methods = ["restore_queue_system", "restore_select_menus", "restore_ticket_views", "restore_views", "restore_gamble_views", "restore_auction_views"]
            
            reloaded_count = 0
            for c, m in zip(cogs, methods):
                cog = self.bot.get_cog(c)
                if cog and hasattr(cog, m): 
                    await getattr(cog, m)()
                    reloaded_count += 1
            
            await msg.add_reaction("✅")
            await interaction.followup.send(f"✅ **Restore สำเร็จ!**\nขนาดไฟล์: `{attachment.size} bytes` | รีโหลดระบบ: `{reloaded_count}`", ephemeral=True)
            
        except asyncio.TimeoutError:
            await interaction.followup.send("⌛ **หมดเวลาการรอไฟล์** (กรุณากดปุ่ม Restore ใหม่อีกครั้ง)", ephemeral=True)

    async def return_to_main(self, interaction: discord.Interaction):
        self.setup_main_menu()
        embed = self.get_status_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # --- INFO MODE HELPERS (API SAFE) ---
    async def update_info_view(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        self.clear_items()
        guilds = list(self.bot.guilds)
        total_pages = (len(guilds) - 1) // self.items_per_page + 1

        b_prev = discord.ui.Button(label="⬅️ ก่อนหน้า", style=discord.ButtonStyle.primary, disabled=(self.current_page == 0))
        b_prev.callback = self.prev_page
        self.add_item(b_prev)

        b_cancel = discord.ui.Button(label="ยกเลิก (กลับ)", style=discord.ButtonStyle.danger)
        b_cancel.callback = self.return_to_main_from_deferred
        self.add_item(b_cancel)

        b_next = discord.ui.Button(label="ถัดไป ➡️", style=discord.ButtonStyle.primary, disabled=(self.current_page >= total_pages - 1))
        b_next.callback = self.next_page
        self.add_item(b_next)

        embed = await self.get_info_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    async def return_to_main_from_deferred(self, interaction: discord.Interaction):
        self.setup_main_menu()
        embed = self.get_status_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self.update_info_view(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self.update_info_view(interaction)

    # --- EMBED GENERATORS ---
    def get_status_embed(self):
        ram = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        file_size = os.path.getsize(DATA_FILE) / 1024 if os.path.exists(DATA_FILE) else 0
        ping = self.bot.latency * 1000
        guild_count = len(self.bot.guilds)
        
        embed = discord.Embed(title="🛡️ Owner Control Panel", color=discord.Color.dark_theme())
        embed.description = (
            f"**สถานะบอท**\n"
            f"⚡ Ping: `{ping:.0f} ms`\n"
            f"🧠 RAM: `{ram:.2f} MB`\n"
            f"💾 Data: `{file_size:.2f} KB`\n"
            f"🏢 Servers: `{guild_count}`\n"
        )
        return embed

    async def get_info_embed(self):
        guilds = list(self.bot.guilds)
        total_pages = (len(guilds) - 1) // self.items_per_page + 1
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current = guilds[start:end]
        
        embed = discord.Embed(title=f"📜 Server List ({self.current_page + 1}/{total_pages})", color=discord.Color.blue())
        desc = ""
        for g in current:
            owner = g.owner.name if g.owner else "Unknown"
            join_ts = int(g.me.joined_at.timestamp()) if g.me.joined_at else 0
            join_str = f"<t:{join_ts}:f>" if join_ts else "Unknown"
            
            try:
                invites = await g.invites()
                if invites:
                    link = invites[0].url
                    by = "ลิ้งค์ที่มีอยู่"
                else:
                    ch = next((c for c in g.text_channels if c.permissions_for(g.me).create_instant_invite), None)
                    if ch:
                        new = await ch.create_invite(max_age=0, max_uses=0, reason="Owner Panel Info")
                        link = new.url
                        by = "บอทสร้างใหม่"
                    else:
                        link = "#no-perm"
                        by = "ไม่มีสิทธิ์"
            except Exception as e:
                print(f"Invite Error {g.id}: {e}")
                link = "#error"
                by = "Error"
                
            desc += f"**{g.name}** (`{g.id}`)\n👑 {owner} | 👥 {g.member_count}\n📅 เข้าเมื่อ: {join_str}\n🔗 [Link]({link}) ({by})\n\n"
            
        embed.description = desc or "ไม่มีข้อมูล"
        return embed

# =========================================
# 🛠️ AUTO BACKUP SETUP VIEW
# =========================================
class AutoBackupSetupView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกห้องสำหรับ Auto Backup...")
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel_id = select.values[0].id
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["autobackup_channel"] = channel_id
        save_data(data)
        
        await interaction.response.send_message(f"✅ **บันทึกการตั้งค่าแล้ว!**\nAuto Backup จะถูกส่งไปที่ <#{channel_id}>\nกำลังส่งไฟล์ Backup ล่าสุดให้ครับ...", ephemeral=True)
        
        if os.path.exists(DATA_FILE):
            timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
            file = discord.File(DATA_FILE, filename=f"manual-backup-{timestamp}.json")
            await interaction.followup.send("📦 **Manual Backup:**", file=file, ephemeral=True)

class ServerSelectMenu(discord.ui.Select):
    def __init__(self, bot, action_type):
        self.bot = bot
        self.action_type = action_type 
        
        options = []
        data = load_data()
        target_guilds = self.bot.guilds[:25]
        
        for g in target_guilds:
            status = "✅" if str(g.id) in data.get("whitelisted_guilds", []) else "⬜"
            desc = f"ID: {g.id} | Members: {g.member_count}"
            label = g.name[:90]
            if self.action_type == "whitelist":
                label = f"{status} {label}"
            options.append(discord.SelectOption(label=label, value=str(g.id), description=desc, emoji="🏢"))

        super().__init__(placeholder="เลือกเซิฟเวอร์ (เลือกได้หลายอัน)", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        selected_ids = self.values
        msg = []
        
        if self.action_type == "whitelist":
            for gid in selected_ids:
                if gid not in data["whitelisted_guilds"]:
                    data["whitelisted_guilds"].append(gid)
                    msg.append(f"✅ Whitelisted: {gid}")
                else:
                    data["whitelisted_guilds"].remove(gid)
                    msg.append(f"⛔ Un-Whitelisted: {gid}")
            save_data(data)
            await interaction.followup.send("\n".join(msg), ephemeral=True)
            
            view = self.view
            embed = discord.Embed(title="🛡️ Whitelist Management", description="อัปเดตข้อมูลแล้ว", color=discord.Color.green())
            view.clear_items()
            view.add_item(ServerSelectMenu(self.bot, "whitelist"))
            b_cancel = discord.ui.Button(label="ยกเลิก", style=discord.ButtonStyle.danger, row=1)
            b_cancel.callback = view.return_to_main
            view.add_item(b_cancel)
            await interaction.message.edit(embed=embed, view=view)

        elif self.action_type == "reset":
            for gid in selected_ids:
                if gid in data["guilds"]:
                    del data["guilds"][gid]
                    msg.append(f"💥 Deleted Data: {gid}")
                else:
                    msg.append(f"⚠️ No Data: {gid}")
            save_data(data)
            await interaction.followup.send("\n".join(msg), ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
