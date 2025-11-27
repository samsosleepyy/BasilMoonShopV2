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
import re # สำหรับใช้ตรวจสอบชื่อผู้ใช้ในช่องส่งรูป

# --- KEEP ALIVE SERVER ---
# ... (โค้ด Keep Alive เดิม)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION (อัปเดตข้อความให้ตรงกับความต้องการใหม่) ---
TOKEN = os.environ.get('TOKEN') or 'YOUR_BOT_TOKEN_HERE' 
DATA_FILE = "auction_data.json"

TEXT_CONFIG = {
    # ข้อความทั่วไป
    "no_permission": "คุณไม่มีสิทธิ์ใช้คำสั่งนี้❌",
    "modal_error_time_format": "รูปแบบเวลาไม่ถูกต้อง (ใช้ ชช:นน เช่น 01:00)",
    "modal_error_number_format": "กรุณาใส่ราคาเป็นตัวเลขเท่านั้น",
    "generic_btn_label": "💳 เปิดการประมูล", # ค่าเริ่มต้นของปุ่มใน /auction
    # ระบบส่งรูป
    "image_channel_name_prefix": "✧꒰ส่งรูปสินค้า📦", 
    "image_prompt_first": "มีเวลา 3 นาทีในการส่งรูปสินค้าของคุณที่ {channel_mention}",
    "image_prompt_channel_1": "@user ส่งรูปสินค้าของคุณที่ช่องนี้📦\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่",
    "image_prompt_channel_2": "โปรดส่งรูป QR code หรือช่องทางการชำระเงิน🧾\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่",
    "image_received_1": "ได้รับรูปสินค้าเรียบร้อยแล้ว ✅",
    "image_received_2": "ได้รับรูป QR code/ช่องทางชำระเงินเรียบร้อยแล้ว📥 รอแอดมินยืนยัน⏳",
    "image_timeout_delete": "หมดเวลา 3 นาทีในการส่งรูปสินค้าแล้ว ช่องส่งรูปถูกลบอัตโนมัติ❌",
    "image_error_mismatch": "❌ การส่งรูปต้องเป็น User เดียวกันกับที่เริ่มกระบวนการ",
    # การประมูล
    "auction_approval_title": "คำขอเปิดประมูลใหม่",
    "auction_approval_embed_title": " ⊹ [{owner_name}] .ᐟ⊹",
    "auction_approve_category_error": "หมวดหมู่ประมูลไม่ถูกต้อง",
    "auction_approve_channel_error": "สร้างห้องไม่สำเร็จ: {error}",
    "auction_channel_name_format": "ประมูลครั้งที่-{count}-ราคา-{price}", # ใช้กับชื่อช่อง
    "auction_open_message": """# ˚₊‧꒰ა ☆ ໒꒱ ‧₊˚
      *เปิดประมูล!*

ᯓ★ โดย : {owner_mention}
ᯓ★ ราคาเริ่มต้น : {start_price}
ᯓ★ บิดครั้งละ : {bid_step}
ᯓ★ ราคาปิดประมูล : {bin_price}
ᯓ★ สิ่งที่ได้ : {item}
ᯓ★ สิทธิ์ : {rights}
ᯓ★ เพิ่มเติม : {extra}

-ˋˏ✄┈┈┈┈
**เวลาปิดประมูล : {end_time_relative}**

{ping_msg}""",
    "auction_deny_log": " ⊹ [{owner_name}] .ᐟ⊹\nประมูลของคุณไม่ได้รับอนุมัติจากแอดมิน : {admin_mention}❌\nเหตุผล : {reason}",
    "auction_deny_ephemeral": "❌ การประมูลของคุณไม่ได้รับอนุมัติ. โปรดตรวจสอบช่อง Log",
    "bid_too_low": "ราคาที่คุณบิดต่ำเกินไป❌",
    "bid_message_new": "# {user_mention} ราคา {amount} บ.-",
    "bid_message_overtake": "# {user_mention} ราคา {amount} บ.-\n{prev_winner_mention} โดนนำแล้ว!",
    "bid_message_bin": "# {user_mention} ราคา {amount} บ.-\n{prev_winner_mention} โดนนำแล้ว!\n-# ⚠️ตอนนี้ราคาถึงราคาปิดประมูลแล้วจะปิดประมูลอัตโนมัติทันทีหากไม่มีการประมูลเพิ่มภายใน {cooldown_min} นาที",
    "bid_message_bin_new": "# {user_mention} ราคา {amount} บ.-\n-# ⚠️ตอนนี้ราคาถึงราคาปิดประมูลแล้วจะปิดประมูลอัตโนมัติทันทีหากไม่มีการประมูลเพิ่มภายใน {cooldown_min} นาที",
    "auction_end_countdown": "📜 | {winner_mention} ชนะการประมูลครั้งที่ - {count}\nจบที่ราคา - {price} บ.-\n-# ช่องนี้กำลังจะถูกล็อคภายใน {lock_time} วินาทีเพื่อทำธุรกรรม🔐",
    "auction_end_no_winner": "การประมูลครั้งที่ - {count}\nโดย {owner_mention}\nการประมูลหมดเวลา",
    "lock_success_message": "ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\n{winner_mention} (ผู้ชนะประมูล) สามารถชำระเงินได้เลย\n-# ปุ่มสำหรับผู้เปิดประมูล\n{qr_code_url}",
    # ธุรกรรม/ยกเลิก
    "trans_success_ephemeral": "ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว ทางเราจะไม่รับผิดชอบใดๆ",
    "trans_success_log": "── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──\n╭﹕การประมูลครั้งที่ - {count}\n | ﹕โดย {owner_mention}\n | ﹕ผู้ชนะประมูล {winner_mention}\n╰ ﹕จบที่ราคา : {price} บ.",
    "trans_cancel_log": "╭﹕การประมูลครั้งที่ - {count}\n | ﹕โดย {owner_mention}\n | ﹕ถูกยกเลิกโดย {canceller_mention}\n╰ ﹕เหตุผล : {reason}",
    "trans_cancel_ephemeral": "ยกเลิกสำเร็จ ส่งรายงานไปที่ Log แล้ว.",
    # Forum Ticket
    "forum_btn_message": "กดสั่งซื้อตรงนี้",
    "forum_ticket_channel_name_format": "ID-{count}-{owner_name}",
    "forum_ticket_channel_msg": "ช่องนี้ได้เป็นช่องส่วนตัวแล้ว🔐\n{buyer_mention} (ผู้ซื้อ) - {seller_mention} (ผู้ขาย)\nสามารถทำธุรกรรมได้เลย",
    "forum_ticket_error_owner_buy": "❌ คุณเป็นเจ้าของฟอรั่มนี้ ไม่สามารถกดสั่งซื้อได้",
    "forum_ticket_finish_request": "ส่งคำขอเสร็จสิ้นแล้ว @supportadmin รอยืนยัน...",
    "forum_ticket_cancel_request": "ส่งคำขอยกเลิกแล้ว...",
    "forum_ticket_admin_confirm_error": "❌ ข้อมูลห้องนี้ผิดพลาด หรือถูกลบไปแล้ว",
    "forum_ticket_admin_confirm_success": "✅ ยืนยันเรียบร้อย! กำลังลบห้องและฟอรั่ม..."
}

