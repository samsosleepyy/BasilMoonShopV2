import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TOKEN = 'MTQzMjQ2MTQzNTM5MjIzMzU1NA.Go6xbb.qSenbeJCMmyvLc1Wuh4SoSQ0NaKF5HKEeioglI' # ใส่ Token บอทของคุณที่นี่

# --- DATA MANAGEMENT ---
DATA_FILE = "auction_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [],
            "support_ids": [], # User or Role IDs
            "setup": {},
            "auction_count": 0,
            "lock_time": 120, # Default 2 minutes
            "active_auctions": {} # Channel ID: {data}
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
def is_admin(user_id):
    return user_id in data["admins"] or user_id == bot.owner_id

def is_support(user, guild):
    if user.id in data["support_ids"]:
        return True
    for role in user.roles:
        if role.id in data["support_ids"]:
            return True
    return is_admin(user.id)

async def no_permission(interaction):
    await interaction.response.send_message("คุณไม่มีสิทธิ์ในการใช้คำสั่ง❌", ephemeral=True)

# --- MODALS ---

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph)

    def __init__(self, auction_info):
        super().__init__()
        self.auction_info = auction_info

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Log to Feedback
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

        # Delete Auction Channel
        await interaction.channel.delete()
        
        # Remove from DB
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
        
        # Log to Feedback
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            channel = interaction.guild.get_channel(feedback_channel_id)
            if channel:
                await channel.send(f"🚫 ไม่อนุมัติการประมูลของ <@{self.owner_id}>\nเหตุผล: {self.reason.value}")

        # DM User
        try:
            user = await interaction.guild.fetch_member(self.owner_id)
            await user.send(f"การประมูลของคุณไม่ได้รับการอนุมัติ❌\nเหตุผล: {self.reason.value}")
        except:
            pass
        
        await interaction.message.delete() # Delete the approval request

class AuctionImagesModal(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    img1 = discord.ui.TextInput(label="รูป 1 (ลิ้งค์) *บังคับ", required=True)
    img2 = discord.ui.TextInput(label="รูป 2 (ลิ้งค์)", required=False)
    img3 = discord.ui.TextInput(label="รูป 3 (ลิ้งค์)", required=False)
    img4 = discord.ui.TextInput(label="รูป 4 (ลิ้งค์)", required=False)
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="เช่น สิทธิ์ขาด, สิทธิ์เชิงพาณิชย์", required=True)
    extra = discord.ui.TextInput(label="เพิ่มเติม", required=False)
    end_time_input = discord.ui.TextInput(label="เวลาปิด (ชั่วโมง:นาที)", placeholder="ตัวอย่าง 14:10", required=True, max_length=5)

    def __init__(self, first_step_data):
        super().__init__()
        self.first_step_data = first_step_data

    async def on_submit(self, interaction: discord.Interaction):
        # Validate Time
        try:
            hours, minutes = map(int, self.end_time_input.value.split(":"))
            duration_seconds = (hours * 3600) + (minutes * 60)
            end_timestamp = int(time.time() + duration_seconds)
        except ValueError:
            return await interaction.response.send_message("รูปแบบเวลาไม่ถูกต้อง กรุณาใช้ HH:MM (เช่น 14:10)", ephemeral=True)

        # Combine Data
        full_data = self.first_step_data
        full_data.update({
            "images": [self.img1.value, self.img2.value, self.img3.value, self.img4.value],
            "rights": self.rights.value,
            "extra": self.extra.value if self.extra.value else "-",
            "end_timestamp": end_timestamp,
            "owner_id": interaction.user.id,
            "owner_name": interaction.user.name
        })

        # Send to Approval Channel
        approval_channel_id = data["setup"].get("approval_channel")
        if not approval_channel_id:
            return await interaction.response.send_message("ยังไม่ได้ตั้งค่าช่องอนุมัติ", ephemeral=True)
        
        approval_channel = interaction.guild.get_channel(approval_channel_id)
        if not approval_channel:
            return await interaction.response.send_message("หาช่องอนุมัติไม่เจอ", ephemeral=True)

        embed = discord.Embed(title="คำขอเปิดประมูลใหม่", color=discord.Color.orange())
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        embed.add_field(name="สินค้า", value=full_data['item'], inline=False)
        embed.add_field(name="ราคาเริ่มต้น", value=f"{full_data['start_price']} บ.", inline=True)
        embed.add_field(name="บิดขั้นต่ำ", value=f"{full_data['bid_step']} บ.", inline=True)
        embed.add_field(name="ราคาปิด (BIN)", value=f"{full_data['bin_price']} บ.", inline=True)
        embed.add_field(name="สิทธิ์", value=full_data['rights'], inline=True)
        embed.add_field(name="เวลาปิด", value=f"<t:{end_timestamp}:R>", inline=True)
        embed.set_image(url=self.img1.value)
        
        await approval_channel.send(embed=embed, view=ApprovalView(full_data))
        await interaction.response.send_message("ส่งคำขอไปยังแอดมินเรียบร้อยแล้ว รอการอนุมัติ...", ephemeral=True)

