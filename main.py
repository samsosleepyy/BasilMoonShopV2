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
import random
from keep_alive import keep_alive

# =========================================
# 📝 CONFIGURATION & TEXT MESSAGES (แก้ไขข้อความทุกอย่างที่นี่)
# =========================================
MESSAGES = {
    # ---------------------------------------------------------
    # ⚙️ ระบบทั่วไป (System)
    # ---------------------------------------------------------
    "no_permission": "🚫 คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
    "cmd_success": "✅ ดำเนินการเรียบร้อย",
    "loading": "⏳ กำลังประมวลผล...",
    "processing": "⚙️ กำลังดำเนินการ...",
    
    # ข้อความ Admin Commands
    "sys_add_admin": "✅ เพิ่ม {target} เป็นแอดมิน",
    "sys_already_admin": "⚠️ {target} เป็นแอดมินอยู่แล้ว",
    "sys_remove_admin": "✅ ลบ {target} ออกจากแอดมิน",
    "sys_not_admin": "⚠️ {target} ไม่ได้เป็นแอดมิน",
    
    "sys_add_support": "✅ เพิ่ม {target} เป็น Support",
    "sys_already_support": "⚠️ {target} เป็น Support อยู่แล้ว",
    "sys_remove_support": "✅ ลบ {target} ออกจาก Support",
    "sys_not_support": "⚠️ {target} ไม่ได้เป็น Support",
    
    "sys_lockdown_set": "✅ ตั้งเวลา Lockdown: {seconds} วินาที",
    "sys_reset_done": "✅ รีเซ็ตข้อมูลเรียบร้อย",

    # ---------------------------------------------------------
    # 🔨 ระบบประมูล (Auction)
    # ---------------------------------------------------------
    # ปุ่มและสถานะ
    "auc_btn_default": "💳 เปิดการประมูล",
    "auc_prompt_step2": "👇 กรุณากดปุ่มด้านล่างเพื่อกรอกข้อมูลส่วนที่ 2",
    "auc_btn_step2": "กดกรอกข้อมูล 2",
    "auc_closing": "🛑 กำลังปิดประมูล...",
    "auc_no_data": "❌ เกิดข้อความผิดพลาด ไม่พบข้อมูลการประมูล",
    
    # Modal ขั้นตอนที่ 1 (ชื่อช่องกรอกข้อมูล)
    "auc_step1_title": "📝 ข้อมูลการประมูล (1/2)",
    "auc_lbl_start": "ราคาเริ่มต้น",
    "auc_ph_start": "ใส่ตัวเลขเท่านั้น",
    "auc_lbl_step": "บิดครั้งละ",
    "auc_ph_step": "ใส่ตัวเลขเท่านั้น",
    "auc_lbl_close": "ราคาปิดประมูล (Auto Buy)",
    "auc_ph_close": "ใส่ตัวเลขเท่านั้น",
    "auc_lbl_item": "สิ่งที่ได้ (ชื่อสินค้า)",
    
    # Modal ขั้นตอนที่ 2
    "auc_step2_title": "📝 ข้อมูลการประมูล (2/2)",
    "auc_lbl_link": "ลิ้งค์ดาวน์โหลดสินค้า",
    "auc_ph_link": "ใส่ลิ้งค์ดาวน์โหลดสินค้าของคุณ",
    "auc_lbl_rights": "สิทธิ์",
    "auc_ph_rights": "สิทธิ์ขาด / สิทธ์เชิงพาณิชย์",
    "auc_lbl_extra": "เพิ่มเติม",
    "auc_ph_extra": "รายละเอียดเพิ่มเติม (ไม่บังคับ)",
    "auc_lbl_time": "เวลาปิดประมูล (ชช:นน)",
    "auc_ph_time": "เช่น 01:00 คือ 1 ชั่วโมง",

    # การตรวจสอบรูปภาพ
    "auc_created_channel": "✅ สร้างช่องส่งรูปแล้วที่ {channel}",
    "auc_wait_img_1": "{user} 📦 ส่งรูปสินค้าของคุณที่ช่องนี้\n-# **สามารถส่งได้หลายรูปใน 1 ข้อความ** เพื่อให้แสดงเป็นอัลบั้มรวม",
    "auc_wait_img_2": "🧾 โปรดส่งรูป QR code หรือช่องทางการชำระเงิน\n-# ข้อมูลตรงนี้จะไม่มีการเผยแพร่",
    "auc_img_received": "📥 ได้รับรูปสินค้าเรียบร้อย รอแอดมินยืนยัน ⏳",
    "auc_err_num": "❌ กรุณากรอกช่องราคาเป็นตัวเลขเท่านั้น",
    "auc_err_time": "❌ รูปแบบเวลาไม่ถูกต้อง (ใช้ ชช:นน)",

    # การอนุมัติ (แอดมิน)
    "auc_embed_request_title": "คำขอเปิดประมูลใหม่", # หัวข้อ Embed ขออนุมัติ
    "auc_btn_approve": "อนุมัติ",
    "auc_btn_deny": "ไม่อนุมัติ",
    "auc_lbl_deny_reason": "เหตุผล",
    "auc_admin_approve_log": "✅ อนุมัติการประมูล สร้างห้องที่ {channel}",
    "auc_modal_deny_title": "เหตุผลการไม่อนุมัติ",
    "auc_deny_msg": "❌ ปฏิเสธการประมูลแล้ว",
    "auc_log_deny_title": "🚫 ไม่อนุมัติการประมูล", # หัวข้อ Embed Log
    
    # หน้าห้องประมูล (Public)
    "auc_embed_title": "# ˚₊‧꒰ა ☆ ໒꒱ ‧₊˚\n*🔥 เปิดประมูล!*",
    "auc_btn_force_close": "🧾 ปิดประมูล",
    
    # การบิด (Bidding)
    "auc_bid_response": "# {user} ราคา {amount}",
    "auc_bid_outbid": "\n{old_winner} โดนนำแล้ว!",
    "auc_bid_autobuy": "\n-# ⚠️ถึงราคาปิดประมูลแล้ว จะปิดอัตโนมัติหากไม่มีใครเพิ่มใน 10 นาที",
    
    # จบประมูล
    "auc_end_winner": "🎉 **จบการประมูล!**\n📜 ครั้งที่ {count} | ผู้ชนะ: {winner}\n💰 จบที่ราคา: **{price} บาท**\n-# 🔐 ช่องนี้จะถูกล็อคใน {time} วินาที",
    "auc_end_no_bid": "⚠️ **การประมูลจบลง (ไม่มีผู้ประมูล)**\n📜 ครั้งที่ {count} | ผู้ขาย: {seller}",
    "auc_lock_msg": "🔐 **ช่องนี้เป็นส่วนตัวแล้ว**\n({winner} ผู้ชนะประมูล) สามารถชำระเงินได้เลยครับ",
    
    # การชำระเงิน (Transaction)
    "auc_btn_confirm": "ยืนยันเสร็จสิ้น✅",
    "auc_btn_cancel": "ยกเลิก❌",
    "auc_btn_double_confirm": "ยืนยันอีกครั้ง",
    "auc_check_money": "⚠️ ตรวจสอบให้แน่ใจว่าได้รับเงินแล้ว ทางเราจะไม่รับผิดชอบใดๆ",
    "auc_modal_cancel_title": "เหตุผลการยกเลิก",
    "auc_msg_cancel_success": "✅ ยกเลิกเรียบร้อย ลบช่องใน 5 วินาที",
    
    # DM ส่งของ
    "auc_dm_success": "✅ ส่งลิ้งค์สินค้าทาง DM แล้วครับ",
    "auc_dm_fail": "⚠️ ไม่สามารถส่ง DM หา {user} ได้ (เขาอาจปิด DM)",
    "auc_dm_content": "📦 **ดาวน์โหลดสินค้าของคุณ:**\n{link}",
    
    # Logs (Embeds)
    "auc_success_log": "── .✦ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬 ✦. ──\n╭﹕📜 ประมูลครั้งที่ - {count}\n | ﹕👤 โดย {seller}\n | ﹕🏆 ผู้ชนะ {winner}\n╰ ﹕💰 จบที่ราคา : {price}",
    "auc_cancel_log": "╭﹕🚫 **ยกเลิกการประมูล** ครั้งที่ {count}\n | ﹕👤 โดย {seller}\n | ﹕❌ ยกเลิกโดย {user}\n╰ ﹕📝 เหตุผล : {reason}",

    # ---------------------------------------------------------
    # 🎫 ระบบ Ticket Forum
    # ---------------------------------------------------------
    "tf_setup_success": "✅ ตั้งค่า Forum {forum} เรียบร้อย",
    "tf_guide_msg": "👇 กดสั่งซื้อสินค้าตรงนี้", # ข้อความในกระทู้
    
    # ปุ่มหน้ากระทู้
    "tf_btn_buy": "🛒 สั่งซื้อ (Tickets)",
    "tf_btn_buying": "⏳ อยู่ในระหว่างการซื้อ", # ปุ่มสีเทา
    "tf_btn_report": "🚩 รายงาน",
    
    # Error Checks
    "tf_err_own_post": "❌ คุณไม่สามารถสั่งซื้อสินค้าของตัวเองได้",
    "tf_err_own_report": "❌ คุณไม่สามารถรายงานโพสต์ของตัวเองได้",
    "tf_only_seller": "🚫 เฉพาะ **ผู้ขาย** เท่านั้นที่สามารถกดปุ่มนี้ได้",
    
    # ในห้อง Ticket
    "tf_room_created": "🔐 **ช่องซื้อขายส่วนตัว**\n👤 ผู้ซื้อ: {buyer}\n👤 ผู้ขาย: {seller}\n-# สามารถเจรจาและโอนเงินได้เลยครับ",
    "tf_wait_admin": "🔔 กำลังเรียกแอดมินมาตรวจสอบ...",
    "tf_admin_panel_msg": "🛡️ ปุ่มสำหรับแอดมิน:",
    
    # ปุ่มควบคุม Ticket
    "tf_btn_finish": "เสร็จสิ้น(ปิดช่อง)",
    "tf_btn_cancel": "ยกเลิก",
    "tf_btn_admin_close": "ปิดช่องและลบโพสต์",
    
    # Modal รายงาน/ยกเลิก
    "tf_modal_report_title": "รายงานโพสต์",
    "tf_lbl_reason": "เหตุผล",
    "tf_msg_report_success": "✅ ส่งรายงานเรียบร้อย",
    "tf_modal_cancel_title": "เหตุผลการยกเลิก",
    
    # Logs Ticket (Embeds)
    "tf_log_report_title": "🚩 มีการรายงานโพสต์",
    "tf_log_cancel_title": "❌ 𝗧𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱",
    "tf_log_cancel_desc": "รายการถูกยกเลิก (Ticket ID-{count})",
    "tf_log_success_title": "✅ 𝗧𝗿𝗮𝗻𝘀𝗮𝗰𝘁𝗶𝗼𝗻 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱",
    "tf_log_success_desc": "ธุรกรรมเสร็จสิ้น (Ticket ID-{count})",

    # ---------------------------------------------------------
    # 🎰 ระบบ Gamble / Gacha & Points
    # ---------------------------------------------------------
    "msg_error_num": "❌ กรุณากรอกตัวเลขเท่านั้น",
    "insufficient_points": "❌ แต้มของคุณไม่พอ (ต้องการ {cost} แต้ม)",
    "point_balance": "💰 แต้มคงเหลือ: {points}",
    
    # --- Admin Point Commands ---
    "pt_add_success": "✅ เพิ่ม {amount} แต้ม ให้กับ {user} เรียบร้อย",
    "pt_remove_success": "✅ ลบ {amount} แต้ม ออกจาก {user} เรียบร้อย",
    "pt_current": "แต้มปัจจุบัน: {points}",

    # --- Gamble Setup (Step 1) ---
    "gam_setup_1_msg": "🛠️ **Setup 1/3**\nเลือกช่องที่จะส่งข้อความกิจกรรม และกรอกข้อมูลเบื้องต้น",
    "gam_setup_1_btn": "กรอกข้อมูล (ข้อความ/รูป)",
    "gam_modal_1_title": "ตั้งค่าพื้นฐาน",
    "gam_lbl_content": "ข้อความที่จะเขียน",
    "gam_lbl_img1": "ลิ้งค์รูปปก (Embed)",
    "gam_lbl_img2": "ลิ้งค์รูปตอนสุ่ม (Gacha Show)",
    "gam_lbl_btn_txt": "ข้อความปุ่มสุ่ม",
    "gam_lbl_cost": "ราคาต่อการสุ่ม 1 ครั้ง",
    "gam_ph_cost": "ใส่ตัวเลขเท่านั้น",

    # --- Gamble Setup (Step 2) ---
    "gam_setup_2_msg": "🛠️ **Setup 2/3**\nเลือกช่อง Log และตั้งค่าเรทรางวัล",
    "gam_setup_2_btn_chance": "ปรับโอกาส (%)",
    "gam_setup_2_btn_img": "ลิ้งค์รูปรางวัล",
    "gam_setup_2_next": "ถัดไป ➡️",
    "gam_modal_chance_title": "ตั้งค่าโอกาส (รวมต้อง 100%)",
    "gam_lbl_c1": "รางวัลที่ 1 (%)",
    "gam_lbl_c2": "รางวัลที่ 2 (%)",
    "gam_lbl_c3": "รางวัลที่ 3 (%)",
    "gam_lbl_c4": "รางวัลที่ 4 (%)",
    "gam_lbl_c5": "รางวัลที่ 5 (เกลือ) (%)",
    "gam_modal_img_title": "ใส่ลิ้งค์รูปรางวัล (ตามลำดับ)",
    "gam_lbl_i1": "รูปรางวัลที่ 1",
    "gam_lbl_i2": "รูปรางวัลที่ 2",
    "gam_lbl_i3": "รูปรางวัลที่ 3",
    "gam_lbl_i4": "รูปรางวัลที่ 4",
    "gam_lbl_i5": "รูปรางวัลที่ 5",

    # --- Gamble Setup (Step 3) ---
    "gam_setup_3_msg": "🛠️ **Setup 3/3**\nตั้งค่าระบบชำระเงิน",
    "gam_setup_3_btn": "ตั้งค่าการโอน",
    "gam_setup_finish": "✅ เสร็จสิ้น! สร้างห้องกิจกรรมเรียบร้อย",
    "gam_modal_pay_title": "ข้อมูลการชำระเงิน",
    "gam_lbl_tm_txt": "ข้อความ TrueMoney",
    "gam_lbl_pp_txt": "ข้อความ PromptPay",
    "gam_lbl_phone": "เบอร์วอเลท (รับซอง)",
    "gam_lbl_qr": "ลิ้งค์รูป QR Code",

    # --- Gamble Front-end (User View) ---
    "gam_select_topup": "เติม Point (Top-up)",
    "gam_opt_tm": "TrueMoney Wallet (ซอง)",
    "gam_opt_pp": "PromptPay (โอนสลิป)",
    
    # --- Top-up Flow ---
    "top_tm_modal_title": "เติมเงิน TrueMoney (ซอง)",
    "top_tm_lbl_link": "ลิ้งค์ซองอั่งเปา",
    "top_tm_sent": "✅ ส่งข้อมูลแล้ว รอแอดมินตรวจสอบ...",
    "top_tm_log": "🧧 **แจ้งเตือนเติมเงิน (ซอง)**\n👤 ผู้เติม: {user}\n🔗 ลิ้งค์: {link}",
    
    "top_pp_msg": "🏦 **โอนเงินผ่าน PromptPay**\nโปรดโอนเงินและกดปุ่มยืนยันเพื่อส่งสลิป",
    "top_pp_btn_confirm": "ยืนยันการโอน (ส่งสลิป)",
    "top_slip_room_created": "✅ สร้างห้องส่งสลิปแล้ว: {channel}",
    "top_slip_wait": "{user} 🧾 โปรดส่งรูปสลิปในช่องนี้\n-# จะมีแอดมินมาตรวจสอบและเติมพอยท์ให้",
    "top_slip_received": "📥 ได้รับสลิปแล้ว กำลังเรียกแอดมิน...",
    "top_slip_log_embed": "🧾 **รายการแจ้งโอน (สลิป)**\n👤 ผู้ใช้: {user}",
    "top_btn_give_point": "อนุมัติ / ให้ Point",
    "top_modal_give_title": "ระบุจำนวน Point",
    "top_lbl_amount": "จำนวน Point",
    "top_success_dm": "✅ เติมเงินสำเร็จ! คุณได้รับ {amount} Point",
    
    # --- Gameplay ---
    "play_anim_title": "🎰 กำลังสุ่ม...",
    "play_result_title": "🎉 ผลการสุ่ม",
    "play_result_desc": "คุณได้รับ: **รางวัลที่ {rank}**",
}

