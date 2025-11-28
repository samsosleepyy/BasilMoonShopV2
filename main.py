import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
from typing import Literal, Optional, Union
import time

# --- การตั้งค่าเบื้องต้น ---
# กำหนด Intents ที่จำเป็น (ต้องเปิดใน Discord Developer Portal ด้วย)
intents = discord.Intents.default()
intents.members = True # จำเป็นสำหรับการจัดการสมาชิก
intents.message_content = True # ถ้าคุณต้องการอ่านข้อความทั่วไปด้วย

# Prefix สำหรับคำสั่งเก่า (ถึงแม้จะใช้ Slash commands แต่ก็ควรมีไว้)
bot = commands.Bot(command_prefix="!", intents=intents)

# ฐานข้อมูล/ที่เก็บข้อมูลเบื้องต้น (ควรเปลี่ยนไปใช้ฐานข้อมูลจริงในการใช้งานจริง)
ADMIN_USERS_ROLES = set()
SUPPORT_ADMIN_USERS_ROLES = set()
AUCTION_COUNTER = 1
TICKET_ID_COUNTER = 1
LOCKDOWN_TIME_SECONDS = 60 # ค่าเริ่มต้นสำหรับ /lockdown
ONGOING_AUCTIONS = {} # เก็บข้อมูลการประมูลที่กำลังดำเนินอยู่
bot.forum_ticket_config = {} # เก็บการตั้งค่าฟอรั่มตั๋ว

# --- ฟังก์ชันช่วยเหลือ ---

def is_admin():
    """ตรวจสอบว่าผู้ใช้/บทบาทมีสิทธิ์ Admin ที่กำหนดไว้ หรือมีสิทธิ์ผู้ดูแลระบบ (Administrator) ของ Discord"""
    async def predicate(interaction: discord.Interaction):
        # ตรวจสอบสิทธิ์ผู้ดูแลระบบของ Discord
        if interaction.user.guild_permissions.administrator:
            return True
        
        # ตรวจสอบสิทธิ์ Admin ที่กำหนดเอง
        if interaction.user.id in ADMIN_USERS_ROLES:
            return True
        for role in interaction.user.roles:
            if role.id in ADMIN_USERS_ROLES:
                return True
        
        # ถ้าไม่มีสิทธิ์เลย
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
        return False
    return app_commands.check(predicate)

# --- Events ---

@bot.event
async def on_ready():
    """เมื่อบอทพร้อมใช้งาน"""
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    try:
        # ล้างคำสั่งเก่าและซิงค์คำสั่งใหม่ทั้งหมด
        bot.tree.clear_commands(guild=None) # ล้างคำสั่งสำหรับ Global (ถ้ามี)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- 🛠️ คำสั่งผู้ดูแลระบบ (Admin Commands) 🛠️ ---

def get_target_from_options(user: Optional[discord.Member], role: Optional[discord.Role]):
    """ฟังก์ชันช่วยเหลือสำหรับการรับผู้ใช้หรือบทบาทจากพารามิเตอร์"""
    if user and role:
        return None, "❌ โปรดระบุ **ผู้ใช้** หรือ **บทบาท** เพียงอย่างใดอย่างหนึ่งเท่านั้น"
    target = user or role
    if not target:
        return None, "❌ โปรดระบุผู้ใช้หรือบทบาท"
    return target, None

@bot.tree.command(name="addadmin", description="เพิ่มสมาชิกหรือบทบาทให้สามารถใช้คำสั่งบอทได้")
@app_commands.describe(user="สมาชิกที่ต้องการเพิ่มสิทธิ์ (ไม่บังคับ)", role="บทบาทที่ต้องการเพิ่มสิทธิ์ (ไม่บังคับ)")
@is_admin()
async def add_admin(
    interaction: discord.Interaction, 
    user: Optional[discord.Member] = None, 
    role: Optional[discord.Role] = None
):
    """/addadmin {user} หรือ {role}"""
    target, error_msg = get_target_from_options(user, role)
    if error_msg:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return

    target_id = target.id
    ADMIN_USERS_ROLES.add(target_id)
    await interaction.response.send_message(f"✅ เพิ่ม `{target.name}` (ID: {target_id}) เป็น Admin เรียบร้อยแล้ว", ephemeral=True)

@bot.tree.command(name="removeadmin", description="ลบสิทธิ์ Admin ออกจากสมาชิกหรือบทบาท")
@app_commands.describe(user="สมาชิกที่ต้องการลบสิทธิ์ (ไม่บังคับ)", role="บทบาทที่ต้องการลบสิทธิ์ (ไม่บังคับ)")
@is_admin()
async def remove_admin(
    interaction: discord.Interaction, 
    user: Optional[discord.Member] = None, 
    role: Optional[discord.Role] = None
):
    """/removeadmin {user} หรือ {role}"""
    target, error_msg = get_target_from_options(user, role)
    if error_msg:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return
        
    target_id = target.id
    if target_id in ADMIN_USERS_ROLES:
        ADMIN_USERS_ROLES.remove(target_id)
        await interaction.response.send_message(f"✅ ลบ `{target.name}` (ID: {target_id}) ออกจาก Admin เรียบร้อยแล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ `{target.name}` (ID: {target_id}) ไม่ได้เป็น Admin", ephemeral=True)

@bot.tree.command(name="addsupportadmin", description="เพิ่มสมาชิกหรือบทบาทเป็น Support Admin")
@app_commands.describe(user="สมาชิกที่ต้องการเพิ่มสิทธิ์ (ไม่บังคับ)", role="บทบาทที่ต้องการเพิ่มสิทธิ์ (ไม่บังคับ)")
@is_admin()
async def add_support_admin(
    interaction: discord.Interaction, 
    user: Optional[discord.Member] = None, 
    role: Optional[discord.Role] = None
):
    """/addsupportadmin {user} หรือ {role}"""
    target, error_msg = get_target_from_options(user, role)
    if error_msg:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return
        
    target_id = target.id
    SUPPORT_ADMIN_USERS_ROLES.add(target_id)
    await interaction.response.send_message(f"✅ เพิ่ม `{target.name}` (ID: {target_id}) เป็น Support Admin เรียบร้อยแล้ว", ephemeral=True)

@bot.tree.command(name="removesupportadmin", description="ลบสิทธิ์ Support Admin ออกจากสมาชิกหรือบทบาท")
@app_commands.describe(user="สมาชิกที่ต้องการลบสิทธิ์ (ไม่บังคับ)", role="บทบาทที่ต้องการลบสิทธิ์ (ไม่บังคับ)")
@is_admin()
async def remove_support_admin(
    interaction: discord.Interaction, 
    user: Optional[discord.Member] = None, 
    role: Optional[discord.Role] = None
):
    """/removesupportadmin {user} หรือ {role}"""
    target, error_msg = get_target_from_options(user, role)
    if error_msg:
        await interaction.response.send_message(error_msg, ephemeral=True)
        return
        
    target_id = target.id
    if target_id in SUPPORT_ADMIN_USERS_ROLES:
        SUPPORT_ADMIN_USERS_ROLES.remove(target_id)
        await interaction.response.send_message(f"✅ ลบ `{target.name}` (ID: {target_id}) ออกจาก Support Admin เรียบร้อยแล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ `{target.name}` (ID: {target_id}) ไม่ได้เป็น Support Admin", ephemeral=True)

@bot.tree.command(name="lockdown", description="กำหนดเวลาล็อคช่องสำหรับการประมูล")
@app_commands.describe(seconds="เวลานาทีที่ใช้ล็อคช่องหลังจบประมูล (หน่วยเป็นวินาที)")
@is_admin()
async def set_lockdown_time(interaction: discord.Interaction, seconds: int):
    """/lockdown {เวลาวินาที}"""
    global LOCKDOWN_TIME_SECONDS
    if seconds < 0:
        await interaction.response.send_message("❌ เวลาต้องเป็นจำนวนเต็มบวก", ephemeral=True)
        return
    LOCKDOWN_TIME_SECONDS = seconds
    await interaction.response.send_message(f"✅ กำหนดเวลาล็อคช่องประมูลเป็น **{seconds} วินาที**", ephemeral=True)

