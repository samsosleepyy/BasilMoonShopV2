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

    @app_commands.command(name="setup-queue", description="ติดตั้งระบบเช็คคิวงาน (รองรับสูงสุด 4 Sheets)")
    async def setup_queue(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        # เริ่มต้น Cache
        queue_setup_cache[interaction.user.id] = {
            "channel_id": None,
            "image_url": None,
            "embed_title": None, # Custom Title
            "embed_desc": None,  # Custom Description
            "json_key": None,
            "sheets": {} 
        }
        
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 1/2)",
            description="ตั้งค่าหน้าตาของ Embed\n\n1. เลือกช่องที่จะส่งข้อความ\n2. (Optional) ตกแต่งรูปภาพ / หัวข้อ / คำอธิบาย\n3. กดถัดไป",
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

    @discord.ui.button(label="📝 แก้ไข Title Embed", style=discord.ButtonStyle.secondary, row=1)
    async def edit_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueTitleModal(self.user_id))

    @discord.ui.button(label="📝 แก้ไข Description", style=discord.ButtonStyle.secondary, row=2)
    async def edit_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueDescriptionModal(self.user_id))

    @discord.ui.button(label="ถัดไป ➡️", style=discord.ButtonStyle.primary, row=2)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if not queue_setup_cache[self.user_id]["channel_id"]:
            return await interaction.response.send_message("❌ กรุณาเลือกช่องก่อนครับ", ephemeral=True)
        
        # [UPDATED] ใส่คู่มือกลับมาให้ครบถ้วน
        embed = discord.Embed(
            title="🛠️ Setup Queue System (Step 2/2): ตั้งค่า Sheet",
            description=(
                "### 📚 คู่มือการเชื่อมต่อ Google Sheets\n"
                "หากคุณยังไม่มีไฟล์ JSON Key ให้ทำตามขั้นตอนนี้:\n\n"
                "**1. เตรียม Google Cloud**\n"
                "• ไปที่ [Google Cloud Console](https://console.cloud.google.com/)\n"
                "• สร้าง Project ใหม่ -> ค้นหาและกด **Enable** API 2 ตัวนี้: `Google Sheets API` และ `Google Drive API`\n\n"
                "**2. สร้างกุญแจ (Service Account)**\n"
                "• ไปที่เมนู **Credentials** > **Create Credentials** > **Service Account**\n"
                "• ตั้งชื่ออะไรก็ได้ กด Done\n"
                "• คลิกที่อีเมล Service Account ที่สร้างเสร็จ > แท็บ **Keys** > **Add Key** > **Create new key** > เลือก **JSON**\n"
                "• ไฟล์ `.json` จะถูกโหลดลงคอม ให้เปิดอ่านแล้ว **ก๊อปปี้โค้ดข้างในทั้งหมด** มาเตรียมไว้\n\n"
                "**3. แชร์ Sheets ให้บอท**\n"
                "• ในไฟล์ JSON ดูบรรทัด `client_email`\n"
                "• ก๊อปปี้อีเมลนั้น ไปกดปุ่ม **Share (แชร์)** ในไฟล์ Google Sheets ของคุณ (ให้สิทธิ์ Editor)\n"
                "──────────────────────────\n"
                "**⚙️ การตั้งค่าในหน้านี้**\n"
                "1. กด **'ตั้งค่า Sheet 1-2'** หรือ **'3-4'** เพื่อใส่ชื่อปุ่มและลิ้งค์\n"
                "2. กด **'วางโค้ด JSON Key'** เพื่อใส่โค้ดที่ก๊อปมา\n"
                "3. กด **'เสร็จสิ้น'** เพื่อสร้างปุ่ม"
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

class QueueTitleModal(discord.ui.Modal, title="ตั้งชื่อหัวข้อ Embed"):
    title_input = discord.ui.TextInput(label="หัวข้อ (Title)", placeholder="เช่น รายการคิวงานทั้งหมด", required=True)
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        queue_setup_cache[self.user_id]["embed_title"] = self.title_input.value
        await interaction.response.send_message(f"✅ ตั้งชื่อหัวข้อเป็น: **{self.title_input.value}**", ephemeral=True)

class QueueDescriptionModal(discord.ui.Modal, title="ตั้งค่ารายละเอียด Embed"):
    desc_input = discord.ui.TextInput(
        label="รายละเอียด (Description)", 
        placeholder="กดปุ่มด้านล่างเพื่อเช็คสถานะ...", 
        style=discord.TextStyle.paragraph, 
        required=True
    )
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        queue_setup_cache[self.user_id]["embed_desc"] = self.desc_input.value
        await interaction.response.send_message("✅ บันทึกคำอธิบายเรียบร้อย", ephemeral=True)

# =========================================
# STEP 2: Google Sheets Inputs (Split Modals)
# =========================================
class QueueSetupStep2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="ตั้งค่า Sheet 1-2", style=discord.ButtonStyle.secondary, row=0)
    async def input_sheet_1_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueSheetsModalPart1(self.user_id))

    @discord.ui.button(label="ตั้งค่า Sheet 3-4", style=discord.ButtonStyle.secondary, row=0)
    async def input_sheet_3_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueSheetsModalPart2(self.user_id))

    @discord.ui.button(label="วางโค้ด JSON Key", style=discord.ButtonStyle.secondary, row=1)
    async def input_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(QueueJsonModal(self.user_id))

    @discord.ui.button(label="เสร็จสิ้น (สร้างปุ่ม) ✅", style=discord.ButtonStyle.success, row=2)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        cache = queue_setup_cache.get(self.user_id)
        
        if not cache["sheets"]:
            return await interaction.response.send_message("❌ กรุณาตั้งค่า Sheet อย่างน้อย 1 อันครับ", ephemeral=True)
        if not cache["json_key"]:
            return await interaction.response.send_message("❌ ยังไม่ได้ใส่โค้ด JSON Key", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # 1. บันทึกไฟล์ Credentials
        try:
            json_content = json.loads(cache["json_key"])
            with open("credentials.json", "w", encoding="utf-8") as f:
                json.dump(json_content, f, indent=4)
        except Exception as e:
            return await interaction.followup.send(f"❌ บันทึกไฟล์ Key ไม่สำเร็จ: {e}", ephemeral=True)

        # 2. จัดเตรียมข้อมูล Title/Desc
        final_title = cache["embed_title"]
        final_desc = cache["embed_desc"] if cache["embed_desc"] else "กดปุ่มด้านล่างเพื่อตรวจสอบรายละเอียดงานและสถานะของคุณ"
        
        # ถ้าไม่มี Custom Title ให้พยายามดึงจาก Sheet แรก
        if not final_title:
            try:
                scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
                client = gspread.authorize(creds)
                
                first_sheet_key = sorted(cache["sheets"].keys())[0]
                first_sheet_url = cache["sheets"][first_sheet_key]["url"]
                
                sheet = client.open_by_url(first_sheet_url)
                fetched_title = sheet.title
                if "Queue" in fetched_title:
                    fetched_title = fetched_title.replace("Queue", "คิว")
                final_title = f"📋 {fetched_title}"
            except Exception as e:
                final_title = "📋 เช็คสถานะคิวงาน" 
                print(f"Fetch title error: {e}")

        # 3. สร้าง Embed และ ปุ่ม
        target_channel = interaction.guild.get_channel(cache["channel_id"])
        if target_channel:
            embed = discord.Embed(
                title=final_title,
                description=final_desc,
                color=discord.Color.green()
            )
            if cache["image_url"]:
                embed.set_image(url=cache["image_url"])
            
            sheets_config = []
            for i in sorted(cache["sheets"].keys()):
                sheets_config.append(cache["sheets"][i])

            view = QueueMainView(sheets_config)
            await target_channel.send(embed=embed, view=view)
            
            await interaction.followup.send(f"✅ **ติดตั้งเสร็จสิ้น!** สร้างปุ่มจำนวน {len(sheets_config)} ปุ่ม เรียบร้อยครับ", ephemeral=True)
        else:
            await interaction.followup.send("❌ หาห้องเป้าหมายไม่เจอ", ephemeral=True)
            
        if self.user_id in queue_setup_cache:
            del queue_setup_cache[self.user_id]

class QueueSheetsModalPart1(discord.ui.Modal, title="ตั้งค่า Sheet 1 และ 2"):
    label1 = discord.ui.TextInput(label="ชื่อปุ่มที่ 1", placeholder="เช่น เช็คงานวาด", required=True)
    url1 = discord.ui.TextInput(label="ลิ้งค์ Sheet 1", placeholder="https://docs.google.com...", required=True)
    label2 = discord.ui.TextInput(label="ชื่อปุ่มที่ 2 (เว้นว่างถ้าไม่มี)", required=False)
    url2 = discord.ui.TextInput(label="ลิ้งค์ Sheet 2 (เว้นว่างถ้าไม่มี)", required=False)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        
        cache = queue_setup_cache.get(user_id, {}).get("sheets", {})
        if 1 in cache:
            self.label1.default = cache[1]["label"]
            self.url1.default = cache[1]["url"]
        if 2 in cache:
            self.label2.default = cache[2]["label"]
            self.url2.default = cache[2]["url"]

    async def on_submit(self, interaction: discord.Interaction):
        cache = queue_setup_cache[self.user_id]["sheets"]
        cache[1] = {"label": self.label1.value, "url": self.url1.value}
        if self.label2.value and self.url2.value:
            cache[2] = {"label": self.label2.value, "url": self.url2.value}
        elif 2 in cache: del cache[2]
        await interaction.response.send_message("✅ บันทึกข้อมูล Sheet 1-2 แล้ว", ephemeral=True)

class QueueSheetsModalPart2(discord.ui.Modal, title="ตั้งค่า Sheet 3 และ 4"):
    label3 = discord.ui.TextInput(label="ชื่อปุ่มที่ 3 (เว้นว่างถ้าไม่มี)", required=False)
    url3 = discord.ui.TextInput(label="ลิ้งค์ Sheet 3 (เว้นว่างถ้าไม่มี)", required=False)
    label4 = discord.ui.TextInput(label="ชื่อปุ่มที่ 4 (เว้นว่างถ้าไม่มี)", required=False)
    url4 = discord.ui.TextInput(label="ลิ้งค์ Sheet 4 (เว้นว่างถ้าไม่มี)", required=False)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        
        cache = queue_setup_cache.get(user_id, {}).get("sheets", {})
        if 3 in cache:
            self.label3.default = cache[3]["label"]
            self.url3.default = cache[3]["url"]
        if 4 in cache:
            self.label4.default = cache[4]["label"]
            self.url4.default = cache[4]["url"]

    async def on_submit(self, interaction: discord.Interaction):
        cache = queue_setup_cache[self.user_id]["sheets"]
        if self.label3.value and self.url3.value:
            cache[3] = {"label": self.label3.value, "url": self.url3.value}
        elif 3 in cache: del cache[3]
        if self.label4.value and self.url4.value:
            cache[4] = {"label": self.label4.value, "url": self.url4.value}
        elif 4 in cache: del cache[4]
        await interaction.response.send_message("✅ บันทึกข้อมูล Sheet 3-4 แล้ว", ephemeral=True)

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

class QueueButton(discord.ui.Button):
    def __init__(self, label, sheet_url, index):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"q_btn_{index}_{sheet_url[-5:]}")
        self.sheet_url = sheet_url

    async def callback(self, interaction: discord.Interaction):
        await self.view.check_queue_logic(interaction, self.sheet_url)

