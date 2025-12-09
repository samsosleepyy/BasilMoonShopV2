import discord
from discord.ext import commands
import os
import asyncio
from keep_alive import keep_alive
from config import load_data, is_owner, MESSAGES

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        await self.tree.sync()
        print("Commands synced! Cogs loaded.")

    # 🛑 GLOBAL CHECK: ระบบคัดกรองเซิฟเวอร์
    async def interaction_check(self, interaction: discord.Interaction):
        # 1. อนุญาตให้ Owner ใช้งานได้เสมอ (ไม่สน Whitelist)
        if is_owner(interaction):
            return True
            
        # 2. ตรวจสอบ Whitelist
        data = load_data()
        whitelist = data.get("whitelisted_guilds", [])
        
        # ถ้า ID เซิฟเวอร์ไม่อยู่ในรายการ -> บล็อก
        if str(interaction.guild_id) not in whitelist:
            await interaction.response.send_message(MESSAGES["whitelist_only"], ephemeral=True)
            return False
            
        return True

bot = MyBot()

# ผูก Check เข้ากับ Tree (เพื่อให้ทำงานกับ Slash Command)
bot.tree.interaction_check = bot.interaction_check

keep_alive()
token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("กรุณาตั้งค่า DISCORD_TOKEN")