@bot.tree.command(name="resetdata", description="ลบการจำข้อมูลลำดับการประมูลและ ID ตั๋ว")
@is_admin()
async def reset_data(interaction: discord.Interaction):
    """/resetdata"""
    global AUCTION_COUNTER, TICKET_ID_COUNTER
    AUCTION_COUNTER = 1
    TICKET_ID_COUNTER = 1
    # **ข้อควรระวัง:** ในการใช้งานจริงควรมีระบบยืนยันและการสำรองข้อมูล
    await interaction.response.send_message("⚠️ ข้อมูลลำดับการประมูล (`AUCTION_COUNTER`) และ ID ตั๋ว (`TICKET_ID_COUNTER`) ถูกรีเซ็ตเป็น **1** แล้ว", ephemeral=True)

# --- 🖼️ ระบบประมูล (Auction System) 🖼️ ---

# 1. Modal: ข้อมูลพื้นฐานการประมูล (Modal 1)
class AuctionInfoModal1(ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    def __init__(self, bot_message_id, auction_data):
        super().__init__(timeout=None)
        self.bot_message_id = bot_message_id
        self.auction_data = auction_data
        
    start_price = ui.TextInput(label="ราคาเริ่มต้น (ตัวเลข)", style=discord.TextStyle.short, required=True)
    bid_step = ui.TextInput(label="บิดครั้งละ (ตัวเลข)", style=discord.TextStyle.short, required=True)
    close_price = ui.TextInput(label="ราคาปิดประมูล (ตัวเลข)", style=discord.TextStyle.short, required=True)
    item_details = ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.long, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start = int(self.start_price.value)
            step = int(self.bid_step.value)
            close = int(self.close_price.value)
        except ValueError:
            await interaction.response.send_message("❌ ราคาเริ่มต้น, บิดครั้งละ, และ ราคาปิดประมูล ต้องเป็นตัวเลขเท่านั้น", ephemeral=True)
            return

        if start <= 0 or step <= 0:
             await interaction.response.send_message("❌ ราคาเริ่มต้นและบิดครั้งละต้องมากกว่า 0", ephemeral=True)
             return
        
        # อัปเดตข้อมูลประมูลชั่วคราว
        self.auction_data.update({
            "start_price": start,
            "bid_step": step,
            "close_price": close,
            "item_details": self.item_details.value,
        })
        
        # ส่งข้อความให้กรอก Modal 2
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="กดกรอกข้อมูล 2", custom_id=f"auction_modal2_{self.bot_message_id}", style=discord.ButtonStyle.primary))
        
        await interaction.response.send_message("✅ ได้รับข้อมูล (1/2) แล้ว\nโปรดกรอกข้อมูลส่วนที่เหลือ:", view=view, ephemeral=True)