DATA_FILE = "data.json"

# =========================================
# DATA MANAGEMENT
# =========================================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [], "supports": [], "auction_count": 0, "ticket_count": 0,
            "ticket_configs": {}, "lockdown_time": 0,
            "points": {} # {user_id: int}
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

# Temporary cache for setup wizard
setup_cache = {}

# =========================================
# POINT SYSTEM COMMANDS
# =========================================
@bot.tree.command(name="addpoint", description="เพิ่มแต้มให้ผู้ใช้")
async def addpoint(interaction: discord.Interaction, user: discord.User, amount: int):
    if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    
    str_id = str(user.id)
    current = data["points"].get(str_id, 0)
    data["points"][str_id] = current + amount
    save_data(data)
    
    await interaction.response.send_message(f"{MESSAGES['pt_add_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=data['points'][str_id])})", ephemeral=True)

@bot.tree.command(name="removepoint", description="ลบแต้มออกจากผู้ใช้")
async def removepoint(interaction: discord.Interaction, user: discord.User, amount: int):
    if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    
    str_id = str(user.id)
    current = data["points"].get(str_id, 0)
    new_bal = max(0, current - amount)
    data["points"][str_id] = new_bal
    save_data(data)
    
    await interaction.response.send_message(f"{MESSAGES['pt_remove_success'].format(amount=amount, user=user.mention)} ({MESSAGES['pt_current'].format(points=new_bal)})", ephemeral=True)

