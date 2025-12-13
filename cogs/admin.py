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
    # 🔄 AUTO BACKUP LOOP (Safe Mode 🛡️)
    # =========================================
    @tasks.loop(hours=1)
    async def autobackup_task(self):
        await self.bot.wait_until_ready()
        try:
            if not os.path.exists(DATA_FILE): return
            data = load_data()
            
            if "guilds" in data:
                # [SAFETY] นับจำนวนเซิฟที่ต้องส่งเพื่อ Debug
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
                                
                                # [CRITICAL SAFETY] พัก 2 วินาทีต่อ 1 เซิฟเวอร์ ป้องกัน 429 Too Many Requests
                                await asyncio.sleep(2) 
                                
                        except Exception as e:
                            print(f"Auto-backup fail for {guild_id_str}: {e}")
                
                if count_sent > 0:
                    print(f"✅ Auto-Backup sent to {count_sent} guilds.")
                    
        except Exception as e:
            print(f"Auto-backup loop error: {e}")

    # =========================================
    # 👑 OWNER PANEL COMMAND
    # =========================================
    @app_commands.command(name="owner-panel", description="[Owner Only] แผงควบคุมบอทและการจัดการข้อมูล")
    async def owner_panel(self, interaction: discord.Interaction):
        if not is_owner(interaction):
            return await interaction.response.send_message(MESSAGES["owner_only"], ephemeral=True)
        
        # Defer ทันทีเพื่อให้เวลาบอทโหลดข้อมูล
        await interaction.response.defer(ephemeral=False)
        view = OwnerPanelView(self.bot, interaction.user.id)
        embed = view.get_status_embed()
        await interaction.followup.send(embed=embed, view=view)

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
        # [SAFETY] Defer ถ้ายังไม่ได้ Defer
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
        # [SAFETY] Defer ก่อนเสมอเพราะการ Fetch Invite หลายๆ อันอาจใช้เวลา > 3 วิ
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
        # [SAFETY] ใช้ edit_original_message แทน response.edit_message เพราะเรา defer ไปแล้ว
        await interaction.edit_original_message(embed=embed, view=self)

    # Helper สำหรับปุ่มที่ Defer ไปแล้ว
    async def return_to_main_from_deferred(self, interaction: discord.Interaction):
        # ถ้ากดกลับจากหน้า Info เรา defer มาแล้ว ต้องใช้ edit_original_message
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
                # [SAFETY] Try to get existing invite first to save API calls
                invites = await g.invites()
                if invites:
                    link = invites[0].url
                    by = "ลิ้งค์ที่มีอยู่"
                else:
                    # Create new only if necessary
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