# --- DATA MANAGEMENT ---
# ... (โค้ด Load/Save เดิม)
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [], # User/Role IDs ที่ใช้คำสั่ง Admin ได้
            "support_ids": [], # User/Role IDs ที่ใช้สำหรับกลาง/อนุมัติ
            "setup": {}, 
            "forum_setup": {}, 
            "auction_count": 0,
            "forum_ticket_count": 0, 
            "lock_time": 120, # /lockdown
            "bid_debounce_sec": 30, # Rate Limit Debounce
            "bid_bin_cooldown_min": 10, # Cooldown เมื่อถึงราคาปิดประมูล
            "active_auctions": {},
            "active_forum_tickets": {},
            "pending_auction_images": {} # {user_id: {data}} สำหรับเก็บข้อมูลการส่งรูป 2 ขั้นตอน
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        # ตรวจสอบและกำหนดค่าเริ่มต้นสำหรับค่าใหม่
        if "bid_debounce_sec" not in data:
            data["bid_debounce_sec"] = 30
        if "bid_bin_cooldown_min" not in data:
            data["bid_bin_cooldown_min"] = 10
        if "pending_auction_images" not in data:
            data["pending_auction_images"] = {}
        return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4) # **แก้ไขตามที่คุณแจ้ง**

data = load_data()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- UTILS ---
# ... (is_admin, is_support_admin, no_permission, get_support_mention เหมือนเดิม)
def is_admin(user):
    # ผู้ที่มีสิทธิ์ Administrator ใน Guild สามารถใช้คำสั่ง Admin ได้
    if user.id == bot.owner_id:
        return True
    if user.id in data["admins"]:
        return True
    if isinstance(user, discord.Member) and user.guild_permissions.administrator:
        return True
    # ตรวจสอบ Role Admin
    if isinstance(user, discord.Member):
        for role_id in data["admins"]:
            if user.get_role(role_id):
                return True
    return False

def is_support_admin(user):
    # ผู้ที่มีสิทธิ์ Support Admin หรือ Admin สามารถใช้คำสั่ง Support Admin ได้
    if is_admin(user): return True
    if user.id in data["support_ids"]: return True
    # ตรวจสอบ Role Support Admin
    if isinstance(user, discord.Member):
        for role_id in data["support_ids"]:
            if user.get_role(role_id):
                return True
    return False

async def no_permission(interaction):
    msg = TEXT_CONFIG["no_permission"]
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

def get_support_mention():
    msg = ""
    for sup_id in data["support_ids"]:
        msg += f" <@{sup_id}>"
    if not msg:
        msg = "@everyone" 
    return msg

async def revoke_permissions_after_timeout(user_id, channel_id, guild_id):
    await asyncio.sleep(180) # 3 นาที
    if user_id in data["pending_auction_images"]:
        del data["pending_auction_images"][user_id]
        save_data(data)
        
        guild = bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id)
        member = guild.get_member(user_id)
        
        if channel and member:
            try: await channel.delete()
            except: pass
        print(TEXT_CONFIG["image_timeout_delete"])
# --- LOGIC FUNCTIONS ---

# จัดการ Debounce การเปลี่ยนชื่อห้อง
async def update_channel_name_task(channel, count, amount):
    delay = data.get("bid_debounce_sec", 30)
    await asyncio.sleep(delay) 
    try:
        new_name = TEXT_CONFIG["auction_channel_name_format"].format(count=count, price=amount)
        await channel.edit(name=new_name)
    except Exception as e:
        print(f"Error updating channel name after delay: {e}")
    finally:
        cid = str(channel.id)
        if cid in data["active_auctions"] and data["active_auctions"][cid].get("name_task"):
            data["active_auctions"][cid]["name_task"] = None
            save_data(data)

# ฟังก์ชันนับถอยหลัง (เมื่อถึง BIN Price หรือหมดเวลาจริง)
async def run_countdown(channel, user_id, price, auction_data, is_bin_cooldown=False):
    channel_id = str(channel.id)
    
    if is_bin_cooldown:
        countdown_sec = data.get("bid_bin_cooldown_min", 10) * 60 # 10 นาที
        end_time = time.time() + countdown_sec
    else:
        end_time = auction_data["end_timestamp"]

    # ยกเลิก Task เก่า (ถ้ามี)
    if auction_data.get("timer_task"):
        auction_data["timer_task"].cancel()
        auction_data["timer_task"] = None

    # ลูปนับถอยหลัง
    while time.time() < end_time:
        remaining_sec = int(end_time - time.time())
        
        # สำหรับการนับถอยหลังปิดประมูลจริง (ทุก 1 นาที)
        if not is_bin_cooldown and remaining_sec % 60 == 0:
            remaining_delta = timedelta(seconds=remaining_sec)
            
            # แก้ไขข้อความหลัก
            try:
                main_msg = await channel.fetch_message(auction_data["main_msg_id"])
                new_content = main_msg.content.replace(
                    f"**เวลาปิดประมูล : <t:{auction_data['end_timestamp']}:R>**",
                    f"**เวลาปิดประมูล : {remaining_delta}**"
                )
                await main_msg.edit(content=new_content)
            except: pass # หากข้อความถูกลบไปแล้ว

        # หยุดชั่วคราว 1 วินาที
        await asyncio.sleep(1) 
        
    # เมื่อหมดเวลา (00:00)
    if not is_bin_cooldown:
        await end_auction_process(channel, auction_data, is_expired=True)
    # เมื่อหมดเวลา BIN Cooldown
    elif channel_id in data["active_auctions"] and data["active_auctions"][channel_id]["winner_id"] == user_id:
        await end_auction_process(channel, auction_data, is_expired=False)