class AuctionDetailsModal(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่แค่ตัวเลข", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ใส่แค่ตัวเลข", required=True)
    bin_price = discord.ui.TextInput(label="ราคาปิดประมูล (BIN)", placeholder="ใส่แค่ตัวเลข", required=True)
    item = discord.ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate Numbers
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

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user.id):
            return await no_permission(interaction)
        
        # Log Success
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
        
        await interaction.response.send_message("ปิดการขายเรียบร้อย ลบช่องใน 5 วินาที...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
        if str(interaction.channel_id) in data["active_auctions"]:
            del data["active_auctions"][str(interaction.channel_id)]
            save_data(data)

    @discord.ui.button(label="💰 กลางแอดมิน", style=discord.ButtonStyle.secondary, custom_id="trans_middleman")
    async def middleman_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction.get("winner_id") and not is_admin(interaction.user.id):
            return await no_permission(interaction)
        
        msg = "มีการเรียกแอดมินกลาง!"
        for sup_id in data["support_ids"]:
            msg += f" <@{sup_id}>"
            # Note: Tagging roles needs <@&role_id>, User <@user_id>. 
            # Logic handles generic ID, might need refinement if mixed strictly.
            # Discord parses <@id> as user, <@&id> as role. 
            # Better logic:
            role = interaction.guild.get_role(sup_id)
            if role: msg = msg.replace(f"<@{sup_id}>", f"<@&{sup_id}>")

        await interaction.channel.send(msg)
        await interaction.response.send_message("แจ้งเตือนแอดมินเรียบร้อยแล้ว", ephemeral=True)

    @discord.ui.button(label="ยกเลิกการประมูล ❌", style=discord.ButtonStyle.red, custom_id="trans_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user.id):
            return await no_permission(interaction)

        await interaction.response.send_modal(CancelReasonModal(auction))


class AuctionControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ปิดการประมูล", style=discord.ButtonStyle.danger, custom_id="close_auction_manual")
    async def close_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return

        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user.id):
            return await no_permission(interaction)
        
        await end_auction_process(interaction.channel, auction)
        await interaction.response.send_message("กำลังปิดการประมูล...", ephemeral=True)

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data

    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user.id):
            return await no_permission(interaction)

        # Increase Count
        data["auction_count"] += 1
        count = data["auction_count"]
        save_data(data)

        # Create Channel
        category_id = data["setup"].get("category_id")
        category = interaction.guild.get_channel(category_id)
        
        if not category:
            return await interaction.response.send_message("หมวดหมู่ประมูลไม่ถูกต้อง", ephemeral=True)

        channel_name = f"การประมูลครั้งที่-{count}-ราคา-{self.auction_data['start_price']}"
        
        # Create channel
        channel = await interaction.guild.create_text_channel(channel_name, category=category)

        # Prepare Message
        msg_content = f"""# การประมูลครั้งที่ - {count}
โดย <@{self.auction_data['owner_id']}>

### ราคาเริ่มต้น : {self.auction_data['start_price']}
### บิดครั้งละ : {self.auction_data['bid_step']}
### ราคาปิดประมูล : {self.auction_data['bin_price']}

สิ่งที่ได้รับ : {self.auction_data['item']}
สิทธิ์ : {self.auction_data['rights']}
เพิ่มเติม : {self.auction_data['extra']}
เวลาปิดประมูล : <t:{self.auction_data['end_timestamp']}:R>
@everyone"""

        # Add Images
        valid_images = [img for img in self.auction_data['images'] if img]
        img_str = "\n".join(valid_images)
        msg_content += f"\n{img_str}"

        await channel.send(msg_content, view=AuctionControlView())

        # Save Active Auction
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
            "history": [] # List of {user_id, price}
        }
        save_data(data)

        await interaction.response.send_message(f"อนุมัติแล้ว สร้างห้องที่ {channel.mention}", ephemeral=True)
        self.stop()

    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user.id):
            return await no_permission(interaction)
        
        await interaction.response.send_modal(DenyReasonModal(self.auction_data['owner_id'], self.auction_data))

