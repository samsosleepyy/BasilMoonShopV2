import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio # เพิ่มแล้ว
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, is_support_or_admin

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketf", description=MESSAGES["desc_ticketf"])
    async def ticketf(self, interaction: discord.Interaction, category: discord.CategoryChannel, forum: discord.ForumChannel, log_channel: discord.TextChannel = None):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        data = load_data()
        data["ticket_configs"][str(forum.id)] = {"category_id": category.id, "log_id": log_channel.id if log_channel else None}
        save_data(data)
        await interaction.response.send_message(MESSAGES["tf_setup_success"].format(forum=forum.mention), ephemeral=True)

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        data = load_data()
        if str(thread.parent_id) in data["ticket_configs"]:
            await asyncio.sleep(1)
            await thread.send(MESSAGES["tf_guide_msg"], view=TicketForumView())

class TicketForumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label=MESSAGES["tf_btn_buy"], style=discord.ButtonStyle.green, custom_id="tf_buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id: return await interaction.response.send_message(MESSAGES["tf_err_own_post"], ephemeral=True)
        data = load_data()
        conf = data["ticket_configs"].get(str(interaction.channel.parent_id))
        if not conf: return
        button.disabled = True
        button.label = MESSAGES["tf_btn_buying"]
        button.style = discord.ButtonStyle.gray
        await interaction.response.edit_message(view=self)
        data["ticket_count"] += 1
        save_data(data)
        category = interaction.guild.get_channel(conf["category_id"])
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),interaction.user: discord.PermissionOverwrite(read_messages=True),interaction.channel.owner: discord.PermissionOverwrite(read_messages=True),interaction.guild.me: discord.PermissionOverwrite(read_messages=True)}
        chan_name = f"ID-{data['ticket_count']}"
        ticket_chan = await interaction.guild.create_text_channel(chan_name, category=category, overwrites=overwrites)
        msg = MESSAGES["tf_room_created"].format(buyer=interaction.user.mention, seller=interaction.channel.owner.mention)
        view = TicketControlView(interaction.channel.id, conf["log_id"], interaction.user.id, interaction.channel.owner_id, interaction.message.id)
        await ticket_chan.send(msg, view=view)
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
        conf = data["ticket_configs"].get(self.parent_id)
        if conf and conf["log_id"]:
            log = interaction.guild.get_channel(conf["log_id"])
            embed = discord.Embed(title=MESSAGES["tf_log_report_title"], color=discord.Color.orange())
            embed.add_field(name="📍 ฟอรั่ม", value=interaction.channel.mention, inline=False)
            embed.add_field(name="👤 ผู้รายงาน", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.datetime.now()
            await log.send(embed=embed)
        await interaction.response.send_message(MESSAGES["msg_report_success"], ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id, forum_msg_id):
        super().__init__(timeout=None)
        self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id, self.forum_msg_id = forum_thread_id, log_id, buyer_id, seller_id, forum_msg_id
    @discord.ui.button(label=MESSAGES["tf_btn_finish"], style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id: return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
        msg = MESSAGES["tf_wait_admin"]
        data = load_data()
        for sid in data["supports"]: msg += f" <@{sid}>"
        await interaction.channel.send(msg)
        await interaction.channel.send(MESSAGES["tf_admin_panel_msg"], view=AdminCloseView(self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id))
        await interaction.response.defer()
    @discord.ui.button(label=MESSAGES["tf_btn_cancel"], style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id: return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
        await interaction.response.send_modal(TicketCancelModal(self.log_id, self.buyer_id, self.seller_id, self.forum_thread_id, self.forum_msg_id))

class TicketCancelModal(discord.ui.Modal, title=MESSAGES["tf_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["tf_lbl_reason"], required=True)
    def __init__(self, log_id, buyer_id, seller_id, forum_thread_id, forum_msg_id):
        super().__init__()
        self.log_id, self.buyer_id, self.seller_id, self.forum_thread_id, self.forum_msg_id = log_id, buyer_id, seller_id, forum_thread_id, forum_msg_id
    async def on_submit(self, interaction: discord.Interaction):
        if self.log_id:
            log_chan = interaction.guild.get_channel(self.log_id)
            if log_chan:
                data = load_data()
                embed = discord.Embed(title=MESSAGES["tf_log_cancel_title"], description=MESSAGES["tf_log_cancel_desc"].format(count=data['ticket_count']), color=discord.Color.red())
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🚫 ยกเลิกโดย", value=interaction.user.mention, inline=True)
                embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        try:
            forum_thread = interaction.guild.get_channel(self.forum_thread_id)
            if forum_thread:
                msg = await forum_thread.fetch_message(self.forum_msg_id)
                if msg: await msg.edit(view=TicketForumView())
        except: pass
        await interaction.response.send_message(f"ยกเลิกโดย {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class AdminCloseView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id):
        super().__init__(timeout=None)
        self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id = forum_thread_id, log_id, buyer_id, seller_id
    @discord.ui.button(label=MESSAGES["tf_btn_admin_close"], style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_message(MESSAGES["processing"], ephemeral=True)
        if self.log_id:
            log_chan = interaction.guild.get_channel(self.log_id)
            if log_chan:
                data = load_data()
                embed = discord.Embed(title=MESSAGES["tf_log_success_title"], description=MESSAGES["tf_log_success_desc"].format(count=data["ticket_count"]), color=discord.Color.green())
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🔒 ปิดช่องโดย", value=interaction.user.mention, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        try: await interaction.channel.delete()
        except: pass
        try:
            thread = interaction.guild.get_channel(self.forum_thread_id)
            if thread: await thread.delete()
        except: pass

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
