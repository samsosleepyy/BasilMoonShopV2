import discord
from discord import app_commands
from discord.ext import commands, tasks
import sys
import os
import datetime
import asyncio
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin, init_guild_data, DATA_FILE, is_owner

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autobackup_task.start()

    def cog_unload(self):
        self.autobackup_task.cancel()

    # =========================================
    # 🔄 AUTO BACKUP LOOP
    # =========================================
    @tasks.loop(hours=1)
    async def autobackup_task(self):
        await self.bot.wait_until_ready()
        try:
            if not os.path.exists(DATA_FILE): return
            data = load_data()
            
            # --- Report ---
            server_names = []
            if "guilds" in data:
                for gid in data["guilds"]:
                    g = self.bot.get_guild(int(gid))
                    name = g.name if g else f"Unknown({gid})"
                    server_names.append(name)
            
            server_list = ", ".join(server_names) if server_names else "-"
            count_ticket_v1 = len(data.get('active_tickets', {}))
            count_ticket_v2 = len(data.get('active_tickets_v2', {}))
            count_auction = len(data.get('active_auctions', {}))
            count_gamble = len(data.get('gamble_configs', {}))
            count_queue = len(data.get('queue_views', {}))
            count_select = len(data.get('select_menus', {}))
            count_points = len(data.get('points', {}))

            report_msg = (
                f"📊 **Auto Backup Report**\n"
                f"⏰ เวลา: <t:{int(datetime.datetime.now().timestamp())}:f>\n\n"
                f"🏢 **เซิฟเวอร์ที่มีข้อมูล ({len(server_names)}):**\n`{server_list}`\n\n"
                f"💾 **ระบบที่บันทึก:**\n"
                f"• 🎫 Ticket V1 (Active): `{count_ticket_v1}` ห้อง\n"
                f"• 📨 Ticket V2 (Active): `{count_ticket_v2}` ห้อง\n"
                f"• 🔨 Auction (Active): `{count_auction}` รายการ\n"
                f"• 🎰 Gamble Configs: `{count_gamble}` ตู้\n"
                f"• 📋 Queue Configs: `{count_queue}` ปุ่ม\n"
                f"• 🔻 Select Menus: `{count_select}` เมนู\n"
                f"• 💰 User Points: `{count_points}` คน"
            )

            if "guilds" in data:
                for guild_id_str, guild_data in data["guilds"].items():
                    channel_id = guild_data.get("autobackup_channel")
                    if channel_id:
                        try:
                            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                            if channel:
                                guild = self.bot.get_guild(int(guild_id_str))
                                guild_name = guild.name if guild else f"Guild-{guild_id_str}"
                                safe_name = "".join([c for c in guild_name if c.isalnum() or c in " -_"]).strip()
                                if not safe_name: safe_name = "ServerData"
                                timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
                                filename = f"{safe_name}-data-{timestamp}.json"
                                
                                file = discord.File(DATA_FILE, filename=filename)
                                await channel.send(content=report_msg, file=file)
                                print(f"Auto-backup sent to guild {guild_name} ({guild_id_str})")
                        except Exception as e:
                            print(f"Failed to send backup to guild {guild_id_str}: {e}")
        except Exception as e:
            print(f"Auto-backup loop error: {e}")

    # =========================================
    # 🔒 OWNER ONLY COMMANDS
    # =========================================

    @app_commands.command(name="info", description="ดูข้อมูลบอท")
    async def info_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_owner(interaction):
            return await interaction.followup.send(MESSAGES["owner_only"], ephemeral=True)
        
        guilds = self.bot.guilds
        total_guilds = len(guilds)
        total_members = sum(g.member_count for g in guilds)
        
        details = []
        for guild in guilds:
            invite_url = "❌ ไม่พบลิ้งค์"
            try:
                invites = await guild.invites()
                if invites:
                    target_invite = next((inv for inv in invites if inv.max_age == 0), invites[0])
                    invite_url = target_invite.url
            except: pass
            if invite_url.startswith("❌"):
                try:
                    target_channel = next((c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None)
                    if target_channel:
                        invite = await target_channel.create_invite(max_age=0, max_uses=0, reason="Bot Owner Info Request")
                        invite_url = invite.url
                except: pass
            
            owner_name = guild.owner.name if guild.owner else "Unknown"
            details.append(f"• **{guild.name}** (`{guild.id}`)\n   👑 เจ้าของ: {owner_name} | 👥 สมาชิก: {guild.member_count}\n   🔗 {invite_url}")

        embed = discord.Embed(title="🤖 ข้อมูลบอท (System Info)", color=discord.Color.blue())
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.add_field(name="📊 สถิติภาพรวม", value=f"🏢 จำนวนเซิฟเวอร์: `{total_guilds}`\n👤 สมาชิกทั้งหมด: `{total_members}`", inline=False)
        
        server_list_str = "\n\n".join(details)
        if len(server_list_str) > 3800:
            with io.StringIO(server_list_str) as f:
                file = discord.File(f, filename="server_list.txt")
                embed.description = "📜 **รายชื่อเซิฟเวอร์ทั้งหมด**\n*(เนื่องจากข้อมูลมีจำนวนมาก ระบบจึงแนบไฟล์ Text มาให้แทนครับ)*"
                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        else:
            embed.description = f"📜 **รายชื่อเซิฟเวอร์ทั้งหมด**\n\n{server_list_str}"
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="whitelist", description="[Owner Only] อนุญาตให้เซิฟเวอร์ใช้บอทได้")
    async def whitelist(self, interaction: discord.Interaction, server_id: str):
        await interaction.response.defer(ephemeral=True)
        if not is_owner(interaction):
            return await interaction.followup.send(MESSAGES["owner_only"], ephemeral=True)
        
        data = load_data()
        if server_id not in data["whitelisted_guilds"]:
            data["whitelisted_guilds"].append(server_id)
            save_data(data)
            await interaction.followup.send(f"✅ เพิ่ม Server ID `{server_id}` เข้าสู่ Whitelist เรียบร้อยแล้ว", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ Server ID `{server_id}` มีอยู่ใน Whitelist อยู่แล้ว", ephemeral=True)

    @app_commands.command(name="restore", description="[Owner Only] กู้คืนข้อมูลจากไฟล์ data.json")
    @app_commands.describe(file="ไฟล์ data.json ที่ต้องการกู้คืน")
    async def restore(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if not is_owner(interaction):
            return await interaction.followup.send(MESSAGES["owner_only"], ephemeral=True)
        
        if not file.filename.endswith(".json"):
            return await interaction.followup.send("❌ โปรดอัปโหลดไฟล์ .json เท่านั้น", ephemeral=True)
            
        try:
            await file.save(DATA_FILE)
            load_data() 
            cogs_to_reload = [
                ("QueueSystem", "restore_queue_system"),
                ("SelectSystem", "restore_select_menus"),
                ("TicketSystem", "restore_ticket_views"),
                ("TicketSystemV2", "restore_views"),
                ("GambleSystem", "restore_gamble_views"),
                ("AuctionSystem", "restore_auction_views")
            ]
            restored_count = 0
            for cog_name, method_name in cogs_to_reload:
                cog = self.bot.get_cog(cog_name)
                if cog and hasattr(cog, method_name):
                    await getattr(cog, method_name)()
                    restored_count += 1
            await interaction.followup.send(f"✅ **กู้คืนข้อมูลสำเร็จ!**\nขนาดไฟล์: {file.size} bytes\nรีโหลดระบบย่อย: {restored_count} ระบบ", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการกู้คืน: {e}", ephemeral=True)

    @app_commands.command(name="backup", description="[Owner Only] สำรองข้อมูล data.json")
    async def backup(self, interaction: discord.Interaction, autobackup_log: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        if not is_owner(interaction): 
            return await interaction.followup.send(MESSAGES["owner_only"], ephemeral=True)
        
        if not os.path.exists(DATA_FILE):
            return await interaction.followup.send("❌ ไม่พบไฟล์ข้อมูล", ephemeral=True)

        safe_name = "".join([c for c in interaction.guild.name if c.isalnum() or c in " -_"]).strip()
        if not safe_name: safe_name = "ServerData"
        timestamp = datetime.datetime.now().strftime('%d%m%y-%H%M')
        filename = f"{safe_name}-data-{timestamp}.json"

        if autobackup_log:
            data = load_data()
            init_guild_data(data, interaction.guild_id)
            data["guilds"][str(interaction.guild_id)]["autobackup_channel"] = autobackup_log.id
            save_data(data)
            await interaction.followup.send(f"✅ **ตั้งค่า Auto Backup เรียบร้อย!**\nจะส่งไฟล์ Backup เข้าห้อง {autobackup_log.mention} ของเซิร์ฟเวอร์นี้ ทุก 1 ชั่วโมง", ephemeral=True)
            file = discord.File(DATA_FILE, filename=filename)
            await autobackup_log.send(f"📦 **Backup เริ่มต้น** (Setup by {interaction.user.mention})", file=file)
        else:
            file = discord.File(DATA_FILE, filename=filename)
            await interaction.followup.send("📦 **ไฟล์ Backup ข้อมูลปัจจุบัน**", file=file, ephemeral=True)

    # =========================================
    # [UPDATED] RESET DATA COMMAND (Advanced)
    # =========================================
    @app_commands.command(name="resetdata", description="เลือกลบข้อมูล")
    async def resetdata(self, interaction: discord.Interaction):
        if not is_owner(interaction):
             return await interaction.response.send_message(MESSAGES["owner_only"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        
        guild_ids = list(data.get("guilds", {}).keys())
        if not guild_ids:
            return await interaction.followup.send("❌ ไม่พบข้อมูลเซิฟเวอร์ในฐานข้อมูล", ephemeral=True)
            
        view = ServerPaginationView(guild_ids, self.bot)
        await interaction.followup.send("🗑️ **เลือกเซิฟเวอร์ที่ต้องการลบข้อมูล:**", view=view)

    # ... (Command อื่นๆ คงเดิม) ...
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
        pass

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
# 📄 RESET DATA VIEWS (Pagination & Selection)
# =========================================

class ServerPaginationView(discord.ui.View):
    def __init__(self, guild_ids, bot):
        super().__init__(timeout=None)
        self.guild_ids = guild_ids
        self.bot = bot
        self.current_page = 0
        self.items_per_page = 20
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_ids = self.guild_ids[start:end]

        for gid in page_ids:
            guild = self.bot.get_guild(int(gid))
            label = guild.name if guild else f"ID: {gid}"
            if len(label) > 20: label = label[:17] + "..."
            
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=f"reset_g_{gid}")
            btn.callback = self.create_callback(gid)
            self.add_item(btn)

        total_pages = (len(self.guild_ids) - 1) // self.items_per_page + 1
        if total_pages > 1:
            if self.current_page > 0:
                prev_btn = discord.ui.Button(label="⬅️ ก่อนหน้า", style=discord.ButtonStyle.primary, row=4)
                prev_btn.callback = self.prev_page
                self.add_item(prev_btn)
            if self.current_page < total_pages - 1:
                next_btn = discord.ui.Button(label="ถัดไป ➡️", style=discord.ButtonStyle.primary, row=4)
                next_btn.callback = self.next_page
                self.add_item(next_btn)

    def create_callback(self, guild_id):
        async def callback(interaction: discord.Interaction):
            view = ResetSystemSelectorView(guild_id, self.bot)
            guild = self.bot.get_guild(int(guild_id))
            g_name = guild.name if guild else guild_id
            await interaction.response.edit_message(content=f"🗑️ **จัดการข้อมูล: {g_name}**\nเลือกรูปแบบข้อมูลที่ต้องการลบ:", view=view)
        return callback

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(view=self)

class ResetSystemSelectorView(discord.ui.View):
    def __init__(self, guild_id, bot):
        super().__init__(timeout=None)
        self.add_item(ResetSystemSelect(guild_id, bot))
        
        back_btn = discord.ui.Button(label="🔙 กลับไปหน้ารายชื่อ", style=discord.ButtonStyle.secondary, row=4)
        back_btn.callback = self.back_to_list
        self.add_item(back_btn)

    async def back_to_list(self, interaction: discord.Interaction):
        data = load_data()
        guild_ids = list(data.get("guilds", {}).keys())
        view = ServerPaginationView(guild_ids, interaction.client)
        await interaction.response.edit_message(content="🗑️ **เลือกเซิฟเวอร์ที่ต้องการลบข้อมูล:**", view=view)

class ResetSystemSelect(discord.ui.Select):
    def __init__(self, guild_id, bot):
        self.guild_id = str(guild_id)
        self.bot = bot
        
        data = load_data()
        
        tk2_count = 0
        if "ticket_v2_configs" in data:
            for mid, conf in data["ticket_v2_configs"].items():
                chan = bot.get_channel(conf["channel_id"])
                if chan and str(chan.guild.id) == self.guild_id:
                    tk2_count += 1
                elif not chan:
                    # ถ้าหาห้องไม่เจอ แต่ข้อมูลอาจยังอยู่ (ถ้าแน่ใจว่าลบได้ก็ลบ)
                    pass

        gamble_count = 0
        if "gamble_configs" in data:
            for mid, conf in data["gamble_configs"].items():
                chan_id = conf.get("target_channel")
                if chan_id:
                    chan = bot.get_channel(chan_id)
                    if chan and str(chan.guild.id) == self.guild_id:
                        gamble_count += 1

        options = [
            discord.SelectOption(label=f"Ticket V2 Panels (มี {tk2_count} รายการ)", value="ticket_v2", emoji="🎫", description="เลือกลบแผงตั๋ว V2 แบบเจาะจง"),
            discord.SelectOption(label=f"Gamble Machines (มี {gamble_count} รายการ)", value="gamble", emoji="🎰", description="เลือกลบตู้กาชาแบบเจาะจง"),
            discord.SelectOption(label="ตั้งค่าทั่วไป / รีเซ็ตตัวนับ", value="general", emoji="⚙️", description="รีเซ็ตเลขคิว, ประวัติ, Anti-Raid ฯลฯ"),
            discord.SelectOption(label="⚠️ ลบข้อมูลเซิฟเวอร์นี้ทั้งหมด", value="all", emoji="💥", description="ลบทุกอย่างออกจาก Database"),
        ]
        super().__init__(placeholder="เลือกหมวดหมู่ข้อมูลที่ต้องการลบ...", options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        
        if val == "general":
            view = ResetGeneralView(self.guild_id)
            await interaction.response.edit_message(content="⚙️ **เลือกข้อมูลทั่วไปที่ต้องการรีเซ็ต (เลือกได้หลายอัน):**", view=view)
        
        elif val == "ticket_v2":
            view = DeleteItemListView(self.guild_id, "ticket_v2", self.bot)
            if not view.options_available:
                await interaction.response.send_message("❌ ไม่พบข้อมูล Ticket V2 ในเซิฟเวอร์นี้", ephemeral=True)
            else:
                await interaction.response.edit_message(content="🎫 **เลือกแผง Ticket V2 ที่ต้องการลบ:**", view=view)

        elif val == "gamble":
            view = DeleteItemListView(self.guild_id, "gamble", self.bot)
            if not view.options_available:
                await interaction.response.send_message("❌ ไม่พบตู้กาชาในเซิฟเวอร์นี้", ephemeral=True)
            else:
                await interaction.response.edit_message(content="🎰 **เลือกตู้กาชาที่ต้องการลบ:**", view=view)
        
        elif val == "all":
            data = load_data()
            if self.guild_id in data["guilds"]:
                del data["guilds"][self.guild_id]
                save_data(data)
                await interaction.response.edit_message(content=f"💥 **ลบข้อมูลทั้งหมดของ Guild ID {self.guild_id} เรียบร้อยแล้ว**", view=None)
            else:
                await interaction.response.send_message("❌ ไม่พบข้อมูล", ephemeral=True)

class ResetGeneralView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.add_item(ResetGeneralSelect(guild_id))

class ResetGeneralSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="รีเซ็ตจำนวนประมูล (Auction Count)", value="auction_count", emoji="🔨"),
            discord.SelectOption(label="รีเซ็ตจำนวนตั๋ว (Ticket Count)", value="ticket_count", emoji="🎫"),
            discord.SelectOption(label="รีเซ็ตลำดับเร่งด่วน (Rush Queue)", value="rush_queue", emoji="🔥"),
            discord.SelectOption(label="ล้างการตั้งค่าตั๋วเก่า (Ticket V1 Configs)", value="ticket_configs", emoji="🗑️"),
            discord.SelectOption(label="ล้างสถิติกาชา (Gamble Stats)", value="gamble_stats", emoji="🎰"),
            discord.SelectOption(label="ล้างประวัติรางวัล (Claimed Prizes)", value="claimed_prizes", emoji="🏆"),
            discord.SelectOption(label="ปิด/รีเซ็ต Anti-Raid", value="antiraid", emoji="🛡️"),
            discord.SelectOption(label="ยกเลิก Auto Backup Channel", value="autobackup", emoji="💾"),
        ]
        super().__init__(placeholder="เลือกรายการที่ต้องการรีเซ็ต (เลือกได้หลายข้อ)", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        
        if self.guild_id not in data["guilds"]:
            return await interaction.followup.send("❌ ไม่พบข้อมูลเซิฟเวอร์นี้", ephemeral=True)
            
        g_data = data["guilds"][self.guild_id]
        msg = []
        
        for val in self.values:
            if val == "auction_count":
                g_data["auction_count"] = 0
                msg.append("✅ รีเซ็ต Auction Count")
            elif val == "ticket_count":
                g_data["ticket_count"] = 0
                msg.append("✅ รีเซ็ต Ticket Count")
            elif val == "rush_queue":
                g_data["rush_queue"] = 0
                msg.append("✅ รีเซ็ต Rush Queue")
            elif val == "ticket_configs":
                g_data["ticket_configs"] = {}
                msg.append("✅ ล้าง Ticket V1 Configs")
            elif val == "gamble_stats":
                g_data["gamble_stats"] = {}
                msg.append("✅ ล้าง Gamble Stats")
            elif val == "claimed_prizes":
                g_data["claimed_prizes"] = {}
                msg.append("✅ ล้าง Claimed Prizes")
            elif val == "antiraid":
                g_data["antiraid"] = {"status": False, "log_channel": None}
                msg.append("✅ ปิด/รีเซ็ต Anti-Raid")
            elif val == "autobackup":
                g_data["autobackup_channel"] = None
                msg.append("✅ ยกเลิก Auto Backup Channel")
        
        save_data(data)
        await interaction.followup.send("\n".join(msg), ephemeral=True)

class DeleteItemListView(discord.ui.View):
    def __init__(self, guild_id, data_type, bot):
        super().__init__(timeout=None)
        self.options_available = False
        
        select = DeleteItemSelect(guild_id, data_type, bot)
        if len(select.options) > 0:
            self.add_item(select)
            self.options_available = True

class DeleteItemSelect(discord.ui.Select):
    def __init__(self, guild_id, data_type, bot):
        self.guild_id = guild_id
        self.data_type = data_type
        self.bot = bot
        
        data = load_data()
        options = []
        
        if data_type == "ticket_v2":
            if "ticket_v2_configs" in data:
                for mid, conf in data["ticket_v2_configs"].items():
                    chan = bot.get_channel(conf["channel_id"])
                    if chan and str(chan.guild.id) == str(guild_id):
                        title = conf["embed_data"].get("title", "No Title")[:50]
                        options.append(discord.SelectOption(label=f"{title}", value=mid, description=f"Channel: {chan.name}", emoji="🎫"))
                        if len(options) >= 25: break 

        elif data_type == "gamble":
            if "gamble_configs" in data:
                for mid, conf in data["gamble_configs"].items():
                    chan_id = conf.get("target_channel")
                    if chan_id:
                        chan = bot.get_channel(chan_id)
                        if chan and str(chan.guild.id) == str(guild_id):
                            label = f"ตู้กาชา ({mid[-4:]})"
                            options.append(discord.SelectOption(label=label, value=mid, description=f"Channel: {chan.name}", emoji="🎰"))
                            if len(options) >= 25: break

        if not options:
            options.append(discord.SelectOption(label="ไม่มีข้อมูล", value="none"))
        
        super().__init__(placeholder=f"เลือก {data_type} ที่ต้องการลบ...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "none": return
        
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        
        if self.data_type == "ticket_v2":
            if val in data["ticket_v2_configs"]:
                del data["ticket_v2_configs"][val]
                save_data(data)
                await interaction.followup.send(f"✅ ลบแผง Ticket V2 (ID: {val}) เรียบร้อยแล้ว", ephemeral=True)
                
        elif self.data_type == "gamble":
            if val in data["gamble_configs"]:
                del data["gamble_configs"][val]
                if "gamble_stats" in data and val in data["gamble_stats"]: del data["gamble_stats"][val]
                if "claimed_prizes" in data and val in data["claimed_prizes"]: del data["claimed_prizes"][val]
                save_data(data)
                await interaction.followup.send(f"✅ ลบตู้กาชา (ID: {val}) เรียบร้อยแล้ว", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
