import discord
from discord.ext import commands
import os
import threading
import json
import logging
# Import Web Dashboard
from web_dashboard import run_flask

# --- Config ---
if os.path.exists("data.json"):
    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {"guilds": {}, "owners": [], "active_auctions": {}, "active_tickets": {}}
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f)

token = os.environ.get("TOKEN") or "MTQ0Mzc4NTU4MTM2MzQ2MjE2NA.GlBD0S.0XKGaCq8FGPym4s8v_1M3GyTJdwhDJOJ--EHqI" # ใส่ Token ของคุณถ้าเทสในเครื่อง

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # จำเป็นสำหรับดู Member Count

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Events ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    # Load Cogs
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"Loaded {filename}")
            except Exception as e:
                print(f"Failed to load {filename}: {e}")

# --- Start Web Server in Background ---
def start_web():
    run_flask(bot)

if __name__ == '__main__':
    # รัน Flask ใน Thread แยก เพื่อไม่ให้บล็อค Discord Bot
    t = threading.Thread(target=start_web)
    t.start()
    
    bot.run(token)
