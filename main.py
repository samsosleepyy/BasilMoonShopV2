import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import io 

# --- KEEP ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION ---
TOKEN = os.environ.get('TOKEN') or 'YOUR_BOT_TOKEN_HERE'

# --- DATA MANAGEMENT ---
DATA_FILE = "auction_data.json"

# ตัวแปรชั่วคราวสำหรับเก็บข้อมูลระหว่างรออัปโหลดรูป (RAM Only)
# Format: {user_id: {data_dict}}
pending_auctions = {}

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [],
            "support_ids": [],
            "setup": {}, 
            "auction_count": 0,
            "lock_time": 120,
            "active_auctions": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

data = load_data()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- UTILS ---
def is_admin(user):
    if user.id == bot.owner_id:
        return True
    if user.id in data["admins"]:
        return True
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True
    return False

async def no_permission(interaction):
    msg = "คุณไม่มีสิทธิ์ในการใช้คำสั่ง❌"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

# --- LOGIC FUNCTIONS (MOVED UP) ---

async def submit_to_approval(guild, full_data):
    # ฟังก์ชันส่งข้อมูลไปช่องอนุมัติ (แบบส่งไฟล์แนบหลายไฟล์พร้อม Embed)
    approval_channel_id = data["setup"].get("approval_channel")
    if not approval_channel_id:
        return None 
    
    approval_channel = guild.get_channel(approval_channel_id)
    if not approval_channel:
        return None
    
    # --- 1. เตรียมไฟล์สำหรับส่ง ---
    files_to_send = []
    # ใช้ io.BytesIO เพื่อให้ discord.File อ่านข้อมูลไบนารีได้
    if "images_data" in full_data:
        for img_info in full_data["images_data"]:
            files_to_send.append(
                discord.File(
                    fp=io.BytesIO(img_info["data"]), 
                    filename=img_info["filename"]
                )
            )

    # --- 2. สร้าง Embed หลัก (ข้อมูลครบ) ---
    main_embed = discord.Embed(title="คำขอเปิดประมูลใหม่", color=discord.Color.orange())
    main_embed.set_author(name=full_data['owner_name'], icon_url=None)
    main_embed.add_field(name="สินค้า", value=full_data['item'], inline=False)
    main_embed.add_field(name="ราคาเริ่มต้น", value=f"{full_data['start_price']} บ.", inline=True)
    main_embed.add_field(name="บิดขั้นต่ำ", value=f"{full_data['bid_step']} บ.", inline=True)
    main_embed.add_field(name="ราคาปิด (BIN)", value=f"{full_data['bin_price']} บ.", inline=True)
    main_embed.add_field(name="สิทธิ์", value=full_data['rights'], inline=True)
    main_embed.add_field(name="เวลาปิด", value=f"<t:{full_data['end_timestamp']}:R>", inline=True)
    main_embed.add_field(name="เพิ่มเติม", value=full_data['extra'], inline=False)

    # 3. ส่งไฟล์และ Embed ในข้อความเดียว
    sent_message = await approval_channel.send(
        embed=main_embed, 
        files=files_to_send, 
        view=ApprovalView(full_data)
    )
    
    # 4. บันทึก URL ใหม่ที่ Discord สร้างให้ และลบข้อมูลไบนารีออกจาก RAM
    full_data["images"] = [att.url for att in sent_message.attachments]
    if "images_data" in full_data:
        del full_data["images_data"] # ลบข้อมูลไบนารีทันทีเพื่อประหยัด RAM
    
    return True

# --- MODALS ---

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph)

    def __init__(self, auction_info):
        super().__init__()
        self.auction_info = auction_info

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            channel = interaction.guild.get_channel(feedback_channel_id)
            if channel:
                embed = discord.Embed(title="❌ การประมูลถูกยกเลิก", color=discord.Color.red())
                embed.add_field(name="การประมูลครั้งที่", value=str(self.auction_info['count']))
                embed.add_field(name="โดย", value=self.auction_info['owner_name'])
                embed.add_field(name="สถานะ", value=f"ไม่สำเร็จ (ยกเลิกโดย {interaction.user.name})")
                embed.add_field(name="เหตุผล", value=self.reason.value)
                await channel.send(embed=embed)

        await interaction.channel.delete()
        
        if str(interaction.channel_id) in data["active_auctions"]:
            del data["active_auctions"][str(interaction.channel_id)]
            save_data(data)

