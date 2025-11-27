import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import datetime
import re

# --- CONFIGURATION ---
TOKEN = 'YOUR_BOT_TOKEN_HERE'  # ใส่ Token หรือใช้ os.getenv('TOKEN') สำหรับ Render
GUILD_ID = discord.Object(id=1420339720277463112) # ใส่ ID ของ Server คุณ (ตัวเลข)

# --- DATA MANAGEMENT ---
DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [], # รายชื่อ user_id หรือ role_id
            "supports": [],
            "auction_count": 0,
            "ticket_count": 0,
            "lockdown_seconds": 60, # ค่า default
            "active_auctions": {} # เก็บ state ของการประมูลที่กำลังวิ่งอยู่
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

bot_data = load_data()

# --- BOT SETUP ---
class Client(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=GUILD_ID)
        await self.tree.sync(guild=GUILD_ID)
        self.check_auctions.start()
        self.update_channel_names.start()

client = Client()

# --- HELPER FUNCTIONS ---
def is_admin(interaction: discord.Interaction):
    user_id = interaction.user.id
    role_ids = [r.id for r in interaction.user.roles]
    if interaction.user.guild_permissions.administrator:
        return True
    if user_id in bot_data["admins"]:
        return True
    for rid in role_ids:
        if rid in bot_data["admins"]:
            return True
    return False

def is_support(interaction: discord.Interaction):
    if is_admin(interaction): return True
    user_id = interaction.user.id
    role_ids = [r.id for r in interaction.user.roles]
    if user_id in bot_data["supports"]:
        return True
    for rid in role_ids:
        if rid in bot_data["supports"]:
            return True
    return False

# --- MODALS & VIEWS (UI) ---

class AuctionModal1(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น (ตัวเลข)", placeholder="เช่น 100", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ (ตัวเลข)", placeholder="เช่น 10", required=True)
    close_price = discord.ui.TextInput(label="ราคาปิดประมูล (ตัวเลข)", placeholder="เช่น 1000", required=True)
    item_name = discord.ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate numbers
        try:
            sp = int(self.start_price.value)
            bs = int(self.bid_step.value)
            cp = int(self.close_price.value)
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกช่องราคาเป็นตัวเลขเท่านั้น", ephemeral=True)
            return

        # Pass data to next step via a hidden state or temporary storage
        # Here we use a View to trigger the next Modal
        view = AuctionStep2View(
            start_price=sp, bid_step=bs, close_price=cp, item_name=self.item_name.value,
            config=self.config # Passing config from initial command
        )
        await interaction.response.send_message("กรอกข้อมูลส่วนแรกเรียบร้อย โปรดกดปุ่มด้านล่างเพื่อกรอกส่วนที่ 2", view=view, ephemeral=True)

    def __init__(self, config):
        super().__init__()
        self.config = config

class AuctionModal2(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    download_link = discord.ui.TextInput(label="ลิ้งค์ดาวน์โหลดสินค้า", placeholder="ใส่ลิ้งค์ดาวน์โหลดสินค้าของคุณ", required=True)
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="สิทธิ์ขาด-สิทธ์เชิง", required=True)
    extra_info = discord.ui.TextInput(label="เพิ่มเติม", placeholder="บอกว่าสินค้ามาจากที่ใด...", required=False)
    close_time = discord.ui.TextInput(label="เวลาปิดประมูล (ชช:นน)", placeholder="เช่น 01:00 คือ 1 ชั่วโมง", required=True)

    def __init__(self, data_step1, config):
        super().__init__()
        self.data_step1 = data_step1
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        # Validate Time
        time_str = self.close_time.value
        try:
            hours, minutes = map(int, time_str.split(':'))
            total_seconds = (hours * 3600) + (minutes * 60)
            if total_seconds <= 0: raise ValueError
        except:
            await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง (ชช:นน)", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Create Temp Channel for Image Upload
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Add admin perms to view
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        cat = self.config['category']
        temp_channel = await guild.create_text_channel(
            name=f"✧꒰ส่งรูปสินค้า📦 {interaction.user.name}꒱",
            category=cat,
            overwrites=overwrites
        )

        await interaction.followup.send(f"ไปที่ห้อง {temp_channel.mention} เพื่อส่งรูปภาพ", ephemeral=True)

        # Instruction in temp channel
        await temp_channel.send(
            f"{interaction.user.mention} ส่งรูปสินค้าของคุณที่ช่องนี้📦\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่"
        )

        # Process Logic (Store context and start waiting)
        # Using create_task to handle the wait flow without blocking
        asyncio.create_task(process_image_upload(
            guild, temp_channel, interaction.user, 
            self.data_step1, 
            {
                "download_link": self.download_link.value,
                "rights": self.rights.value,
                "extra_info": self.extra_info.value,
                "duration": total_seconds
            },
            self.config
        ))

