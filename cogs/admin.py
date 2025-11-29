# cogs/admin.py
import discord
from discord import app_commands
from discord.ext import commands
from config import MESSAGES, load_data, save_data # ดึงค่าจาก config มาใช้

class AdminSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ฟังก์ชันเช็คสิทธิ์ (ย้ายมาไว้ในนี้ หรือจะ import มาก็ได้)
    def is_admin(self, interaction):
        data = load_data()
        # ... logic เช็ค admin แบบเดิม ...
        return True # (ตัวอย่างย่อ)

    @app_commands.command(name="addpoint", description="เพิ่มแต้มให้ผู้ใช้")
    async def addpoint(self, interaction: discord.Interaction, user: discord.User, amount: int):
        # ... logic เดิม ...
        # เวลาเรียกใช้ data ต้อง load_data() ใหม่ทุกครั้งเพื่อความชัวร์
        data = load_data()
        str_id = str(user.id)
        # ... ทำงาน ...
        save_data(data)
        await interaction.response.send_message(...)

# ส่วนสำคัญที่ต้องมีท้ายไฟล์ เพื่อให้ main.py รู้จักไฟล์นี้
async def setup(bot):
    await bot.add_cog(AdminSystem(bot))
