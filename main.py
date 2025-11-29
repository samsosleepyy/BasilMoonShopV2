import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import datetime
import re
import aiohttp
import io
from keep_alive import keep_alive

# =========================================
# 📝 CONFIGURATION & TEXT MESSAGES (แก้ไขข้อความตรงนี้)
# =========================================
MESSAGES = {
    # --- ข้อความระบบทั่วไป ---
    "no_permission": "🚫 คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
    "cmd_success": "✅ ดำเนินการเรียบร้อย",
    "loading": "⏳ กำลังประมวลผล...",
    
    # --- ข้อความ Auction (เริ่มประมูล) ---
    "auc_btn_default": "💳 เปิดการประมูล",
    "auc_step1_title": "📝 ข้อมูลการประมูล (1/2)",
    "auc_step2_title": "📝 ข้อมูลการประมูล (2/2)",
    "auc_created_channel": "✅ สร้างช่องส่งรูปแล้วที่ {channel}",
    "auc_wait_img_1": "{user} 📦 ส่งรูปสินค้าของคุณที่ช่องนี้\n-# **สามารถส่งได้หลายรูปใน 1 ข้อความ** เพื่อให้แสดงเป็นอัลบั้มรวม",
    "auc_wait_img_2": "🧾 โปรดส่งรูป QR code หรือช่องทางการชำระเงิน\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่",
    "auc_img_received": "📥 ได้รับรูปสินค้าเรียบร้อย รอแอดมินยืนยัน ⏳",
    
    # --- ข้อความ Auction (อนุมัติ/แสดงผล) ---
    "auc_embed_title": "# ˚₊‧꒰ა ☆ ໒꒱ ‧₊˚\n*🔥 เปิดประมูล!*",
    "auc_admin_approve_log": "✅ อนุมัติการประมูล สร้างห้องที่ {channel}",
    "auc_admin_deny_reason": "เหตุผลการไม่อนุมัติ",
    "auc_deny_msg": "❌ ปฏิเสธการประมูลแล้ว",
    "auc_deny_log": "🚫 **ไม่อนุมัติการประมูล**\n👤 ผู้ขาย: {seller}\n👮 โดยแอดมิน: {admin}\n📝 เหตุผล: {reason}",
    
    # --- ข้อความ Auction (จบ/ยกเลิก) ---
    "auc_end_winner": "🎉 **จบการประมูล!**\n📜 ครั้งที่ {count} | ผู้ชนะ: {winner}\n💰 จบที่ราคา: **{price} บาท**\n-# 🔐 ช่องนี้จะถูกล็อคใน {time} วินาที",
    "auc_end_no_bid": "⚠️ **การประมูลจบลง (ไม่มีผู้ประมูล)**\n📜 ครั้งที่ {count} | ผู้ขาย: {seller}",
    "auc_lock_msg": "🔐 **ช่องนี้เป็นส่วนตัวแล้ว**\n({winner} ผู้ชนะประมูล) สามารถชำระเงินได้เลยครับ",
    "auc_success_log": "── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──\n╭﹕📜 ประมูลครั้งที่ - {count}\n | ﹕👤 โดย {seller}\n | ﹕🏆 ผู้ชนะ {winner}\n╰ ﹕💰 จบที่ราคา : {price}",
    "auc_cancel_log": "╭﹕🚫 **ยกเลิกการประมูล** ครั้งที่ {count}\n | ﹕👤 โดย {seller}\n | ﹕❌ ยกเลิกโดย {user}\n╰ ﹕📝 เหตุผล : {reason}",
    "auc_dm_success": "✅ ส่งลิ้งค์สินค้าทาง DM แล้วครับ",
    "auc_dm_fail": "⚠️ ไม่สามารถส่ง DM หา {user} ได้ (เขาอาจปิด DM)",
    "auc_dm_content": "📦 **ดาวน์โหลดสินค้าของคุณ:**\n{link}",

    # --- ข้อความ Ticket Forum ---
    "tf_btn_buy": "🛒 สั่งซื้อ (Tickets)",
    "tf_btn_report": "🚩 รายงาน",
    "tf_err_own_post": "❌ คุณไม่สามารถสั่งซื้อสินค้าของตัวเองได้",
    "tf_err_own_report": "❌ คุณไม่สามารถรายงานโพสต์ของตัวเองได้",
    "tf_only_seller": "🚫 เฉพาะ **ผู้ขาย** เท่านั้นที่สามารถกดปุ่มนี้ได้",
    "tf_room_created": "🔐 **ช่องซื้อขายส่วนตัว**\n👤 ผู้ซื้อ: {buyer}\n👤 ผู้ขาย: {seller}\n-# สามารถเจรจาและโอนเงินได้เลยครับ",
    "tf_log_report": "🚩 **มีการรายงานโพสต์**\n📍 ฟอรั่ม: {channel}\n👤 โดย: {user}\n📝 เหตุผล: {reason}",
    "tf_log_cancel_title": "❌ 𝗧𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱",
    "tf_log_cancel_desc": "รายการถูกยกเลิก (Ticket ID-{count})",
    "tf_log_success_title": "✅ 𝗧𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱",
    "tf_log_success_desc": "ธุรกรรมเสร็จสิ้น (Ticket ID-{count})",
    "tf_wait_admin": "🔔 กำลังเรียกแอดมินมาตรวจสอบ...",
}