# =========================================
# GAMBLE SYSTEM (WIZARD SETUP)
# =========================================
@bot.tree.command(name="gamble", description="สร้างห้องสุ่มกาชา (Wizard)")
async def gamble(interaction: discord.Interaction):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    
    # Init Cache
    setup_cache[interaction.user.id] = {
        "step": 1,
        "chances": [0]*5,
        "prizes": [None]*5
    }
    
    view = GambleSetupView1(interaction.user.id)
    await interaction.response.send_message(MESSAGES["gam_setup_1_msg"], view=view, ephemeral=True)

class GambleSetupView1(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    
    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่องกิจกรรม")
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["target_channel"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label=MESSAGES["gam_setup_1_btn"], style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(GambleStep1Modal(self.user_id, self))

class GambleStep1Modal(discord.ui.Modal, title=MESSAGES["gam_modal_1_title"]):
    content = discord.ui.TextInput(label=MESSAGES["gam_lbl_content"], style=discord.TextStyle.paragraph)
    img1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_img1"])
    img2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_img2"])
    btn_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_btn_txt"])
    cost = discord.ui.TextInput(label=MESSAGES["gam_lbl_cost"], placeholder=MESSAGES["gam_ph_cost"])

    def __init__(self, user_id, parent_view):
        super().__init__()
        self.user_id = user_id
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost_val = int(self.cost.value)
        except: return await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)

        cache = setup_cache[self.user_id]
        cache.update({
            "content": self.content.value,
            "img_main": self.img1.value,
            "img_gacha": self.img2.value,
            "btn_text": self.btn_text.value,
            "cost": cost_val
        })
        
        # Change to Step 2 (EDIT Message instead of Delete)
        view = GambleSetupView2(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_2_msg"], view=view)

class GambleSetupView2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่อง Log")
    async def select_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["log_channel"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label=MESSAGES["gam_setup_2_btn_chance"], style=discord.ButtonStyle.secondary)
    async def config_chance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleChancesModal(self.user_id))

    @discord.ui.button(label=MESSAGES["gam_setup_2_btn_img"], style=discord.ButtonStyle.secondary)
    async def config_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleImagesModal(self.user_id))

    @discord.ui.button(label=MESSAGES["gam_setup_2_next"], style=discord.ButtonStyle.green)
    async def go_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        # Check basic requirement
        if not setup_cache[self.user_id].get("log_channel"):
             return await interaction.response.send_message("❌ กรุณาเลือกช่อง Log ก่อน", ephemeral=True)
        
        # Change to Step 3 (EDIT Message)
        view = GambleSetupView3(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_3_msg"], view=view)

class GambleChancesModal(discord.ui.Modal, title=MESSAGES["gam_modal_chance_title"]):
    c1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c1"], placeholder="e.g. 1")
    c2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c2"], placeholder="e.g. 5")
    c3 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c3"], placeholder="e.g. 10")
    c4 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c4"], placeholder="e.g. 30")
    c5 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c5"], placeholder="e.g. 54")

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            chances = [float(self.c1.value), float(self.c2.value), float(self.c3.value), float(self.c4.value), float(self.c5.value)]
            if sum(chances) != 100:
                return await interaction.response.send_message("❌ ผลรวมต้องเท่ากับ 100%", ephemeral=True)
            setup_cache[self.user_id]["chances"] = chances
            await interaction.response.send_message("✅ บันทึกโอกาสแล้ว", ephemeral=True)
        except: await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)

