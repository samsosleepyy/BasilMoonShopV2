import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import datetime
import re
from keep_alive import keep_alive 

# =========================================
# CONFIGURATION & DATA MANAGEMENT
# =========================================
DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [],
            "supports": [],
            "auction_count": 0,
            "ticket_count": 0,
            "ticket_configs": {}, 
            "lockdown_time": 0
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

data = load_data()

# ตั้งค่า Intent
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands synced!")

bot = MyBot()

# =========================================
# HELPER FUNCTIONS & CHECKS
# =========================================

def is_admin_or_has_permission(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_roles = [r.id for r in interaction.user.roles]
    
    if user_id in data["admins"] or any(r in data["admins"] for r in user_roles):
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    return False

def is_support_or_admin(interaction: discord.Interaction):
    if is_admin_or_has_permission(interaction):
        return True
    user_id = interaction.user.id
    user_roles = [r.id for r in interaction.user.roles]
    if user_id in data["supports"] or any(r in data["supports"] for r in user_roles):
        return True
    return False

# =========================================
# ADMIN / SUPPORT COMMANDS
# =========================================

@bot.tree.command(name="addadmin", description="เพิ่มสิทธิ์แอดมินให้ผู้ใช้หรือบทบาท")
@app_commands.describe(target="User หรือ Role")
async def addadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    if target.id not in data["admins"]:
        data["admins"].append(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ เพิ่ม {target.mention} เป็นแอดมินบอทแล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removeadmin", description="ลบสิทธิ์แอดมิน")
async def removeadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    if target.id in data["admins"]:
        data["admins"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ ลบ {target.mention} ออกจากแอดมินแล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} ไม่ได้เป็นแอดมิน", ephemeral=True)

@bot.tree.command(name="addsupportadmin", description="เพิ่มสิทธิ์ Support")
async def addsupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    if target.id not in data["supports"]:
        data["supports"].append(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ เพิ่ม {target.mention} เป็น Support แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} เป็น Support อยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removesupportadmin", description="ลบสิทธิ์ Support")
async def removesupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    if target.id in data["supports"]:
        data["supports"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ ลบ {target.mention} ออกจาก Support แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} ไม่ได้เป็น Support", ephemeral=True)

@bot.tree.command(name="lockdown", description="กำหนดเวลาล็อคช่อง (วินาที)")
async def lockdown_cmd(interaction: discord.Interaction, seconds: int):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    data["lockdown_time"] = seconds
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งเวลา Lockdown เป็น {seconds} วินาที", ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตข้อมูลการนับประมูลและ Ticket")
async def resetdata(interaction: discord.Interaction):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    data["auction_count"] = 0
    data["ticket_count"] = 0
    save_data(data)
    await interaction.response.send_message("✅ รีเซ็ตข้อมูล ID เรียบร้อยแล้ว", ephemeral=True)

# =========================================
# AUCTION SYSTEM
# =========================================

@bot.tree.command(name="auction", description="เริ่มระบบประมูล")
@app_commands.describe(
    category="หมวดหมู่สร้างช่อง", channel_send="ช่องส่งข้อความ", message="ข้อความ", 
    approval_channel="ช่องอนุมัติ", role_ping="บทบาทแจ้งเตือน", log_channel="ช่อง Log",
    btn_text="ข้อความปุ่ม", img_link="ลิ้งค์รูป"
)
async def auction(
    interaction: discord.Interaction, 
    category: discord.CategoryChannel,
    channel_send: discord.TextChannel,
    message: str,
    approval_channel: discord.TextChannel,
    role_ping: discord.Role,
    log_channel: discord.TextChannel = None,
    btn_text: str = "💳 เปิดการประมูล",
    img_link: str = None
):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(description=message, color=discord.Color.green())
    if img_link:
        embed.set_image(url=img_link)
    
    view = StartAuctionView(category, approval_channel, role_ping, log_channel, btn_text)
    await channel_send.send(embed=embed, view=view)
    await interaction.followup.send("✅ สร้างข้อความประมูลเรียบร้อย", ephemeral=True)

class StartAuctionView(discord.ui.View):
    def __init__(self, category, approval_channel, role_ping, log_channel, label):
        super().__init__(timeout=None)
        self.category = category
        self.approval_channel = approval_channel
        self.role_ping = role_ping
        self.log_channel = log_channel
        
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn")
        button.callback = self.start_callback
        self.add_item(button)

    async def start_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AuctionModalStep1(self.category, self.approval_channel, self.role_ping, self.log_channel))