DATA_FILE = "data.json"

# =========================================
# DATA MANAGEMENT & SETUP
# =========================================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [], "supports": [], "auction_count": 0, "ticket_count": 0,
            "ticket_configs": {}, "lockdown_time": 0
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

data = load_data()
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# =========================================
# HELPER FUNCTIONS
# =========================================
def is_admin_or_has_permission(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_roles = [r.id for r in interaction.user.roles]
    if user_id in data["admins"] or any(r in data["admins"] for r in user_roles): return True
    if interaction.user.guild_permissions.administrator: return True
    return False

def is_support_or_admin(interaction: discord.Interaction):
    if is_admin_or_has_permission(interaction): return True
    user_id = interaction.user.id
    user_roles = [r.id for r in interaction.user.roles]
    if user_id in data["supports"] or any(r in data["supports"] for r in user_roles): return True
    return False

async def get_files_from_urls(urls):
    files = []
    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(urls):
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        files.append(discord.File(io.BytesIO(data), filename=f"image_{i}.png"))
            except: pass
    return files

# =========================================
# SYSTEM COMMANDS
# =========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="addadmin", description="เพิ่มสิทธิ์แอดมิน")
async def addadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id not in data["admins"]:
        data["admins"].append(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ เพิ่ม {target.mention} เป็นแอดมิน", ephemeral=True)
    else: await interaction.response.send_message("เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removeadmin", description="ลบสิทธิ์แอดมิน")
async def removeadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id in data["admins"]:
        data["admins"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ ลบ {target.mention} แล้ว", ephemeral=True)
    else: await interaction.response.send_message("ไม่ได้เป็นแอดมิน", ephemeral=True)

@bot.tree.command(name="addsupportadmin", description="เพิ่มสิทธิ์ Support")
async def addsupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id not in data["supports"]:
        data["supports"].append(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ เพิ่ม {target.mention} เป็น Support", ephemeral=True)
    else: await interaction.response.send_message("เป็น Support อยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removesupportadmin", description="ลบสิทธิ์ Support")
async def removesupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id in data["supports"]:
        data["supports"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(f"✅ ลบ {target.mention} แล้ว", ephemeral=True)
    else: await interaction.response.send_message("ไม่ได้เป็น Support", ephemeral=True)

@bot.tree.command(name="lockdown", description="กำหนดเวลาล็อคช่อง (วินาที)")
async def lockdown_cmd(interaction: discord.Interaction, seconds: int):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    data["lockdown_time"] = seconds
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งเวลา Lockdown: {seconds} วินาที", ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตข้อมูล ID")
async def resetdata(interaction: discord.Interaction):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    data["auction_count"] = 0
    data["ticket_count"] = 0
    save_data(data)
    await interaction.response.send_message("✅ รีเซ็ตข้อมูลเรียบร้อย", ephemeral=True)

# =========================================
# AUCTION SYSTEM
# =========================================
@bot.tree.command(name="auction", description="เริ่มระบบประมูล")
async def auction(interaction: discord.Interaction, category: discord.CategoryChannel, channel_send: discord.TextChannel, message: str, approval_channel: discord.TextChannel, role_ping: discord.Role, log_channel: discord.TextChannel = None, btn_text: str = None, img_link: str = None):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    
    embed = discord.Embed(description=message, color=discord.Color.green())
    if img_link: embed.set_image(url=img_link)
    
    label = btn_text if btn_text else MESSAGES["auc_btn_default"]
    view = StartAuctionView(category, approval_channel, role_ping, log_channel, label)
    await channel_send.send(embed=embed, view=view)
    await interaction.followup.send(MESSAGES["cmd_success"], ephemeral=True)

class StartAuctionView(discord.ui.View):
    def __init__(self, category, approval_channel, role_ping, log_channel, label):
        super().__init__(timeout=None)
        self.category, self.approval_channel, self.role_ping, self.log_channel = category, approval_channel, role_ping, log_channel
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn")
        button.callback = self.start_callback
        self.add_item(button)

    async def start_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AuctionModalStep1(self.category, self.approval_channel, self.role_ping, self.log_channel))

class AuctionModalStep1(discord.ui.Modal, title=MESSAGES["auc_step1_title"]):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ตัวเลขเท่านั้น", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ตัวเลขเท่านั้น", required=True)
    close_price = discord.ui.TextInput(label="ราคาปิดประมูล (Auto Buy)", placeholder="ตัวเลขเท่านั้น", required=True)
    item_name = discord.ui.TextInput(label="สิ่งที่ได้ (ชื่อสินค้า)", required=True)

    def __init__(self, category, approval_channel, role_ping, log_channel):
        super().__init__()
        self.category, self.approval_channel, self.role_ping, self.log_channel = category, approval_channel, role_ping, log_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            auction_data = {
                "start_price": int(self.start_price.value),
                "bid_step": int(self.bid_step.value),
                "close_price": int(self.close_price.value),
                "item_name": self.item_name.value,
                "category_id": self.category.id,
                "approval_id": self.approval_channel.id,
                "role_ping_id": self.role_ping.id,
                "log_id": self.log_channel.id if self.log_channel else None
            }
            view = Step2View(auction_data)
            await interaction.response.send_message("กดปุ่มเพื่อกรอกข้อมูลส่วนที่ 2", view=view, ephemeral=True)
        except ValueError: await interaction.response.send_message("❌ กรอกตัวเลขเท่านั้น", ephemeral=True)

class Step2View(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data
    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def open_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModalStep2(self.auction_data))

class AuctionModalStep2(discord.ui.Modal, title=MESSAGES["auc_step2_title"]):
    download_link = discord.ui.TextInput(label="ลิ้งค์ดาวน์โหลดสินค้า", required=True)
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="สิทธิ์ขาด-สิทธ์เชิง", required=True)
    extra_info = discord.ui.TextInput(label="เพิ่มเติม", required=False)
    end_time_str = discord.ui.TextInput(label="เวลาปิดประมูล (ชช:นน)", placeholder="เช่น 01:00", required=True)

    def __init__(self, auction_data):
        super().__init__()
        self.auction_data = auction_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            h, m = map(int, self.end_time_str.value.split(':'))
            total_minutes = (h * 60) + m
            if total_minutes <= 0: raise ValueError
            
            self.auction_data.update({
                "download_link": self.download_link.value, "rights": self.rights.value,
                "extra_info": self.extra_info.value if self.extra_info.value else "-",
                "duration_minutes": total_minutes, "seller_id": interaction.user.id
            })
            
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for admin_id in data["admins"]:
                member = interaction.guild.get_member(admin_id)
                if member: overwrites[member] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await interaction.guild.create_text_channel(f"✧꒰ส่งรูปสินค้า📦-{interaction.user.name}꒱", overwrites=overwrites)
            await interaction.response.send_message(MESSAGES["auc_created_channel"].format(channel=channel.mention), ephemeral=True)
            bot.loop.create_task(self.wait_for_images(channel, interaction.user, self.auction_data))
        except: await interaction.response.send_message("❌ เวลาไม่ถูกต้อง", ephemeral=True)

    async def wait_for_images(self, channel, user, auction_data):
        def check(m): return m.author.id == user.id and m.channel.id == channel.id and m.attachments
        try:
            await channel.send(MESSAGES["auc_wait_img_1"].format(user=user.mention), delete_after=300)
            msg1 = await bot.wait_for('message', check=check, timeout=300)
            auction_data["img_product_urls"] = [att.url for att in msg1.attachments]

            await channel.send(MESSAGES["auc_wait_img_2"])
            msg2 = await bot.wait_for('message', check=check, timeout=300)
            auction_data["img_qr_url"] = msg2.attachments[0].url

            await channel.send(MESSAGES["auc_img_received"])

            approval_channel = bot.get_channel(auction_data["approval_id"])
            if approval_channel:
                base_embed = discord.Embed(title="คำขอเปิดประมูลใหม่", color=discord.Color.gold())
                base_embed.add_field(name="ผู้ขาย", value=f"<@{auction_data['seller_id']}>", inline=False)
                base_embed.add_field(name="สินค้า", value=auction_data['item_name'], inline=True)
                base_embed.add_field(name="ราคาเริ่ม", value=f"{auction_data['start_price']}", inline=True)
                base_embed.add_field(name="บิดครั้งละ", value=f"{auction_data['bid_step']}", inline=True)
                base_embed.add_field(name="ราคาปิด", value=f"{auction_data['close_price']}", inline=True)
                base_embed.add_field(name="สิทธิ์", value=f"{auction_data['rights']}", inline=True)
                base_embed.add_field(name="เวลาประมูล", value=f"{auction_data['duration_minutes']} นาที", inline=True)
                base_embed.add_field(name="ลิ้งค์สินค้า", value=f"{auction_data['download_link']}", inline=False)
                base_embed.add_field(name="เพิ่มเติม", value=f"{auction_data['extra_info']}", inline=False)
                base_embed.set_thumbnail(url=auction_data['img_qr_url'])
                
                files_to_send = await get_files_from_urls(auction_data["img_product_urls"])
                view = ApprovalView(auction_data, channel)
                await approval_channel.send(embed=base_embed, files=files_to_send, view=view)
        except asyncio.TimeoutError: await channel.delete()

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data, temp_channel):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel = auction_data, temp_channel

    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.temp_channel: await self.temp_channel.delete()
        
        category = interaction.guild.get_channel(self.auction_data["category_id"])
        data["auction_count"] += 1
        save_data(data)
        
        auction_channel = await interaction.guild.create_text_channel(f"ประมูลครั้งที่-{data['auction_count']}-ราคา-{self.auction_data['start_price']}", category=category)
        
        ping_role = interaction.guild.get_role(self.auction_data["role_ping_id"])
        if ping_role: await auction_channel.send(ping_role.mention, delete_after=5)

        end_time = datetime.datetime.now() + datetime.timedelta(minutes=self.auction_data["duration_minutes"])
        timestamp = int(end_time.timestamp())

        main_embed = discord.Embed(description=MESSAGES["auc_embed_title"], color=discord.Color.purple())
        main_embed.add_field(name="ᯓ★ โดย", value=f"<@{self.auction_data['seller_id']}>", inline=False)
        main_embed.add_field(name="ᯓ★ ราคาเริ่มต้น", value=f"{self.auction_data['start_price']}", inline=True)
        main_embed.add_field(name="ᯓ★ บิดครั้งละ", value=f"{self.auction_data['bid_step']}", inline=True)
        main_embed.add_field(name="ᯓ★ ราคาปิดประมูล", value=f"{self.auction_data['close_price']}", inline=True)
        main_embed.add_field(name="ᯓ★ สิ่งที่ได้", value=f"{self.auction_data['item_name']}", inline=True)
        main_embed.add_field(name="ᯓ★ สิทธิ์", value=f"{self.auction_data['rights']}", inline=True)
        main_embed.add_field(name="ᯓ★ เพิ่มเติม", value=f"{self.auction_data['extra_info']}", inline=False)
        main_embed.add_field(name="-ˋˏ✄┈┈┈┈", value=f"**เวลาปิดประมูล : <t:{timestamp}:R>**", inline=False)
        
        files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
        
        view = AuctionControlView(self.auction_data['seller_id'])
        msg = await auction_channel.send(embed=main_embed, view=view)
        if files_to_send:
            await auction_channel.send(files=files_to_send)

        self.auction_data.update({
            'channel_id': auction_channel.id, 'current_price': self.auction_data['start_price'],
            'end_time': end_time, 'winner_id': None, 'message_id': msg.id, 'active': True, 'last_bid_msg_id': None
        })
        active_auctions[auction_channel.id] = self.auction_data
        bot.loop.create_task(auction_countdown(auction_channel.id))
        
        await interaction.followup.send(MESSAGES["auc_admin_approve_log"].format(channel=auction_channel.mention))
        self.stop()

    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyModal(self.auction_data, self.temp_channel))