class AuctionStep2View(discord.ui.View):
    def __init__(self, start_price, bid_step, close_price, item_name, config):
        super().__init__(timeout=None)
        self.data_step1 = {
            "start_price": start_price, "bid_step": bid_step, 
            "close_price": close_price, "item_name": item_name
        }
        self.config = config

    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def open_modal_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModal2(self.data_step1, self.config))

class AuctionStartView(discord.ui.View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config

    @discord.ui.button(label="💳 เปิดการประมูล", style=discord.ButtonStyle.success, custom_id="start_auction_btn")
    async def start_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModal1(self.config))

class AdminApprovalView(discord.ui.View):
    def __init__(self, auction_data, user_id, temp_channel_id, config):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.user_id = user_id
        self.temp_channel_id = temp_channel_id
        self.config = config

    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("อนุมัติเรียบร้อย กำลังสร้างห้องประมูล...", ephemeral=True)
        await start_public_auction(interaction, self.auction_data, self.user_id, self.temp_channel_id, self.config)
        self.stop()

    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyReasonModal(self.user_id, self.temp_channel_id, self.config))

class DenyReasonModal(discord.ui.Modal, title="เหตุผลการไม่อนุมัติ"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)

    def __init__(self, user_id, temp_channel_id, config):
        super().__init__()
        self.user_id = user_id
        self.temp_channel_id = temp_channel_id
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = self.config['log_channel']
        if log_channel:
            embed = discord.Embed(description=f"⊹ [<@{self.user_id}>] .ᐟ⊹\nประมูลของคุณไม่ได้รับอนุมัติจากแอดมิน : {interaction.user.mention} ({self.reason.value})❌\nเหตุผล : {self.reason.value}", color=discord.Color.red())
            await log_channel.send(embed=embed)
        
        # Delete temp channel
        channel = interaction.guild.get_channel(self.temp_channel_id)
        if channel:
            await channel.delete()
        await interaction.response.send_message("ดำเนินการไม่อนุมัติเรียบร้อย", ephemeral=True)

class AuctionPaymentView(discord.ui.View):
    def __init__(self, host_id, winner_id, channel_id, log_channel, img_url, price, item_name):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.winner_id = winner_id
        self.channel_id = channel_id
        self.log_channel = log_channel
        self.img_url = img_url
        self.price = price
        self.item_name = item_name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.host_id or is_admin(interaction):
            return True
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
        return False

    @discord.ui.button(label="ยืนยันเสร็จสิ้น✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Double confirm logic per requirement
        view = ConfirmSuccessView(self.host_id, self.channel_id, self.log_channel, self.img_url, self.winner_id, self.price, self.item_name)
        await interaction.response.send_message("ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว ทางเราจะไม่รับผิดชอบใดๆ", view=view, ephemeral=True)

    @discord.ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CancelReasonModal(self.host_id, self.winner_id, self.log_channel))

