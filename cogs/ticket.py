import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin, init_guild_data

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self.restore_ticket_views())

    async def restore_ticket_views(self):
        await self.bot.wait_until_ready()
        print("🔄 Restoring Ticket Forums Views...")
        
        self.bot.add_view(TicketForumView())
        
        data = load_data()
        
        count = 0
        if "active_tickets" in data:
            for channel_id, info in data["active_tickets"].items():
                try:
                    view = TicketControlView(
                        info["forum_thread_id"], 
                        info["log_id"], 
                        info["buyer_id"], 
                        info["seller_id"], 
                        info["forum_msg_id"], 
                        info["count"]
                    )
                    self.bot.add_view(view)
                    count += 1
                except: pass
        
        panel_count = 0
        if "guilds" in data:
            for guild_id, guild_data in data["guilds"].items():
                if "ticket_configs" in guild_data:
                    for forum_id, conf in guild_data["ticket_configs"].items():
                        if "panel_msg_id" in conf:
                            try:
                                view = TicketPanelControlView(guild_id, forum_id)
                                self.bot.add_view(view, message_id=conf["panel_msg_id"])
                                panel_count += 1
                            except Exception as e:
                                print(f"Failed to restore panel {forum_id}: {e}")

        print(f"✅ Restored {count} tickets & {panel_count} panels.")

    @app_commands.command(name="ticket-forums", description="สร้าง Panel ควบคุมระบบ Ticket Forums")
    async def ticket_forums(self, interaction: discord.Interaction, 
                            panel_channel: discord.TextChannel,
                            category: discord.CategoryChannel, 
                            forum: discord.ForumChannel, 
                            log_channel: discord.TextChannel = None):
        
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        guild_id = str(interaction.guild_id)
        forum_id = str(forum.id)

        if forum_id not in data["guilds"][guild_id]["ticket_configs"]:
             data["guilds"][guild_id]["ticket_configs"][forum_id] = {}
        
        config = {
            "category_id": category.id,
            "log_id": log_channel.id if log_channel else None,
            "panel_channel_id": panel_channel.id,
            "status": True 
        }
        
        embed = discord.Embed(title="⚙️ Ticket Forums Control Panel", description="แผงควบคุมการตั้งค่าระบบ Ticket สำหรับ Forum นี้", color=discord.Color.blue())
        embed.add_field(name="📂 หมวดหมู่ (Category)", value=category.mention, inline=False)
        embed.add_field(name="💬 ฟอรั่ม (Forum)", value=forum.mention, inline=False)
        log_ment = log_channel.mention if log_channel else "ไม่ระบุ"
        embed.add_field(name="📜 ช่อง Log", value=log_ment, inline=False)
        embed.add_field(name="🟢 สถานะ", value="**เปิดใช้งาน (Active)**", inline=False)
        embed.set_footer(text=f"Forum ID: {forum_id}")

        view = TicketPanelControlView(guild_id, forum_id)
        msg = await panel_channel.send(embed=embed, view=view)
        
        config["panel_msg_id"] = msg.id
        data["guilds"][guild_id]["ticket_configs"][forum_id] = config
        save_data(data)
        
        await interaction.followup.send(f"✅ สร้าง Panel เรียบร้อยแล้วที่ {panel_channel.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        data = load_data()
        guild_id = str(thread.guild.id)
        init_guild_data(data, guild_id)
        configs = data["guilds"][guild_id].get("ticket_configs", {})
        
        parent_id = str(thread.parent_id)
        if parent_id in configs:
            await asyncio.sleep(1)
            await thread.send(MESSAGES["tf_guide_msg"], view=TicketForumView())

# ====================================================
# 🎛️ TICKET PANEL CONTROL VIEW
# ====================================================
class TicketPanelControlView(discord.ui.View):
    def __init__(self, guild_id, forum_id):
        super().__init__(timeout=None)
        self.guild_id = str(guild_id)
        self.forum_id = str(forum_id)
        self.update_buttons()

    def update_buttons(self):
        data = load_data()
        try:
            config = data["guilds"][self.guild_id]["ticket_configs"].get(self.forum_id, {})
            status = config.get("status", True)
            
            btn_toggle = [x for x in self.children if x.custom_id == "tf_panel_toggle"][0]
            if status:
                btn_toggle.label = "ปิดระบบ 🔴"
                btn_toggle.style = discord.ButtonStyle.danger
            else:
                btn_toggle.label = "เปิดระบบ 🟢"
                btn_toggle.style = discord.ButtonStyle.success
        except: pass

    @discord.ui.button(label="Loading...", style=discord.ButtonStyle.secondary, custom_id="tf_panel_toggle", row=0)
    async def toggle_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.response.defer()
        
        data = load_data()
        config = data["guilds"][self.guild_id]["ticket_configs"].get(self.forum_id)
        if not config: return
        
        new_status = not config.get("status", True)
        config["status"] = new_status
        save_data(data)
        
        try:
            forum_channel = interaction.guild.get_channel(int(self.forum_id))
            if forum_channel:
                current_overwrites = forum_channel.overwrites
                new_overwrites = current_overwrites.copy()
                
                for role in interaction.guild.roles:
                    if role.permissions.administrator: continue
                        
                    overwrite = new_overwrites.get(role, discord.PermissionOverwrite())
                    if new_status: 
                        overwrite.send_messages = None
                        if role == interaction.guild.default_role: overwrite.send_messages = None
                    else: 
                        overwrite.send_messages = False
                    new_overwrites[role] = overwrite
                
                await forum_channel.edit(overwrites=new_overwrites)
        except Exception as e:
            print(f"Failed to update permissions: {e}")
        
        self.update_buttons()
        
        embed = interaction.message.embeds[0]
        status_text = "**เปิดใช้งาน (Active)** 🟢" if new_status else "**ปิดใช้งาน (Inactive)** 🔴"
        
        for i, field in enumerate(embed.fields):
            if "สถานะ" in field.name:
                embed.set_field_at(i, name=field.name, value=status_text, inline=False)
                break
        
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="เปลี่ยนหมวดหมู่ 📂", style=discord.ButtonStyle.primary, custom_id="tf_panel_cat", row=0)
    async def change_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ChannelSelectorView(self.guild_id, self.forum_id, "category")
        await interaction.response.send_message("🔻 **เลือกหมวดหมู่ใหม่ (Category):**", view=view, ephemeral=True)

    @discord.ui.button(label="เปลี่ยนฟอรั่ม 💬", style=discord.ButtonStyle.primary, custom_id="tf_panel_forum", row=0)
    async def change_forum(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ChannelSelectorView(self.guild_id, self.forum_id, "forum")
        await interaction.response.send_message("🔻 **เลือกช่องฟอรั่มใหม่ (Forum):**", view=view, ephemeral=True)

    @discord.ui.button(label="เปลี่ยนช่อง Log 📜", style=discord.ButtonStyle.secondary, custom_id="tf_panel_log", row=1)
    async def change_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ChannelSelectorView(self.guild_id, self.forum_id, "log")
        await interaction.response.send_message("🔻 **เลือกช่อง Log ใหม่:**", view=view, ephemeral=True)

    @discord.ui.button(label="รีเซ็ตเลข ID 🔄", style=discord.ButtonStyle.danger, custom_id="tf_panel_reset", row=1)
    async def reset_count(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        data = load_data()
        data["guilds"][self.guild_id]["ticket_count"] = 0
        save_data(data)
        
        await interaction.response.send_message("✅ **รีเซ็ตตัวนับ Ticket ID เป็น 0 เรียบร้อยแล้ว**", ephemeral=True)

class ChannelSelectorView(discord.ui.View):
    def __init__(self, guild_id, forum_id, mode):
        super().__init__(timeout=60)
        if mode == "category":
            self.add_item(CategorySelect(guild_id, forum_id))
        elif mode == "forum":
            self.add_item(ForumSelect(guild_id, forum_id))
        elif mode == "log":
            self.add_item(LogSelect(guild_id, forum_id))

class CategorySelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id, forum_id):
        super().__init__(channel_types=[discord.ChannelType.category], placeholder="เลือกหมวดหมู่ใหม่...")
        self.tg_guild_id = guild_id
        self.tg_forum_id = forum_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cat_id = self.values[0].id
        data = load_data()
        if self.tg_forum_id in data["guilds"][self.tg_guild_id]["ticket_configs"]:
            data["guilds"][self.tg_guild_id]["ticket_configs"][self.tg_forum_id]["category_id"] = cat_id
            save_data(data)
            await self.update_panel(interaction, "หมวดหมู่", self.values[0].mention)
        else:
            await interaction.followup.send("❌ ไม่พบข้อมูล", ephemeral=True)

    async def update_panel(self, interaction, field_name, value):
        data = load_data()
        conf = data["guilds"][self.tg_guild_id]["ticket_configs"][self.tg_forum_id]
        channel = interaction.guild.get_channel(conf["panel_channel_id"])
        msg = await channel.fetch_message(conf["panel_msg_id"])
        embed = msg.embeds[0]
        for i, field in enumerate(embed.fields):
            if field_name in field.name:
                embed.set_field_at(i, name=field.name, value=value, inline=False)
                break
        await msg.edit(embed=embed)
        await interaction.followup.send(f"✅ อัปเดต {field_name} เรียบร้อย", ephemeral=True)

class ForumSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id, forum_id):
        super().__init__(channel_types=[discord.ChannelType.forum], placeholder="เลือกฟอรั่มใหม่...")
        self.tg_guild_id = guild_id
        self.old_forum_id = forum_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_forum_id = str(self.values[0].id)
        data = load_data()
        guild_data = data["guilds"][self.tg_guild_id]
        
        if self.old_forum_id in guild_data["ticket_configs"]:
            config = guild_data["ticket_configs"].pop(self.old_forum_id)
            guild_data["ticket_configs"][new_forum_id] = config
            save_data(data)
            
            channel = interaction.guild.get_channel(config["panel_channel_id"])
            msg = await channel.fetch_message(config["panel_msg_id"])
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if "ฟอรั่ม" in field.name:
                    embed.set_field_at(i, name=field.name, value=self.values[0].mention, inline=False)
                    break
            embed.set_footer(text=f"Forum ID: {new_forum_id}")
            
            new_view = TicketPanelControlView(self.tg_guild_id, new_forum_id)
            await msg.edit(embed=embed, view=new_view)
            await interaction.followup.send(f"✅ เปลี่ยนฟอรั่มเรียบร้อย", ephemeral=True)
        else:
            await interaction.followup.send("❌ ไม่พบข้อมูล", ephemeral=True)