# 2. Modal: ข้อมูลเพิ่มเติมการประมูล (Modal 2)
class AuctionInfoModal2(ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    def __init__(self, auction_data, creator):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.creator = creator

    download_link = ui.TextInput(label="ลิ้งค์ดาวน์โหลดสินค้า", placeholder="ใส่ลิ้งค์ดาวน์โหลดสินค้าของคุณ", style=discord.TextStyle.short, required=True)
    item_rights = ui.TextInput(label="สิทธิ์", placeholder="สิทธิ์ขาด-สิทธ์เชิง", style=discord.TextStyle.short, required=True)
    additional_info = ui.TextInput(label="เพิ่มเติม (ไม่บังคับ)", placeholder="บอกว่าสินค้ามาจากที่ใดหรือเป็นของตัวเอง", style=discord.TextStyle.long, required=False)
    close_time = ui.TextInput(label="เวลาปิดประมูล (ชช:นน)", placeholder="เช่น 01:00 คือ 1 ชั่วโมง", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # ตรวจสอบรูปแบบเวลา ชช:นน
        try:
            h, m = map(int, self.close_time.value.split(':'))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError
            total_seconds = (h * 3600) + (m * 60)
            if total_seconds <= 0:
                 await interaction.response.send_message("❌ เวลาปิดประมูลต้องมากกว่า 0", ephemeral=True)
                 return
        except ValueError:
            await interaction.response.send_message("❌ รูปแบบเวลาไม่ถูกต้อง โปรดใช้รูปแบบ ชช:นน (เช่น 01:00)", ephemeral=True)
            return
        
        # อัปเดตข้อมูลประมูลชั่วคราว
        self.auction_data.update({
            "download_link": self.download_link.value,
            "item_rights": self.item_rights.value,
            "additional_info": self.additional_info.value or "ไม่มี",
            "close_time_str": self.close_time.value,
            "close_time_seconds": total_seconds,
            "creator_id": self.creator.id
        })
        
        # สร้างช่องส่งรูปสินค้า
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False), # ทุกคนไม่เห็น
            guild.me: discord.PermissionOverwrite(view_channel=True), # บอทเห็น
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), # ผู้สร้างเห็น
        }

        # อนุญาตบทบาทที่มีสิทธิ์ผู้ดูแลเห็นช่อง (Administrator Permission)
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        
        # ใช้หมวดหมู่ที่ตั้งค่ามา
        category = self.auction_data.get('category') 
        
        # ชื่อช่อง: ✧꒰ส่งรูปสินค้า📦 {username(ชื่อของผู้กด)}꒱
        channel_name = f"✧꒰ส่งรูปสินค้า📦 {interaction.user.name}꒱"
        
        try:
            image_channel = await guild.create_text_channel(
                name=channel_name, 
                category=category, 
                overwrites=overwrites
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ บอทไม่มีสิทธิ์สร้างช่องในหมวดหมู่ที่กำหนด", ephemeral=True)
            return

        # อัปเดตข้อมูลช่อง
        self.auction_data["image_channel_id"] = image_channel.id
        
        await interaction.response.send_message(
            f"✅ ได้รับข้อมูล (2/2) แล้ว\nมีเวลา **3 นาที** ในการส่งรูปสินค้าของคุณที่ {image_channel.mention}", 
            ephemeral=True
        )

        # ส่งข้อความในช่องส่งรูป
        await image_channel.send(
            f"{interaction.user.mention} ส่งรูปสินค้าของคุณที่ช่องนี้📦\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่"
        )
        
        # เริ่มกระบวนการรับรูป
        self.bot.loop.create_task(
            handle_image_uploads(interaction.client, interaction.user, image_channel, self.auction_data)
        )

# 4. ฟังก์ชันจัดการกระบวนการรับรูป
async def handle_image_uploads(bot, user: discord.User, channel: discord.TextChannel, auction_data: dict):
    """จัดการการรับรูปสินค้าและ QR Code"""
    
    def check_message(m):
        # ตรวจสอบว่าเป็นข้อความจากผู้ใช้ที่ต้องการ และมีไฟล์แนบ
        return m.channel.id == channel.id and m.author.id == user.id and len(m.attachments) > 0

    # รอบ 1: รับรูปสินค้า
    try:
        msg1 = await bot.wait_for('message', check=check_message, timeout=180.0) # 3 นาที = 180 วินาที
        auction_data["item_image_url"] = msg1.attachments[0].url
    except asyncio.TimeoutError:
        # ไม่ส่งรูปใน 3 นาที -> ลบช่อง
        await channel.delete()
        try:
             # พยายามส่งข้อความส่วนตัวแจ้งผู้ใช้ (ถ้าทำได้)
             await user.send(f"❌ การประมูลของคุณถูกยกเลิก: ไม่ได้ส่งรูปสินค้าภายใน 3 นาที")
        except:
             pass
        return

    # รอบ 2: รับรูป QR Code
    await channel.send("โปรดส่งรูป QR code หรือช่องทางการชำระเงิน🧾\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่")
    try:
        msg2 = await bot.wait_for('message', check=check_message, timeout=180.0)
        auction_data["payment_image_url"] = msg2.attachments[0].url
    except asyncio.TimeoutError:
        # ไม่ส่งรูปใน 3 นาที -> ลบช่อง
        await channel.delete()
        try:
             await user.send(f"❌ การประมูลของคุณถูกยกเลิก: ไม่ได้ส่งรูปชำระเงินภายใน 3 นาที")
        except:
             pass
        return

    # ลบสิทธิ์ส่งข้อความของผู้ใช้ทันทีหลังจากส่งครบ
    await channel.set_permissions(user, send_messages=False)
    
    await channel.send("ได้รับรูปสินค้าและช่องทางการชำระเงินเรียบร้อยแล้ว📥 รอแอดมินยืนยัน⏳")
    
    # 5. ส่งข้อมูลไปยังช่องอนุมัติ (Approval Channel)
    await send_for_approval(bot, user, auction_data, channel)


# 5. ฟังก์ชันส่งข้อมูลการประมูลไปช่องอนุมัติ
async def send_for_approval(bot, creator: discord.User, auction_data: dict, temp_channel: discord.TextChannel):
    """ส่งข้อมูลทั้งหมดไปยังช่องอนุมัติ"""
    
    approval_channel = auction_data.get('approval_channel')
    log_channel = auction_data.get('log_channel')
    
    if not approval_channel:
        return 

    embed = discord.Embed(
        title=f"⏳ การประมูลใหม่จาก {creator.display_name} ({creator.id})",
        color=discord.Color.gold()
    )
    embed.add_field(name="ราคาเริ่มต้น/บิดครั้งละ/ราคาปิด", value=f"{auction_data['start_price']}/{auction_data['bid_step']}/{auction_data['close_price']}", inline=True)
    embed.add_field(name="เวลาปิดประมูล", value=f"{auction_data['close_time_str']}", inline=True)
    embed.add_field(name="สิทธิ์", value=auction_data['item_rights'], inline=False)
    embed.add_field(name="สิ่งที่ได้", value=auction_data['item_details'], inline=False)
    embed.add_field(name="เพิ่มเติม", value=auction_data['additional_info'], inline=False)
    embed.add_field(name="Link", value=f"[Download Link]({auction_data['download_link']})", inline=False)
    embed.set_image(url=auction_data['item_image_url']) # รูปสินค้า
    
    # สร้าง View สำหรับปุ่มอนุมัติ/ไม่อนุมัติ
    view = ApprovalView(
        auction_data=auction_data,
        temp_channel_id=temp_channel.id,
        log_channel=log_channel,
        creator=creator
    )
    
    # ส่งรูป QR Code/ชำระเงินแยก
    # เนื่องจากใช้ Render.com และการใช้ bot.http.get อาจซับซ้อนในการจัดการ bytes/file
    # ในการทำงานจริงบน Render คุณอาจต้องใช้ requests.get หรือ aiohttp.ClientSession
    try:
        async with bot.http.session.get(auction_data['payment_image_url']) as resp:
            if resp.status == 200:
                data = await resp.read()
                payment_file = discord.File(fp=data, filename="payment.png")
            else:
                 payment_file = None
                 print("Failed to download payment image.")
    except Exception as e:
        print(f"Error downloading payment image: {e}")
        payment_file = None

    if payment_file:
         await approval_channel.send(
            f"**ข้อมูลสำหรับอนุมัติ**\nรูปช่องทางการชำระเงินจาก {creator.mention}:",
            file=payment_file
         )
    
    # ส่ง embed และปุ่ม
    await approval_channel.send(
        content=f"**ผู้สร้าง:** {creator.mention}\n**รูปสินค้า:**", 
        embed=embed, 
        view=view
    )

# 6. View: ปุ่มอนุมัติ/ไม่อนุมัติ (Approval View)
class ApprovalView(ui.View):
    def __init__(self, auction_data, temp_channel_id, log_channel, creator):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.temp_channel_id = temp_channel_id
        self.log_channel = log_channel
        self.creator = creator

    # ปุ่มอนุมัติ
    @ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve_callback(self, interaction: discord.Interaction, button: ui.Button):
        # ตรวจสอบสิทธิ์ Admin อีกครั้ง
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        await interaction.response.defer() # ตอบกลับทันทีเพื่อไม่ให้หมดเวลา
        
        # 7. สร้างช่องประมูล
        await start_final_auction(interaction.client, self.auction_data, self.creator)
        
        # ลบช่องส่งรูปชั่วคราว
        temp_channel = interaction.guild.get_channel(self.temp_channel_id)
        if temp_channel:
            await temp_channel.delete(reason="Admin Approved Auction")
            
        await interaction.edit_original_response(content="✅ **อนุมัติแล้ว**", view=None, embed=interaction.message.embeds[0])

    # ปุ่มไม่อนุมัติ
    @ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def reject_callback(self, interaction: discord.Interaction, button: ui.Button):
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return
        
        # แสดง Modal สำหรับกรอกเหตุผล
        await interaction.response.send_modal(RejectModal(self.auction_data, self.temp_channel_id, self.log_channel, self.creator, interaction.message))

# 7. Modal: กรอกเหตุผลไม่อนุมัติ
class RejectModal(ui.Modal, title="เหตุผลในการไม่อนุมัติ"):
    def __init__(self, auction_data, temp_channel_id, log_channel, creator, approval_message):
        super().__init__(timeout=None)
        self.auction_data = auction_data
        self.temp_channel_id = temp_channel_id
        self.log_channel = log_channel
        self.creator = creator
        self.approval_message = approval_message

    reason = ui.TextInput(label="เหตุผล (บังคับ)", style=discord.TextStyle.long, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ **ไม่อนุมัติ** การประมูลแล้ว", ephemeral=True)
        
        # ส่งข้อความไป Log
        if self.log_channel:
            embed = discord.Embed(
                description=f" ⊹ {self.creator.mention} .ᐟ⊹\n"
                            f"ประมูลของคุณไม่ได้รับอนุมัติจากแอดมิน : {interaction.user.mention} ❌\n"
                            f"เหตุผล : {self.reason.value}",
                color=discord.Color.red()
            )
            embed.set_author(name="การประมูลถูกปฏิเสธ", icon_url=self.creator.display_avatar.url)
            await self.log_channel.send(embed=embed)

        # ลบช่องส่งรูปชั่วคราว
        temp_channel = interaction.guild.get_channel(self.temp_channel_id)
        if temp_channel:
            await temp_channel.delete(reason=f"Admin Rejected Auction: {self.reason.value}")
            
        # แก้ไขข้อความอนุมัติ
        await self.approval_message.edit(content="❌ **ถูกปฏิเสธแล้ว**", view=None, embed=self.approval_message.embeds[0])
        
        # แจ้งผู้สร้าง
        try:
             await self.creator.send(f"❌ การประมูลของคุณไม่ได้รับอนุมัติจากแอดมิน: {interaction.user.mention}\nเหตุผล: {self.reason.value}")
        except:
             pass

# 8. ฟังก์ชันสร้างช่องประมูลสุดท้ายและเริ่มจับเวลา
async def start_final_auction(bot, auction_data: dict, creator: discord.User):
    """สร้างช่องประมูลจริงและเริ่มกระบวนการประมูล"""
    global AUCTION_COUNTER
    
    guild = creator.guild
    category = auction_data.get('category')
    notify_role = auction_data.get('notify_role')
    log_channel = auction_data.get('log_channel')
    
    auction_id = AUCTION_COUNTER
    current_price = auction_data['start_price']
    
    # ชื่อช่อง: "ประมูลครั้งที่ ... ราคา ...(ราคาล่าสุด)"
    channel_name = f"ประมูลครั้งที่ {auction_id} ราคา {current_price}บ."
    
    # Overwrites
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True), # ทุกคนเห็นและส่งข้อความได้
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }

    # อนุญาตบทบาทที่มีสิทธิ์ผู้ดูแลเห็นช่อง (Administrator Permission)
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
            
    try:
        auction_channel = await guild.create_text_channel(
            name=channel_name, 
            category=category, 
            overwrites=overwrites
        )
    except discord.Forbidden:
        if log_channel:
            await log_channel.send("❌ บอทไม่มีสิทธิ์สร้างช่องประมูลในหมวดหมู่ที่กำหนด")
        return
        
    AUCTION_COUNTER += 1

    # เก็บข้อมูลการประมูลที่กำลังดำเนินอยู่
    auction_data.update({
        "auction_id": auction_id,
        "auction_channel": auction_channel,
        "current_price": current_price,
        "highest_bidder": None,
        "message_to_edit": None, # ข้อความหลักที่จะแก้ไข
        "last_bid_message_id": None, # ข้อความบิดล่าสุด
        "last_rename_time": time.time(),
        "close_time_timestamp": time.time() + auction_data['close_time_seconds'],
        "bidding_active": True,
        "bidding_over_time": None, # สำหรับ 10 นาทีหลังราคาถึงราคาปิด
    })
    
    ONGOING_AUCTIONS[auction_channel.id] = auction_data

    # สร้าง Embed ข้อความหลัก
    time_remaining_str = format_countdown(auction_data['close_time_seconds'])
    embed = discord.Embed(
        title="˚₊‧꒰ა ☆ ໒꒱ ‧₊˚\n      *เปิดประมูล!*",
        color=discord.Color.blue()
    )
    embed.description = f"""
ᯓ★ โดย : {creator.mention}
ᯓ★ ราคาเริ่มต้น : {auction_data['start_price']}
ᯓ★ บิดครั้งละ : {auction_data['bid_step']}
ᯓ★ ราคาปิดประมูล : {auction_data['close_price']}
ᯓ★ สิ่งที่ได้ : {auction_data['item_details']}
ᯓ★ สิทธิ์ : {auction_data['item_rights']}
ᯓ★ เพิ่มเติม : {auction_data['additional_info']}

-ˋˏ✄┈┈┈┈
**เวลาปิดประมูล : {time_remaining_str}**
"""
    embed.set_image(url=auction_data['item_image_url'])
    
    # ปุ่มปิดประมูล
    view = AuctionCloseView(creator_id=creator.id, is_admin_check=is_admin)

    # ส่งข้อความหลัก
    main_message = await auction_channel.send(
        content=notify_role.mention if notify_role else "📢 **เปิดการประมูลใหม่!**", 
        embed=embed, 
        view=view
    )
    
    auction_data["message_to_edit"] = main_message
    
    # เริ่มงานแก้ไขชื่อช่องและนับถอยหลัง
    bot.loop.create_task(
        auction_countdown_and_rename(bot, auction_channel.id)
    )