class DenyReasonModal(discord.ui.Modal, title="เหตุผลไม่อนุมัติ"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph)

    def __init__(self, owner_id, embed_data):
        super().__init__()
        self.owner_id = owner_id
        self.embed_data = embed_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("ส่งเหตุผลเรียบร้อยแล้ว", ephemeral=True)
        
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            channel = interaction.guild.get_channel(feedback_channel_id)
            if channel:
                await channel.send(f"🚫 ไม่อนุมัติการประมูลของ <@{self.owner_id}>\nเหตุผล: {self.reason.value}")
        
        try:
            await interaction.message.delete()
        except:
            pass

class AuctionImagesModal(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    # [แก้ไข] ลบช่องใส่รูปออก เหลือแค่ข้อมูลอื่น
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="เช่น สิทธิ์ขาด, สิทธิ์เชิงพาณิชย์", required=True)
    extra = discord.ui.TextInput(label="เพิ่มเติม", required=False)
    end_time_input = discord.ui.TextInput(label="เวลาปิด (ชั่วโมง:นาที)", placeholder="ตัวอย่าง 14:10", required=True, max_length=5)

    def __init__(self, first_step_data):
        super().__init__()
        self.first_step_data = first_step_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hours, minutes = map(int, self.end_time_input.value.split(":"))
            duration_seconds = (hours * 3600) + (minutes * 60)
            end_timestamp = int(time.time() + duration_seconds)
        except ValueError:
            return await interaction.response.send_message("รูปแบบเวลาไม่ถูกต้อง กรุณาใช้ HH:MM (เช่น 14:10)", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # รวมข้อมูล
        full_data = self.first_step_data
        full_data.update({
            "rights": self.rights.value,
            "extra": self.extra.value if self.extra.value else "-",
            "end_timestamp": end_timestamp,
            "owner_id": interaction.user.id,
            "owner_name": interaction.user.name,
            "images": [] # ล้าง/รอใส่ URL ใหม่หลังส่งไฟล์
        })

        # ตรวจสอบว่ามีการตั้งค่าช่องอัปโหลดรูปไหม
        img_channel_id = data["setup"].get("image_channel")
        if not img_channel_id:
            return await interaction.followup.send("❌ ระบบยังไม่ได้ตั้งค่าช่องอัปโหลดรูป (/imagec)", ephemeral=True)
        
        img_channel = interaction.guild.get_channel(img_channel_id)
        if not img_channel:
            return await interaction.followup.send("❌ หาช่องอัปโหลดรูปไม่เจอ", ephemeral=True)

        # 1. บันทึกข้อมูลลงตัวแปรชั่วคราว (Pending)
        pending_auctions[interaction.user.id] = full_data

        # 2. เปิดสิทธิ์ให้ผู้ใช้เห็นช่อง (Allow User)
        overwrite = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True
            # Others are False/Inherit
        )
        await img_channel.set_permissions(interaction.user, overwrite=overwrite)

        # 3. แจ้งเตือนผู้ใช้
        await interaction.followup.send(f"กรุณาส่งรูปภาพสินค้าที่ช่อง : {img_channel.mention} (ส่งได้หลายรูปใน 1 ข้อความ)", ephemeral=True)
        
        # ส่งข้อความ Tag ในช่องรูปภาพเพื่อให้รู้ง่ายๆ
        try:
            await img_channel.send(f"<@{interaction.user.id}> กรุณาส่งรูปสินค้าของคุณที่นี่...")
        except:
            pass