class GambleImagesModal(discord.ui.Modal, title=MESSAGES["gam_modal_img_title"]):
    i1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i1"])
    i2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i2"])
    i3 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i3"])
    i4 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i4"])
    i5 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i5"])

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        imgs = [self.i1.value, self.i2.value, self.i3.value, self.i4.value, self.i5.value]
        setup_cache[self.user_id]["prizes"] = imgs
        await interaction.response.send_message("✅ บันทึกรูปรางวัลแล้ว", ephemeral=True)

class GambleSetupView3(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label=MESSAGES["gam_setup_3_btn"], style=discord.ButtonStyle.primary)
    async def open_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GamblePaymentModal(self.user_id))

class GamblePaymentModal(discord.ui.Modal, title=MESSAGES["gam_modal_pay_title"]):
    tm_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_tm_txt"])
    pp_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_pp_txt"])
    phone = discord.ui.TextInput(label=MESSAGES["gam_lbl_phone"])
    qr = discord.ui.TextInput(label=MESSAGES["gam_lbl_qr"])

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache[self.user_id]
        cache.update({
            "pay_tm": self.tm_text.value,
            "pay_pp": self.pp_text.value,
            "pay_phone": self.phone.value,
            "pay_qr": self.qr.value
        })
        
        # FINALIZE SETUP: Send the actual embed
        target_channel = cache["target_channel"]
        
        embed = discord.Embed(description=cache["content"], color=discord.Color.green())
        embed.set_image(url=cache["img_main"])
        
        # Create View for Users
        view = GambleMainView(cache)
        await target_channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(MESSAGES["gam_setup_finish"], ephemeral=True)
        del setup_cache[self.user_id]