# 9. View: ปุ่มปิดประมูล (Auction Close View)
class AuctionCloseView(ui.View):
    def __init__(self, creator_id, is_admin_check):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.is_admin_check = is_admin_check

    @ui.button(label="🧾ปิดประมูล (กดได้แค่ผู้เปิดประมูลหรือแอดมิน)", style=discord.ButtonStyle.red)
    async def close_auction(self, interaction: discord.Interaction, button: ui.Button):
        auction_data = ONGOING_AUCTIONS.get(interaction.channel_id)
        
        # ตรวจสอบสิทธิ์ (ผู้สร้างหรือ Admin)
        is_creator = interaction.user.id == self.creator_id
        
        # ตรวจสอบสิทธิ์ Admin/ผู้ดูแล ด้วยตนเองเนื่องจาก is_admin_check เป็นแค่ decorator
        is_admin_user = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        
        if not (is_creator or is_admin_user):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        if not auction_data or not auction_data.get("bidding_active"):
            await interaction.response.send_message("❌ การประมูลนี้ปิดไปแล้วหรือไม่มีอยู่", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # บังคับปิดประมูลทันที
        await end_auction(interaction.client, interaction.channel_id)
        await interaction.followup.send("✅ การประมูลถูกปิดโดยผู้สร้าง/แอดมินแล้ว", ephemeral=True)

# 10. ฟังก์ชันนับถอยหลังและแก้ไขชื่อช่อง (Task)
async def auction_countdown_and_rename(bot, channel_id):
    """จัดการการนับถอยหลังของเวลาและแก้ไขชื่อช่อง"""
    
    # รอ 1 นาทีแรกก่อนแก้ไขครั้งแรก (ตามที่คุณแจ้ง)
    await asyncio.sleep(60) 
    
    while True:
        await asyncio.sleep(30) # ตรวจสอบทุก 30 วินาที

        auction_data = ONGOING_AUCTIONS.get(channel_id)
        if not auction_data or not auction_data.get("bidding_active"):
            break

        channel = auction_data['auction_channel']
        main_message = auction_data['message_to_edit']
        
        # --- จัดการเวลา ---
        time_left_seconds = int(auction_data['close_time_timestamp'] - time.time())
        
        # ตรวจสอบ 10 นาทีสุดท้าย (หากถึงราคาปิดประมูล)
        if auction_data.get("bidding_over_time"):
            time_over_seconds = int(auction_data['bidding_over_time'] - time.time())
            if time_over_seconds <= 0:
                time_left_seconds = 0 # บังคับปิดเมื่อหมด 10 นาที
        
        # กรณีถึงเวลาปิดปกติ
        if time_left_seconds <= 0:
            await end_auction(bot, channel_id)
            break

        # แก้ไขข้อความหลัก (ทุก 1 นาที)
        # ตรวจสอบว่านาทีเปลี่ยนไปหรือไม่
        current_minute = (time_left_seconds + 59) // 60
        previous_minute = (time_left_seconds + 30 + 59) // 60 # ประมาณนาทีที่แล้ว (บวก 30 เนื่องจาก sleep 30 วิ)
        
        # แก้ไขทุก 1 นาที (หรือหากมีการเปลี่ยนเวลาในการนับถอยหลัง)
        if main_message and (current_minute != previous_minute or time_left_seconds % 60 == 0):
            time_remaining_str = format_countdown(time_left_seconds)
            
            try:
                embed = main_message.embeds[0]
                desc_lines = embed.description.splitlines()
                # ค้นหาและแก้ไขบรรทัดเวลา
                for i, line in enumerate(desc_lines):
                    if line.startswith('**เวลาปิดประมูล'):
                        desc_lines[i] = f"**เวลาปิดประมูล : {time_remaining_str}**"
                        break
                embed.description = '\n'.join(desc_lines)
                
                await main_message.edit(embed=embed)
            except discord.HTTPException as e:
                # จัดการ Rate Limit (ถ้าเกิดขึ้น)
                print(f"Error editing auction message: {e}")

        # แก้ไขชื่อช่อง (ทุก 30 วินาที)
        if time.time() - auction_data['last_rename_time'] >= 30:
            new_price = auction_data['current_price']
            new_name = f"ประมูลครั้งที่ {auction_data['auction_id']} ราคา {new_price}บ."
            try:
                await channel.edit(name=new_name)
                auction_data['last_rename_time'] = time.time()
            except discord.HTTPException as e:
                # จัดการ Rate Limit
                print(f"Error renaming auction channel: {e}")

# 11. ฟังก์ชันจบการประมูล
async def end_auction(bot, channel_id: int):
    """จัดการเมื่อการประมูลจบลง"""
    
    auction_data = ONGOING_AUCTIONS.pop(channel_id, None)
    if not auction_data:
        return

    auction_channel: discord.TextChannel = auction_data['auction_channel']
    log_channel: discord.TextChannel = auction_data['log_channel']
    main_message: discord.Message = auction_data['message_to_edit']
    creator: discord.User = await bot.fetch_user(auction_data['creator_id'])
    
    auction_data['bidding_active'] = False

    # กรณีไม่มีใครบิดเลย
    if not auction_data['highest_bidder']:
        if log_channel:
            embed = discord.Embed(
                description=f"การประมูลครั้งที่ {auction_data['auction_id']}\nโดย {creator.mention}\nการประมูลหมดเวลา",
                color=discord.Color.gold()
            )
            embed.set_author(name="การประมูลหมดเวลา", icon_url=creator.display_avatar.url)
            await log_channel.send(embed=embed)
            
        await auction_channel.delete(reason="Auction ended with no bids")
        return

    # กรณีมีผู้ชนะ
    winner: discord.User = auction_data['highest_bidder']
    final_price = auction_data['current_price']
    
    # 11.1 ข้อความ Countdown
    lockdown_time = LOCKDOWN_TIME_SECONDS
    countdown_message = f"""
📜 | {winner.mention} ชนะการประมูลครั้งที่ - {auction_data['auction_id']}
จบที่ราคา - {final_price} บ.-
-# ช่องนี้กำลังจะถูกล็อคภายใน {lockdown_time} วินาทีเพื่อทำธุรกรรม🔐
"""
    # แก้ไขข้อความหลักให้เป็นข้อความ countdown
    await main_message.edit(content=countdown_message, embed=None, view=None)
    
    # 11.2 ล็อคช่อง (Perms)
    await asyncio.sleep(lockdown_time) # รอนับถอยหลังตาม /lockdown

    # ตั้งค่า Permission ให้เห็นเฉพาะผู้ชนะ ผู้เปิดประมูล และ Admin
    overwrites = {
        auction_channel.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        creator: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        winner: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        auction_channel.guild.me: discord.PermissionOverwrite(view_channel=True)
    }
    
    # อนุญาตบทบาทที่มีสิทธิ์ผู้ดูแลเห็นช่อง (Administrator Permission)
    for role in auction_channel.guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
            
    try:
        await auction_channel.edit(overwrites=overwrites)
    except discord.Forbidden:
        if log_channel:
            await log_channel.send("❌ บอทไม่มีสิทธิ์แก้ไข Permssion ช่องประมูล")
            
    # 11.3 แก้ไขข้อความ Countdown สุดท้าย
    payment_view = PaymentView(creator_id=creator.id, winner_id=winner.id, auction_id=auction_data['auction_id'], log_channel=log_channel, final_price=final_price, item_image_url=auction_data['item_image_url'])
    
    final_countdown_message = f"""
ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐
({winner.mention} ผู้ชนะประมูล) สามารถชำระเงินได้เลย
-# ปุ่มสำหรับผู้เปิดประมูล
"""
    
    # ดาวน์โหลดรูปช่องทางการชำระเงิน
    try:
        async with bot.http.session.get(auction_data['payment_image_url']) as resp:
            if resp.status == 200:
                data = await resp.read()
                payment_file = discord.File(fp=data, filename="payment_qr.png")
            else:
                 payment_file = None
    except Exception as e:
        print(f"Error downloading payment image for end_auction: {e}")
        payment_file = None

    await auction_channel.send(
        content=final_countdown_message,
        file=payment_file,
        view=payment_view
    )
    
# 12. View: ปุ่มยืนยันเสร็จสิ้น/ยกเลิก (Payment View)
class PaymentView(ui.View):
    def __init__(self, creator_id, winner_id, auction_id, log_channel, final_price, item_image_url):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.winner_id = winner_id
        self.auction_id = auction_id
        self.log_channel = log_channel
        self.final_price = final_price
        self.item_image_url = item_image_url
    
    # ปุ่มยืนยันเสร็จสิ้น (สีเขียว)
    @ui.button(label="ยืนยันเสร็จสิ้น✅", style=discord.ButtonStyle.green)
    async def confirm_payment(self, interaction: discord.Interaction, button: ui.Button):
        # กดได้แค่ผู้เปิดประมูลหรือแอดมิน
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        if not (interaction.user.id == self.creator_id or is_admin):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        # Pop-up ยืนยันอีกครั้ง
        confirm_view = ui.View(timeout=60)
        
        # ต้องสร้าง custom_id ใหม่ทุกครั้ง เนื่องจาก custom_id ซ้ำกันไม่ได้ในโค้ด
        # เราจะใช้วิธีเพิ่ม view ใหม่เข้าไปในบอทเพื่อจัดการปุ่มยืนยัน
        final_confirm_view = FinalConfirmView(self.creator_id, self.winner_id, self.auction_id, self.log_channel, self.final_price, self.item_image_url)
        interaction.client.add_view(final_confirm_view)

        # สร้างปุ่มที่ใช้ custom_id ของ view ที่เพิ่งสร้างมา
        confirm_button = ui.Button(label="ยืนยันการรับเงินอีกครั้ง", style=discord.ButtonStyle.danger, custom_id=f"final_confirm_{self.auction_id}")
        confirm_button.callback = final_confirm_view.final_confirm # กำหนด callback ให้ปุ่มนี้

        confirm_view = ui.View(timeout=60)
        confirm_view.add_item(confirm_button)
        
        await interaction.response.send_message("ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว ทางเราจะไม่รับผิดชอบใดๆ", view=confirm_view, ephemeral=True)
        

    # ปุ่มยกเลิก (สีแดง)
    @ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.red)
    async def cancel_payment(self, interaction: discord.Interaction, button: ui.Button):
        # กดได้แค่ผู้เปิดประมูลหรือแอดมิน
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        if not (interaction.user.id == self.creator_id or is_admin):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return
        
        await interaction.response.send_modal(CancelModal(self.creator_id, self.winner_id, self.auction_id, self.log_channel, interaction.channel))

