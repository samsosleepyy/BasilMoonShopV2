import discord
from discord.ext import commands
import os
import asyncio
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        # Load all cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        await self.tree.sync()
        print("Commands synced! Cogs loaded.")

bot = MyBot()

keep_alive()
token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("กรุณาตั้งค่า DISCORD_TOKEN")