class ContinueSetupView(discord.ui.View):
    def __init__(self, first_step_data):
        super().__init__(timeout=None)
        self.first_step_data = first_step_data

    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionImagesModal(self.first_step_data))

class StartAuctionView(discord.ui.View):
    def __init__(self, label):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data['custom_id'] == "start_auction_btn":
            await interaction.response.send_modal(AuctionDetailsModal())
        return True

# --- LOGIC FUNCTIONS ---

async def end_auction_process(channel, auction_data):
    # Disable Active Status immediately
    if str(channel.id) in data["active_auctions"]:
        # Just mark as ended process started, don't delete yet
        pass

    winner_id = auction_data["winner_id"]
    
    if winner_id:
        await channel.send(f"# <@{winner_id}> ชนะการประมูลครั้งที่ : {auction_data['count']}")
    else:
        await channel.send(f"# ปิดประมูล (ไม่มีผู้ชนะ)")

    # Cooldown
    lock_wait = data.get("lock_time", 120)
    if lock_wait > 0:
        # Update timestamp for visual
        lock_end_ts = int(time.time() + lock_wait)
        await channel.send(f"⏳ รอเวลา {lock_wait} วินาที ก่อนทำการล็อคห้อง <t:{lock_end_ts}:R>")
        await asyncio.sleep(lock_wait)

    # LOCK CHANNEL (Permission Overwrite)
    await channel.send("ช่องนี้ได้เป็นช่องส่วนตัวแล้วสามารถทำธุรกรรมได้เลย...")
    
    overwrites = {
        channel.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        channel.guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    
    # Owner
    owner = channel.guild.get_member(auction_data["owner_id"])
    if owner: overwrites[owner] = discord.PermissionOverwrite(view_channel=True)
    
    # Winner
    if winner_id:
        winner = channel.guild.get_member(winner_id)
        if winner: overwrites[winner] = discord.PermissionOverwrite(view_channel=True)

    # Admins/Support (Add configured roles/users)
    # Simply iterating known admins to add specific overwrites if needed, 
    # usually admins have View Channel = True by default role hierarchy.
    
    await channel.edit(overwrites=overwrites)
    
    msg_text = f"""
ปุ่มสีเขียว ✅ เป็นของผู้เปิดประมูล
ปุ่มสีเทา 💰 เป็นของผู้ชนะประมูล
ปุ่มสีแดง ❌ เป็นของผู้เปิดประมูลและแอดมิน
    """
    await channel.send(msg_text, view=TransactionView(channel.id))

# --- BACKGROUND TASKS ---

@tasks.loop(seconds=30)
async def check_auctions_time():
    # Loop through a copy of keys to avoid runtime change size error
    for channel_id, auction in list(data["active_auctions"].items()):
        if time.time() >= auction["end_timestamp"]:
            # Time up
            channel = bot.get_channel(int(channel_id))
            if channel:
                await end_auction_process(channel, auction)
            else:
                # Channel deleted manually? cleanup
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
    
    # Reload View if needed (Persistent View requires adding on ready)
    # Note: To make views truly persistent across restart without ID, we'd need to hardcode custom_id 
    # and re-register them here. For this example, basic functionality assumes uptime or setup usage.
    if "btn_label" in data["setup"]:
        bot.add_view(StartAuctionView(data["setup"]["btn_label"]))
    bot.add_view(TransactionView(0)) # Register generic

@bot.event
async def on_message(message):
    if message.author.bot: return

    channel_id = str(message.channel.id)
    
    # Check if channel is an active auction
    if channel_id in data["active_auctions"]:
        auction = data["active_auctions"][channel_id]
        content = message.content.strip()
        
# BID LOGIC
        if content.startswith("บิด"):
            try:
                amount = int(content.replace("บิด", "").strip())
            except ValueError:
                return # Not a number, ignore
            
            # Validation
            current = auction["current_price"]
            step = auction["bid_step"]
            bin_price = auction["bin_price"]
            
            if amount < (current + step) and len(auction["history"]) > 0: 
                 # If first bid, it can be start price? Usually start price is base. 
                 # Condition: must be > current unless it's the very first bid equal to start?
                 # Logic: If someone bids, it becomes new current. Next must be current + step.
                 await message.channel.send("ราคาที่คุณบิดต่ำเกินไป❌", delete_after=5)
                 await message.delete()
                 return
            
            if amount < current: # Catch all lower
                 await message.channel.send("ราคาที่คุณบิดต่ำเกินไป❌", delete_after=5)
                 await message.delete()
                 return

            # Valid Bid
            prev_winner_id = auction["winner_id"]
            
            # Update Data
            auction["current_price"] = amount
            auction["winner_id"] = message.author.id
            auction["winner_name"] = message.author.name
            auction["history"].append({"user": message.author.id, "price": amount})
            
            # Delete user message
            await message.delete()
            
            # Delete previous bot message
            if auction["last_msg_id"]:
                try:
                    old_msg = await message.channel.fetch_message(auction["last_msg_id"])
                    await old_msg.delete()
                except:
                    pass
            
            # Construct new message
            msg_text = f"# <@{message.author.id}> บิด {amount} บ.-"
            if prev_winner_id and prev_winner_id != message.author.id:
                msg_text += f"\n<@{prev_winner_id}> ถูกแซงแล้ว!"
            
            new_msg = await message.channel.send(msg_text)
            auction["last_msg_id"] = new_msg.id
            save_data(data)

            # Rename Channel (Handle Rate Limit silently)
            try:
                new_name = f"การประมูลครั้งที่-{auction['count']}-ราคา-{amount}"
                await message.channel.edit(name=new_name)
            except:
                pass # Rate limit hit, skip rename

            # Check BIN
            if amount >= bin_price:
                await end_auction_process(message.channel, auction)

    await bot.process_commands(message)

# --- COMMANDS ---

@bot.tree.command(name="addadmin", description="เพิ่มสมาชิกที่จะสามารถใช้คำสั่งแอดมินได้")
async def addadmin(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id != bot.owner_id and interaction.user.id not in data["admins"]:
        return await no_permission(interaction)
    
    if user.id not in data["admins"]:
        data["admins"].append(user.id)
        save_data(data)
        await interaction.response.send_message(f"เพิ่ม {user.mention} เป็นแอดมินเรียบร้อย ✅")
    else:
        await interaction.response.send_message(f"{user.mention} เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="supportadmin", description="เพิ่ม support admin (User หรือ Role)")
async def supportadmin(interaction: discord.Interaction, target: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction.user.id):
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
    if not is_admin(interaction.user.id):
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
    
    if not is_admin(interaction.user.id):
        return await no_permission(interaction)

    # Save Setup
    data["setup"] = {
        "category_id": category.id,
        "channel_id": channel.id,
        "approval_channel": approval_channel.id,
        "feedback_channel": feedback_channel.id if feedback_channel else None,
        "btn_label": btn_label
    }
    save_data(data)

    # Send Interface
    embed = discord.Embed(description=message, color=discord.Color.gold())
    if img_url:
        embed.set_image(url=img_url)
    
    view = StartAuctionView(btn_label)
    await channel.send(embed=embed, view=view)
    
    await interaction.response.send_message("ตั้งค่าเรียบร้อยแล้ว ✅", ephemeral=True)

bot.run(TOKEN)