class AuctionDetailsModal(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่แค่ตัวเลข", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ใส่แค่ตัวเลข", required=True)
    bin_price = discord.ui.TextInput(label="ราคาปิดประมูล (BIN)", placeholder="ใส่แค่ตัวเลข", required=True)
    item = discord.ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            s_price = int(self.start_price.value)
            b_step = int(self.bid_step.value)
            bin_p = int(self.bin_price.value)
        except ValueError:
            return await interaction.response.send_message("กรุณาใส่ราคาเป็นตัวเลขเท่านั้น", ephemeral=True)

        first_step_data = {
            "start_price": s_price,
            "bid_step": b_step,
            "bin_price": bin_p,
            "item": self.item.value
        }
        
        view = ContinueSetupView(first_step_data)
        await interaction.response.send_message("กรอกข้อมูลส่วนแรกเสร็จสิ้น กดปุ่มด้านล่างเพื่อกรอกส่วนที่เหลือ", ephemeral=True, view=view)

# --- VIEWS ---

class TransactionView(discord.ui.View):
    def __init__(self, auction_id):
        super().__init__(timeout=None)
        self.auction_id = str(auction_id)

    @discord.ui.button(label="✅ เสร็จสิ้นการซื้อขาย", style=discord.ButtonStyle.green, custom_id="trans_success")
    async def success_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        await interaction.response.defer()

        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            channel = interaction.guild.get_channel(feedback_channel_id)
            if channel:
                embed = discord.Embed(title="✅ การซื้อขายเสร็จสิ้น", color=discord.Color.green())
                embed.add_field(name="การประมูลครั้งที่", value=str(auction['count']))
                embed.add_field(name="โดย", value=auction['owner_name'])
                embed.add_field(name="ผู้ชนะประมูล", value=auction.get('winner_name', 'Unknown'))
                embed.add_field(name="จบที่ราคา", value=f"{auction['current_price']} บ.")
                embed.add_field(name="สถานะ", value="สำเร็จเสร็จสิ้น")
                await channel.send(embed=embed)
        
        await interaction.followup.send("ปิดการขายเรียบร้อย ลบช่องใน 5 วินาที...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
        if str(interaction.channel_id) in data["active_auctions"]:
            del data["active_auctions"][str(interaction.channel_id)]
            save_data(data)

    @discord.ui.button(label="💰 กลางแอดมิน", style=discord.ButtonStyle.secondary, custom_id="trans_middleman")
    async def middleman_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction.get("winner_id") and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        msg = "มีการเรียกแอดมินกลาง!"
        for sup_id in data["support_ids"]:
            role = interaction.guild.get_role(sup_id)
            if role: 
                msg += f" {role.mention}"
            else:
                msg += f" <@{sup_id}>"

        await interaction.channel.send(msg)
        if not interaction.response.is_done():
            await interaction.response.send_message("แจ้งเตือนแอดมินเรียบร้อยแล้ว", ephemeral=True)

    @discord.ui.button(label="ยกเลิกการประมูล ❌", style=discord.ButtonStyle.red, custom_id="trans_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)

        await interaction.response.send_modal(CancelReasonModal(auction))


class AuctionControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ปิดการประมูล", style=discord.ButtonStyle.danger, custom_id="close_auction_manual")
    async def close_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        await interaction.response.send_message("กำลังปิดการประมูล...", ephemeral=True)
        await end_auction_process(interaction.channel, auction)

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data

    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            return await no_permission(interaction)
        
        await interaction.response.defer(ephemeral=True)

        data["auction_count"] += 1
        count = data["auction_count"]
        save_data(data)

        category_id = data["setup"].get("category_id")
        category = interaction.guild.get_channel(category_id)
        
        if not category:
            return await interaction.followup.send("หมวดหมู่ประมูลไม่ถูกต้อง", ephemeral=True)

        channel_name = f"การประมูลครั้งที่-{count}-ราคา-{self.auction_data['start_price']}"
        
        try:
            channel = await interaction.guild.create_text_channel(channel_name, category=category)
        except Exception as e:
            return await interaction.followup.send(f"สร้างห้องไม่สำเร็จ: {e}", ephemeral=True)

        noti_role_id = data["setup"].get("noti_role")
        ping_msg = f"<@&{noti_role_id}>" if noti_role_id else "@everyone"

        msg_content = f"""# การประมูลครั้งที่ - {count}
โดย <@{self.auction_data['owner_id']}>

### ราคาเริ่มต้น : {self.auction_data['start_price']}
### บิดครั้งละ : {self.auction_data['bid_step']}
### ราคาปิดประมูล : {self.auction_data['bin_price']}

สิ่งที่ได้รับ : {self.auction_data['item']}
สิทธิ์ : {self.auction_data['rights']}
เพิ่มเติม : {self.auction_data['extra']}
เวลาปิดประมูล : <t:{self.auction_data['end_timestamp']}:R>
{ping_msg}"""

        # [แก้ไข] ใช้ -# นำหน้าลิงก์แทนการใช้ ||...|| เพื่อให้ภาพแสดงพรีวิวได้
        valid_images = [img for img in self.auction_data['images'] if img]
        
        # ใช้ -# นำหน้า URL เพื่อให้แสดงเป็นลิงก์ปกติและภาพพรีวิวปรากฏ
        prefixed_images = [f"-# {url}" for url in valid_images] 

        img_str = "\n".join(prefixed_images)
        msg_content += f"\n{img_str}"

        await channel.send(msg_content, view=AuctionControlView())

        data["active_auctions"][str(channel.id)] = {
            "count": count,
            "owner_id": self.auction_data['owner_id'],
            "owner_name": self.auction_data['owner_name'],
            "current_price": self.auction_data['start_price'],
            "bid_step": self.auction_data['bid_step'],
            "bin_price": self.auction_data['bin_price'],
            "end_timestamp": self.auction_data['end_timestamp'],
            "winner_id": None,
            "winner_name": None,
            "last_msg_id": None,
            "history": [],
            "status": "active"
        }
        save_data(data)

        await interaction.followup.send(f"อนุมัติแล้ว สร้างห้องที่ {channel.mention}", ephemeral=True)
        self.stop()

    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            return await no_permission(interaction)
        
        await interaction.response.send_modal(DenyReasonModal(self.auction_data['owner_id'], self.auction_data))

class ContinueSetupView(discord.ui.View):
    def __init__(self, first_step_data):
        super().__init__(timeout=None)
        self.first_step_data = first_step_data

    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(AuctionImagesModal(self.first_step_data))
        except discord.HTTPException as e:
            print(f"Error opening modal: {e}")
            try:
                await interaction.followup.send("⚠️ ระบบกำลังทำงานช้า (Server Sleep) กรุณากดปุ่มใหม่อีกครั้งใน 10 วินาที", ephemeral=True)
            except:
                pass

class StartAuctionView(discord.ui.View):
    def __init__(self, label):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data['custom_id'] == "start_auction_btn":
            await interaction.response.send_modal(AuctionDetailsModal())
        return True

# --- NEW INFO COMMAND VIEWS ---

class InfoSelectView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=None)
        # ข้อมูลสำหรับส่งกลับ
        self.data = data
        
        # --- สร้าง Select Menu ---
        select = discord.ui.Select(
            placeholder=data['select_placeholder'],
            options=[
                discord.SelectOption(
                    label=data['select_label1'],
                    value="option1",
                    description=f"ข้อมูลเกี่ยวกับ {data['select_label1']}"
                ),
                discord.SelectOption(
                    label=data['select_label2'],
                    value="option2",
                    description=f"ข้อมูลเกี่ยวกับ {data['select_label2']}"
                )
            ],
            custom_id="info_select_menu"
        )
        select.callback = self.select_callback # กำหนด callback ให้ฟังก์ชันด้านล่าง
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        selected_value = interaction.data['values'][0]
        
        if selected_value == "option1":
            response_text = f"## 🎁 ข้อมูลเพิ่มเติม: {self.data['select_label1']}\n\n{self.data['info1']}"
        elif selected_value == "option2":
            response_text = f"## 🎁 ข้อมูลเพิ่มเติม: {self.data['select_label2']}\n\n{self.data['info2']}"
        else:
            response_text = "❌ ไม่มีข้อมูลสำหรับตัวเลือกนี้"
            
        # ส่งข้อความตอบกลับแบบส่วนตัว (Ephemeral)
        await interaction.response.send_message(response_text, ephemeral=True)


class InfoButtonView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=None)
        self.data = data

    @discord.ui.button(label=data['button_label'], style=discord.ButtonStyle.primary, custom_id="open_info_select_btn")
    async def open_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        select_view = InfoSelectView(self.data)
        
        # ตอบกลับด้วย Select Menu ใหม่ โดยส่งแบบ ephemeral เพื่อไม่ให้เกะกะ
        await interaction.response.send_message(
            f"✅ **กรุณาเลือกตัวเลือก:**", 
            view=select_view, 
            ephemeral=True
        )