class QueueMainView(discord.ui.View):
    def __init__(self, sheets_config):
        super().__init__(timeout=None)
        
        for i, conf in enumerate(sheets_config):
            btn = QueueButton(label=conf["label"], sheet_url=conf["url"], index=i)
            self.add_item(btn)

    async def check_queue_logic(self, interaction: discord.Interaction, sheet_url):
        await interaction.response.defer(ephemeral=True)
        
        creds_file = "credentials.json"
        if not os.path.exists(creds_file):
            return await interaction.followup.send("⚠️ ระบบยังไม่พร้อมใช้งาน (ไม่พบ Credentials)", ephemeral=True)

        try:
            scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                     "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.get_worksheet(0)
            
            records = worksheet.get_all_records()
            if not records:
                return await interaction.followup.send("❌ ไม่พบข้อมูลในตาราง", ephemeral=True)

            possible_headers = ["ชื่อลูกค้า", "ID", "ลูกค้า", "ชื่อ", "Discord", "Discord ID", "User", "Username"]
            target_key = None
            
            first_row_keys = records[0].keys()
            for key in first_row_keys:
                if key.strip() in possible_headers:
                    target_key = key
                    break
            
            if not target_key:
                return await interaction.followup.send(f"⚠️ ไม่พบหัวตารางระบุตัวตน (ต้องมี: {', '.join(possible_headers)})", ephemeral=True)

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
                title_text = sheet.title.replace("Queue", "คิว") if "Queue" in sheet.title else sheet.title
                embed = discord.Embed(title=f"📄 สถานะจาก: {title_text}", color=discord.Color.green())
                embed.set_author(name=f"{user_display}", icon_url=interaction.user.display_avatar.url)
                
                for k, v in found_row.items():
                    if str(v).strip():
                        embed.add_field(name=str(k), value=str(v), inline=True)
                
                embed.set_footer(text=f"อัปเดตล่าสุด: {discord.utils.utcnow().strftime('%H:%M')}")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ ไม่พบข้อมูลของคุณในรายการนี้", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