class AuctionModalStep1(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่ตัวเลขเท่านั้น", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ใส่ตัวเลขเท่านั้น", required=True)
    close_price = discord.ui.TextInput(label="ราคาปิดประมูล (Auto Buy)", placeholder="ใส่ตัวเลขเท่านั้น", required=True)
    item_name = discord.ui.TextInput(label="สิ่งที่ได้ (ชื่อสินค้า)", required=True)

    def __init__(self, category, approval_channel, role_ping, log_channel):
        super().__init__()
        self.category = category
        self.approval_channel = approval_channel
        self.role_ping = role_ping
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            s_price = int(self.start_price.value)
            b_step = int(self.bid_step.value)
            c_price = int(self.close_price.value)
        except ValueError:
            return await interaction.response.send_message("❌ กรุณากรอกช่องราคาเป็นตัวเลขเท่านั้น", ephemeral=True)

        auction_data = {
            "start_price": s_price,
            "bid_step": b_step,
            "close_price": c_price,
            "item_name": self.item_name.value,
            "category_id": self.category.id,
            "approval_id": self.approval_channel.id,
            "role_ping_id": self.role_ping.id,
            "log_id": self.log_channel.id if self.log_channel else None
        }

        view = Step2View(auction_data)
        await interaction.response.send_message("กรุณากดปุ่มเพื่อกรอกข้อมูลส่วนที่ 2", view=view, ephemeral=True)

class Step2View(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data
    
    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def open_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModalStep2(self.auction_data))