class DenyModal(discord.ui.Modal, title=MESSAGES["auc_admin_deny_reason"]):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, auction_data, temp_channel):
        super().__init__()
        self.auction_data, self.temp_channel = auction_data, temp_channel
    async def on_submit(self, interaction: discord.Interaction):
        if self.temp_channel: await self.temp_channel.delete()
        if self.auction_data["log_id"]:
            log_chan = bot.get_channel(self.auction_data["log_id"])
            seller_mention = f"<@{self.auction_data['seller_id']}>"
            await log_chan.send(MESSAGES["auc_deny_log"].format(seller=seller_mention, admin=interaction.user.mention, reason=self.reason.value))
        await interaction.response.send_message(MESSAGES["auc_deny_msg"], ephemeral=True)

class AuctionControlView(discord.ui.View):
    def __init__(self, seller_id):
        super().__init__(timeout=None)
        self.seller_id = seller_id
    @discord.ui.button(label="🧾ปิดประมูล", style=discord.ButtonStyle.red)
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id or is_admin_or_has_permission(interaction):
            if interaction.channel_id in active_auctions:
                active_auctions[interaction.channel_id]['end_time'] = datetime.datetime.now()
                await interaction.response.send_message("กำลังปิดประมูล...", ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)

active_auctions = {} 