async def end_auction_process(channel, auction_data, is_expired=False):
    cid = str(channel.id)
    if cid not in data["active_auctions"]: return
    
    # ยกเลิก Task ต่างๆ
    if auction_data.get("timer_task"): auction_data["timer_task"].cancel()
    if auction_data.get("name_task"): auction_data["name_task"].cancel()
    
    if data["active_auctions"][cid].get("status") == "ended": return 

    data["active_auctions"][cid]["status"] = "ended"
    save_data(data)

    winner_id = auction_data["winner_id"]
    
    # 1. ไม่มีผู้ชนะ
    if not winner_id:
        await channel.delete()
        log_channel_id = data["setup"].get("log_channel")
        if log_channel_id:
            log_channel = channel.guild.get_channel(log_channel_id)
            if log_channel:
                owner_mention = f"<@{auction_data['owner_id']}>"
                log_msg = TEXT_CONFIG["auction_end_no_winner"].format(count=auction_data['count'], owner_mention=owner_mention)
                embed = discord.Embed(description=log_msg, color=discord.Color.yellow())
                await log_channel.send(embed=embed)
        if cid in data["active_auctions"]: del data["active_auctions"][cid]; save_data(data)
        return

    # 2. มีผู้ชนะ (เข้าสู่ขั้นตอน Countdown Lock)
    lock_wait = data.get("lock_time", 120)
    winner_mention = f"<@{winner_id}>"
    
    countdown_msg_text = TEXT_CONFIG["auction_end_countdown"].format(
        winner_mention=winner_mention,
        count=auction_data['count'],
        price=auction_data['current_price'],
        lock_time=lock_wait
    )
    
    # ตรวจสอบและแก้ไข/ส่งข้อความ countdown
    countdown_msg = None
    if auction_data.get("last_bid_msg_id"):
        try:
            countdown_msg = await channel.fetch_message(auction_data["last_bid_msg_id"])
            await countdown_msg.edit(content=countdown_msg_text)
        except:
            countdown_msg = await channel.send(countdown_msg_text)
    else:
        countdown_msg = await channel.send(countdown_msg_text)

    await asyncio.sleep(lock_wait)

    # 3. ล็อคช่องและส่งปุ่มธุรกรรม
    await lock_channel_for_transaction(channel, auction_data, winner_id)

async def lock_channel_for_transaction(channel, auction_data, winner_id):
    try:
        overwrites = {}
        deny_all = discord.PermissionOverwrite(view_channel=False)
        for role in channel.guild.roles:
            if role.permissions.administrator: continue
            overwrites[role] = deny_all

        strict_allow = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True, attach_files=True, embed_links=True)

        owner = channel.guild.get_member(auction_data["owner_id"])
        if owner: overwrites[owner] = strict_allow
        
        winner = channel.guild.get_member(winner_id)
        if winner: overwrites[winner] = strict_allow
        
        await channel.edit(overwrites=overwrites)
        
        # นำ URL รูป QR Code จากรูปที่ 2 มาแสดง
        qr_code_url = auction_data.get("image_qr_url", "❌ ไม่พบรูป QR Code/ช่องทางชำระเงิน")

        lock_msg_text = TEXT_CONFIG["lock_success_message"].format(
            winner_mention=f"<@{winner_id}>",
            qr_code_url=qr_code_url
        )
        
        # ส่งข้อความล็อคช่องและปุ่มธุรกรรม
        await channel.send(lock_msg_text, view=TransactionView())
        
    except discord.Forbidden:
        await channel.send("❌ บอทไม่มีสิทธิ์จัดการช่อง (Manage Channels) กรุณาตรวจสอบสิทธิ์บอท", delete_after=30)
    except Exception as e:
        print(f"Error locking channel: {e}")

async def submit_to_approval(guild, full_data):
    # ... (โค้ดส่งไปช่องอนุมัติ)
    approval_channel_id = data["setup"].get("approval_channel")
    if not approval_channel_id: return None 
    approval_channel = guild.get_channel(approval_channel_id)
    if not approval_channel: return None
    
    files_to_send = []
    # รูปสินค้า (1)
    if "image_data_1" in full_data:
        files_to_send.append(discord.File(fp=io.BytesIO(full_data["image_data_1"]), filename="product_image.png"))
    # รูป QR Code/ชำระเงิน (2)
    if "image_data_2" in full_data:
        files_to_send.append(discord.File(fp=io.BytesIO(full_data["image_data_2"]), filename="qr_code_image.png"))

    main_embed = discord.Embed(title=TEXT_CONFIG["auction_approval_title"], color=discord.Color.orange())
    main_embed.set_author(name=full_data['owner_name'])
    main_embed.add_field(name="สินค้า", value=full_data['item'], inline=False)
    main_embed.add_field(name="ราคาเริ่มต้น", value=f"{full_data['start_price']} บ.", inline=True)
    main_embed.add_field(name="บิดขั้นต่ำ", value=f"{full_data['bid_step']} บ.", inline=True)
    main_embed.add_field(name="ราคาปิด", value=f"{full_data['bin_price']} บ.", inline=True)
    main_embed.add_field(name="สิทธิ์", value=full_data['rights'], inline=True)
    main_embed.add_field(name="เวลาปิด", value=f"<t:{full_data['end_timestamp']}:R>", inline=True)
    main_embed.add_field(name="เพิ่มเติม", value=full_data['extra'], inline=False)
    main_embed.set_footer(text=f"Owner ID: {full_data['owner_id']}")

    support_msg = get_support_mention()
    
    sent_message = await approval_channel.send(
        content=support_msg,
        embed=main_embed, 
        files=files_to_send, 
        view=ApprovalView(full_data)
    )
    
    # ดึง URL รูปภาพที่บอทส่งขึ้นไปแล้ว เพื่อเก็บไว้ใช้ภายหลัง
    full_data["image_url_1"] = sent_message.attachments[0].url if len(sent_message.attachments) > 0 else None
    full_data["image_qr_url"] = sent_message.attachments[1].url if len(sent_message.attachments) > 1 else None

    # ลบข้อมูลไบต์รูปภาพ
    if "image_data_1" in full_data: del full_data["image_data_1"]
    if "image_data_2" in full_data: del full_data["image_data_2"]
    
    return True

# --- MODALS ---