class AuctionModalStep2(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    download_link = discord.ui.TextInput(label="ลิ้งค์ดาวน์โหลดสินค้า", placeholder="ใส่ลิ้งค์ดาวน์โหลดสินค้าของคุณ", required=True)
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="สิทธิ์ขาด-สิทธ์เชิง", required=True)
    extra_info = discord.ui.TextInput(label="เพิ่มเติม", placeholder="บอกว่าสินค้ามาจากที่ใด...", required=False)
    end_time_str = discord.ui.TextInput(label="เวลาปิดประมูล (ชช:นน)", placeholder="เช่น 01:00 คือ 1 ชั่วโมง", required=True)

    def __init__(self, auction_data):
        super().__init__()
        self.auction_data = auction_data

    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.end_time_str.value
        try:
            h, m = map(int, time_str.split(':'))
            total_minutes = (h * 60) + m
            if total_minutes <= 0: raise ValueError
        except:
            return await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง (ใช้ ชช:นน เช่น 01:30)", ephemeral=True)
        
        self.auction_data.update({
            "download_link": self.download_link.value,
            "rights": self.rights.value,
            "extra_info": self.extra_info.value if self.extra_info.value else "-",
            "duration_minutes": total_minutes,
            "seller_id": interaction.user.id
        })

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        for admin_id in data["admins"]:
            member = guild.get_member(admin_id)
            if member: overwrites[member] = discord.PermissionOverwrite(read_messages=True)
        
        channel_name = f"✧꒰ส่งรูปสินค้า📦-{interaction.user.name}꒱"
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites)

        await interaction.response.send_message(f"สร้างช่องส่งรูปแล้วที่ {channel.mention}", ephemeral=True)

        msg = await channel.send(
            f"{interaction.user.mention} ส่งรูปสินค้าของคุณที่ช่องนี้📦\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่"
        )
        
        bot.loop.create_task(self.wait_for_images(channel, interaction.user, self.auction_data))

    async def wait_for_images(self, channel, user, auction_data):
        def check(m):
            return m.author.id == user.id and m.channel.id == channel.id and m.attachments

        try:
            # 1. Product Image
            await channel.send(f"มีเวลา 3 นาทีในการส่งรูปสินค้าของคุณที่ {channel.mention}", delete_after=180)
            msg1 = await bot.wait_for('message', check=check, timeout=180)
            auction_data["img_product_url"] = msg1.attachments[0].url

            # 2. QR Code
            await channel.send("โปรดส่งรูป QR code หรือช่องทางการชำระเงิน🧾\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่")
            msg2 = await bot.wait_for('message', check=check, timeout=180)
            auction_data["img_qr_url"] = msg2.attachments[0].url

            await channel.send("ได้รับรูปสินค้าเรียบร้อย📥 รอแอดมินยืนยัน⏳")

            # Send to Approval Channel (อัปเดตใหม่: แสดงข้อมูลครบ)
            approval_channel = bot.get_channel(auction_data["approval_id"])
            if approval_channel:
                embed = discord.Embed(title="คำขอเปิดประมูลใหม่", color=discord.Color.gold())
                embed.add_field(name="ผู้ขาย", value=f"<@{auction_data['seller_id']}>", inline=False)
                embed.add_field(name="สินค้า", value=auction_data['item_name'], inline=True)
                embed.add_field(name="ราคาเริ่ม", value=f"{auction_data['start_price']}", inline=True)
                embed.add_field(name="บิดครั้งละ", value=f"{auction_data['bid_step']}", inline=True)
                embed.add_field(name="ราคาปิด", value=f"{auction_data['close_price']}", inline=True)
                embed.add_field(name="สิทธิ์", value=f"{auction_data['rights']}", inline=True)
                embed.add_field(name="เวลาประมูล", value=f"{auction_data['duration_minutes']} นาที", inline=True)
                embed.add_field(name="ลิ้งค์สินค้า", value=f"{auction_data['download_link']}", inline=False)
                embed.add_field(name="เพิ่มเติม", value=f"{auction_data['extra_info']}", inline=False)
                
                embed.set_image(url=auction_data['img_product_url'])
                embed.set_thumbnail(url=auction_data['img_qr_url']) 
                
                view = ApprovalView(auction_data, channel) 
                await approval_channel.send(embed=embed, view=view)

        except asyncio.TimeoutError:
            await channel.delete()

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data, temp_channel):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.temp_channel = temp_channel

    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.temp_channel:
            await self.temp_channel.delete()
        
        guild = interaction.guild
        category = guild.get_channel(self.auction_data["category_id"])
        
        data["auction_count"] += 1
        save_data(data)
        
        channel_name = f"ประมูลครั้งที่-{data['auction_count']}-ราคา-{self.auction_data['start_price']}"
        auction_channel = await guild.create_text_channel(channel_name, category=category)
        
        ping_role = guild.get_role(self.auction_data["role_ping_id"])
        if ping_role:
            await auction_channel.send(ping_role.mention, delete_after=5)

        end_time = datetime.datetime.now() + datetime.timedelta(minutes=self.auction_data["duration_minutes"])
        timestamp = int(end_time.timestamp())

        embed = discord.Embed(description=f"# ˚₊‧꒰ა ☆ ໒꒱ ‧₊˚\n*เปิดประมูล!*", color=discord.Color.purple())
        embed.add_field(name="ᯓ★ โดย", value=f"<@{self.auction_data['seller_id']}>", inline=False)
        embed.add_field(name="ᯓ★ ราคาเริ่มต้น", value=f"{self.auction_data['start_price']}", inline=True)
        embed.add_field(name="ᯓ★ บิดครั้งละ", value=f"{self.auction_data['bid_step']}", inline=True)
        embed.add_field(name="ᯓ★ ราคาปิดประมูล", value=f"{self.auction_data['close_price']}", inline=True)
        embed.add_field(name="ᯓ★ สิ่งที่ได้", value=f"{self.auction_data['item_name']}", inline=True)
        embed.add_field(name="ᯓ★ สิทธิ์", value=f"{self.auction_data['rights']}", inline=True)
        embed.add_field(name="ᯓ★ เพิ่มเติม", value=f"{self.auction_data['extra_info']}", inline=False)
        embed.add_field(name="-ˋˏ✄┈┈┈┈", value=f"**เวลาปิดประมูล : <t:{timestamp}:R>**", inline=False)
        embed.set_image(url=self.auction_data['img_product_url'])
        
        view = AuctionControlView(self.auction_data['seller_id'])
        msg = await auction_channel.send(embed=embed, view=view)

        self.auction_data['channel_id'] = auction_channel.id
        self.auction_data['current_price'] = self.auction_data['start_price']
        self.auction_data['end_time'] = end_time
        self.auction_data['winner_id'] = None
        self.auction_data['message_id'] = msg.id
        self.auction_data['active'] = True
        
        active_auctions[auction_channel.id] = self.auction_data
        
        bot.loop.create_task(auction_countdown(auction_channel.id))
        
        await interaction.followup.send(f"✅ อนุมัติการประมูล สร้างห้องที่ {auction_channel.mention}")
        self.stop()

    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyModal(self.auction_data, self.temp_channel))