# 13. View: ปุ่มยืนยันสุดท้าย (Final Confirm View)
class FinalConfirmView(ui.View):
    def __init__(self, creator_id, winner_id, auction_id, log_channel, final_price, item_image_url):
        # Timeout ต้องเป็น None เพื่อให้บอทจำปุ่มได้หลังจากบอทรีสตาร์ท
        super().__init__(timeout=180) 
        self.creator_id = creator_id
        self.winner_id = winner_id
        self.auction_id = auction_id
        self.log_channel = log_channel
        self.final_price = final_price
        self.item_image_url = item_image_url
        self.custom_id = f"final_confirm_{self.auction_id}"
        
        # เพิ่มปุ่มเข้าไปใน View โดยกำหนด custom_id ที่สอดคล้อง
        self.add_item(ui.Button(label="ยืนยันการรับเงินอีกครั้ง", style=discord.ButtonStyle.danger, custom_id=self.custom_id))

    # Callback สำหรับปุ่มยืนยันสุดท้าย
    async def final_confirm(self, interaction: discord.Interaction):
        # ต้องใช้ interaction.data.get('custom_id') เพื่อให้แน่ใจว่าเป็นปุ่มนี้จริงๆ
        if interaction.data.get('custom_id') != self.custom_id:
             return
             
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        if not (interaction.user.id == self.creator_id or is_admin):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return
        
        await interaction.response.send_message("✅ ยืนยันการเสร็จสิ้นธุรกรรมแล้ว ช่องจะถูกลบภายใน 1 นาที", ephemeral=True)
        
        # ส่งผลลัพธ์ไปที่ Log
        if self.log_channel:
            creator = await interaction.client.fetch_user(self.creator_id)
            winner = await interaction.client.fetch_user(self.winner_id)
            
            embed = discord.Embed(
                title="── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──",
                description=f"╭﹕การประมูลครั้งที่ - {self.auction_id}\n"
                            f" | ﹕โดย {creator.mention}\n"
                            f" | ﹕ผู้ชนะประมูล {winner.mention}\n"
                            f"╰ ﹕จบที่ราคา : {self.final_price}",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=self.item_image_url)
            await self.log_channel.send(embed=embed)
            
        # ลบช่อง
        await asyncio.sleep(60)
        try:
             await interaction.channel.delete(reason="Auction/Payment Completed")
        except:
             pass


