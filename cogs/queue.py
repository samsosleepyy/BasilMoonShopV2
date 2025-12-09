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
        
        # เริ่มต้น Cache
        queue_setup_cache[interaction.user.id] = {
            "channel_id": None,
            "image_url": None,
            "sheet_url": None,
            "json_key": None
        }
        
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 1/2)",
            description="ตั้งค่าช่องและหน้าตาของปุ่มเช็คคิว\n\n1. เลือกช่องที่จะส่งข้อความ\n2. (Optional) ใส่รูปภาพที่จะแสดงใน Embed\n3. กดถัดไป",
            color=discord.Color.blue()
        )
        
        view = QueueSetupStep1(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    def get_sheet_data(self, sheet_url):
        try:
            if not os.path.exists(self.creds_file): return None
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_file, self.scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_url(sheet_url)
            return sheet.get_worksheet(0).get_all_records()
        except Exception as e:
            print(f"Sheet Error: {e}")
            return None

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

    @discord.ui.button(label="ใส่รูปภาพ (Image URL)", style=discord.ButtonStyle.secondary)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueImageModal(self.user_id))

    @discord.ui.button(label="ถัดไป ➡️", style=discord.ButtonStyle.primary)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if not queue_setup_cache[self.user_id]["channel_id"]:
            return await interaction.response.send_message("❌ กรุณาเลือกช่องก่อนครับ", ephemeral=True)
        
        # ไป Step 2
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 2/2): Google Sheets",
            description=(
                "ขั้นตอนการเชื่อมต่อ Google Sheets (อ่านดีๆ นะครับ)\n\n"
                "**1. เตรียม Google Cloud Project**\n"
                "• ไปที่ [Google Cloud Console](https://console.cloud.google.com/)\n"
                "• สร้าง Project ใหม่\n"
                "• ค้นหาและกด **Enable** API 2 ตัวนี้: `Google Sheets API` และ `Google Drive API`\n\n"
                "**2. สร้างกุญแจ (Service Account)**\n"
                "• ไปที่เมนู **Credentials** > **Create Credentials** > **Service Account**\n"
                "• ตั้งชื่ออะไรก็ได้ กด Done\n"
                "• คลิกที่อีเมล Service Account ที่เพิ่งสร้าง > แท็บ **Keys** > **Add Key** > **Create new key** > เลือก **JSON**\n"
                "• ไฟล์ `.json` จะโหลดลงคอม ให้เปิดไฟล์นั้นด้วย Notepad แล้ว **ก๊อปปี้ข้อความข้างในทั้งหมด** มาเตรียมไว้\n\n"
                "**3. แชร์ Sheets ให้บอท**\n"
                "• ในไฟล์ JSON ดูบรรทัด `client_email` (เช่น `xxx@project.iam.gserviceaccount.com`)\n"
                "• ก๊อปปี้อีเมลนั้น ไปกดปุ่ม **Share** ในไฟล์ Google Sheets ของคุณ (ให้สิทธิ์ Editor)\n\n"
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

        # 1. บันทึกไฟล์ credentials.json
        try:
            # แปลง String เป็น JSON Object เพื่อเช็คความถูกต้อง
            json_content = json.loads(cache["json_key"])
            
            # บันทึกลงไฟล์
            with open("credentials.json", "w", encoding="utf-8") as f:
                json.dump(json_content, f, indent=4)
                
        except json.JSONDecodeError:
            return await interaction.followup.send("❌ รูปแบบโค้ด JSON ไม่ถูกต้อง ลองก๊อปปี้ใหม่อีกครั้งครับ", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ บันทึกไฟล์ไม่สำเร็จ: {e}", ephemeral=True)

        # 2. บันทึก Config ลง Data (เช่น sheet url)
        # เนื่องจากเราต้องการให้ใช้ได้ตลอด เราอาจจะเก็บ Sheet URL ไว้ในปุ่มเลย หรือเก็บใน data.json ก็ได้
        # ในที่นี้จะเก็บไว้ใน View ของปุ่ม เพื่อความง่าย (Stateless)
        
        # 3. ส่งข้อความเข้าห้องเป้าหมาย
        target_channel = interaction.guild.get_channel(cache["channel_id"])
        if target_channel:
            embed = discord.Embed(
                title="📋 เช็คสถานะคิวงาน (Queue Status)",
                description="กดปุ่มด้านล่างเพื่อตรวจสอบลำดับคิวและสถานะงานของคุณแบบ Real-time",
                color=discord.Color.green()
            )
            if cache["image_url"]:
                embed.set_image(url=cache["image_url"])
            
            # ส่ง View ที่มีปุ่มเช็คคิว
            view = QueueMainView(cache["sheet_url"])
            await target_channel.send(embed=embed, view=view)
            
            await interaction.followup.send("✅ **ติดตั้งเสร็จสิ้น!** บอทสร้างปุ่มให้แล้วครับ\n(อย่าลืม: หาก Deploy ใหม่ ต้องมากรอก JSON Key ใหม่อีกครั้งนะครับ เพราะ Render จะลบไฟล์ทิ้ง)", ephemeral=True)
        else:
            await interaction.followup.send("❌ หาห้องเป้าหมายไม่เจอ", ephemeral=True)
            
        # ล้าง Cache
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
    # TextInput รองรับได้สูงสุด 4000 ตัวอักษร (JSON Key ปกติประมาณ 2300 ตัวอักษร ใส่พอแน่นอน)
    json_str = discord.ui.TextInput(
        label="วางโค้ดจากไฟล์ .json ที่นี่", 
        style=discord.TextStyle.paragraph, 
        placeholder='{"type": "service_account", "project_id": ...}',
        required=True
    )
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        content = self.json_str.value
        # ลองเช็คเบื้องต้นว่ามี client_email ไหม
        if "client_email" in content:
            try:
                data = json.loads(content)
                email = data.get("client_email", "ไม่พบอีเมล")
                queue_setup_cache[self.user_id]["json_key"] = content
                await interaction.response.send_message(f"✅ รับข้อมูล Key เรียบร้อย!\n📧 **อย่าลืมแชร์ Sheets ให้:**\n`{email}`", ephemeral=True)
            except:
                await interaction.response.send_message("⚠️ รูปแบบ JSON ผิดพลาด แต่บันทึกไว้ก่อน (อาจใช้งานไม่ได้)", ephemeral=True)
                queue_setup_cache[self.user_id]["json_key"] = content
        else:
            await interaction.response.send_message("⚠️ ไม่พบ client_email ในโค้ดที่วาง แต่บันทึกไว้ให้ครับ", ephemeral=True)
            queue_setup_cache[self.user_id]["json_key"] = content

# =========================================
# MAIN VIEW: ปุ่มเช็คคิว (User ใช้งาน)
# =========================================
class QueueMainView(discord.ui.View):
    def __init__(self, sheet_url):
        super().__init__(timeout=None)
        self.sheet_url = sheet_url

    @discord.ui.button(label="🔍 เช็คคิวงาน", style=discord.ButtonStyle.primary, custom_id="check_queue_btn")
    async def check_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        creds_file = "credentials.json"
        if not os.path.exists(creds_file):
            return await interaction.followup.send("⚠️ ระบบยังไม่พร้อมใช้งาน (ไม่พบ Credentials) โปรดแจ้งแอดมินให้ Setup ใหม่", ephemeral=True)

        try:
            scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                     "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_url(self.sheet_url)
            worksheet = sheet.get_worksheet(0)
            records = worksheet.get_all_records()
            
            # Logic การแสดงผล (ปรับแต่งได้ตามต้องการ)
            # ตัวอย่าง: แสดง 5-10 คิวแรกที่ยังไม่เสร็จ
            pending_jobs = []
            for row in records:
                # สมมติใช้คอลัมน์ 'สถานะงาน' หรือ 'Status' ในการเช็ค
                # ต้องปรับ Key ให้ตรงกับหัวตารางจริงใน Excel ของคุณ!!
                # เช่น row.get('สถานะงาน') != 'เสร็จสิ้น'
                pending_jobs.append(row)

            if not pending_jobs:
                return await interaction.followup.send("✅ ไม่พบข้อมูลคิวงานในขณะนี้", ephemeral=True)

            embed = discord.Embed(title="📋 คิวงานล่าสุด", color=discord.Color.blue())
            
            count = 0
            for job in pending_jobs:
                if count >= 8: break # แสดงสูงสุด 8 อันกันรก
                
                # *** สำคัญ: ต้องแก้ Key ตรงนี้ให้ตรงกับหัวตารางใน Google Sheets ***
                # ถ้าหัวตารางเป็นภาษาไทย ก็ใส่ภาษาไทย เช่น job.get('ชื่อลูกค้า', '-')
                
                queue_id = str(list(job.values())[1]) # สมมติว่าคอลัมน์ที่ 2 คือคิว (แก้ได้)
                customer = str(list(job.values())[3]) # สมมติว่าคอลัมน์ที่ 4 คือชื่อ (แก้ได้)
                status = str(list(job.values())[-2])  # สมมติว่าคอลัมน์รองสุดท้ายคือสถานะ (แก้ได้)
                
                # หรือถ้าหัวตารางเป๊ะๆ ให้ใช้แบบนี้:
                # queue_id = job.get('ลำดับคิว', '-')
                # customer = job.get('ชื่อลูกค้า', '-')
                # status = job.get('สถานะงาน', '-')

                embed.add_field(
                    name=f"คิวที่ {queue_id}",
                    value=f"👤 {customer}\nสถานะ: {status}",
                    inline=True
                )
                count += 1
            
            embed.set_footer(text=f"Last Update: {discord.utils.utcnow().strftime('%H:%M')}")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูล: {e}", ephemeral=True)