# =========================================
# GAMBLE FRONT-END (USER INTERACTION)
# =========================================
class GambleMainView(discord.ui.View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config
        
        # Add Gacha Button dynamically
        gacha_btn = discord.ui.Button(label=config["btn_text"], style=discord.ButtonStyle.primary, custom_id="gacha_play")
        gacha_btn.callback = self.play_gacha
        self.add_item(gacha_btn)
        
        # Add Top-up Select
        self.add_item(TopUpSelect(config))

    async def play_gacha(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        points = data["points"].get(user_id, 0)
        cost = self.config["cost"]
        
        if points < cost:
            return await interaction.response.send_message(MESSAGES["insufficient_points"].format(cost=cost), ephemeral=True)
        
        # Deduct Point
        data["points"][user_id] = points - cost
        save_data(data)
        
        # Calculate Reward
        chances = self.config["chances"] # [1, 5, 10, 30, 54]
        prizes = self.config["prizes"]
        
        rand = random.uniform(0, 100)
        cumulative = 0
        prize_index = 4 # Default last one
        for i, chance in enumerate(chances):
            cumulative += chance
            if rand <= cumulative:
                prize_index = i
                break
        
        # Animation (Show Image 2)
        embed_anim = discord.Embed(title=MESSAGES["play_anim_title"], color=discord.Color.gold())
        embed_anim.set_image(url=self.config["img_gacha"])
        await interaction.response.send_message(embed=embed_anim, ephemeral=True)
        
        await asyncio.sleep(2) # Fake wait
        
        # Show Result
        embed_res = discord.Embed(
            title=MESSAGES["play_result_title"], 
            description=MESSAGES["play_result_desc"].format(rank=prize_index+1),
            color=discord.Color.green()
        )
        embed_res.set_image(url=prizes[prize_index])
        embed_res.set_footer(text=MESSAGES["point_balance"].format(points=data["points"][user_id]))
        
        await interaction.edit_original_response(embed=embed_res)

class TopUpSelect(discord.ui.Select):
    def __init__(self, config):
        self.config = config
        options = [
            discord.SelectOption(label=MESSAGES["gam_opt_tm"], value="tm", emoji="🧧"),
            discord.SelectOption(label=MESSAGES["gam_opt_pp"], value="pp", emoji="🏦")
        ]
        super().__init__(placeholder=MESSAGES["gam_select_topup"], options=options, custom_id="topup_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "tm":
            await interaction.response.send_modal(TopUpTMModal(self.config))
        elif self.values[0] == "pp":
            # PromptPay Flow
            embed = discord.Embed(description=self.config["pay_pp"], color=discord.Color.blue())
            embed.set_image(url=self.config["pay_qr"])
            view = PromptPayConfirmView(self.config)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- TrueMoney Modal ---
class TopUpTMModal(discord.ui.Modal, title=MESSAGES["top_tm_modal_title"]):
    link = discord.ui.TextInput(label=MESSAGES["top_tm_lbl_link"])
    
    def __init__(self, config):
        super().__init__()
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = interaction.guild.get_channel(self.config["log_channel"].id)
        if log_channel:
            await log_channel.send(MESSAGES["top_tm_log"].format(user=interaction.user.mention, link=self.link.value))
        await interaction.response.send_message(MESSAGES["top_tm_sent"], ephemeral=True)

# --- PromptPay View ---
class PromptPayConfirmView(discord.ui.View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config

    @discord.ui.button(label=MESSAGES["top_pp_btn_confirm"], style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create Private Channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        for admin_id in data["admins"]:
            mem = interaction.guild.get_member(admin_id)
            if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True)
            
        channel = await interaction.guild.create_text_channel(f"slip-{interaction.user.name}", overwrites=overwrites)
        await interaction.response.send_message(MESSAGES["top_slip_room_created"].format(channel=channel.mention), ephemeral=True)
        
        await channel.send(MESSAGES["top_slip_wait"].format(user=interaction.user.mention))
        
        # Wait for slip
        def check(m): return m.author.id == interaction.user.id and m.channel.id == channel.id and m.attachments
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            slip_url = msg.attachments[0].url
            await channel.send(MESSAGES["top_slip_received"])
            
            # Send to Log
            log_channel = interaction.guild.get_channel(self.config["log_channel"].id)
            if log_channel:
                embed = discord.Embed(description=MESSAGES["top_slip_log_embed"].format(user=interaction.user.mention), color=discord.Color.orange())
                embed.set_image(url=slip_url)
                # View for Admin to give points
                view = AdminSlipCheckView(interaction.user.id, channel.id)
                await log_channel.send(embed=embed, view=view)
                
        except asyncio.TimeoutError:
            await channel.delete()

class AdminSlipCheckView(discord.ui.View):
    def __init__(self, target_user_id, slip_channel_id):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.slip_channel_id = slip_channel_id

    @discord.ui.button(label=MESSAGES["top_btn_give_point"], style=discord.ButtonStyle.green)
    async def give_point(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGivePointModal(self.target_user_id, self.slip_channel_id))

class AdminGivePointModal(discord.ui.Modal, title=MESSAGES["top_modal_give_title"]):
    amount = discord.ui.TextInput(label=MESSAGES["top_lbl_amount"], placeholder="เช่น 100")

    def __init__(self, target_user_id, slip_channel_id):
        super().__init__()
        self.target_user_id = target_user_id
        self.slip_channel_id = slip_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            str_id = str(self.target_user_id)
            current = data["points"].get(str_id, 0)
            data["points"][str_id] = current + amt
            save_data(data)
            
            # Notify User & Delete Channel
            try:
                target_user = await bot.fetch_user(self.target_user_id)
                await target_user.send(MESSAGES["top_success_dm"].format(amount=amt))
            except: pass
            
            slip_channel = bot.get_channel(self.slip_channel_id)
            if slip_channel: await slip_channel.delete()
            
            await interaction.response.send_message(MESSAGES["cmd_success"], ephemeral=True)
            
        except ValueError: await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)

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
        await interaction.response.send_message(MESSAGES["sys_add_admin"].format(target=target.mention), ephemeral=True)
    else: await interaction.response.send_message(MESSAGES["sys_already_admin"].format(target=target.mention), ephemeral=True)

@bot.tree.command(name="removeadmin", description="ลบสิทธิ์แอดมิน")
async def removeadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id in data["admins"]:
        data["admins"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(MESSAGES["sys_remove_admin"].format(target=target.mention), ephemeral=True)
    else: await interaction.response.send_message(MESSAGES["sys_not_admin"].format(target=target.mention), ephemeral=True)

@bot.tree.command(name="addsupportadmin", description="เพิ่มสิทธิ์ Support")
async def addsupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id not in data["supports"]:
        data["supports"].append(target.id)
        save_data(data)
        await interaction.response.send_message(MESSAGES["sys_add_support"].format(target=target.mention), ephemeral=True)
    else: await interaction.response.send_message(MESSAGES["sys_already_support"].format(target=target.mention), ephemeral=True)

@bot.tree.command(name="removesupportadmin", description="ลบสิทธิ์ Support")
async def removesupportadmin(interaction: discord.Interaction, target: discord.User | discord.Role):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    if target.id in data["supports"]:
        data["supports"].remove(target.id)
        save_data(data)
        await interaction.response.send_message(MESSAGES["sys_remove_support"].format(target=target.mention), ephemeral=True)
    else: await interaction.response.send_message(MESSAGES["sys_not_support"].format(target=target.mention), ephemeral=True)

@bot.tree.command(name="lockdown", description="กำหนดเวลาล็อคช่อง (วินาที)")
async def lockdown_cmd(interaction: discord.Interaction, seconds: int):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    data["lockdown_time"] = seconds
    save_data(data)
    await interaction.response.send_message(MESSAGES["sys_lockdown_set"].format(seconds=seconds), ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตข้อมูล ID")
async def resetdata(interaction: discord.Interaction):
    if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
    data["auction_count"] = 0
    data["ticket_count"] = 0
    save_data(data)
    await interaction.response.send_message(MESSAGES["sys_reset_done"], ephemeral=True)

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
    start_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_start"], placeholder=MESSAGES["auc_ph_start"], required=True)
    bid_step = discord.ui.TextInput(label=MESSAGES["auc_lbl_step"], placeholder=MESSAGES["auc_ph_step"], required=True)
    close_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_close"], placeholder=MESSAGES["auc_ph_close"], required=True)
    item_name = discord.ui.TextInput(label=MESSAGES["auc_lbl_item"], required=True)

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
            await interaction.response.send_message(MESSAGES["auc_prompt_step2"], view=view, ephemeral=True)
        except ValueError: await interaction.response.send_message(MESSAGES["auc_err_num"], ephemeral=True)

class Step2View(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data
    @discord.ui.button(label=MESSAGES["auc_btn_step2"], style=discord.ButtonStyle.primary)
    async def open_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModalStep2(self.auction_data))

class AuctionModalStep2(discord.ui.Modal, title=MESSAGES["auc_step2_title"]):
    download_link = discord.ui.TextInput(label=MESSAGES["auc_lbl_link"], placeholder=MESSAGES["auc_ph_link"], required=True)
    rights = discord.ui.TextInput(label=MESSAGES["auc_lbl_rights"], placeholder=MESSAGES["auc_ph_rights"], required=True)
    extra_info = discord.ui.TextInput(label=MESSAGES["auc_lbl_extra"], placeholder=MESSAGES["auc_ph_extra"], required=False)
    end_time_str = discord.ui.TextInput(label=MESSAGES["auc_lbl_time"], placeholder=MESSAGES["auc_ph_time"], required=True)

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
        except: await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)

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
                base_embed = discord.Embed(title=MESSAGES["auc_embed_request_title"], color=discord.Color.gold())
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

    @discord.ui.button(label=MESSAGES["auc_btn_approve"], style=discord.ButtonStyle.green)
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

    @discord.ui.button(label=MESSAGES["auc_btn_deny"], style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyModal(self.auction_data, self.temp_channel))

class DenyModal(discord.ui.Modal, title=MESSAGES["auc_modal_deny_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["auc_lbl_deny_reason"], required=True)
    def __init__(self, auction_data, temp_channel):
        super().__init__()
        self.auction_data, self.temp_channel = auction_data, temp_channel
    async def on_submit(self, interaction: discord.Interaction):
        if self.temp_channel: await self.temp_channel.delete()
        if self.auction_data["log_id"]:
            log_chan = bot.get_channel(self.auction_data["log_id"])
            embed = discord.Embed(title=MESSAGES["auc_log_deny_title"], color=discord.Color.red())
            embed.add_field(name="👤 ผู้ขาย", value=f"<@{self.auction_data['seller_id']}>", inline=True)
            embed.add_field(name="👮 ปฏิเสธโดย", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.datetime.now()
            await log_chan.send(embed=embed)

        await interaction.response.send_message(MESSAGES["auc_deny_msg"], ephemeral=True)

class AuctionControlView(discord.ui.View):
    def __init__(self, seller_id):
        super().__init__(timeout=None)
        self.seller_id = seller_id
    @discord.ui.button(label=MESSAGES["auc_btn_force_close"], style=discord.ButtonStyle.red)
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id or is_admin_or_has_permission(interaction):
            if interaction.channel_id in active_auctions:
                active_auctions[interaction.channel_id]['end_time'] = datetime.datetime.now()
                await interaction.response.send_message(MESSAGES["auc_closing"], ephemeral=True)
            else:
                 await interaction.response.send_message(MESSAGES["auc_no_data"], ephemeral=True)
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
    # Send Winner Announcement and capture the message
    winner_msg = await channel.send(MESSAGES["auc_end_winner"].format(winner=winner_mention, count=data['auction_count'], price=auction_data['current_price'], time=data['lockdown_time']))
    
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
    
    # Clean up clutter messages
    try: await winner_msg.delete()
    except: pass
    
    if auction_data.get('last_bid_msg_id'):
        try:
            last_bid_msg = await channel.fetch_message(auction_data['last_bid_msg_id'])
            await last_bid_msg.delete()
        except: pass

    embed = discord.Embed(description=MESSAGES["auc_lock_msg"].format(winner=winner_mention), color=discord.Color.green())
    embed.add_field(name="ปุ่มสำหรับผู้เปิดประมูล", value="ด้านล่าง")
    embed.set_image(url=auction_data['img_qr_url'])
    view = TransactionView(seller_id, winner_id, auction_data)
    await channel.send(content=winner_mention, embed=embed, view=view)

class TransactionView(discord.ui.View):
    def __init__(self, seller_id, winner_id, auction_data):
        super().__init__(timeout=None)
        self.seller_id, self.winner_id, self.auction_data = seller_id, winner_id, auction_data
    @discord.ui.button(label=MESSAGES["auc_btn_confirm"], style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ConfirmFinalView(self.auction_data, interaction.channel)
        await interaction.response.send_message(MESSAGES["auc_check_money"], view=view, ephemeral=True)
    @discord.ui.button(label=MESSAGES["auc_btn_cancel"], style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_modal(CancelReasonModal(self.auction_data, interaction.channel))

class ConfirmFinalView(discord.ui.View):
    def __init__(self, auction_data, channel):
        super().__init__(timeout=None)
        self.auction_data, self.channel = auction_data, channel
    @discord.ui.button(label=MESSAGES["auc_btn_double_confirm"], style=discord.ButtonStyle.green)
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

class CancelReasonModal(discord.ui.Modal, title=MESSAGES["auc_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["auc_lbl_deny_reason"], required=True)
    def __init__(self, auction_data, channel):
        super().__init__()
        self.auction_data, self.channel = auction_data, channel
    async def on_submit(self, interaction: discord.Interaction):
        if self.auction_data['log_id']:
            log = bot.get_channel(self.auction_data['log_id'])
            embed = discord.Embed(description=MESSAGES["auc_cancel_log"].format(count=data['auction_count'], seller=f"<@{self.auction_data['seller_id']}>", user=interaction.user.mention, reason=self.reason.value), color=discord.Color.red())
            await log.send(embed=embed)
        await interaction.response.send_message(MESSAGES["auc_msg_cancel_success"], ephemeral=True)
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
            
            response_text = MESSAGES["auc_bid_response"].format(user=message.author.mention, amount=amount)
            if old_winner and old_winner != message.author.id: response_text += MESSAGES["auc_bid_outbid"].format(old_winner=f"<@{old_winner}>")
            if amount >= auction_data['close_price']:
                 response_text += MESSAGES["auc_bid_autobuy"]
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
    await interaction.response.send_message(MESSAGES["tf_setup_success"].format(forum=forum.mention), ephemeral=True)

@bot.event
async def on_thread_create(thread):
    if str(thread.parent_id) in data["ticket_configs"]:
        await asyncio.sleep(1)
        await thread.send(MESSAGES["tf_guide_msg"], view=TicketForumView())

class TicketForumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label=MESSAGES["tf_btn_buy"], style=discord.ButtonStyle.green, custom_id="tf_buy")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == interaction.channel.owner_id:
             return await interaction.response.send_message(MESSAGES["tf_err_own_post"], ephemeral=True)
             
        conf = data["ticket_configs"].get(str(interaction.channel.parent_id))
        if not conf: return

        button.disabled = True
        button.label = MESSAGES["tf_btn_buying"]
        button.style = discord.ButtonStyle.gray
        await interaction.response.edit_message(view=self)

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
        
        view = TicketControlView(
            interaction.channel.id, 
            conf["log_id"], 
            interaction.user.id, 
            interaction.channel.owner_id,
            interaction.message.id 
        )
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
        conf = data["ticket_configs"].get(self.parent_id)
        if conf and conf["log_id"]:
            log = bot.get_channel(conf["log_id"])
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
        self.forum_thread_id = forum_thread_id
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.forum_msg_id = forum_msg_id

    @discord.ui.button(label=MESSAGES["tf_btn_finish"], style=discord.ButtonStyle.green)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id:
             return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)

        msg = MESSAGES["tf_wait_admin"]
        for sid in data["supports"]: msg += f" <@{sid}>"
        await interaction.channel.send(msg)
        await interaction.channel.send(MESSAGES["tf_admin_panel_msg"], view=AdminCloseView(self.forum_thread_id, self.log_id, self.buyer_id, self.seller_id))
        await interaction.response.defer()

    @discord.ui.button(label=MESSAGES["tf_btn_cancel"], style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id:
             return await interaction.response.send_message(MESSAGES["tf_only_seller"], ephemeral=True)
             
        await interaction.response.send_modal(TicketCancelModal(self.log_id, self.buyer_id, self.seller_id, self.forum_thread_id, self.forum_msg_id))

class TicketCancelModal(discord.ui.Modal, title=MESSAGES["tf_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["tf_lbl_reason"], required=True)
    def __init__(self, log_id, buyer_id, seller_id, forum_thread_id, forum_msg_id):
        super().__init__()
        self.log_id = log_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.forum_thread_id = forum_thread_id
        self.forum_msg_id = forum_msg_id
        
    async def on_submit(self, interaction: discord.Interaction):
        if self.log_id:
            log_chan = bot.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(
                    title=MESSAGES["tf_log_cancel_title"],
                    description=MESSAGES["tf_log_cancel_desc"].format(count=data['ticket_count']),
                    color=discord.Color.red()
                )
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🚫 ยกเลิกโดย", value=interaction.user.mention, inline=True)
                embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
                embed.timestamp = datetime.datetime.now()
                await log_chan.send(embed=embed)
        
        try:
            forum_thread = bot.get_channel(self.forum_thread_id)
            if forum_thread:
                msg = await forum_thread.fetch_message(self.forum_msg_id)
                if msg:
                    await msg.edit(view=TicketForumView())
        except:
            pass 

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

    @discord.ui.button(label=MESSAGES["tf_btn_admin_close"], style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_admin(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_message(MESSAGES["processing"], ephemeral=True)
        
        if self.log_id:
            log_chan = bot.get_channel(self.log_id)
            if log_chan:
                embed = discord.Embed(
                    title=MESSAGES["tf_log_success_title"],
                    description=MESSAGES["tf_log_success_desc"].format(count=data["ticket_count"]),
                    color=discord.Color.green()
                )
                embed.add_field(name="🪧 ผู้ขาย", value=f"<@{self.seller_id}>", inline=True)
                embed.add_field(name="👤 ผู้ซื้อ", value=f"<@{self.buyer_id}>", inline=True)
                embed.add_field(name="🔒 ปิดช่องโดย", value=interaction.user.mention, inline=False)
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