class DenyModal(discord.ui.Modal, title="เหตุผลการไม่อนุมัติ"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)

    def __init__(self, auction_data, temp_channel):
        super().__init__()
        self.auction_data = auction_data
        self.temp_channel = temp_channel

    async def on_submit(self, interaction: discord.Interaction):
        if self.temp_channel: await self.temp_channel.delete()
        
        log_id = self.auction_data["log_id"]
        if log_id:
            log_chan = bot.get_channel(log_id)
            seller = f"<@{self.auction_data['seller_id']}>"
            admin = interaction.user.mention
            await log_chan.send(f"⊹ [{seller}] .ᐟ⊹\nประมูลของคุณไม่ได้รับอนุมัติจากแอดมิน : {admin}❌\nเหตุผล : {self.reason.value}")
        
        await interaction.response.send_message("❌ ปฏิเสธการประมูลแล้ว", ephemeral=True)

class AuctionControlView(discord.ui.View):
    def __init__(self, seller_id):
        super().__init__(timeout=None)
        self.seller_id = seller_id

    @discord.ui.button(label="🧾ปิดประมูล", style=discord.ButtonStyle.red)
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id or is_admin_or_has_permission(interaction):
            chan_id = interaction.channel_id
            if chan_id in active_auctions:
                active_auctions[chan_id]['end_time'] = datetime.datetime.now() 
                await interaction.response.send_message("กำลังปิดประมูล...", ephemeral=True)
            else:
                await interaction.response.send_message("เกิดข้อผิดพลาด ไม่พบข้อมูลการประมูล", ephemeral=True)
        else:
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)

active_auctions = {} 

async def auction_countdown(channel_id):
    while channel_id in active_auctions:
        data = active_auctions[channel_id]
        now = datetime.datetime.now()
        
        if not data['active']: break

        if now >= data['end_time']:
            await end_auction_logic(channel_id)
            break
            
        await asyncio.sleep(5)

async def end_auction_logic(channel_id):
    if channel_id not in active_auctions: return
    auction_data = active_auctions[channel_id]
    auction_data['active'] = False
    
    channel = bot.get_channel(channel_id)
    if not channel: return

    winner_id = auction_data['winner_id']
    seller_id = auction_data['seller_id']
    
    if winner_id is None:
        if auction_data['log_id']:
            log = bot.get_channel(auction_data['log_id'])
            embed = discord.Embed(description=f"การประมูลครั้งที่ - {data['auction_count']}\nโดย <@{seller_id}>\nการประมูลหมดเวลา", color=discord.Color.yellow())
            await log.send(embed=embed)
        await channel.delete()
        del active_auctions[channel_id]
        return

    await channel.send(
        f"📜 | <@{winner_id}> ชนะการประมูลครั้งที่ - {data['auction_count']}\n"
        f"จบที่ราคา - {auction_data['current_price']} บ.-\n"
        f"-# ช่องนี้กำลังจะถูกล็อคภายใน {data['lockdown_time']} วินาทีเพื่อทำธุรกรรม🔐"
    )

    await asyncio.sleep(data['lockdown_time'])

    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.get_member(seller_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.get_member(winner_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    for admin_id in data["admins"]:
        mem = guild.get_member(admin_id)
        if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True)
    
    await channel.edit(overwrites=overwrites)
    
    embed = discord.Embed(description=f"ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\n(<@{winner_id}> ผู้ชนะประมูล) สามารถชำระเงินได้เลย", color=discord.Color.green())
    embed.add_field(name="ปุ่มสำหรับผู้เปิดประมูล", value="ด้านล่าง")
    embed.set_image(url=auction_data['img_qr_url'])
    
    view = TransactionView(seller_id, winner_id, auction_data)
    await channel.send(content=f"<@{winner_id}>", embed=embed, view=view)

class TransactionView(discord.ui.View):
    def __init__(self, seller_id, winner_id, auction_data):
        super().__init__(timeout=None)
        self.seller_id = seller_id
        self.winner_id = winner_id
        self.auction_data = auction_data

    @discord.ui.button(label="ยืนยันเสร็จสิ้น✅", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction):
             return await interaction.response.send_message("กดได้แค่ผู้เปิดประมูลหรือแอดมิน", ephemeral=True)
        
        view = ConfirmFinalView(self.auction_data, interaction.channel)
        await interaction.response.send_message("ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว ทางเราจะไม่รับผิดชอบใดๆ", view=view, ephemeral=True)

    @discord.ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction):
             return await interaction.response.send_message("กดได้แค่ผู้เปิดประมูลหรือแอดมิน", ephemeral=True)
        
        await interaction.response.send_modal(CancelReasonModal(self.auction_data, interaction.channel))