# --- LOGIC FUNCTIONS (Continued) ---

async def end_auction_process(channel, auction_data):
    cid = str(channel.id)
    
    if cid not in data["active_auctions"]:
        return
    
    if data["active_auctions"][cid].get("status") == "ended":
        return 

    data["active_auctions"][cid]["status"] = "ended"
    save_data(data)

    winner_id = auction_data["winner_id"]
    
    if not winner_id:
        await channel.send("# ปิดประมูล (ไม่มีผู้ชนะ)")
        
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            feed_channel = channel.guild.get_channel(feedback_channel_id)
            if feed_channel:
                embed = discord.Embed(title="❌ การประมูลจบลง (ไม่มีผู้ประมูล)", color=discord.Color.red())
                embed.add_field(name="การประมูลครั้งที่", value=str(auction_data['count']))
                embed.add_field(name="โดย", value=auction_data['owner_name'])
                embed.add_field(name="สถานะ", value="ไม่มีผู้ประมูล")
                await feed_channel.send(embed=embed)
        
        await asyncio.sleep(5)
        await channel.delete()
        del data["active_auctions"][cid]
        save_data(data)
        return

    await channel.send(f"# <@{winner_id}> ชนะการประมูลครั้งที่ : {auction_data['count']}\n### จบที่ราคา : {auction_data['current_price']} บ.")

    lock_wait = data.get("lock_time", 120)
    if lock_wait > 0:
        lock_end_ts = int(time.time() + lock_wait)
        await channel.send(f"⏳ รอเวลา {lock_wait} วินาที ก่อนทำการล็อคห้อง <t:{lock_end_ts}:R>")
        await asyncio.sleep(lock_wait)

    try:
        await channel.send("ช่องนี้ได้เป็นช่องส่วนตัวแล้วสามารถทำธุรกรรมได้เลย...")
        
        overwrites = {}

        # DENY ALL
        deny_all = discord.PermissionOverwrite(
            view_channel=False,
            read_messages=False,
            read_message_history=False,
            send_messages=False,
            send_tts_messages=False,
            manage_messages=False,
            embed_links=False,
            attach_files=False,
            mention_everyone=False,
            use_external_emojis=False,
            add_reactions=False,
            use_application_commands=False,
            manage_channels=False,
            manage_permissions=False,
            manage_webhooks=False,
            create_instant_invite=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            manage_threads=False
        )

        # 1. ปิดกั้นทุกบทบาท
        for role in channel.guild.roles:
            if role.permissions.administrator:
                continue
            overwrites[role] = deny_all

        # 2. อนุญาตบอท
        overwrites[channel.guild.me] = discord.PermissionOverwrite(view_channel=True)
        
        # 3. Strict Allow for User
        strict_allow = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            add_reactions=True,
            create_instant_invite=False,
            manage_channels=False,
            manage_permissions=False,
            manage_webhooks=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            send_tts_messages=False,
            manage_messages=False,
            mention_everyone=False,
            use_external_emojis=False,
            use_application_commands=False,
            manage_threads=False,
            use_external_stickers=False
        )

        # 4. อนุญาตเจ้าของ
        owner = channel.guild.get_member(auction_data["owner_id"])
        if owner: 
            overwrites[owner] = strict_allow
        
        # 5. อนุญาตผู้ชนะ
        if winner_id:
            winner = channel.guild.get_member(winner_id)
            if winner: 
                overwrites[winner] = strict_allow
        
        await channel.edit(overwrites=overwrites)
        
        msg_text = f"""
ปุ่มสีเขียว ✅ เป็นของผู้เปิดประมูล
ปุ่มสีเทา 💰 เป็นของผู้ชนะประมูล
ปุ่มสีแดง ❌ เป็นของผู้เปิดประมูลและแอดมิน
        """
        await channel.send(msg_text, view=TransactionView(channel.id))
    except Exception as e:
        print(f"Error locking channel: {e}")

