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
                except Exception as e:
                    print(f"Failed to restore ticket control view {channel_id}: {e}")
        print(f"✅ Restored {count} active ticket controls.")

    @app_commands.command(name="ticket-forums", description=MESSAGES["desc_ticketf"])
    async def ticket_forums(self, interaction: discord.Interaction, category: discord.CategoryChannel, forum: discord.ForumChannel, log_channel: discord.TextChannel = None):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        
        if str(forum.id) not in data["guilds"][str(interaction.guild_id)]["ticket_configs"]:
             data["guilds"][str(interaction.guild_id)]["ticket_configs"][str(forum.id)] = {}
        
        data["guilds"][str(interaction.guild_id)]["ticket_configs"][str(forum.id)] = {"category_id": category.id, "log_id": log_channel.id if log_channel else None}
        save_data(data)
        await interaction.response.send_message(MESSAGES["tf_setup_success"].format(forum=forum.mention), ephemeral=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        data = load_data()
        guild_id = str(thread.guild.id)
        init_guild_data(data, guild_id)
        configs = data["guilds"][guild_id].get("ticket_configs", {})
        
        if str(thread.parent_id) in configs:
            await asyncio.sleep(1)
            await thread.send(MESSAGES["tf_guide_msg"], view=TicketForumView())

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
        
        msg = MESSAGES["tf_room_created"].format(buyer=interaction.user.mention, seller=interaction.channel.owner.mention)
        
        view = TicketControlView(interaction.channel.id, conf["log_id"], interaction.user.id, interaction.channel.owner_id, interaction.message.id, count)
        await ticket_chan.send(msg, view=view)

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
            
            # [NEW] สร้างข้อความ Ping Admin & Support
            pings = []
            # หา Admin
            for admin_id in data.get("admins", []):
                if interaction.guild.get_role(admin_id): pings.append(f"<@&{admin_id}>")
                else: pings.append(f"<@{admin_id}>")
            # หา Support
            for sup_id in data.get("supports", []):
                if interaction.guild.get_role(sup_id): pings.append(f"<@&{sup_id}>")
                else: pings.append(f"<@{sup_id}>")
            
            ping_msg = " ".join(pings) if pings else "-# ยังมีมีการเพิ่ม supportadmin" # ถ้าไม่มีใครให้ ping @here แทน

            embed = discord.Embed(title=MESSAGES["tf_log_report_title"], color=discord.Color.orange())
            embed.add_field(name="📍 ฟอรั่ม", value=interaction.channel.mention, inline=False)
            embed.add_field(name="👤 ผู้รายงาน", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.datetime.now()
            
            # ส่ง Embed พร้อม Ping
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

    @discord.ui.button(label=MESSAGES["tf_btn_finish"], style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id: return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
        msg = MESSAGES["tf_wait_admin"]
        data = load_data()
        for sid in data["supports"]: msg += f" <@{sid}>"
        await interaction.channel.send(msg)
        await interaction.channel.send(MESSAGES["tf_admin_panel_msg"], view=AdminCloseView(self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id, self.count))
        await interaction.response.defer()

    @discord.ui.button(label=MESSAGES["tf_btn_cancel"], style=discord.ButtonStyle.red)
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