class ConfirmSuccessView(discord.ui.View):
    def __init__(self, host_id, channel_id, log_channel, img_url, winner_id, price, item_name):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.channel_id = channel_id
        self.log_channel = log_channel
        self.img_url = img_url
        self.winner_id = winner_id
        self.price = price
        self.item_name = item_name

    @discord.ui.button(label="ยืนยัน", style=discord.ButtonStyle.success)
    async def real_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ดำเนินการเสร็จสิ้น กำลังลบห้องใน 1 นาที...", ephemeral=True)
        
        # Log Success
        if self.log_channel:
            embed = discord.Embed(color=discord.Color.green())
            embed.description = f"── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──\n╭﹕การประมูลสินค้า: {self.item_name}\n | ﹕โดย <@{self.host_id}>\n | ﹕ผู้ชนะประมูล <@{self.winner_id}>\n╰ ﹕จบที่ราคา : {self.price}"
            embed.set_image(url=self.img_url)
            await self.log_channel.send(embed=embed)

        await asyncio.sleep(60)
        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            await channel.delete()

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)

    def __init__(self, host_id, winner_id, log_channel):
        super().__init__()
        self.host_id = host_id
        self.winner_id = winner_id
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        if self.log_channel:
            embed = discord.Embed(color=discord.Color.red())
            embed.description = f"╭﹕การประมูล\n | ﹕โดย <@{self.host_id}>\n | ﹕ถูกยกเลิกโดย {interaction.user.mention}\n╰ ﹕เหตุผล : {self.reason.value}"
            await self.log_channel.send(embed=embed)
        await interaction.response.send_message("บันทึกการยกเลิกเรียบร้อย", ephemeral=True)

class CloseAuctionEarlyView(discord.ui.View):
    def __init__(self, host_id):
        super().__init__(timeout=None)
        self.host_id = host_id

    @discord.ui.button(label="🧾ปิดประมูล (กดได้แค่ผู้เปิดประมูลหรือแอดมิน)", style=discord.ButtonStyle.danger)
    async def close_early(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.host_id or is_admin(interaction):
            # Trigger close logic immediately
            channel_id = str(interaction.channel_id)
            if channel_id in bot_data['active_auctions']:
                bot_data['active_auctions'][channel_id]['end_time'] = datetime.datetime.now().timestamp()
                save_data(bot_data)
                await interaction.response.send_message("กำลังปิดการประมูล...", ephemeral=True)
            else:
                 await interaction.response.send_message("เกิดข้อผิดพลาดในการหาข้อมูลการประมูล", ephemeral=True)
        else:
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)

# --- TICKET / FORUM LOGIC ---
class TicketBuyView(discord.ui.View):
    def __init__(self, seller_id, log_channel_id):
        super().__init__(timeout=None)
        self.seller_id = seller_id
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="สั่งซื้อ (Tickets)", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id:
             await interaction.response.send_message("คุณไม่สามารถซื้อของตัวเองได้", ephemeral=True)
             return

        bot_data['ticket_count'] += 1
        save_data(bot_data)
        
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            guild.get_member(self.seller_id): discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        
        # Add support admins
        for uid in bot_data['supports']:
            mem = guild.get_member(uid)
            if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True)
        
        channel = await guild.create_text_channel(
            name=f"ID-{bot_data['ticket_count']}",
            category=interaction.channel.category if interaction.channel.category else None,
            overwrites=overwrites
        )

        await channel.send(f"ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\nสามารถทำธุรกรรมได้เลย\n<@{self.seller_id}> <@{interaction.user.id}>", view=TicketControlView(self.seller_id, interaction.user.id, interaction.channel.id))
        await interaction.response.send_message(f"สร้างห้องสั่งซื้อแล้วที่ {channel.mention}", ephemeral=True)

    @discord.ui.button(label="รายงาน", style=discord.ButtonStyle.danger)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketReportModal(self.log_channel_id))

class TicketControlView(discord.ui.View):
    def __init__(self, seller_id, buyer_id, forum_thread_id):
        super().__init__(timeout=None)
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.forum_thread_id = forum_thread_id

    @discord.ui.button(label="เสร็จสิ้น(ปิดช่อง)", style=discord.ButtonStyle.success)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = f"แอดมินมาตรวจสอบและปิดช่องได้เลยครับ\n"
        # Mention support roles/users
        supports = []
        for uid in bot_data['supports']:
            supports.append(f"<@{uid}>")
        msg += " ".join(supports)
        
        view = AdminCloseTicketView(self.forum_thread_id)
        await interaction.channel.send(msg, view=view)
        await interaction.response.send_message("แจ้งแอดมินเรียบร้อย", ephemeral=True)

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCancelModal())

