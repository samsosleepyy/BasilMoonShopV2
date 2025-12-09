import discord
from discord import app_commands
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import sys
import json
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission

# Cache สำหรับเก็บข้อมูลระหว่าง Setup
queue_setup_cache = {}

class QueueSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                      "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        self.creds_file = "credentials.json" 

    @app_commands.command(name="setup-queue", description="ติดตั้งระบบเช็คคิวงาน (เชื่อมต่อ Google Sheets)")
    async def setup_queue(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        # [UPDATED] เพิ่ม button_label ใน cache
        queue_setup_cache[interaction.user.id] = {
            "channel_id": None,
            "image_url": None,
            "sheet_url": None,
            "json_key": None,
            "button_label": "🔍 เช็คคิวงานของฉัน" # ค่า Default
        }
        
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 1/2)",
            description="ตั้งค่าช่องและหน้าตาของปุ่มเช็คคิว\n\n1. เลือกช่องที่จะส่งข้อความ\n2. (Optional) ใส่รูปภาพ / แก้ไขข้อความปุ่ม\n3. กดถัดไป",
            color=discord.Color.blue()
        )
        
        view = QueueSetupStep1(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(QueueSystem(bot))

# =========================================
# STEP 1: หน้าตาและช่อง
# =========================================
class QueueSetupStep1(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่องที่จะส่งปุ่มเช็คคิว")
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        queue_setup_cache[self.user_id]["channel_id"] = select.values[0].id
        await interaction.response.defer()

    @discord.ui.button(label="ใส่รูปภาพ (Image URL)", style=discord.ButtonStyle.secondary, row=1)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueImageModal(self.user_id))

    # [NEW] ปุ่มแก้ไขข้อความปุ่ม
    @discord.ui.button(label="✏️ แก้ไขข้อความปุ่ม", style=discord.ButtonStyle.secondary, row=1)
    async def edit_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueButtonLabelModal(self.user_id))

    @discord.ui.button(label="ถัดไป ➡️", style=discord.ButtonStyle.primary, row=2)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if not queue_setup_cache[self.user_id]["channel_id"]:
            return await interaction.response.send_message("❌ กรุณาเลือกช่องก่อนครับ", ephemeral=True)
        
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 2/2): Google Sheets",
            description=(
                "ขั้นตอนการเชื่อมต่อ Google Sheets\n\n"
                "**1. เตรียม Google Cloud & Service Account**\n"
                "• สร้าง Project และ Service Account ใน Google Cloud Console\n"
                "• เปิดใช้งาน API: `Google Sheets API` และ `Google Drive API`\n"
                "• ดาวน์โหลดไฟล์ JSON Key มาเก็บไว้\n\n"
                "**2. แชร์ Sheets ให้บอท**\n"
                "• ก๊อปปี้ `client_email` จากไฟล์ JSON ไปกดปุ่ม **Share (Editor)** ใน Google Sheets ของคุณ\n\n"
                "✅ **เมื่อทำครบแล้ว กดปุ่มด้านล่างเพื่อกรอกข้อมูลครับ**"
            ),
            color=discord.Color.gold()
        )
        view = QueueSetupStep2(self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

class QueueImageModal(discord.ui.Modal, title="ลิ้งค์รูปภาพ Embed"):
    url = discord.ui.TextInput(label="Image URL", placeholder="https://...", required=True)
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        queue_setup_cache[self.user_id]["image_url"] = self.url.value
        await interaction.response.send_message("✅ บันทึกรูปภาพแล้ว", ephemeral=True)

# [NEW] Modal แก้ไขข้อความปุ่ม
class QueueButtonLabelModal(discord.ui.Modal, title="แก้ไขข้อความบนปุ่ม"):
    label = discord.ui.TextInput(label="ข้อความ", placeholder="เช่น เช็คคิว, ตรวจสอบสถานะ", required=True)
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        queue_setup_cache[self.user_id]["button_label"] = self.label.value
        await interaction.response.send_message(f"✅ เปลี่ยนข้อความปุ่มเป็น: **{self.label.value}**", ephemeral=True)

# =========================================
# STEP 2: Google Sheets & JSON Key
# =========================================
class QueueSetupStep2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="1. กรอกลิ้งค์ Google Sheets", style=discord.ButtonStyle.secondary, row=0)
    async def input_sheet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueSheetUrlModal(self.user_id))

    @discord.ui.button(label="2. วางโค้ด JSON Key", style=discord.ButtonStyle.secondary, row=0)
    async def input_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueJsonModal(self.user_id))

    @discord.ui.button(label="เสร็จสิ้น (สร้างปุ่ม) ✅", style=discord.ButtonStyle.success, row=1)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        cache = queue_setup_cache.get(self.user_id)
        
        if not cache["sheet_url"]:
            return await interaction.response.send_message("❌ ยังไม่ได้กรอกลิ้งค์ Google Sheets", ephemeral=True)
        if not cache["json_key"]:
            return await interaction.response.send_message("❌ ยังไม่ได้ใส่โค้ด JSON Key", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        try:
            json_content = json.loads(cache["json_key"])
            with open("credentials.json", "w", encoding="utf-8") as f:
                json.dump(json_content, f, indent=4)
        except Exception as e:
            return await interaction.followup.send(f"❌ บันทึกไฟล์ Key ไม่สำเร็จ: {e}", ephemeral=True)

        sheet_title = "เช็คสถานะคิวงาน" 
        try:
            scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                     "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_url(cache["sheet_url"])
            sheet_title = sheet.title
            
            if "Queue" in sheet_title:
                sheet_title = sheet_title.replace("Queue", "คิว")
                
        except Exception as e:
            await interaction.followup.send(f"⚠️ ไม่สามารถดึงชื่อไฟล์ Google Sheets ได้ (ใช้ชื่อ Default แทน): {e}", ephemeral=True)

        target_channel = interaction.guild.get_channel(cache["channel_id"])
        if target_channel:
            embed = discord.Embed(
                title=f"📋 {sheet_title}", 
                description=f"กดปุ่ม **{cache['button_label']}** ด้านล่างเพื่อตรวจสอบสถานะงานของคุณ",
                color=discord.Color.green()
            )
            if cache["image_url"]:
                embed.set_image(url=cache["image_url"])
            
            # [UPDATED] ส่ง button_label ที่ตั้งค่าไว้ไปให้ View
            view = QueueMainView(cache["sheet_url"], cache["button_label"])
            await target_channel.send(embed=embed, view=view)
            
            await interaction.followup.send(f"✅ **ติดตั้งเสร็จสิ้น!** เชื่อมต่อกับ Sheet: **{sheet_title}** เรียบร้อยครับ", ephemeral=True)
        else:
            await interaction.followup.send("❌ หาห้องเป้าหมายไม่เจอ", ephemeral=True)
            
        if self.user_id in queue_setup_cache:
            del queue_setup_cache[self.user_id]

class QueueSheetUrlModal(discord.ui.Modal, title="Google Sheets Link"):
    url = discord.ui.TextInput(label="URL", placeholder="https://docs.google.com/spreadsheets/...", required=True)
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        queue_setup_cache[self.user_id]["sheet_url"] = self.url.value
        await interaction.response.send_message("✅ บันทึกลิ้งค์แล้ว", ephemeral=True)

class QueueJsonModal(discord.ui.Modal, title="JSON Credentials Content"):
    json_str = discord.ui.TextInput(label="วางโค้ดจากไฟล์ .json ที่นี่", style=discord.TextStyle.paragraph, required=True)
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            json.loads(self.json_str.value)
            queue_setup_cache[self.user_id]["json_key"] = self.json_str.value
            await interaction.response.send_message("✅ รับข้อมูล Key เรียบร้อย!", ephemeral=True)
        except:
            await interaction.response.send_message("⚠️ รูปแบบ JSON ไม่ถูกต้อง", ephemeral=True)

# =========================================
# MAIN VIEW: ปุ่มเช็คคิว
# =========================================
class QueueMainView(discord.ui.View):
    # [UPDATED] รับค่า button_label มาใช้
    def __init__(self, sheet_url, button_label="🔍 เช็คคิวงานของฉัน"):
        super().__init__(timeout=None)
        self.sheet_url = sheet_url
        
        # อัปเดตชื่อปุ่มตามที่ส่งมา
        self.children[0].label = button_label

    @discord.ui.button(label="🔍 เช็คคิวงานของฉัน", style=discord.ButtonStyle.primary, custom_id="check_my_queue")
    async def check_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        creds_file = "credentials.json"
        if not os.path.exists(creds_file):
            return await interaction.followup.send("⚠️ ระบบยังไม่พร้อมใช้งาน (ไม่พบ Credentials)", ephemeral=True)

        try:
            scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                     "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_url(self.sheet_url)
            worksheet = sheet.get_worksheet(0)
            
            records = worksheet.get_all_records()
            if not records:
                return await interaction.followup.send("❌ ไม่พบข้อมูลในตาราง", ephemeral=True)

            possible_headers = ["ชื่อลูกค้า", "ID", "ลูกค้า", "ชื่อ", "Name", "Discord ID", "User", "Username"]
            target_key = None
            
            first_row_keys = records[0].keys()
            for key in first_row_keys:
                if key.strip() in possible_headers:
                    target_key = key
                    break
            
            if not target_key:
                return await interaction.followup.send(f"⚠️ ใน Google Sheets ต้องมีหัวตารางอย่างน้อย 1 อย่างนี้: {', '.join(possible_headers)} เพื่อใช้ระบุตัวตนครับ", ephemeral=True)

            user_id = str(interaction.user.id)
            user_name = interaction.user.name
            user_display = interaction.user.display_name
            
            found_row = None
            
            for row in records:
                val = str(row.get(target_key, "")).strip()
                if val == user_id or val == user_name or val == user_display:
                    found_row = row
                    break
            
            if found_row:
                embed = discord.Embed(title="📄 รายละเอียดคิวงานของคุณ", color=discord.Color.green())
                embed.set_author(name=f"สวัสดีคุณ {user_display}", icon_url=interaction.user.display_avatar.url)
                
                for k, v in found_row.items():
                    if str(v).strip():
                        embed.add_field(name=str(k), value=str(v), inline=True)
                
                embed.set_footer(text=f"อัปเดตล่าสุด: {discord.utils.utcnow().strftime('%H:%M')}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ ไม่พบข้อมูลของคุณ กรุณาติดต่อแอดมิน", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