# --- BACKGROUND TASKS ---

@tasks.loop(seconds=30)
async def check_auctions_time():
    for channel_id, auction in list(data["active_auctions"].items()):
        if auction.get("status") == "ended":
            continue

        if time.time() >= auction["end_timestamp"]:
            channel = bot.get_channel(int(channel_id))
            if channel:
                await end_auction_process(channel, auction)
            else:
                del data["active_auctions"][channel_id]
                save_data(data)

# --- EVENTS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_auctions_time.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)
    
    if "btn_label" in data["setup"]:
        bot.add_view(StartAuctionView(data["setup"]["btn_label"]))
    # ต้อง add view ของ TransactionView และ InfoSelectView/InfoButtonView ถ้ามีการใช้ custom_id 
    # ในกรณีนี้เราไม่ได้ใช้ custom_id แบบคงที่ใน InfoSelectView และ InfoButtonView ที่มีการส่ง data
    # จึงไม่ต้อง add_view ตรงนี้ แต่ต้องทำให้โค้ดทำงานได้แม้บอทรีสตาร์ท (ซึ่งอาจต้องเปลี่ยนไปใช้ persistent views)
    bot.add_view(TransactionView(0)) # เพิ่มไว้เพื่อดักปุ่ม Transaction

@bot.event
async def on_message(message):
    if message.author.bot: return

    # ------------------------------------------------
    # [แก้ไข] ตรวจจับการอัปรูปในช่อง Image Channel และบันทึกไบนารี
    # ------------------------------------------------
    img_channel_id = data["setup"].get("image_channel")
    if img_channel_id and message.channel.id == img_channel_id:
        # เช็คว่าเป็นผู้ใช้ที่กำลังรอส่งรูปหรือไม่
        if message.author.id in pending_auctions:
            # เช็คว่ามีรูปไหม
            if message.attachments:
                
                # เอาข้อมูลที่จำไว้มาใช้
                full_data = pending_auctions[message.author.id]
                
                # บันทึกไบนารีของไฟล์และชื่อไฟล์
                full_data["images_data"] = [] 
                full_data["images"] = [] # ล้างคีย์ images ทิ้ง

                for attachment in message.attachments:
                    try:
                        file_bytes = await attachment.read()
                        full_data["images_data"].append({
                            "data": file_bytes,
                            "filename": attachment.filename
                        })
                    except Exception as e:
                        print(f"Error reading attachment: {e}")
                        
                # ส่งไปอนุมัติ
                await message.channel.send("ได้รับรูปภาพแล้ว กำลังส่งคำขออนุมัติ... ✅", delete_after=5)
                await submit_to_approval(message.guild, full_data)
                
                # ลบผู้ใช้ออกจาก pending และลบสิทธิ์ออกจากช่อง
                del pending_auctions[message.author.id]
                await message.channel.set_permissions(message.author, overwrite=None)
                
                return
            else:
                # ถ้าผู้ใช้พิมข้อความมาแต่ไม่มีรูป
                return 

    channel_id = str(message.channel.id)
    
    if channel_id in data["active_auctions"] and data["active_auctions"][channel_id].get("status") != "ended":
        auction = data["active_auctions"][channel_id]
        content = message.content.strip()
        
        if content.startswith("บิด"):
            try:
                amount = int(content.replace("บิด", "").strip())
            except ValueError:
                return
            
            current = auction["current_price"]
            step = auction["bid_step"]
            bin_price = auction["bin_price"]
            
            min_next = current + step if len(auction["history"]) > 0 else current
            
            if amount < min_next: 
                 await message.reply("ราคาที่คุณบิดต่ำเกินไป❌", delete_after=10)
                 return

            prev_winner_id = auction["winner_id"]
            
            auction["current_price"] = amount
            auction["winner_id"] = message.author.id
            auction["winner_name"] = message.author.name
            auction["history"].append({"user": message.author.id, "price": amount})
            
            if auction["last_msg_id"]:
                try:
                    old_msg = await message.channel.fetch_message(auction["last_msg_id"])
                    await old_msg.delete()
                except:
                    pass
            
            msg_text = f"# <@{message.author.id}> บิด {amount} บ.-"
            if prev_winner_id and prev_winner_id != message.author.id:
                msg_text += f"\n<@{prev_winner_id}> ถูกแซงแล้ว!"
            
            new_msg = await message.reply(msg_text)
            
            auction["last_msg_id"] = new_msg.id
            save_data(data)

            try:
                new_name = f"การประมูลครั้งที่-{auction['count']}-ราคา-{amount}"
                await message.channel.edit(name=new_name)
            except:
                pass

            if amount >= bin_price:
                await end_auction_process(message.channel, auction)

    await bot.process_commands(message)