class AdminCloseTicketView(discord.ui.View):
    def __init__(self, forum_thread_id):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id

    @discord.ui.button(label="ปิดช่อง (Admin)", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support(interaction):
            await interaction.response.send_message("เฉพาะ Support Admin", ephemeral=True)
            return
        
        # Close/Lock Forum Thread
        try:
            thread = interaction.guild.get_thread(self.forum_thread_id) or interaction.guild.get_channel(self.forum_thread_id)
            if thread:
                await thread.edit(locked=True, archived=True)
        except:
            pass
        
        await interaction.channel.delete()

class TicketReportModal(discord.ui.Modal, title="รายงาน"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, log_channel_id):
        super().__init__()
        self.log_channel_id = log_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.log_channel_id:
            chan = interaction.guild.get_channel(self.log_channel_id)
            if chan: await chan.send(f"รายงานจาก {interaction.user.mention}: {self.reason.value}")
        await interaction.response.send_message("ส่งรายงานแล้ว", ephemeral=True)

class TicketCancelModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"ยกเลิกโดย {interaction.user.mention} เหตุผล: {self.reason.value}")
        await interaction.response.send_message("บันทึกแล้ว", ephemeral=True)

# --- LOGIC FUNCTIONS ---

async def process_image_upload(guild, channel, user, data1, data2, config):
    def check(m):
        return m.channel.id == channel.id and m.author.id == user.id and m.attachments

    img1_url = None
    img2_url = None

    try:
        # Wait for Item Image (3 mins)
        msg1 = await client.wait_for('message', check=check, timeout=180.0)
        img1_url = msg1.attachments[0].url
    except asyncio.TimeoutError:
        await channel.delete()
        return

    await channel.send("โปรดส่งรูป QR code หรือช่องทางการชำระเงิน🧾\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่")

    try:
        # Wait for QR Image (No specific timeout mentioned in 2nd step, assuming same or standard)
        msg2 = await client.wait_for('message', check=check, timeout=180.0)
        img2_url = msg2.attachments[0].url
    except asyncio.TimeoutError:
        await channel.delete()
        return
    
    await channel.send("ได้รับรูปสินค้าเรียบร้อย📥 รอแอดมินยืนยัน⏳")

    # Send to Approve Channel
    approve_channel = config['approve_channel']
    if approve_channel:
        embed = discord.Embed(title="คำขอเปิดประมูล", description=f"โดย: {user.mention}", color=discord.Color.blue())
        embed.add_field(name="สินค้า", value=data1['item_name'])
        embed.add_field(name="ราคาเริ่ม", value=data1['start_price'])
        embed.set_image(url=img1_url)
        # Send QR as separate message or thumbnail? User said "send product img and 2nd round img"
        
        view = AdminApprovalView(
            auction_data={**data1, **data2, "img1": img1_url, "img2": img2_url},
            user_id=user.id,
            temp_channel_id=channel.id,
            config=config
        )
        await approve_channel.send(embed=embed, view=view)
        await approve_channel.send(f"QR Code/Payment: {img2_url}") # Sending as link/msg

async def start_public_auction(interaction, data, user_id, temp_channel_id, config):
    bot_data['auction_count'] += 1
    category = config['category']
    guild = interaction.guild
    
    # Create Auction Channel
    channel_name = f"ประมูลครั้งที่-{bot_data['auction_count']}-ราคา-{data['start_price']}"
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    auction_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

    # Ping Role
    role_to_ping = config['role_ping']
    if role_to_ping:
        await auction_channel.send(role_to_ping.mention, delete_after=5)

    end_timestamp = datetime.datetime.now().timestamp() + data['duration']

    embed = discord.Embed(description=f"# ˚₊‧꒰ა ☆ ໒꒱ ‧₊˚\n      *เปิดประมูล!*\n\nᯓ★ โดย : <@{user_id}>\nᯓ★ ราคาเริ่มต้น : {data['start_price']}\nᯓ★ บิดครั้งละ : {data['bid_step']}\nᯓ★ ราคาปิดประมูล : {data['close_price']}\nᯓ★ สิ่งที่ได้ : {data['item_name']}\nᯓ★ สิทธิ์ : {data['rights']}\nᯓ★ เพิ่มเติม : {data['extra_info']}\n\n-ˋˏ✄┈┈┈┈\n\n**เวลาปิดประมูล : <t:{int(end_timestamp)}:R>**", color=discord.Color.gold())
    embed.set_image(url=data['img1'])
    
    msg = await auction_channel.send(embed=embed, view=CloseAuctionEarlyView(user_id))

    # Save Auction State
    bot_data['active_auctions'][str(auction_channel.id)] = {
        "host_id": user_id,
        "current_price": data['start_price'],
        "bid_step": data['bid_step'],
        "close_price": data['close_price'],
        "end_time": end_timestamp,
        "last_bidder": None,
        "message_id": msg.id,
        "img1": data['img1'],
        "img2": data['img2'],
        "item_name": data['item_name'],
        "auction_num": bot_data['auction_count'],
        "log_channel_id": config['log_channel'].id if config['log_channel'] else None,
        "buyout_triggered": False,
        "ended": False
    }
    save_data(bot_data)
    
    # Delete temp channel
    temp_chan = guild.get_channel(temp_channel_id)
    if temp_chan: await temp_chan.delete()