# 14. Modal: กรอกเหตุผลยกเลิกธุรกรรม
class CancelModal(ui.Modal, title="เหตุผลในการยกเลิกธุรกรรม"):
    def __init__(self, creator_id, winner_id, auction_id, log_channel, auction_channel):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.winner_id = winner_id
        self.auction_id = auction_id
        self.log_channel = log_channel
        self.auction_channel = auction_channel

    reason = ui.TextInput(label="เหตุผล (บังคับ)", style=discord.TextStyle.long, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ **ยกเลิก** การทำธุรกรรมแล้ว ช่องจะถูกลบในภายหลัง", ephemeral=True)
        
        # ส่งข้อความไป Log
        if self.log_channel:
            creator = await interaction.client.fetch_user(self.creator_id)
            winner = await interaction.client.fetch_user(self.winner_id)
            
            embed = discord.Embed(
                description=f"╭﹕การประมูลครั้งที่ - {self.auction_id}\n"
                            f" | ﹕โดย {creator.mention}\n"
                            f" | ﹕ถูกยกเลิกโดย {interaction.user.mention}\n"
                            f" | ﹕ผู้ชนะประมูล {winner.mention}\n"
                            f"╰ ﹕เหตุผล : {self.reason.value}",
                color=discord.Color.red()
            )
            embed.set_author(name="ธุรกรรมถูกยกเลิก", icon_url=creator.display_avatar.url)
            await self.log_channel.send(embed=embed)

        # ลบช่อง
        try:
            await self.auction_channel.delete(reason=f"Payment Cancelled: {self.reason.value}")
        except:
            pass
        
# 15. ฟังก์ชันช่วยเหลือ: จัดรูปแบบเวลา
def format_countdown(seconds):
    """แปลงวินาทีเป็นรูปแบบ ชช:นน:วว"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02}"

# 16. คำสั่งหลัก /auction
@bot.tree.command(name="auction", description="ตั้งค่าการเปิดประมูลใหม่")
@app_commands.describe(
    category="หมวดหมู่ที่จะเอาไว้เพิ่มช่อง", 
    send_channel="ช่องที่จะให้ส่งข้อความไป", 
    message_content="ข้อความต่อข้อความที่บอทจะแสดง", 
    approval_channel="ช่องเอาไว้อนุมัติการประมูล", 
    notify_role="บทบาทที่จะ @ เพื่อแจ้งเตือน", 
    log_channel="ช่องบอกสถานะต่างๆ (ไม่บังคับ)", 
    button_text="ข้อความที่จะอยู่ในปุ่ม (ไม่บังคับ)", 
    image_link="ลิ้งค์รูปที่บอทจะเอาไปเปิด (ไม่บังคับ)"
)
@is_admin()
async def auction(
    interaction: discord.Interaction, 
    category: discord.CategoryChannel, 
    send_channel: discord.TextChannel, 
    message_content: str, 
    approval_channel: discord.TextChannel, 
    notify_role: discord.Role, 
    log_channel: Optional[discord.TextChannel], 
    button_text: Optional[str] = "💳 เปิดการประมูล", 
    image_link: Optional[str] = None
):
    """
    /auction {หมวดหมู่} {ช่องส่งข้อความ} {ข้อความ} {ช่องอนุมัติ} 
    {เลือกบทบาทแจ้งเตือน} {ช่อง log(ไม่บังคับ)} {ข้อความปุ่ม(ไม่บังคับ)} {ลิ้งค์รูป(ไม่บังคับ)}
    """
    
    # ข้อมูลการประมูลชั่วคราว
    temp_auction_data = {
        "creator": interaction.user.id,
        "category": category,
        "send_channel": send_channel,
        "approval_channel": approval_channel,
        "notify_role": notify_role,
        "log_channel": log_channel,
        "bot": interaction.client
    }
    
    # สร้าง Embed (มีขีดสีเขียว)
    embed = discord.Embed(
        description=message_content,
        color=discord.Color.green()
    )
    if image_link:
        embed.set_image(url=image_link)

    # ส่งข้อความไปก่อนเพื่อเอา ID ข้อความ
    message = await send_channel.send(content=message_content, embed=embed)
    
    # สร้าง View ที่แท้จริงที่มี custom_id ผูกกับ ID ข้อความ
    class AuctionStartViewDynamic(ui.View):
        def __init__(self, bot_message_id, auction_data, creator, bot_instance):
            super().__init__(timeout=None)
            self.bot_message_id = bot_message_id
            self.auction_data = auction_data
            self.creator = creator
            self.bot_instance = bot_instance
            
            # ปุ่มหลักที่จะแสดง Modal
            self.add_item(ui.Button(label=button_text, style=discord.ButtonStyle.green, custom_id=f"auction_modal1_{bot_message_id}"))
            
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # ใช้ interaction_check เพื่อดักจับปุ่มที่ถูกกด
            custom_id = interaction.data.get('custom_id')
            
            if custom_id == f"auction_modal1_{self.bot_message_id}":
                await interaction.response.send_modal(AuctionInfoModal1(self.bot_message_id, self.auction_data))
                return False
            
            # ตรวจสอบปุ่ม Modal 2
            if custom_id == f"auction_modal2_{self.bot_message_id}":
                 # ต้องส่ง bot_instance เข้าไปใน Modal 2 ด้วย
                 modal = AuctionInfoModal2(self.auction_data, self.creator)
                 modal.bot = self.bot_instance 
                 await interaction.response.send_modal(modal)
                 return False
            
            return True

    # อัปเดตข้อความด้วย View ที่ถูกต้อง
    view = AuctionStartViewDynamic(message.id, temp_auction_data, interaction.user, interaction.client)
    await message.edit(view=view)
    
    # ให้บอทติดตามปุ่มนี้
    bot.add_view(view)
    
    await interaction.response.send_message("✅ ส่งข้อความตั้งค่าการประมูลเรียบร้อยแล้ว", ephemeral=True)

# 17. On Message Event (สำหรับระบบบิดราคา)
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
        
    # ประมวลผลคำสั่ง Slash Command และ Commands อื่นๆ ก่อน
    await bot.process_commands(message)

    auction_data = ONGOING_AUCTIONS.get(message.channel.id)
    if not auction_data or not auction_data.get("bidding_active"):
        return
    
    content = message.content.strip()
    
    # ตรวจสอบว่าเป็นการบิดราคาหรือไม่: "บิด 1000"
    if content.lower().startswith("บิด"):
        try:
            # ใช้ regex เพื่อหาตัวเลขหลังคำว่า "บิด" ที่คั่นด้วยช่องว่าง
            parts = content.split()
            if len(parts) < 2:
                 return
            if parts[0].lower() != "บิด":
                 return

            bid_amount = int(parts[1])
        except ValueError:
            # ไม่ใช่ตัวเลข
            return

        current_price = auction_data['current_price']
        bid_step = auction_data['bid_step']
        close_price = auction_data['close_price']
        highest_bidder = auction_data['highest_bidder']
        
        # ตรวจสอบว่าราคาบิดมากกว่าราคาปัจจุบัน + ขั้นต่ำในการบิด
        min_bid = current_price + bid_step
        if bid_amount < min_bid:
            try:
                await message.delete() # ลบข้อความที่ไม่ถูกต้อง
                await message.channel.send(f"❌ {message.author.mention} การบิดของคุณต่ำเกินไป! ราคาปัจจุบันคือ {current_price} ต้องบิดอย่างน้อย {min_bid}บ.", delete_after=10)
            except:
                pass
            return
            
        # ถ้าผู้บิดคนเดิมบิดต่ำกว่าหรือเท่ากับราคาสูงสุด
        if highest_bidder and message.author.id == highest_bidder.id and bid_amount <= current_price:
             try:
                 await message.delete()
                 await message.channel.send(f"❌ {message.author.mention} คุณบิดราคาเดิมหรือต่ำกว่า โปรดบิดอย่างน้อย {min_bid}บ.", delete_after=10)
             except:
                 pass
             return

        # บิดถูกต้อง
        old_bidder = highest_bidder
        auction_data['current_price'] = bid_amount
        auction_data['highest_bidder'] = message.author
        
        # ลบข้อความบิดเก่า
        last_bid_msg_id = auction_data.get('last_bid_message_id')
        if last_bid_msg_id:
            try:
                old_message = await message.channel.fetch_message(last_bid_msg_id)
                await old_message.delete()
            except:
                pass # ไม่สนใจถ้าลบไม่ได้

        # สร้างข้อความบิดใหม่
        bid_message_content = f"# {message.author.mention} ราคา {bid_amount}"
        if old_bidder and old_bidder.id != message.author.id:
            bid_message_content += f"\n{old_bidder.mention} โดนนำแล้ว!"

        # ตรวจสอบราคาปิดประมูล (Close Price)
        if bid_amount >= close_price:
            bid_message_content += "\n-# ⚠️ตอนนี้ราคาถึงราคาปิดประมูลแล้วจะปิดประมูลอัตโนมัติทันทีหากไม่มีการประมูลเพิ่มภายใน 10 นาที"
            # เริ่ม/รีเซ็ตจับเวลา 10 นาที
            auction_data['bidding_over_time'] = time.time() + 600
        else:
             # ยกเลิกการจับเวลา 10 นาที (ถ้ามี)
            auction_data['bidding_over_time'] = None

        # ส่งข้อความบิดใหม่และตอบกลับ
        new_bid_message = await message.reply(bid_message_content, mention_author=False)
        auction_data['last_bid_message_id'] = new_bid_message.id
        
        # ลบข้อความบิดของผู้ใช้
        try:
             await message.delete()
        except:
             pass
        
    # ไม่ต้องเรียก bot.process_commands(message) ที่นี่อีก เพราะเรียกไปแล้ว
    # await bot.process_commands(message)

# --- 🎫 ระบบตั๋วฟอรั่ม (Ticket Forum System) 🎫 ---

# 1. คำสั่งหลัก /ticketf
@bot.tree.command(name="ticketf", description="ตั้งค่าระบบตั๋วผ่านช่องฟอรั่ม")
@app_commands.describe(
    category="หมวดหมู่ที่จะเอาไว้สร้างช่องส่วนตัว", 
    forum_channel="ช่องฟอรั่มที่จะใช้สร้างตั๋ว", 
    log_channel="ช่อง log (ไม่บังคับ)"
)
@is_admin()
async def ticket_forum_setup(
    interaction: discord.Interaction, 
    category: discord.CategoryChannel, 
    forum_channel: discord.ForumChannel, 
    log_channel: Optional[discord.TextChannel] = None
):
    """/ticketf {หมวดหมู่} {ช่องฟอรั่ม} {ช่อง log(ไม่บังคับ)}"""
    
    # เก็บข้อมูลการตั้งค่าฟอรั่มในบอท
    bot.forum_ticket_config[forum_channel.id] = {
        "category_id": category.id,
        "log_channel_id": log_channel.id if log_channel else None
    }
    
    await interaction.response.send_message(f"✅ ตั้งค่าระบบตั๋วฟอรั่มใน {forum_channel.mention} เรียบร้อยแล้ว\nช่องส่วนตัวจะถูกสร้างในหมวดหมู่ {category.mention}", ephemeral=True)

# 2. Event เมื่อมีกระทู้ใหม่ (Forum Post) ถูกสร้างขึ้น
@bot.event
async def on_thread_create(thread: discord.Thread):
    
    # ตรวจสอบว่าฟอรั่มนี้มีการตั้งค่าระบบตั๋วหรือไม่
    config = bot.forum_ticket_config.get(thread.parent_id)
    if not config:
        return

    # ปุ่มสั่งซื้อ
    buy_button = ui.Button(label="🛒 กดสั่งซื้อตรงนี้", style=discord.ButtonStyle.green, custom_id=f"ticketf_buy_{thread.id}")
    
    # ปุ่มรายงาน
    report_button = ui.Button(label="🚨 รายงาน", style=discord.ButtonStyle.red, custom_id=f"ticketf_report_{thread.id}")
    
    # ต้องสร้าง View ใหม่ทุกครั้ง
    view = ui.View(timeout=None)
    view.add_item(buy_button)
    view.add_item(report_button)

    # ส่งข้อความในกระทู้
    await thread.send("กดสั่งซื้อตรงนี้", view=view)

# 3. การจัดการปุ่ม (Buy/Report)
@bot.event
async def on_interaction(interaction: discord.Interaction):
    # ตรวจสอบว่าเป็นปุ่มที่ถูกกด
    if not interaction.type == discord.InteractionType.component:
        return

    custom_id = interaction.data.get('custom_id')
    
    if custom_id and custom_id.startswith('ticketf_'):
        try:
             thread_id = int(custom_id.split('_')[-1])
             thread = interaction.client.get_channel(thread_id)
        except ValueError:
             return
        
        if not thread or not isinstance(thread, discord.Thread):
            await interaction.response.send_message("❌ ไม่พบกระทู้ตั๋วนี้", ephemeral=True)
            return
            
        # ผู้สร้างฟอรั่ม (thread.owner ใน Discord.py 2.0+ หมายถึงผู้สร้างกระทู้)
        creator = thread.owner

        # ตรวจสอบว่าผู้กดไม่ใช่ผู้สร้าง
        if interaction.user.id == creator.id:
            await interaction.response.send_message("❌ คุณไม่สามารถกดปุ่มของกระทู้ที่คุณสร้างเองได้", ephemeral=True)
            return
            
        config = bot.forum_ticket_config.get(thread.parent_id)
        if not config:
             await interaction.response.send_message("❌ ไม่พบการตั้งค่าตั๋วฟอรั่ม", ephemeral=True)
             return

        # --- ปุ่มสั่งซื้อ (Buy) ---
        if custom_id.startswith('ticketf_buy'):
            global TICKET_ID_COUNTER
            
            category = interaction.guild.get_channel(config["category_id"])
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            
            if not category:
                 await interaction.response.send_message("❌ ไม่พบหมวดหมู่ที่ตั้งค่าไว้", ephemeral=True)
                 return

            ticket_id = TICKET_ID_COUNTER
            TICKET_ID_COUNTER += 1
            
            # ชื่อช่อง: "ID - ..."
            channel_name = f"ID - {ticket_id}"

            # Perms: เห็นเฉพาะผู้ซื้อ (interaction.user) และผู้ขาย (creator)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True),
                creator: discord.PermissionOverwrite(view_channel=True, send_messages=True), # ผู้ขาย
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), # ผู้ซื้อ
            }

            # อนุญาตบทบาทที่มีสิทธิ์ผู้ดูแลเห็นช่อง
            for role in interaction.guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True)
                    
            try:
                ticket_channel = await interaction.guild.create_text_channel(
                    name=channel_name, 
                    category=category, 
                    overwrites=overwrites
                )
            except discord.Forbidden:
                 await interaction.response.send_message("❌ บอทไม่มีสิทธิ์สร้างช่องส่วนตัวในหมวดหมู่ที่กำหนด", ephemeral=True)
                 return
                 
            # ส่งข้อความในช่องตั๋ว
            ticket_view = TicketView(creator_id=creator.id, buyer_id=interaction.user.id, log_channel=log_channel, thread_to_delete=thread)
            await ticket_channel.send(
                content=f"ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\nสามารถทำธุรกรรมได้เลย\n{creator.mention} (ผู้ขาย) | {interaction.user.mention} (ผู้ซื้อ)",
                view=ticket_view
            )

            await interaction.response.send_message(f"✅ สร้างช่องส่วนตัว {ticket_channel.mention} เรียบร้อยแล้ว", ephemeral=True)

        # --- ปุ่มรายงาน (Report) ---
        elif custom_id.startswith('ticketf_report'):
             # แสดง Modal สำหรับกรอกเหตุผลรายงาน
            log_channel_id = config.get("log_channel_id")
            await interaction.response.send_modal(ReportModal(creator, thread, log_channel_id))

    # ให้คำสั่งอื่นๆ ที่ใช้ปุ่มทำงานต่อ
    # Note: bot.process_commands(interaction) ใช้สำหรับคำสั่งเก่าที่มี prefix 
    # สำหรับ interaction นี้เราไม่ต้องทำอะไรต่อ

# 4. View: ปุ่มเสร็จสิ้น/ยกเลิกในช่องตั๋ว
class TicketView(ui.View):
    def __init__(self, creator_id, buyer_id, log_channel, thread_to_delete):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.buyer_id = buyer_id
        self.log_channel = log_channel
        self.thread_to_delete = thread_to_delete

    # ปุ่มเสร็จสิ้น (ปิดช่อง)
    @ui.button(label="เสร็จสิ้น (ปิดช่อง)", style=discord.ButtonStyle.green)
    async def complete_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # ตรวจสอบสิทธิ์ (ผู้ซื้อ ผู้ขาย Admin/SupportAdmin)
        is_owner = interaction.user.id == self.creator_id or interaction.user.id == self.buyer_id
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        is_support_admin = interaction.user.id in SUPPORT_ADMIN_USERS_ROLES or any(r.id in SUPPORT_ADMIN_USERS_ROLES for r in interaction.user.roles)
        
        if not (is_owner or is_admin or is_support_admin):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        # @supportadmin และแสดงปุ่มปิดช่องสำหรับแอดมิน
        support_admin_mentions = [interaction.guild.get_role(r_id).mention for r_id in SUPPORT_ADMIN_USERS_ROLES if interaction.guild.get_role(r_id)]
        support_mentions_str = ", ".join(support_admin_mentions) if support_admin_mentions else "**[No Support Admin Role Set]**"
        
        admin_close_view = AdminCloseTicketView(self.thread_to_delete)
        
        await interaction.response.send_message(
            f"✅ ธุรกรรมเสร็จสิ้น! {support_mentions_str} โปรดปิดช่องและลบฟอรั่มนี้",
            view=admin_close_view
        )
        
    # ปุ่มยกเลิก
    @ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.red)
    async def cancel_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # ตรวจสอบสิทธิ์ (ผู้ซื้อ ผู้ขาย Admin)
        is_owner = interaction.user.id == self.creator_id or interaction.user.id == self.buyer_id
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        if not (is_owner or is_admin):
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        # แสดง Modal สำหรับกรอกเหตุผล
        await interaction.response.send_modal(TicketCancelModal(self.creator_id, self.buyer_id, self.log_channel, interaction.channel))

# 5. View: ปุ่มปิดช่องสำหรับ Admin
class AdminCloseTicketView(ui.View):
    def __init__(self, thread_to_delete):
        super().__init__(timeout=None)
        self.thread_to_delete = thread_to_delete

    @ui.button(label="🔑 ปิดช่องสำหรับแอดมิน (ลบฟอรั่มด้วย)", style=discord.ButtonStyle.danger)
    async def admin_close(self, interaction: discord.Interaction, button: ui.Button):
        # ตรวจสอบสิทธิ์ Admin/ผู้ดูแล
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USERS_ROLES or any(r.id in ADMIN_USERS_ROLES for r in interaction.user.roles)
        
        if not is_admin:
            await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌", ephemeral=True)
            return

        await interaction.response.send_message("✅ ช่องและฟอรั่มถูกลบเรียบร้อยแล้ว", ephemeral=True)
        
        # ลบช่องตั๋ว
        try:
             await interaction.channel.delete(reason="Admin Closed Ticket")
        except:
             pass
        
        # ลบกระทู้ฟอรั่ม
        if self.thread_to_delete:
            try:
                await self.thread_to_delete.delete(reason="Admin Closed Ticket - Deleting corresponding forum thread")
            except:
                pass

# 6. Modal: ยกเลิกตั๋ว
class TicketCancelModal(ui.Modal, title="เหตุผลในการยกเลิกตั๋ว"):
    def __init__(self, creator_id, buyer_id, log_channel, ticket_channel):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.buyer_id = buyer_id
        self.log_channel = log_channel
        self.ticket_channel = ticket_channel

    reason = ui.TextInput(label="เหตุผล (บังคับ)", style=discord.TextStyle.long, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("❌ **ยกเลิก** ตั๋วแล้ว ช่องจะถูกลบในภายหลัง", ephemeral=True)
        
        # ส่งข้อความไป Log
        if self.log_channel:
            creator = await interaction.client.fetch_user(self.creator_id)
            buyer = await interaction.client.fetch_user(self.buyer_id)
            
            embed = discord.Embed(
                description=f"╭﹕ตั๋ว ID - {self.ticket_channel.name}\n"
                            f" | ﹕ผู้ขาย {creator.mention}\n"
                            f" | ﹕ผู้ซื้อ {buyer.mention}\n"
                            f" | ﹕ถูกยกเลิกโดย {interaction.user.mention}\n"
                            f"╰ ﹕เหตุผล : {self.reason.value}",
                color=discord.Color.red()
            )
            embed.set_author(name="ตั๋วถูกยกเลิก", icon_url=creator.display_avatar.url)
            await self.log_channel.send(embed=embed)
        
        # ลบช่อง
        try:
             await self.ticket_channel.delete(reason=f"Ticket Cancelled: {self.reason.value}")
        except:
             pass

# 7. Modal: รายงานตั๋วฟอรั่ม
class ReportModal(ui.Modal, title="รายงานกระทู้ฟอรั่ม"):
    def __init__(self, creator, thread, log_channel_id):
        super().__init__(timeout=None)
        self.creator = creator
        self.thread = thread
        self.log_channel_id = log_channel_id
        
    reason = ui.TextInput(label="เหตุผลในการรายงาน (บังคับ)", style=discord.TextStyle.long, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        
        await interaction.response.send_message("✅ ได้รับการรายงานแล้ว ขอบคุณที่ให้ความร่วมมือ", ephemeral=True)
        
        if self.log_channel_id:
            log_channel = interaction.guild.get_channel(self.log_channel_id)
            if log_channel:
                embed = discord.Embed(
                    title="🚨 การรายงานกระทู้ฟอรั่ม",
                    description=f"**รายงานจาก:** {interaction.user.mention}\n"
                                f"**กระทู้:** {self.thread.mention}\n"
                                f"**ผู้สร้าง:** {self.creator.mention}\n"
                                f"**เหตุผล:** {self.reason.value}",
                    color=discord.Color.dark_red()
                )
                await log_channel.send(embed=embed)

# --- ⚙️ รันบอท ⚙️ ---
# แทนที่ 'YOUR_BOT_TOKEN' ด้วย Token จริงของบอทคุณ
# bot.run('YOUR_BOT_TOKEN')