async def auction_countdown(channel_id):
    while channel_id in active_auctions:
        data = active_auctions[channel_id]
        if not data['active']: break
        if datetime.datetime.now() >= data['end_time']:
            await end_auction_logic(channel_id)
            break
        await asyncio.sleep(5)

async def end_auction_logic(channel_id):
    if channel_id not in active_auctions: return
    auction_data = active_auctions[channel_id]
    auction_data['active'] = False
    channel = bot.get_channel(channel_id)
    if not channel: return

    winner_id, seller_id = auction_data['winner_id'], auction_data['seller_id']
    seller_mention = f"<@{seller_id}>"
    
    if winner_id is None:
        if auction_data['log_id']:
            log = bot.get_channel(auction_data['log_id'])
            embed = discord.Embed(description=MESSAGES["auc_end_no_bid"].format(count=data['auction_count'], seller=seller_mention), color=discord.Color.yellow())
            await log.send(embed=embed)
        await channel.delete()
        del active_auctions[channel_id]
        return

    winner_mention = f"<@{winner_id}>"
    await channel.send(MESSAGES["auc_end_winner"].format(winner=winner_mention, count=data['auction_count'], price=auction_data['current_price'], time=data['lockdown_time']))
    await asyncio.sleep(data['lockdown_time'])

    overwrites = {
        channel.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        channel.guild.get_member(seller_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
        channel.guild.get_member(winner_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
        channel.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    for admin_id in data["admins"]:
        mem = channel.guild.get_member(admin_id)
        if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True)
    
    await channel.edit(overwrites=overwrites)
    
    embed = discord.Embed(description=MESSAGES["auc_lock_msg"].format(winner=winner_mention), color=discord.Color.green())
    embed.add_field(name="ปุ่มสำหรับผู้เปิดประมูล", value="ด้านล่าง")
    embed.set_image(url=auction_data['img_qr_url'])
    view = TransactionView(seller_id, winner_id, auction_data)
    await channel.send(content=winner_mention, embed=embed, view=view)

class TransactionView(discord.ui.View):
    def __init__(self, seller_id, winner_id, auction_data):
        super().__init__(timeout=None)
        self.seller_id, self.winner_id, self.auction_data = seller_id, winner_id, auction_data
    @discord.ui.button(label="ยืนยันเสร็จสิ้น✅", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ConfirmFinalView(self.auction_data, interaction.channel)
        await interaction.response.send_message("ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว", view=view, ephemeral=True)
    @discord.ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_modal(CancelReasonModal(self.auction_data, interaction.channel))

class ConfirmFinalView(discord.ui.View):
    def __init__(self, auction_data, channel):
        super().__init__(timeout=None)
        self.auction_data, self.channel = auction_data, channel
    @discord.ui.button(label="ยืนยันอีกครั้ง", style=discord.ButtonStyle.green)
    async def double_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            winner = interaction.guild.get_member(self.auction_data['winner_id']) or await bot.fetch_user(self.auction_data['winner_id'])
            await winner.send(MESSAGES["auc_dm_content"].format(link=self.auction_data['download_link']))
            dm_msg = MESSAGES["auc_dm_success"]
        except: dm_msg = MESSAGES["auc_dm_fail"].format(user=f"<@{self.auction_data['winner_id']}>")

        await interaction.followup.send(f"{dm_msg}\nลบช่องใน 1 นาที...", ephemeral=True)
        if self.auction_data['log_id']:
            log = bot.get_channel(self.auction_data['log_id'])
            embed = discord.Embed(description=MESSAGES["auc_success_log"].format(count=data['auction_count'], seller=f"<@{self.auction_data['seller_id']}>", winner=f"<@{self.auction_data['winner_id']}>", price=self.auction_data['current_price']), color=discord.Color.green())
            files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
            await log.send(embed=embed, files=files_to_send)
        await asyncio.sleep(60)
        if self.channel: await self.channel.delete()
        if self.channel.id in active_auctions: del active_auctions[self.channel.id]

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, auction_data, channel):
        super().__init__()
        self.auction_data, self.channel = auction_data, channel
    async def on_submit(self, interaction: discord.Interaction):
        if self.auction_data['log_id']:
            log = bot.get_channel(self.auction_data['log_id'])
            embed = discord.Embed(description=MESSAGES["auc_cancel_log"].format(count=data['auction_count'], seller=f"<@{self.auction_data['seller_id']}>", user=interaction.user.mention, reason=self.reason.value), color=discord.Color.red())
            await log.send(embed=embed)
        await interaction.response.send_message("ยกเลิกเรียบร้อย ลบช่องใน 5 วินาที", ephemeral=True)
        await asyncio.sleep(5)
        if self.channel: await self.channel.delete()
        if self.channel.id in active_auctions: del active_auctions[self.channel.id]

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in active_auctions and active_auctions[message.channel.id]['active']:
        content, auction_data = message.content.strip(), active_auctions[message.channel.id]
        match = re.match(r'^บิด\s*(\d+)', content)
        if match:
            amount = int(match.group(1))
            if amount < auction_data['current_price'] + auction_data['bid_step']: return
            
            old_winner = auction_data['winner_id']
            auction_data['current_price'], auction_data['winner_id'] = amount, message.author.id
            
            response_text = f"# {message.author.mention} ราคา {amount}"
            if old_winner and old_winner != message.author.id: response_text += f"\n<@{old_winner}> โดนนำแล้ว!"
            if amount >= auction_data['close_price']:
                 response_text += "\n-# ⚠️ถึงราคาปิดประมูลแล้ว จะปิดอัตโนมัติหากไม่มีใครเพิ่มใน 10 นาที"
                 auction_data['end_time'] = datetime.datetime.now() + datetime.timedelta(minutes=10)
            
            if auction_data.get('last_bid_msg_id'):
                try: await (await message.channel.fetch_message(auction_data['last_bid_msg_id'])).delete()
                except: pass
            
            sent_msg = await message.reply(response_text)
            auction_data['last_bid_msg_id'] = sent_msg.id
            if (datetime.datetime.now().timestamp() - auction_data.get('last_rename', 0)) > 30:
                try:
                    await message.channel.edit(name=f"ประมูลครั้งที่-{data['auction_count']}-ราคา-{amount}")
                    auction_data['last_rename'] = datetime.datetime.now().timestamp()
                except: pass
    await bot.process_commands(message)

# =========================================
# TICKET FORUM SYSTEM
# =========================================
@bot.tree.command(name="ticketf", description="ตั้งค่า Ticket Forum")
async def ticketf(interaction: discord.Interaction, category: discord.CategoryChannel, forum: discord.ForumChannel, log_channel: discord.TextChannel = None):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    data["ticket_configs"][str(forum.id)] = {"category_id": category.id, "log_id": log_channel.id if log_channel else None}
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งค่า Forum {forum.mention} เรียบร้อย", ephemeral=True)

@bot.event
async def on_thread_create(thread):
    if str(thread.parent_id) in data["ticket_configs"]:
        await asyncio.sleep(1)
        await thread.send("กดสั่งซื้อตรงนี้", view=TicketForumView())

class TicketForumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label=MESSAGES["tf_btn_buy"], style=discord.ButtonStyle.green, custom_id="tf_buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ป้องกันเจ้าของโพสต์กดเอง
        if interaction.user.id == interaction.channel.owner_id:
             return await interaction.response.send_message(MESSAGES["tf_err_own_post"], ephemeral=True)
             
        conf = data["ticket_configs"].get(str(interaction.channel.parent_id))
        if not conf: return
        data["ticket_count"] += 1
        save_data(data)
        
        category = interaction.guild.get_channel(conf["category_id"])
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.channel.owner: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        chan_name = f"ID-{data['ticket_count']}"
        ticket_chan = await interaction.guild.create_text_channel(chan_name, category=category, overwrites=overwrites)
        
        msg = MESSAGES["tf_room_created"].format(buyer=interaction.user.mention, seller=interaction.channel.owner.mention)
        # ส่ง log_id และ user id ไปด้วยเพื่อให้ View ขั้นตอนต่อไปใช้งานได้
        view = TicketControlView(interaction.channel.id, conf["log_id"], interaction.user.id, interaction.channel.owner_id)
        await ticket_chan.send(msg, view=view)
        await interaction.response.send_message(f"สร้างห้องแล้วที่ {ticket_chan.mention}", ephemeral=True)

    @discord.ui.button(label=MESSAGES["tf_btn_report"], style=discord.ButtonStyle.red, custom_id="tf_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id: return await interaction.response.send_message(MESSAGES["tf_err_own_report"], ephemeral=True)
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
            await log.send(MESSAGES["tf_log_report"].format(channel=interaction.channel.mention, user=interaction.user.mention, reason=self.reason.value))
        await interaction.response.send_message("ส่งรายงานเรียบร้อย", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id

    @discord.ui.button(label="เสร็จสิ้น(ปิดช่อง)", style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ⚠️ เช็คสิทธิ์: เฉพาะผู้ขาย (Seller) เท่านั้น
        if interaction.user.id != self.seller_id:
             return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)

        msg = MESSAGES["tf_wait_admin"]
        for sid in data["supports"]: msg += f" <@{sid}>"
        await interaction.channel.send(msg)
        await interaction.channel.send("ปุ่มสำหรับแอดมิน:", view=AdminCloseView(self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id))
        await interaction.response.defer()

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ⚠️ เช็คสิทธิ์: เฉพาะผู้ขาย (Seller) เท่านั้น
        if interaction.user.id != self.seller_id:
             return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
             
        await interaction.response.send_modal(TicketCancelModal(self.log_id, self.buyer_id, self.seller_id))

class TicketCancelModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True)
    def __init__(self, log_id, buyer_id, seller_id):
        super().__init__()
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        
    async def on_submit(self, interaction: discord.Interaction):
        # ส่ง Log เมื่อกดยกเลิก (Embed สวยงาม)
        if self.log_id:
            log_chan = bot.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(
                    title=MESSAGES["tf_log_cancel_title"],
                    description=MESSAGES["tf_log_cancel_desc"].format(count=data['ticket_count']),
                    color=discord.Color.red()
                )
                embed.add_field(name="👤 ผู้ขาย (Seller)", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ (Buyer)", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🚫 ยกเลิกโดย", value=interaction.user.mention, inline=True)
                embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        
        await interaction.response.send_message(f"ยกเลิกโดย {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class AdminCloseView(discord.ui.View):
    def __init__(self, forum_thread_id, log_id, buyer_id, seller_id):
        super().__init__(timeout=None)
        self.forum_thread_id = forum_thread_id
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id

    @discord.ui.button(label="ปิดช่องและลบโพสต์", style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_message("กำลังดำเนินการ...", ephemeral=True)
        
        # ส่ง Log สำเร็จ (Embed สวยงาม)
        if self.log_id:
            log_chan = bot.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(
                    title=MESSAGES["tf_log_success_title"],
                    description=MESSAGES["tf_log_success_desc"].format(count=data["ticket_count"]),
                    color=discord.Color.green()
                )
                embed.add_field(name="👤 ผู้ขาย (Seller)", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ (Buyer)", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="👮 ปิดงานโดย", value=interaction.user.mention, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)

        try: await interaction.channel.delete()
        except: pass
        try:
            thread = bot.get_channel(self.forum_thread_id)
            if thread: await thread.delete()
        except: pass

keep_alive() 
token = os.environ.get("DISCORD_TOKEN") 
if token: bot.run(token)
else: print("กรุณาตั้งค่า DISCORD_TOKEN")