class LogSelect(discord.ui.ChannelSelect):
    def __init__(self, guild_id, forum_id):
        super().__init__(channel_types=[discord.ChannelType.text], placeholder="เลือกช่อง Log ใหม่...")
        self.tg_guild_id = guild_id
        self.tg_forum_id = forum_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        log_id = self.values[0].id
        data = load_data()
        if self.tg_forum_id in data["guilds"][self.tg_guild_id]["ticket_configs"]:
            data["guilds"][self.tg_guild_id]["ticket_configs"][self.tg_forum_id]["log_id"] = log_id
            save_data(data)
            
            conf = data["guilds"][self.tg_guild_id]["ticket_configs"][self.tg_forum_id]
            channel = interaction.guild.get_channel(conf["panel_channel_id"])
            msg = await channel.fetch_message(conf["panel_msg_id"])
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if "ช่อง Log" in field.name:
                    embed.set_field_at(i, name=field.name, value=self.values[0].mention, inline=False)
                    break
            await msg.edit(embed=embed)
            await interaction.followup.send(f"✅ เปลี่ยนช่อง Log เรียบร้อย", ephemeral=True)
        else:
            await interaction.followup.send("❌ ไม่พบข้อมูล", ephemeral=True)

class TicketForumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label=MESSAGES["tf_btn_buy"], style=discord.ButtonStyle.green, custom_id="tf_buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id: 
            return await interaction.response.send_message(MESSAGES["tf_err_own_post"], ephemeral=True)
        
        data = load_data()
        guild_id = str(interaction.guild_id)
        init_guild_data(data, guild_id)
        configs = data["guilds"][guild_id].get("ticket_configs", {})
        
        conf = configs.get(str(interaction.channel.parent_id))
        if not conf: return
        
        button.disabled = True
        button.label = MESSAGES["tf_btn_buying"]
        button.style = discord.ButtonStyle.gray
        await interaction.response.edit_message(view=self)
        
        data["guilds"][guild_id]["ticket_count"] += 1
        count = data["guilds"][guild_id]["ticket_count"]
        
        category = interaction.guild.get_channel(conf["category_id"])
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.channel.owner: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        chan_name = f"ID-{count}"
        ticket_chan = await interaction.guild.create_text_channel(chan_name, category=category, overwrites=overwrites)
        
        msg_content = MESSAGES["tf_room_created"].format(buyer=interaction.user.mention, seller=interaction.channel.owner.mention)
        msg_content += "\n\n💡 **ปุ่มคนกลาง (Middleman):** หากต้องการให้ Admin เข้ามาช่วยดูแล กดปุ่มระฆัง 🔔 ด้านล่างครับ"
        
        view = TicketControlView(interaction.channel.id, conf["log_id"], interaction.user.id, interaction.channel.owner_id, interaction.message.id, count)
        await ticket_chan.send(msg_content, view=view)

        if "active_tickets" not in data: data["active_tickets"] = {}
        data["active_tickets"][str(ticket_chan.id)] = {
            "forum_thread_id": interaction.channel.id,
            "log_id": conf["log_id"],
            "buyer_id": interaction.user.id,
            "seller_id": interaction.channel.owner_id,
            "forum_msg_id": interaction.message.id,
            "count": count
        }
        save_data(data)
        
        # [UPDATED] ส่งข้อความแจ้งเตือนผู้กด (Visible only to user)
        await interaction.followup.send(f"✅ เปิด Ticket เรียบร้อยแล้ว: {ticket_chan.mention}", ephemeral=True)

    @discord.ui.button(label=MESSAGES["tf_btn_report"], style=discord.ButtonStyle.red, custom_id="tf_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id: return await interaction.response.send_message(MESSAGES["tf_err_own_report"], ephemeral=True)
        await interaction.response.send_modal(ReportModal(str(interaction.channel.parent_id)))

class ReportModal(discord.ui.Modal, title=MESSAGES["tf_modal_report_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["tf_lbl_reason"], required=True)
    def __init__(self, parent_id):
        super().__init__()
        self.parent_id = parent_id
    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        guild_id = str(interaction.guild_id)
        init_guild_data(data, guild_id)
        configs = data["guilds"][guild_id].get("ticket_configs", {})
        conf = configs.get(self.parent_id)
        
        if conf and conf["log_id"]:
            log = interaction.guild.get_channel(conf["log_id"])
            
            pings = []
            target_ids = set(data["guilds"][guild_id]["admins"] + data["guilds"][guild_id]["supports"])
            for tid in target_ids:
                role = interaction.guild.get_role(tid)
                if role: pings.append(role.mention)
                else: pings.append(f"<@{tid}>")
            
            ping_msg = " ".join(pings) if pings else "@here"

            embed = discord.Embed(title=MESSAGES["tf_log_report_title"], color=discord.Color.orange())
            embed.add_field(name="📍 ฟอรั่ม", value=interaction.channel.mention, inline=False)
            embed.add_field(name="👤 ผู้รายงาน", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.datetime.now()
            
            await log.send(content=f"🚨 **มีการรายงานเข้ามา!** {ping_msg}", embed=embed)
        
        await interaction.response.send_message(MESSAGES["tf_msg_report_success"], ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id, forum_msg_id, count):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.forum_msg_id = forum_msg_id
        self.count = count

    @discord.ui.button(label="เรียกแอดมิน (คนกลาง) 🔔", style=discord.ButtonStyle.blurple, row=0)
    async def call_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        data = load_data()
        guild_id = str(interaction.guild_id)
        init_guild_data(data, guild_id)
        
        pings = []
        target_ids = set(data["guilds"][guild_id]["admins"] + data["guilds"][guild_id]["supports"])
        
        for target_id in target_ids:
            role = interaction.guild.get_role(target_id)
            if role:
                pings.append(role.mention)
            else:
                pings.append(f"<@{target_id}>")
        
        note = ""
        if not pings:
            for member in interaction.guild.members:
                if not member.bot and member.guild_permissions.administrator:
                    pings.append(member.mention)
            note = "\n-# เนื่องจากไม่ได้มีการตั้งค่า admin และ supportadmin ไว้ ระบบจึงเรียกผู้ที่มีสิทธิ์ Administrator แทน"
        
        ping_msg = " ".join(pings) if pings else "@here"
        
        await interaction.channel.send(f"🔔 **มีผู้เรียกคนกลาง/แอดมิน!** {ping_msg}{note}")
        
        button.disabled = True
        button.label = "เรียกแอดมินแล้ว ✅"
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label=MESSAGES["tf_btn_finish"], style=discord.ButtonStyle.green, row=0)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id: return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
        msg = MESSAGES["tf_wait_admin"]
        data = load_data()
        guild_id = str(interaction.guild_id)
        init_guild_data(data, guild_id)
        
        target_ids = set(data["guilds"][guild_id]["admins"] + data["guilds"][guild_id]["supports"])
        pings = []
        for tid in target_ids:
            role = interaction.guild.get_role(tid)
            if role: pings.append(role.mention)
            else: pings.append(f"<@{tid}>")
            
        msg += " " + " ".join(pings)
        
        await interaction.channel.send(msg)
        await interaction.channel.send(MESSAGES["tf_admin_panel_msg"], view=AdminCloseView(self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id, self.count))
        await interaction.response.defer()

    @discord.ui.button(label=MESSAGES["tf_btn_cancel"], style=discord.ButtonStyle.red, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id: return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
        await interaction.response.send_modal(TicketCancelModal(self.log_id, self.buyer_id, self.seller_id, self.forum_thread_id, self.forum_msg_id, self.count))

class TicketCancelModal(discord.ui.Modal, title=MESSAGES["tf_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["tf_lbl_reason"], required=True)
    def __init__(self, log_id, buyer_id, seller_id, forum_thread_id, forum_msg_id, count):
        super().__init__()
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.forum_thread_id = forum_thread_id
        self.forum_msg_id = forum_msg_id
        self.count = count
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.log_id:
            log_chan = interaction.guild.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(title=MESSAGES["tf_log_cancel_title"], description=MESSAGES["tf_log_cancel_desc"].format(count=self.count), color=discord.Color.red())
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🚫 ยกเลิกโดย", value=interaction.user.mention, inline=True)
                embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        
        try:
            forum_thread = interaction.guild.get_channel(self.forum_thread_id)
            if not forum_thread:
                forum_thread = await interaction.guild.fetch_channel(self.forum_thread_id)
            
            if forum_thread:
                msg = await forum_thread.fetch_message(self.forum_msg_id)
                if msg:
                    await msg.edit(view=TicketForumView())
        except Exception as e:
            print(f"Error resetting forum button: {e}")
        
        await interaction.response.send_message(f"ยกเลิกโดย {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        
        data = load_data()
        if "active_tickets" in data and str(interaction.channel_id) in data["active_tickets"]:
            del data["active_tickets"][str(interaction.channel_id)]
            save_data(data)

        await interaction.channel.send(MESSAGES["msg_channel_ready_delete"], view=AdminCloseView(None, None, None, None, None))

class AdminCloseView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id, count):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.count = count

    @discord.ui.button(label=MESSAGES["tf_btn_admin_close"], style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_message(MESSAGES["processing"], ephemeral=True)
        
        if self.log_id and self.count:
            log_chan = interaction.guild.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(title=MESSAGES["tf_log_success_title"], description=MESSAGES["tf_log_success_desc"].format(count=self.count), color=discord.Color.green())
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🔒 ปิดช่องโดย", value=interaction.user.mention, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        
        try: await interaction.channel.delete()
        except: pass
        
        if self.forum_thread_id:
            try:
                thread = interaction.guild.get_channel(self.forum_thread_id)
                if not thread: thread = await interaction.guild.fetch_channel(self.forum_thread_id)
                if thread: await thread.delete()
            except: pass
        
        data = load_data()
        if "active_tickets" in data and str(interaction.channel_id) in data["active_tickets"]:
            del data["active_tickets"][str(interaction.channel_id)]
            save_data(data)

    @discord.ui.button(label=MESSAGES["btn_close_channel"], style=discord.ButtonStyle.danger)
    async def close_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.channel.delete()
        
        data = load_data()
        if "active_tickets" in data and str(interaction.channel_id) in data["active_tickets"]:
            del data["active_tickets"][str(interaction.channel_id)]
            save_data(data)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