class DenyReasonModal(discord.ui.Modal, title="เหตุผลไม่อนุมัติ"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph)
    def __init__(self, owner_id, owner_name, admin_id):
        super().__init__()
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.admin_id = admin_id
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("ส่งเหตุผลเรียบร้อยแล้ว", ephemeral=True)
        log_channel_id = data["setup"].get("log_channel")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                log_msg = TEXT_CONFIG["auction_deny_log"].format(
                    owner_name=self.owner_name,
                    admin_mention=f"<@{self.admin_id}>",
                    reason=self.reason.value
                )
                embed = discord.Embed(description=log_msg, color=discord.Color.red())
                await log_channel.send(embed=embed)
                
        # แจ้งผู้ใช้ถึงการปฏิเสธ
        owner = interaction.guild.get_member(self.owner_id)
        if owner:
            try:
                await owner.send(TEXT_CONFIG["auction_deny_ephemeral"])
            except: pass
            
        try: await interaction.message.delete()
        except: pass

class AuctionImagesModal2(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    download_link = discord.ui.TextInput(label="ลิ้งค์ดาวน์โหลดสินค้า", placeholder="ใส่ลิ้งค์ดาวน์โหลดสินค้าของคุณ", required=True)
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="สิทธิ์ขาด-สิทธิ์เชิงพาณิชย์", required=True)
    extra = discord.ui.TextInput(label="เพิ่มเติม", placeholder="บอกว่าสินค้ามาจากที่ใดหรือเป็นของตัวเอง", required=False) 
    end_time_input = discord.ui.TextInput(label="เวลาปิดประมูล (ชช:นน)", placeholder="ตัวอย่าง 01:00 คือ 1 ชั่วโมง", required=True, max_length=5)
    
    def __init__(self, first_step_data):
        super().__init__()
        self.first_step_data = first_step_data
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # คำนวณเวลาปิดประมูล (หน่วยเป็นวินาที)
            time_parts = self.end_time_input.value.split(":")
            if len(time_parts) != 2: raise ValueError
            hours, minutes = map(int, time_parts)
            duration_seconds = (hours * 3600) + (minutes * 60)
            if duration_seconds <= 0: raise ValueError
            end_timestamp = int(time.time() + duration_seconds)
        except ValueError:
            return await interaction.response.send_message(TEXT_CONFIG["modal_error_time_format"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        full_data = self.first_step_data
        full_data.update({
            "download_link": self.download_link.value,
            "rights": self.rights.value,
            "extra": self.extra.value if self.extra.value else "-",
            "end_timestamp": end_timestamp,
            "owner_id": interaction.user.id,
            "owner_name": interaction.user.name,
            "image_url_1": None,
            "image_qr_url": None,
            "status": "pending_image_1" # สถานะการส่งรูปภาพ
        })

        # 1. สร้างช่องส่งรูปภาพ
        img_channel_id = data["setup"].get("image_channel")
        img_category_id = data["setup"].get("category_id")
        
        category = interaction.guild.get_channel(img_category_id)
        if not category:
            return await interaction.followup.send("❌ ไม่พบหมวดหมู่ที่จะสร้างช่องส่งรูป กรุณาตั้งค่า /auction ใหม่", ephemeral=True)
        
        channel_name = f"{TEXT_CONFIG['image_channel_name_prefix']}-{interaction.user.name.lower().replace(' ', '-')}"
        
        # Overwrites สำหรับช่องส่งรูป
        overwrites = {}
        deny_all = discord.PermissionOverwrite(view_channel=False)
        for role in interaction.guild.roles:
            if role.permissions.administrator: continue
            overwrites[role] = deny_all
            
        # อนุญาตเฉพาะผู้ใช้คนนี้และบอท
        allow_user = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True)
        overwrites[interaction.user] = allow_user
        overwrites[interaction.guild.me] = allow_user
        
        try:
            img_channel = await interaction.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        except Exception as e:
            return await interaction.followup.send(f"❌ สร้างช่องส่งรูปไม่สำเร็จ: {e}", ephemeral=True)

        # 2. บันทึกข้อมูลและสถานะการส่งรูป
        data["pending_auction_images"][interaction.user.id] = full_data
        data["pending_auction_images"][interaction.user.id]["img_channel_id"] = img_channel.id
        save_data(data)
        
        # 3. ส่งข้อความแจ้งเตือนผู้ใช้
        prompt_msg = TEXT_CONFIG["image_prompt_first"].format(channel_mention=img_channel.mention)
        await interaction.followup.send(prompt_msg, ephemeral=True)
        
        # 4. ส่งข้อความในช่องส่งรูป
        prompt_in_channel = TEXT_CONFIG["image_prompt_channel_1"].replace("@user", interaction.user.mention)
        await img_channel.send(prompt_in_channel)
        
        # 5. ตั้งเวลาลบช่องหากไม่ส่งรูปภายใน 3 นาที
        asyncio.create_task(revoke_permissions_after_timeout(interaction.user.id, img_channel.id, interaction.guild_id))

class AuctionDetailsModal1(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่แค่ตัวเลข", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ใส่แค่ตัวเลข", required=True)
    bin_price = discord.ui.TextInput(label="ราคาปิดประมูล", placeholder="ใส่แค่ตัวเลข", required=True)
    item = discord.ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            s_price = int(self.start_price.value)
            b_step = int(self.bid_step.value)
            bin_p = int(self.bin_price.value)
            if s_price < 0 or b_step <= 0 or bin_p < 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message(TEXT_CONFIG["modal_error_number_format"], ephemeral=True)
            
        first_step_data = {"start_price": s_price, "bid_step": b_step, "bin_price": bin_p, "item": self.item.value}
        
        # ส่งปุ่มเพื่อเรียก Modal ที่สอง
        view = ContinueSetupView(first_step_data)
        await interaction.response.send_message("กรอกข้อมูลส่วนแรกเสร็จสิ้น กดปุ่มด้านล่างเพื่อกรอกส่วนที่เหลือ", ephemeral=True, view=view)

class TicketCancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph, required=True)
    def __init__(self, ticket_data):
        super().__init__()
        self.ticket_data = ticket_data
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        log_channel_id = data["forum_setup"].get("log_channel")
        
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                owner_mention = f"<@{self.ticket_data['seller_id']}>"
                canceller_mention = f"<@{interaction.user.id}>"
                log_msg = TEXT_CONFIG["trans_cancel_log"].format(
                    count=self.ticket_data['count'], 
                    owner_mention=owner_mention,
                    canceller_mention=canceller_mention, 
                    reason=self.reason.value
                )
                embed = discord.Embed(description=log_msg, color=discord.Color.red())
                await log_channel.send(embed=embed)

        await interaction.followup.send(TEXT_CONFIG["trans_cancel_ephemeral"], ephemeral=True)
        # ลบช่อง Ticket ทันทีเมื่อยกเลิก
        if str(interaction.channel_id) in data["active_forum_tickets"]:
            del data["active_forum_tickets"][str(interaction.channel_id)]
            save_data(data)
        try: await interaction.channel.delete()
        except: pass