# --- COMMANDS ---

@client.tree.command(name="addadmin", description="เพิ่มสิทธิ์แอดมิน")
@app_commands.describe(user="เลือกผู้ใช้", role="เลือกบทบาท")
async def addadmin(interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator: # Only server admin can add bot admin
        return await interaction.response.send_message("คุณไม่มีสิทธิ์", ephemeral=True)
    
    target_id = user.id if user else role.id if role else None
    if not target_id: return await interaction.response.send_message("ระบุ user หรือ role", ephemeral=True)
    
    if target_id not in bot_data["admins"]:
        bot_data["admins"].append(target_id)
        save_data(bot_data)
        await interaction.response.send_message(f"เพิ่ม {user.mention if user else role.mention} เป็น Admin แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message("มีสิทธิ์อยู่แล้ว", ephemeral=True)

@client.tree.command(name="removeadmin", description="ลบสิทธิ์แอดมิน")
async def removeadmin(interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("คุณไม่มีสิทธิ์", ephemeral=True)
    
    target_id = user.id if user else role.id if role else None
    if target_id in bot_data["admins"]:
        bot_data["admins"].remove(target_id)
        save_data(bot_data)
        await interaction.response.send_message(f"ลบสิทธิ์ Admin แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message("ไม่พบข้อมูล", ephemeral=True)

@client.tree.command(name="addsupportadmin", description="เพิ่มสิทธิ์ support")
async def addsupport(interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    target_id = user.id if user else role.id if role else None
    if target_id not in bot_data["supports"]:
        bot_data["supports"].append(target_id)
        save_data(bot_data)
        await interaction.response.send_message("เพิ่ม Support แล้ว", ephemeral=True)

@client.tree.command(name="removesupportadmin", description="ลบสิทธิ์ support")
async def removesupport(interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    target_id = user.id if user else role.id if role else None
    if target_id in bot_data["supports"]:
        bot_data["supports"].remove(target_id)
        save_data(bot_data)
        await interaction.response.send_message("ลบ Support แล้ว", ephemeral=True)

@client.tree.command(name="lockdown", description="กำหนดเวลาล็อคช่อง (วินาที)")
async def lockdown(interaction: discord.Interaction, seconds: int):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    bot_data["lockdown_seconds"] = seconds
    save_data(bot_data)
    await interaction.response.send_message(f"ตั้งค่า lockdown เป็น {seconds} วินาที", ephemeral=True)

@client.tree.command(name="resetdata", description="รีเซ็ตข้อมูลจำนวนการประมูลและตั๋ว")
async def resetdata(interaction: discord.Interaction):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    bot_data["auction_count"] = 0
    bot_data["ticket_count"] = 0
    save_data(bot_data)
    await interaction.response.send_message("Reset Data เรียบร้อย", ephemeral=True)

@client.tree.command(name="auction", description="สร้างห้องและปุ่มเปิดประมูล")
async def auction(interaction: discord.Interaction, category: discord.CategoryChannel, channel_send: discord.TextChannel, message: str, approve_channel: discord.TextChannel, role_ping: discord.Role, log_channel: discord.TextChannel = None, btn_text: str = "💳 เปิดการประมูล", img_link: str = None):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    
    embed = discord.Embed(description=message, color=discord.Color.green())
    if img_link: embed.set_image(url=img_link)
    
    # Store config for this session in the View
    config = {
        'category': category,
        'approve_channel': approve_channel,
        'role_ping': role_ping,
        'log_channel': log_channel,
        'channel_send': channel_send
    }
    
    view = AuctionStartView(config)
    # Customize button label
    view.children[0].label = btn_text
    
    await channel_send.send(embed=embed, view=view)
    await interaction.response.send_message("ติดตั้งระบบประมูลเรียบร้อย", ephemeral=True)

@client.tree.command(name="ticketf", description="สร้างระบบ Ticket ใน Forum")
async def ticketf(interaction: discord.Interaction, category: discord.CategoryChannel, forum_channel: discord.ForumChannel, log_channel: discord.TextChannel = None):
    if not is_admin(interaction): return await interaction.response.send_message("ต้องเป็น Admin", ephemeral=True)
    # This command just registers/saves logic or instructs. Since forum threads are dynamic, we handle "on_thread_create" or check message inside forum.
    # But user said "When user create forum... bot send message". So we need to watch this forum channel.
    # We'll save the monitored forum channel ID.
    if "monitored_forums" not in bot_data: bot_data["monitored_forums"] = {}
    bot_data["monitored_forums"][str(forum_channel.id)] = {"log": log_channel.id if log_channel else None}
    save_data(bot_data)
    await interaction.response.send_message(f"ติดตั้งระบบ Ticket บน Forum {forum_channel.mention} เรียบร้อย", ephemeral=True)

# --- EVENTS ---

@client.event
async def on_thread_create(thread):
    # Check if thread is in monitored forum
    if str(thread.parent_id) in bot_data.get("monitored_forums", {}):
        await asyncio.sleep(1) # wait a bit
        log_id = bot_data["monitored_forums"][str(thread.parent_id)]["log"]
        view = TicketBuyView(thread.owner_id, log_id)
        await thread.send("กดสั่งซื้อตรงนี้", view=view)

@client.event
async def on_message(message):
    if message.author.bot: return

    # AUCTION BIDDING LOGIC
    chan_id = str(message.channel.id)
    if chan_id in bot_data['active_auctions']:
        auction = bot_data['active_auctions'][chan_id]
        if auction['ended']: return

        # Check for "บิด [price]"
        match = re.search(r"บิด\s*(\d+)", message.content)
        if match:
            bid_amount = int(match.group(1))
            current = auction['current_price']
            step = auction['bid_step']
            
            # Validation
            if bid_amount < current + step:
                # Silently ignore or warn? User didn't specify error msg for low bid, just logic.
                return 

            # Update State
            previous_bidder = auction['last_bidder']
            auction['current_price'] = bid_amount
            auction['last_bidder'] = message.author.id
            
            reply_msg = f"# {message.author.mention} ราคา {bid_amount}"
            
            if previous_bidder and previous_bidder != message.author.id:
                reply_msg += f"\n<@{previous_bidder}> โดนนำแล้ว!"

            # Buyout Logic
            if bid_amount >= auction['close_price'] and not auction['buyout_triggered']:
                auction['buyout_triggered'] = True
                reply_msg += "\n-# ⚠️ตอนนี้ราคาถึงราคาปิดประมูลแล้วจะปิดประมูลอัตโนมัติทันทีหากไม่มีการประมูลเพิ่มภายใน 10 นาที"
                # Reset timer to 10 mins from now
                auction['end_time'] = datetime.datetime.now().timestamp() + 600

            elif auction['buyout_triggered']:
                # Extension if someone bids again after buyout trigger
                auction['end_time'] = datetime.datetime.now().timestamp() + 600

            save_data(bot_data)

            # Reply and Delete old user message if possible? User said "Reply to message". 
            # "If new bid, delete old price and write new". This implies bot's previous confirmation message.
            # We need to track the bot's last bid confirmation message.
            if 'last_bot_msg' in auction:
                try:
                    old_msg = await message.channel.fetch_message(auction['last_bot_msg'])
                    await old_msg.delete()
                except: pass
            
            sent_msg = await message.channel.send(reply_msg, reference=message)
            auction['last_bot_msg'] = sent_msg.id
            
            # Update Main Embed (optional but good for UX)
            try:
                main_msg = await message.channel.fetch_message(auction['message_id'])
                embed = main_msg.embeds[0]
                # Modify description or fields to show current price (Parsing embed desc is hard, better to reconstruct)
                # For simplicity, we assume users look at the latest message for price as per "reply" logic
                # But we should update the Time in embed if it changed due to extension
                embed.description = embed.description.replace(f"ราคาเริ่มต้น : {current}", f"ราคาเริ่มต้น : {bid_amount}") # Just a hacky visual update
                embed.description = re.sub(r"<t:\d+:R>", f"<t:{int(auction['end_time'])}:R>", embed.description)
                await main_msg.edit(embed=embed)
            except: pass

# --- BACKGROUND TASKS ---

@tasks.loop(seconds=1)
async def check_auctions():
    now = datetime.datetime.now().timestamp()
    to_remove = []
    
    for chan_id, auction in bot_data['active_auctions'].items():
        if auction['ended']: continue

        if now >= auction['end_time']:
            auction['ended'] = True
            save_data(bot_data)
            
            channel = client.get_channel(int(chan_id))
            if not channel:
                to_remove.append(chan_id)
                continue

            # Lockdown
            guild = channel.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            # Admin roles
            for uid in bot_data['admins']:
                mem = guild.get_member(uid)
                if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Winner & Host
            if auction['last_bidder']:
                winner = guild.get_member(auction['last_bidder'])
                if winner: overwrites[winner] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            host = guild.get_member(auction['host_id'])
            if host: overwrites[host] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            await channel.edit(overwrites=overwrites)

            if not auction['last_bidder']:
                # No Bids
                log_c = client.get_channel(auction['log_channel_id']) if auction['log_channel_id'] else None
                if log_c:
                    embed = discord.Embed(description=f"การประมูลครั้งที่ - {auction['auction_num']}\nโดย <@{auction['host_id']}>\nการประมูลหมดเวลา", color=discord.Color.gold())
                    await log_c.send(embed=embed)
                await channel.delete()
                to_remove.append(chan_id)
            else:
                # Has Winner
                await channel.send(f"📜 | <@{auction['last_bidder']}> ชนะการประมูลครั้งที่ - {auction['auction_num']}\nจบที่ราคา - {auction['current_price']} บ.-\n-# ช่องนี้กำลังจะถูกล็อคภายใน {bot_data['lockdown_seconds']} วินาทีเพื่อทำธุรกรรม🔐")
                
                # Wait lockdown seconds (Non-blocking sleep in loop is bad, but for simplicity we rely on async flow or separate task. 
                # Better: schedule a coroutine)
                asyncio.create_task(finalize_auction_channel(channel, auction))

    for rid in to_remove:
        del bot_data['active_auctions'][rid]
    save_data(bot_data)

async def finalize_auction_channel(channel, auction):
    await asyncio.sleep(bot_data['lockdown_seconds'])
    
    msg_text = f"ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\n(<@{auction['last_bidder']}> ผู้ชนะประมูล) สามารถชำระเงินได้เลย\n-# ปุ่มสำหรับผู้เปิดประมูล"
    
    # Send QR (Img2) again
    await channel.send(msg_text)
    await channel.send(f"{auction['img2']}") 
    
    log_c = client.get_channel(auction['log_channel_id']) if auction['log_channel_id'] else None
    
    view = AuctionPaymentView(
        auction['host_id'], auction['last_bidder'], channel.id, log_c, 
        auction['img1'], auction['current_price'], auction['item_name']
    )
    await channel.send("เลือกดำเนินการ:", view=view)

@tasks.loop(seconds=30)
async def update_channel_names():
    # Update active auction channel names to show current price
    # Bypass rate limit by doing it infrequently
    for chan_id, auction in bot_data['active_auctions'].items():
        if not auction['ended']:
            channel = client.get_channel(int(chan_id))
            if channel:
                new_name = f"ประมูลครั้งที่-{auction['auction_num']}-ราคา-{auction['current_price']}"
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name)
                    except:
                        pass # Rate limit hit or permission error

# --- RUN ---
client.run(TOKEN)