# --- COMMANDS ---

@bot.tree.command(name="info", description="สร้างข้อความพร้อมปุ่มเมนูสำหรับแสดงข้อมูลเฉพาะผู้ใช้")
@app_commands.describe(
    channel="ช่องที่จะส่งข้อความไป",
    message="ข้อความหลัก",
    button_label="ข้อความปุ่มสำหรับเปิด Select (เช่น กดเพื่อดูข้อมูล)",
    select_placeholder="ข้อความที่แสดงในช่องเลือก (เช่น เลือกหัวข้อที่ต้องการ)",
    select_label1="ข้อความปุ่มตัวเลือกที่ 1 (เช่น วิธีการสั่ง)",
    select_label2="ข้อความปุ่มตัวเลือกที่ 2 (เช่น อัตราค่าบริการ)",
    info1="รายละเอียดที่จะแสดงเฉพาะผู้ใช้เมื่อเลือกตัวเลือก 1",
    info2="รายละเอียดที่จะแสดงเฉพาะผู้ใช้เมื่อเลือกตัวเลือก 2"
)
async def info_cmd(
    interaction: discord.Interaction, 
    channel: discord.TextChannel, 
    message: str, 
    button_label: str,
    select_placeholder: str,
    select_label1: str,
    select_label2: str,
    info1: str,
    info2: str
):
    if not is_admin(interaction.user):
        return await no_permission(interaction)

    await interaction.response.defer(ephemeral=True)
    
    # รวมข้อมูลสำหรับส่งให้ View
    info_data = {
        "button_label": button_label,
        "select_placeholder": select_placeholder,
        "select_label1": select_label1,
        "select_label2": select_label2,
        "info1": info1,
        "info2": info2
    }

    # สร้าง View ที่มีปุ่มเริ่มต้น
    view = InfoButtonView(info_data)

    # ส่งข้อความหลักพร้อมปุ่มเริ่มต้นไปยังช่องที่กำหนด
    try:
        await channel.send(message, view=view)
        await interaction.followup.send(f"ส่งข้อความพร้อมปุ่มไปยัง {channel.mention} เรียบร้อยแล้ว ✅", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการส่งข้อความ: {e}", ephemeral=True)


@bot.tree.command(name="imagec", description="ตั้งค่าช่องสำหรับอัปโหลดรูปภาพ")
async def imagec(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    # บันทึก ID ช่อง
    data["setup"]["image_channel"] = channel.id
    save_data(data)

    # ล็อคช่องไม่ให้ใครเห็น (นอกจาก Admin)
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    # ไล่ปิด Role อื่นๆ ด้วยเผื่อเหนียว
    for role in interaction.guild.roles:
        if role.permissions.administrator:
            continue
        overwrites[role] = discord.PermissionOverwrite(view_channel=False)
    
    await channel.edit(overwrites=overwrites)

    await interaction.response.send_message(f"ตั้งค่าช่องอัปโหลดรูปเป็น {channel.mention} และล็อคช่องเรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตจำนวนครั้งการประมูลกลับเป็น 0")
async def resetdata(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    data["auction_count"] = 0
    save_data(data)
    await interaction.response.send_message("รีเซ็ตจำนวนครั้งการประมูลเรียบร้อยแล้ว (ครั้งถัดไปจะเริ่มที่ 1) ✅", ephemeral=True)

@bot.tree.command(name="noti", description="ตั้งค่าบทบาทที่จะแจ้งเตือนเมื่อเปิดประมูล (แทนที่ @everyone)")
async def noti(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    data["setup"]["noti_role"] = role.id
    save_data(data)
    
    await interaction.response.send_message(f"ตั้งค่าแจ้งเตือนเป็น {role.mention} เรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="addadmin", description="เพิ่มสมาชิกที่จะสามารถใช้คำสั่งแอดมินได้")
async def addadmin(interaction: discord.Interaction, user: discord.User):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    if user.id not in data["admins"]:
        data["admins"].append(user.id)
        save_data(data)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"เพิ่ม {user.mention} เป็นแอดมินเรียบร้อย ✅")
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{user.mention} เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="supportadmin", description="เพิ่ม support admin (User หรือ Role)")
async def supportadmin(interaction: discord.Interaction, target: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    target_id = target.id if target else role.id if role else None
    if not target_id:
        return await interaction.response.send_message("กรุณาระบุ User หรือ Role", ephemeral=True)

    if target_id not in data["support_ids"]:
        data["support_ids"].append(target_id)
        save_data(data)
        name = target.mention if target else role.mention
        await interaction.response.send_message(f"เพิ่ม {name} เป็น Support Admin เรียบร้อย ✅")
    else:
        await interaction.response.send_message("มีอยู่ในรายการอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="lock", description="ตั้งเวลาคูลดาวน์ก่อนล็อคห้อง (วินาที)")
async def lock_cmd(interaction: discord.Interaction, time_sec: int = 120):
    if not is_admin(interaction.user):
        return await no_permission(interaction)
    
    data["lock_time"] = time_sec
    save_data(data)
    await interaction.response.send_message(f"ตั้งเวลาคูลดาวน์ก่อนล็อคห้องเป็น {time_sec} วินาที ✅")

@bot.tree.command(name="setup", description="ตั้งค่าห้องเปิดประมูล")
async def setup(interaction: discord.Interaction, 
                category: discord.CategoryChannel, 
                channel: discord.TextChannel, 
                message: str, 
                approval_channel: discord.TextChannel, 
                feedback_channel: discord.TextChannel = None, 
                btn_label: str = "💰 เปิดประมูล", 
                img_url: str = None):
    
    if not is_admin(interaction.user):
        return await no_permission(interaction)

    await interaction.response.defer(ephemeral=True)

    data["setup"] = {
        "category_id": category.id,
        "channel_id": channel.id,
        "approval_channel": approval_channel.id,
        "feedback_channel": feedback_channel.id if feedback_channel else None,
        "btn_label": btn_label,
        "noti_role": data["setup"].get("noti_role"),
        "image_channel": data["setup"].get("image_channel") # คงค่าเดิมถ้ามี
    }
    save_data(data)

    embed = discord.Embed(description=message, color=discord.Color.gold())
    if img_url:
        embed.set_image(url=img_url)
    
    view = StartAuctionView(btn_label)
    await channel.send(embed=embed, view=view)
    
    await interaction.followup.send("ตั้งค่าเรียบร้อยแล้ว ✅", ephemeral=True)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    keep_alive() 
    
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: ไม่พบ TOKEN ใน Environment Variables")