class ConfirmFinalView(discord.ui.View):
    def __init__(self, auction_data, channel):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.channel = channel

    @discord.ui.button(label="ยืนยันอีกครั้ง", style=discord.ButtonStyle.green)
    async def double_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() # รอการประมวลผล (ส่ง DM)

        # 1. ส่ง DM หาผู้ชนะ
        winner_id = self.auction_data['winner_id']
        download_link = self.auction_data['download_link']
        dm_msg = "✅ ส่งลิ้งค์สินค้าทาง DM แล้ว"
        
        try:
            winner = interaction.guild.get_member(winner_id)
            if not winner:
                winner = await bot.fetch_user(winner_id)
            
            await winner.send(f"ดาวน์โหลดสินค้าของคุณ {download_link}")
        except:
            dm_msg = f"⚠️ ไม่สามารถส่ง DM หา <@{winner_id}> ได้ (เขาอาจปิด DM)"

        await interaction.followup.send(f"{dm_msg}\nยืนยันเรียบร้อย ลบช่องใน 1 นาที...", ephemeral=True)
        
        # 2. Log Success
        if self.auction_data['log_id']:
            log = bot.get_channel(self.auction_data['log_id'])
            embed = discord.Embed(
                description=f"── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──\n╭﹕การประมูลครั้งที่ - {data['auction_count']}\n | ﹕โดย <@{self.auction_data['seller_id']}>\n | ﹕ผู้ชนะประมูล <@{self.auction_data['winner_id']}>\n╰ ﹕จบที่ราคา : {self.auction_data['current_price']}",
                color=discord.Color.green()
            )
            embed.set_image(url=self.auction_data['img_product_url'])
            await log.send(embed=embed)
        
        await asyncio.sleep(60)
        if self.channel: await self.channel.delete()
        if self.channel.id in active_auctions: del active_auctions[self.channel.id]

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, auction_data, channel):
        super().__init__()
        self.auction_data = auction_data
        self.channel = channel
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.auction_data['log_id']:
            log = bot.get_channel(self.auction_data['log_id'])
            embed = discord.Embed(
                description=f"╭﹕การประมูลครั้งที่ - {data['auction_count']}\n | ﹕โดย <@{self.auction_data['seller_id']}>\n | ﹕ถูกยกเลิกโดย {interaction.user.mention}\n╰ ﹕เหตุผล : {self.reason.value}",
                color=discord.Color.red()
            )
            await log.send(embed=embed)
        
        await interaction.response.send_message("ยกเลิกเรียบร้อย ลบช่องใน 5 วินาที", ephemeral=True)
        await asyncio.sleep(5)
        if self.channel: await self.channel.delete()
        if self.channel.id in active_auctions: del active_auctions[self.channel.id]

# =========================================
# BIDDING LOGIC (On Message)
# =========================================
@bot.event
async def on_message(message):
    if message.author.bot: return

    if message.channel.id in active_auctions and active_auctions[message.channel.id]['active']:
        content = message.content.strip()
        match = re.match(r'^บิด\s*(\d+)', content)
        
        if match:
            amount = int(match.group(1))
            auction_data = active_auctions[message.channel.id]
            current = auction_data['current_price']
            step = auction_data['bid_step']
            close_price = auction_data['close_price']
            
            if amount < current + step:
                return 

            old_winner = auction_data['winner_id']
            auction_data['current_price'] = amount
            auction_data['winner_id'] = message.author.id
            
            response_text = f"# {message.author.mention} ราคา {amount}"
            if old_winner and old_winner != message.author.id:
                 response_text += f"\n<@{old_winner}> โดนนำแล้ว!"

            is_auto_buy = amount >= close_price
            if is_auto_buy:
                 response_text += "\n-# ⚠️ตอนนี้ราคาถึงราคาปิดประมูลแล้วจะปิดประมูลอัตโนมัติทันทีหากไม่มีการประมูลเพิ่มภายใน 10 นาที"
                 auction_data['end_time'] = datetime.datetime.now() + datetime.timedelta(minutes=10)
            
            sent_msg = await message.reply(response_text)
            
            last_rename = auction_data.get('last_rename', 0)
            import time
            if time.time() - last_rename > 30:
                try:
                    new_name = f"ประมูลครั้งที่-{data['auction_count']}-ราคา-{amount}"
                    await message.channel.edit(name=new_name)
                    auction_data['last_rename'] = time.time()
                except: pass

    await bot.process_commands(message)