class ReportModal(discord.ui.Modal, title="แจ้งรายงาน (Report)"):
    reason = discord.ui.TextInput(label="รายละเอียด/เหตุผล", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        log_channel_id = data["forum_setup"].get("log_channel")
        if not log_channel_id: 
            return await interaction.followup.send("❌ ระบบยังไม่ได้ตั้งค่าช่อง Log สำหรับ Report", ephemeral=True)
            
        report_channel = interaction.guild.get_channel(log_channel_id)
        if report_channel:
            embed = discord.Embed(title="🚨 มีการแจ้งรายงานใหม่ (Report)", color=discord.Color.red())
            embed.add_field(name="👤 ผู้รายงาน", value=interaction.user.mention, inline=True)
            if isinstance(interaction.channel, discord.Thread):
                embed.add_field(name="👑 เจ้าของกระทู้", value=f"<@{interaction.channel.owner_id}>", inline=True)
                embed.add_field(name="🔗 ลิงก์กระทู้", value=f"[กดเพื่อไปที่กระทู้]({interaction.channel.jump_url})", inline=False)
            embed.add_field(name="📝 รายละเอียด/เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.now()
            
            support_msg = get_support_mention()
            await report_channel.send(content=support_msg, embed=embed)
            
            await interaction.followup.send("ส่งรายงานเรียบร้อยแล้ว ขอบคุณที่แจ้งครับ 🙏", ephemeral=True)
        else:
            await interaction.followup.send("❌ หาช่อง Log ไม่เจอ", ephemeral=True)

# --- VIEWS ---

class TransactionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="ยืนยันเสร็จสิ้น✅", style=discord.ButtonStyle.green, custom_id="trans_success_final")
    async def success_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        # ขั้นตอนที่ 1: ยืนยันก่อน
        await interaction.response.send_message(TEXT_CONFIG["trans_success_ephemeral"], ephemeral=True, view=ConfirmSuccessView())

    @discord.ui.button(label="ยกเลิก❌", style=discord.ButtonStyle.red, custom_id="trans_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        await interaction.response.send_modal(CancelReasonModal(auction))

class ConfirmSuccessView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60)
    @discord.ui.button(label="ยืนยันอีกครั้ง", style=discord.ButtonStyle.primary, custom_id="trans_confirm_final")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        await interaction.response.defer()
        
        log_channel_id = data["setup"].get("log_channel")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                owner_mention = f"<@{auction['owner_id']}>"
                winner_mention = f"<@{auction['winner_id']}>"
                log_msg = TEXT_CONFIG["trans_success_log"].format(
                    count=auction['count'], owner_mention=owner_mention, 
                    winner_mention=winner_mention, price=auction['current_price']
                )
                embed = discord.Embed(description=log_msg, color=discord.Color.green())
                # แนบรูปสินค้า (รูปแรก)
                if auction.get("image_url_1"):
                    embed.set_image(url=auction["image_url_1"])
                await log_channel.send(embed=embed)
        
        await interaction.followup.send("เสร็จสิ้น! ลบช่องใน 1 นาที...", ephemeral=True)
        await asyncio.sleep(60)
        await interaction.channel.delete()
        if str(interaction.channel_id) in data["active_auctions"]:
            del data["active_auctions"][str(interaction.channel_id)]
            save_data(data)

class AuctionControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🧾ปิดประมูล", style=discord.ButtonStyle.red, custom_id="close_auction_manual")
    async def close_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        
        if auction["winner_id"]:
            await interaction.response.send_message("กำลังปิดการประมูลและเข้าสู่ขั้นตอนธุรกรรม...", ephemeral=True)
            await end_auction_process(interaction.channel, auction)
        else:
            await interaction.response.send_message("กำลังปิดการประมูล (ไม่มีผู้ชนะ)...", ephemeral=True)
            await end_auction_process(interaction.channel, auction, is_expired=True)

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data
    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_admin(interaction.user): return await no_permission(interaction)
        await interaction.response.defer(ephemeral=True)
        
        # 1. เพิ่ม count
        data["auction_count"] += 1
        count = data["auction_count"]
        
        # 2. สร้างช่องประมูล
        category_id = data["setup"].get("category_id")
        category = interaction.guild.get_channel(category_id)
        
        channel_name = TEXT_CONFIG["auction_channel_name_format"].format(count=count, price=self.auction_data['start_price'])
        try: channel = await interaction.guild.create_text_channel(channel_name, category=category)
        except Exception as e: 
            return await interaction.followup.send(f"❌ สร้างห้องไม่สำเร็จ: {e}", ephemeral=True)
        
        # 3. ส่งข้อความหลัก
        noti_role_id = data["setup"].get("noti_role")
        ping_msg = f"<@&{noti_role_id}>" if noti_role_id else ""
        
        msg_content = TEXT_CONFIG["auction_open_message"].format(
            owner_mention=f"<@{self.auction_data['owner_id']}>",
            start_price=self.auction_data['start_price'], bid_step=self.auction_data['bid_step'],
            bin_price=self.auction_data['bin_price'], item=self.auction_data['item'],
            rights=self.auction_data['rights'], extra=self.auction_data['extra'],
            end_time_relative=f"<t:{self.auction_data['end_timestamp']}:R>", ping_msg=ping_msg
        )
        embed = discord.Embed(description=msg_content, color=discord.Color.green())
        if self.auction_data.get("image_url_1"):
            embed.set_image(url=self.auction_data["image_url_1"])
        
        main_msg = await channel.send(embed=embed, view=AuctionControlView())
        
        # 4. บันทึกข้อมูล
        auction_info = {
            "count": count, "owner_id": self.auction_data['owner_id'], "owner_name": self.auction_data['owner_name'],
            "current_price": self.auction_data['start_price'], "bid_step": self.auction_data['bid_step'],
            "bin_price": self.auction_data['bin_price'], "end_timestamp": self.auction_data['end_timestamp'],
            "winner_id": None, "winner_name": None, "last_bid_msg_id": None, "history": [], "status": "active",
            "image_url_1": self.auction_data.get("image_url_1"),
            "image_qr_url": self.auction_data.get("image_qr_url"),
            "main_msg_id": main_msg.id,
            "name_task": None,
            "timer_task": bot.loop.create_task(run_countdown(channel, self.auction_data['owner_id'], self.auction_data['start_price'], auction_info)) # เริ่มนับถอยหลัง
        }
        data["active_auctions"][str(channel.id)] = auction_info
        save_data(data)
        
        await interaction.followup.send(f"✅ อนุมัติแล้ว สร้างห้องที่ {channel.mention}", ephemeral=True)
        await interaction.message.delete()
        self.stop()
        
    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_admin(interaction.user): return await no_permission(interaction)
        await interaction.response.send_modal(DenyReasonModal(self.auction_data['owner_id'], self.auction_data['owner_name'], interaction.user.id))

class ContinueSetupView(discord.ui.View):
    def __init__(self, first_step_data):
        super().__init__(timeout=None)
        self.first_step_data = first_step_data
    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.send_modal(AuctionImagesModal2(self.first_step_data))
        except discord.HTTPException as e: pass

class StartAuctionView(discord.ui.View):
    def __init__(self, label):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn"))
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data['custom_id'] == "start_auction_btn":
            await interaction.response.send_modal(AuctionDetailsModal1())
        return True

class ForumPostControlView(discord.ui.View):
    def __init__(self, buy_label, report_label):
        super().__init__(timeout=None)
        self.buy_label = buy_label
        self.report_label = report_label
        self.add_item(discord.ui.Button(label=buy_label, style=discord.ButtonStyle.green, custom_id="forum_buy_btn"))
        self.add_item(discord.ui.Button(label=report_label, style=discord.ButtonStyle.red, custom_id="forum_report_btn"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.channel.owner_id == interaction.user.id:
            await interaction.response.send_message(TEXT_CONFIG["forum_ticket_error_owner_buy"], ephemeral=True)
            return False
        
        if interaction.data['custom_id'] == "forum_report_btn":
            await interaction.response.send_modal(ReportModal())
            return False
            
        elif interaction.data['custom_id'] == "forum_buy_btn":
            await self.handle_buy_ticket(interaction)
            return False
        return True

    async def handle_buy_ticket(self, interaction: discord.Interaction):
        # ... (โค้ดสร้าง Ticket Channel คล้ายกับโค้ดเดิม แต่ปรับชื่อ)
        setup = data.get("forum_setup", {})
        category_id = setup.get("category_id")
        if not category_id: 
            return await interaction.response.send_message("❌ ระบบขัดข้อง (Category not set)", ephemeral=True)
            
        category = interaction.guild.get_channel(category_id)
        if not category: 
            return await interaction.response.send_message("❌ หาหมวดหมู่ Ticket ไม่เจอ", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        data["forum_ticket_count"] += 1
        count = data["forum_ticket_count"]
        save_data(data)
        
        seller_id = interaction.channel.owner_id
        seller = interaction.guild.get_member(seller_id)
        buyer = interaction.user
        
        channel_name = TEXT_CONFIG["forum_ticket_channel_name_format"].format(count=count, owner_name=seller.name.lower().replace(' ', '-'))
        
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        strict_allow = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True, attach_files=True, embed_links=True)
        overwrites[buyer] = strict_allow
        if seller: overwrites[seller] = strict_allow
        overwrites[interaction.guild.me] = strict_allow
        
        ticket_channel = await interaction.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        data["active_forum_tickets"][str(ticket_channel.id)] = {
            "count": count, "thread_id": interaction.channel.id,
            "buyer_id": buyer.id, "seller_id": seller_id, "created_at": int(time.time()),
            "status": "active"
        }
        save_data(data)
        
        channel_msg = TEXT_CONFIG["forum_ticket_channel_msg"].format(
            buyer_mention=buyer.mention, seller_mention=seller.mention if seller else f"<@{seller_id}>"
        )
        await ticket_channel.send(channel_msg, view=ForumTicketControlView())
        await interaction.followup.send(f"สร้างห้องสั่งซื้อเรียบร้อยแล้ว: {ticket_channel.mention}", ephemeral=True)

class ForumTicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="เสร็จสิ้น", style=discord.ButtonStyle.green, custom_id="ft_finish")
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket_data = data["active_forum_tickets"].get(str(interaction.channel_id))
        if not ticket_data: return
        
        # ผู้ซื้อหรือผู้ขายกดได้
        if interaction.user.id not in [ticket_data["buyer_id"], ticket_data["seller_id"]]:
             return await no_permission(interaction)

        support_mention = get_support_mention()
        await interaction.channel.send(f"ส่งคำขอเสร็จสิ้นแล้ว {support_mention} รอยืนยัน...", view=AdminConfirmTicketView(ticket_data, "finish"))
        await interaction.response.send_message("ส่งคำขอจบงานแล้ว รอแอดมินยืนยัน...", ephemeral=True)
        
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.red, custom_id="ft_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket_data = data["active_forum_tickets"].get(str(interaction.channel_id))
        if not ticket_data: return
        
        # ผู้ซื้อหรือผู้ขายกดได้
        if interaction.user.id not in [ticket_data["buyer_id"], ticket_data["seller_id"]]:
             return await no_permission(interaction)
             
        await interaction.response.send_modal(TicketCancelReasonModal(ticket_data))

class AdminConfirmTicketView(discord.ui.View):
    def __init__(self, ticket_data, action):
        super().__init__(timeout=None)
        self.ticket_data = ticket_data
        self.action = action
    @discord.ui.button(label="ปิดช่องสำหรับแอดมิน", style=discord.ButtonStyle.primary, custom_id="admin_confirm_ticket_btn")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_admin(interaction.user): return await no_permission(interaction)
        await interaction.response.defer()
        
        channel_id = str(interaction.channel_id)
        thread_id = self.ticket_data.get("thread_id")
        
        # ลบกระทู้ Forum ต้นทาง (เพื่อไม่ให้กดซ้ำ)
        try:
            thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
            if thread: await thread.delete()
        except: pass

        # ส่ง Log (เหมือนกับ Log ใน Auction Success)
        log_channel_id = data["forum_setup"].get("log_channel")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=f"✅ Forum Ticket: ID-{self.ticket_data['count']} (สำเร็จ)", color=discord.Color.green())
                embed.add_field(name="ผู้ซื้อ", value=f"<@{self.ticket_data['buyer_id']}>", inline=True)
                embed.add_field(name="ผู้ขาย", value=f"<@{self.ticket_data['seller_id']}>", inline=True)
                await log_channel.send(embed=embed)


        await interaction.channel.send(TEXT_CONFIG["forum_ticket_admin_confirm_success"], delete_after=5)
        await asyncio.sleep(3)
        await interaction.channel.delete()
        if channel_id in data["active_forum_tickets"]:
            del data["active_forum_tickets"][channel_id]
            save_data(data)

# --- EVENTS ---

@bot.event
async def on_thread_create(thread):
    forum_channel_id = data.get("forum_setup", {}).get("forum_channel_id")
    if forum_channel_id and thread.parent_id == forum_channel_id:
        await asyncio.sleep(1)
        buy_label = data["forum_setup"].get("buy_label", "กดสั่งซื้อตรงนี้")
        report_label = data["forum_setup"].get("report_label", "รายงาน")
        view = ForumPostControlView(buy_label, report_label)
        await thread.send(buy_label, view=view)


@bot.event
async def on_message(message):
    if message.author.bot: 
        await bot.process_commands(message)
        return

    # 1. จัดการการส่งรูปภาพ (2 ขั้นตอน)
    user_id = message.author.id
    if user_id in data["pending_auction_images"]:
        pending_data = data["pending_auction_images"][user_id]
        if message.channel.id == pending_data.get("img_channel_id"):
            if not message.attachments: return
            
            attachment = message.attachments[0]
            file_bytes = await attachment.read()
            
            if pending_data["status"] == "pending_image_1":
                # ส่งรูปสินค้า (1)
                pending_data["image_data_1"] = file_bytes
                pending_data["status"] = "pending_image_2"
                save_data(data)
                
                await message.reply(TEXT_CONFIG["image_received_1"], delete_after=5)
                # ขอรูป QR Code/ช่องทางชำระเงิน (2)
                prompt_in_channel = TEXT_CONFIG["image_prompt_channel_2"].replace("@user", message.author.mention)
                await message.channel.send(prompt_in_channel)
                
            elif pending_data["status"] == "pending_image_2":
                # ส่งรูป QR Code/ชำระเงิน (2)
                pending_data["image_data_2"] = file_bytes
                
                await message.reply(TEXT_CONFIG["image_received_2"], delete_after=5)
                await message.channel.delete() # ลบช่องส่งรูปเมื่อเสร็จสิ้น
                
                del data["pending_auction_images"][user_id] # ลบข้อมูล Pending ออก
                save_data(data)
                
                await submit_to_approval(message.guild, pending_data) # ส่งไปช่องอนุมัติ
            return

    channel_id = str(message.channel.id)
    # 2. จัดการการบิดราคา
    if channel_id in data["active_auctions"] and data["active_auctions"][channel_id].get("status") != "ended":
        auction = data["active_auctions"][channel_id]
        content = message.content.strip()
        
        if content.lower().startswith("บิด"):
            try: amount = int(re.sub(r'[^0-9]', '', content[3:].strip()))
            except ValueError: return
            
            current = int(auction["current_price"])
            step = int(auction["bid_step"])
            bin_price = int(auction["bin_price"])
            prev_winner_id = auction["winner_id"]
            
            min_next = current + step 
            if amount < min_next: 
                 await message.reply(TEXT_CONFIG["bid_too_low"], ephemeral=False, delete_after=5)
                 return
                 
            # 1. อัปเดตข้อมูลการบิด
            auction["current_price"] = amount
            auction["winner_id"] = message.author.id
            auction["winner_name"] = message.author.name
            auction["history"].append({"user": message.author.id, "price": amount})
            
            # 2. จัดการ Task นับถอยหลัง (ยกเลิกถ้ามีการบิดใหม่)
            if auction.get("timer_task"): auction["timer_task"].cancel(); auction["timer_task"] = None
            
            # 3. สร้างข้อความตอบกลับ
            cooldown_min = data.get("bid_bin_cooldown_min", 10)
            is_overtake = (prev_winner_id and prev_winner_id != message.author.id)
            
            if bin_price > 0 and amount >= bin_price:
                # กรณีถึง BIN Price
                if is_overtake:
                    msg_text = TEXT_CONFIG["bid_message_bin"].format(
                        user_mention=message.author.mention, amount=amount, 
                        prev_winner_mention=f"<@{prev_winner_id}>", cooldown_min=cooldown_min
                    )
                else:
                    msg_text = TEXT_CONFIG["bid_message_bin_new"].format(
                        user_mention=message.author.mention, amount=amount, cooldown_min=cooldown_min
                    )
                
                # เริ่มนับถอยหลัง 10 นาที (BIN Cooldown)
                task = bot.loop.create_task(run_countdown(message.channel, message.author.id, amount, auction, is_bin_cooldown=True))
                auction["timer_task"] = task
                
            else:
                # กรณีบิดปกติ
                if is_overtake:
                    msg_text = TEXT_CONFIG["bid_message_overtake"].format(
                        user_mention=message.author.mention, amount=amount, prev_winner_mention=f"<@{prev_winner_id}>"
                    )
                else:
                    msg_text = TEXT_CONFIG["bid_message_new"].format(user_mention=message.author.mention, amount=amount)

            # 4. จัดการข้อความเก่าและส่ง/แก้ไขข้อความใหม่
            old_msg = None
            if auction.get("last_bid_msg_id"):
                try:
                    old_msg = await message.channel.fetch_message(auction["last_bid_msg_id"])
                    await old_msg.edit(content=msg_text)
                except:
                    old_msg = None # ถ้าแก้ไขไม่ได้/ถูกลบ
            
            new_msg = old_msg or await message.reply(msg_text)
            
            auction["last_bid_msg_id"] = new_msg.id
            save_data(data)
            
            # 5. จัดการ Rate Limit Debounce สำหรับชื่อช่อง
            if auction.get("name_task"): auction["name_task"].cancel()
            
            task = bot.loop.create_task(update_channel_name_task(message.channel, auction['count'], amount))
            auction["name_task"] = task
            save_data(data)

    await bot.process_commands(message)

# --- COMMANDS ---

@bot.tree.command(name="sync", description="ซิงค์คำสั่ง")
async def sync(interaction: discord.Interaction):
    if not is_admin(interaction.user): return await no_permission(interaction)
    try:
        fmt = await bot.tree.sync()
        await interaction.response.send_message(f"✅ Synced {len(fmt)} commands.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="addadmin", description="เพิ่มสมาชิกหรือบทบาทให้สามารถใช้คำสั่งบอทได้")
@app_commands.describe(target="สมาชิกหรือบทบาท")
async def addadmin_cmd(interaction: discord.Interaction, target: discord.User):
    if not is_admin(interaction.user): return await no_permission(interaction)
    target_id = target.id
    if target_id not in data["admins"]:
        data["admins"].append(target_id)
        save_data(data)
        await interaction.response.send_message(f"เพิ่ม {target.mention} เป็นแอดมินเรียบร้อย ✅", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removeadmin", description="เอาสิทธิ์แอดมินออก")
@app_commands.describe(target="สมาชิกหรือบทบาท")
async def removeadmin_cmd(interaction: discord.Interaction, target: discord.User):
    if not is_admin(interaction.user): return await no_permission(interaction)
    target_id = target.id
    if target_id in data["admins"]:
        data["admins"].remove(target_id)
        save_data(data)
        await interaction.response.send_message(f"เอาสิทธิ์แอดมินของ {target.mention} ออกเรียบร้อย ✅", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} ไม่ได้เป็นแอดมิน", ephemeral=True)

@bot.tree.command(name="addsupportadmin", description="เพิ่มสมาชิกหรือบทบาทให้เป็น Support Admin")
@app_commands.describe(target="สมาชิกหรือบทบาท")
async def addsupportadmin_cmd(interaction: discord.Interaction, target: discord.User):
    if not is_admin(interaction.user): return await no_permission(interaction)
    target_id = target.id
    if target_id not in data["support_ids"]:
        data["support_ids"].append(target_id)
        save_data(data)
        await interaction.response.send_message(f"เพิ่ม {target.mention} เป็น Support Admin เรียบร้อย ✅", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} เป็น Support Admin อยู่แล้ว", ephemeral=True)

@bot.tree.command(name="removesupportadmin", description="เอาสิทธิ์ Support Admin ออก")
@app_commands.describe(target="สมาชิกหรือบทบาท")
async def removesupportadmin_cmd(interaction: discord.Interaction, target: discord.User):
    if not is_admin(interaction.user): return await no_permission(interaction)
    target_id = target.id
    if target_id in data["support_ids"]:
        data["support_ids"].remove(target_id)
        save_data(data)
        await interaction.response.send_message(f"เอาสิทธิ์ Support Admin ของ {target.mention} ออกเรียบร้อย ✅", ephemeral=True)
    else:
        await interaction.response.send_message(f"{target.mention} ไม่ได้เป็น Support Admin", ephemeral=True)

@bot.tree.command(name="auction", description="ตั้งค่าระบบประมูล")
@app_commands.describe(
    category="หมวดหมู่สำหรับห้องประมูล", 
    channel="ช่องที่จะสร้างปุ่มเปิดประมูล", 
    message="ข้อความหลักในห้องเปิดประมูล", 
    approval_channel="ช่องสำหรับแอดมินอนุมัติ", 
    noti_role="บทบาทที่จะแจ้งเตือน", 
    log_channel="ช่องบอกสถานะต่างๆ (ไม่บังคับ)", 
    btn_label="ข้อความปุ่มเปิดประมูล (ไม่บังคับ)", 
    img_url="URL รูปภาพ (ไม่บังคับ)"
)
async def setup_auction(
    interaction: discord.Interaction, 
    category: discord.CategoryChannel, 
    channel: discord.TextChannel, 
    message: str, 
    approval_channel: discord.TextChannel, 
    noti_role: discord.Role,
    log_channel: discord.TextChannel = None, 
    btn_label: str = TEXT_CONFIG["generic_btn_label"], 
    img_url: str = None
):
    if not is_admin(interaction.user): return await no_permission(interaction)
    await interaction.response.defer(ephemeral=True)
    data["setup"] = {
        "category_id": category.id, 
        "channel_id": channel.id, 
        "approval_channel": approval_channel.id,
        "noti_role": noti_role.id,
        "log_channel": log_channel.id if log_channel else None, 
    }
    save_data(data)
    embed = discord.Embed(description=message, color=discord.Color.gold())
    if img_url: embed.set_image(url=img_url)
    view = StartAuctionView(btn_label)
    await channel.send(embed=embed, view=view)
    await interaction.followup.send("ตั้งค่าระบบประมูลเรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="lockdown", description="ตั้งเวลาคูลดาวน์ก่อนล็อคห้อง (วินาที)")
@app_commands.describe(time_sec="เวลาเป็นวินาที (ค่าเริ่มต้น 120)")
async def lockdown_cmd(interaction: discord.Interaction, time_sec: int):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["lock_time"] = time_sec
    save_data(data)
    await interaction.response.send_message(f"ตั้งเวลาคูลดาวน์ก่อนล็อคห้องเป็น {time_sec} วินาที ✅", ephemeral=True)

@bot.tree.command(name="ticketf", description="ตั้งค่าระบบ Forum Ticket")
@app_commands.describe(
    category="หมวดหมู่ที่จะสร้างห้อง Ticket", 
    forum_channel="ช่อง Forum ที่จะให้บอททำงาน", 
    log_channel="ช่องบอกสถานะต่างๆ (ไม่บังคับ)",
    buy_label="ข้อความปุ่มซื้อ (ไม่บังคับ)",
    report_label="ข้อความปุ่มรายงาน (ไม่บังคับ)"
)
async def ticketf_cmd(
    interaction: discord.Interaction, 
    category: discord.CategoryChannel, 
    forum_channel: discord.ForumChannel, 
    log_channel: discord.TextChannel = None,
    buy_label: str = TEXT_CONFIG["forum_btn_message"],
    report_label: str = "รายงาน"
):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["forum_setup"] = {
        "category_id": category.id, 
        "forum_channel_id": forum_channel.id, 
        "log_channel": log_channel.id if log_channel else None,
        "buy_label": buy_label,
        "report_label": report_label
    }
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งค่า Tickets Forum เรียบร้อย!\n- Forum: {forum_channel.mention}\n- Category สร้างห้อง: {category.mention}", ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตจำนวนครั้งการประมูลและ ID ของ Ticket")
async def resetdata_cmd(interaction: discord.Interaction):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["auction_count"] = 0
    data["forum_ticket_count"] = 0
    save_data(data)
    await interaction.response.send_message("รีเซ็ตจำนวนครั้งการประมูลและ Forum Tickets กลับเป็น 0 เรียบร้อยแล้ว ✅", ephemeral=True)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    keep_alive() 
    if TOKEN: bot.run(TOKEN)
    else: print("Error: ไม่พบ TOKEN")