# =========================================
# TICKET FORUM SYSTEM (/ticketf)
# =========================================

@bot.tree.command(name="ticketf", description="ตั้งค่าระบบ Ticket Forum")
async def ticketf(interaction: discord.Interaction, category: discord.CategoryChannel, forum: discord.ForumChannel, log_channel: discord.TextChannel = None):
    if not is_admin_or_has_permission(interaction):
        return await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
    
    data["ticket_configs"][str(forum.id)] = {
        "category_id": category.id,
        "log_id": log_channel.id if log_channel else None
    }
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งค่า Ticket Forum ที่ {forum.mention} เรียบร้อย", ephemeral=True)

@bot.event
async def on_thread_create(thread):
    if str(thread.parent_id) in data["ticket_configs"]:
        await asyncio.sleep(1) 
        view = TicketForumView()
        await thread.send("กดสั่งซื้อตรงนี้", view=view)

class TicketForumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="สั่งซื้อ (Tickets)", style=discord.ButtonStyle.green, custom_id="tf_buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        conf = data["ticket_configs"].get(str(interaction.channel.parent_id))
        if not conf: return
        
        data["ticket_count"] += 1
        save_data(data)
        
        guild = interaction.guild
        category = guild.get_channel(conf["category_id"])
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True), 
            interaction.channel.owner: discord.PermissionOverwrite(read_messages=True), 
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        
        chan_name = f"ID-{data['ticket_count']}"
        ticket_chan = await guild.create_text_channel(chan_name, category=category, overwrites=overwrites)
        
        msg = f"ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\nสามารถทำธุรกรรมได้เลย\n{interaction.user.mention} {interaction.channel.owner.mention}"
        view = TicketControlView(interaction.channel.id) 
        await ticket_chan.send(msg, view=view)
        
        await interaction.response.send_message(f"สร้างห้องสั่งซื้อแล้วที่ {ticket_chan.mention}", ephemeral=True)

    @discord.ui.button(label="รายงาน", style=discord.ButtonStyle.red, custom_id="tf_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id:
             return await interaction.response.send_message("เจ้าของโพสต์รายงานตัวเองไม่ได้", ephemeral=True)
        await interaction.response.send_modal(ReportModal(str(interaction.channel.parent_id)))

class ReportModal(discord.ui.Modal, title="รายงานโพสต์"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, parent_id):
        super().__init__()
        self.parent_id = parent_id

    async def on_submit(self, interaction: discord.Interaction):
        conf = data["ticket_configs"].get(self.parent_id)
        if conf and conf["log_id"]:
            log = bot.get_channel(conf["log_id"])
            await log.send(f"⚠️ มีการรายงานฟอรั่ม {interaction.channel.mention}\nโดย: {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        await interaction.response.send_message("ส่งรายงานเรียบร้อย", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, forum_thread_id):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id

    @discord.ui.button(label="เสร็จสิ้น(ปิดช่อง)", style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = "เรียกแอดมินมาตรวจสอบ..."
        for sid in data["supports"]:
            msg += f" <@{sid}>"
        await interaction.channel.send(msg)
        
        view = AdminCloseView(self.forum_thread_id)
        await interaction.channel.send("ปุ่มสำหรับแอดมิน:", view=view)
        await interaction.response.defer()

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCancelModal())

class TicketCancelModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"ยกเลิกโดย {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class AdminCloseView(discord.ui.View):
    def __init__(self, forum_thread_id):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id

    @discord.ui.button(label="ปิดช่องและลบโพสต์", style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction):
            return await interaction.response.send_message("เฉพาะแอดมิน/Support", ephemeral=True)
            
        await interaction.response.send_message("กำลังดำเนินการ...", ephemeral=True)
        
        try:
            await interaction.channel.delete()
        except: pass
        
        try:
            thread = bot.get_channel(self.forum_thread_id)
            if thread: await thread.delete()
        except: pass

# =========================================
# START BOT
# =========================================

keep_alive() 
token = os.environ.get("DISCORD_TOKEN") 

if token:
    bot.run(token)
else:
    print("กรุณาตั้งค่า DISCORD_TOKEN ใน Environment Variables")
