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

# --- KEEP ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION ---
TOKEN = os.environ.get('TOKEN') or 'YOUR_BOT_TOKEN_HERE'

# --- DATA MANAGEMENT ---
DATA_FILE = "auction_data.json"

# ตัวแปรชั่วคราวสำหรับเก็บข้อมูลระหว่างรออัปโหลดรูป (RAM Only)
pending_auctions = {}

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [],
            "support_ids": [],
            "setup": {}, 
            "forum_setup": {}, 
            "auction_count": 0,
            "forum_ticket_count": 0, 
            "lock_time": 120,
            "active_auctions": {},
            "active_forum_tickets": {}
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
def is_admin(user):
    if user.id == bot.owner_id:
        return True
    if user.id in data["admins"]:
        return True
    if hasattr(user, "guild_permissions") and user.guild_permissions.administrator:
        return True
    return False

async def no_permission(interaction):
    msg = "คุณไม่มีสิทธิ์ในการใช้คำสั่ง❌"
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
    await asyncio.sleep(180) 
    if user_id in pending_auctions:
        guild = bot.get_guild(guild_id)
        channel = bot.get_channel(channel_id)
        member = guild.get_member(user_id)
        
        if channel and member:
            try:
                await channel.set_permissions(member, overwrite=None)
                await channel.send(f"<@{user_id}> สิทธิ์การส่งรูปถูกยกเลิกเนื่องจากหมดเวลา (3 นาที)", delete_after=10)
            except:
                pass
        if user_id in pending_auctions:
            del pending_auctions[user_id]

# --- LOGIC FUNCTIONS ---

async def submit_to_approval(guild, full_data):
    approval_channel_id = data["setup"].get("approval_channel")
    if not approval_channel_id: return None 
    approval_channel = guild.get_channel(approval_channel_id)
    if not approval_channel: return None
    
    files_to_send = []
    if "images_data" in full_data:
        for img_info in full_data["images_data"]:
            files_to_send.append(
                discord.File(
                    fp=io.BytesIO(img_info["data"]), 
                    filename=img_info["filename"]
                )
            )

    main_embed = discord.Embed(title="คำขอเปิดประมูลใหม่", color=discord.Color.orange())
    main_embed.set_author(name=full_data['owner_name'], icon_url=None)
    main_embed.add_field(name="สินค้า", value=full_data['item'], inline=False)
    main_embed.add_field(name="ราคาเริ่มต้น", value=f"{full_data['start_price']} บ.", inline=True)
    main_embed.add_field(name="บิดขั้นต่ำ", value=f"{full_data['bid_step']} บ.", inline=True)
    main_embed.add_field(name="ราคาปิด (BIN)", value=f"{full_data['bin_price']} บ.", inline=True)
    main_embed.add_field(name="สิทธิ์", value=full_data['rights'], inline=True)
    main_embed.add_field(name="เวลาปิด", value=f"<t:{full_data['end_timestamp']}:R>", inline=True)
    main_embed.add_field(name="เพิ่มเติม", value=full_data['extra'], inline=False)

    sent_message = await approval_channel.send(
        embed=main_embed, 
        files=files_to_send, 
        view=ApprovalView(full_data)
    )
    
    full_data["images"] = [att.url for att in sent_message.attachments]
    if "images_data" in full_data:
        del full_data["images_data"]
    
    return True

async def end_auction_process(channel, auction_data):
    cid = str(channel.id)
    if cid not in data["active_auctions"]: return
    if data["active_auctions"][cid].get("status") == "ended": return 

    data["active_auctions"][cid]["status"] = "ended"
    save_data(data)

    winner_id = auction_data["winner_id"]
    
    if not winner_id:
        await channel.send("# ปิดประมูล (ไม่มีผู้ชนะ)")
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            feed_channel = channel.guild.get_channel(feedback_channel_id)
            if feed_channel:
                embed = discord.Embed(title="❌ การประมูลจบลง (ไม่มีผู้ประมูล)", color=discord.Color.red())
                embed.add_field(name="การประมูลครั้งที่", value=str(auction_data['count']))
                embed.add_field(name="โดย", value=auction_data['owner_name'])
                embed.add_field(name="สถานะ", value="ไม่มีผู้ประมูล")
                await feed_channel.send(embed=embed)
        
        await asyncio.sleep(5)
        await channel.delete()
        del data["active_auctions"][cid]
        save_data(data)
        return

    await channel.send(f"# <@{winner_id}> ชนะการประมูลครั้งที่ : {auction_data['count']}\n### จบที่ราคา : {auction_data['current_price']} บ.")

    lock_wait = data.get("lock_time", 120)
    if lock_wait > 0:
        lock_end_ts = int(time.time() + lock_wait)
        await channel.send(f"⏳ รอเวลา {lock_wait} วินาที ก่อนทำการล็อคห้อง <t:{lock_end_ts}:R>")
        await asyncio.sleep(lock_wait)

    try:
        await channel.send("ช่องนี้ได้เป็นช่องส่วนตัวแล้วสามารถทำธุรกรรมได้เลย...")
        
        overwrites = {}
        deny_all = discord.PermissionOverwrite(
            view_channel=False, read_messages=False, read_message_history=False,
            send_messages=False, send_tts_messages=False, manage_messages=False,
            embed_links=False, attach_files=False, mention_everyone=False,
            use_external_emojis=False, add_reactions=False, use_application_commands=False,
            manage_channels=False, manage_permissions=False, manage_webhooks=False,
            create_instant_invite=False, create_public_threads=False, create_private_threads=False,
            send_messages_in_threads=False, manage_threads=False
        )
        for role in channel.guild.roles:
            if role.permissions.administrator: continue
            overwrites[role] = deny_all

        overwrites[channel.guild.me] = discord.PermissionOverwrite(view_channel=True)
        
        strict_allow = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True,
            attach_files=True, embed_links=True, add_reactions=True,
            create_instant_invite=False, manage_channels=False, manage_permissions=False,
            manage_webhooks=False, create_public_threads=False, create_private_threads=False,
            send_messages_in_threads=False, send_tts_messages=False, manage_messages=False,
            mention_everyone=False, use_external_emojis=False, use_application_commands=False,
            manage_threads=False, use_external_stickers=False
        )

        owner = channel.guild.get_member(auction_data["owner_id"])
        if owner: overwrites[owner] = strict_allow
        
        if winner_id:
            winner = channel.guild.get_member(winner_id)
            if winner: overwrites[winner] = strict_allow
        
        await channel.edit(overwrites=overwrites)
        
        msg_text = f"""
ปุ่มสีเขียว ✅ เป็นของผู้เปิดประมูล
ปุ่มสีเทา 💰 เป็นของผู้ชนะประมูล
ปุ่มสีแดง ❌ เป็นของผู้เปิดประมูลและแอดมิน
        """
        await channel.send(msg_text, view=TransactionView(channel.id))
    except Exception as e:
        print(f"Error locking channel: {e}")

# --- MODALS ---

class CancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph)
    def __init__(self, auction_info):
        super().__init__()
        self.auction_info = auction_info
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
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
        await interaction.channel.delete()
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
        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            channel = interaction.guild.get_channel(feedback_channel_id)
            if channel:
                await channel.send(f"🚫 ไม่อนุมัติการประมูลของ <@{self.owner_id}>\nเหตุผล: {self.reason.value}")
        try: await interaction.message.delete()
        except: pass

class AuctionImagesModal(discord.ui.Modal, title="ข้อมูลการประมูล (2/2)"):
    rights = discord.ui.TextInput(label="สิทธิ์", placeholder="เช่น สิทธิ์ขาด, สิทธิ์เชิงพาณิชย์", required=True)
    extra = discord.ui.TextInput(label="เพิ่มเติม", required=False)
    end_time_input = discord.ui.TextInput(label="เวลาปิด (ชั่วโมง:นาที)", placeholder="ตัวอย่าง 14:10", required=True, max_length=5)
    def __init__(self, first_step_data):
        super().__init__()
        self.first_step_data = first_step_data
    async def on_submit(self, interaction: discord.Interaction):
        try:
            hours, minutes = map(int, self.end_time_input.value.split(":"))
            duration_seconds = (hours * 3600) + (minutes * 60)
            end_timestamp = int(time.time() + duration_seconds)
        except ValueError:
            return await interaction.response.send_message("รูปแบบเวลาไม่ถูกต้อง", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        full_data = self.first_step_data
        full_data.update({
            "rights": self.rights.value,
            "extra": self.extra.value if self.extra.value else "-",
            "end_timestamp": end_timestamp,
            "owner_id": interaction.user.id,
            "owner_name": interaction.user.name,
            "images": []
        })

        img_channel_id = data["setup"].get("image_channel")
        if not img_channel_id: return await interaction.followup.send("❌ ยังไม่ได้ตั้งค่าช่องอัปโหลดรูป", ephemeral=True)
        img_channel = interaction.guild.get_channel(img_channel_id)
        if not img_channel: return await interaction.followup.send("❌ หาช่องอัปโหลดรูปไม่เจอ", ephemeral=True)

        pending_auctions[interaction.user.id] = full_data

        overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=False)
        await img_channel.set_permissions(interaction.user, overwrite=overwrite)

        await interaction.followup.send(f"กรุณาส่งรูปภาพสินค้าที่ช่อง : {img_channel.mention} (คุณมีเวลา 3 นาที)", ephemeral=True)
        try: await img_channel.send(f"<@{interaction.user.id}> กรุณาส่งรูปสินค้าของคุณที่นี่...")
        except: pass
        
        asyncio.create_task(revoke_permissions_after_timeout(interaction.user.id, img_channel.id, interaction.guild_id))

class AuctionDetailsModal(discord.ui.Modal, title="ข้อมูลการประมูล (1/2)"):
    start_price = discord.ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่แค่ตัวเลข", required=True)
    bid_step = discord.ui.TextInput(label="บิดครั้งละ", placeholder="ใส่แค่ตัวเลข", required=True)
    bin_price = discord.ui.TextInput(label="ราคาปิดประมูล (BIN)", placeholder="ใส่แค่ตัวเลข", required=True)
    item = discord.ui.TextInput(label="สิ่งที่ได้", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            s_price = int(self.start_price.value)
            b_step = int(self.bid_step.value)
            bin_p = int(self.bin_price.value)
        except ValueError:
            return await interaction.response.send_message("กรุณาใส่ราคาเป็นตัวเลขเท่านั้น", ephemeral=True)
        first_step_data = {"start_price": s_price, "bid_step": b_step, "bin_price": bin_p, "item": self.item.value}
        view = ContinueSetupView(first_step_data)
        await interaction.response.send_message("กรอกข้อมูลส่วนแรกเสร็จสิ้น กดปุ่มด้านล่างเพื่อกรอกส่วนที่เหลือ", ephemeral=True, view=view)

class ReportModal(discord.ui.Modal, title="แจ้งรายงาน (Report)"):
    reason = discord.ui.TextInput(label="รายละเอียด/เหตุผล", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        report_channel_id = data["forum_setup"].get("report_channel_id")
        if not report_channel_id: return await interaction.response.send_message("❌ ระบบยังไม่ได้ตั้งค่าช่อง Report", ephemeral=True)
        report_channel = interaction.guild.get_channel(report_channel_id)
        if report_channel:
            embed = discord.Embed(title="🚨 มีการแจ้งรายงานใหม่", color=discord.Color.red())
            embed.add_field(name="ผู้รายงาน", value=interaction.user.mention, inline=True)
            embed.add_field(name="มาจากช่อง/กระทู้", value=interaction.channel.mention, inline=True)
            embed.add_field(name="เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.now()
            await report_channel.send(embed=embed)
            await interaction.response.send_message("ส่งรายงานเรียบร้อยแล้ว 🙏", ephemeral=True)
        else:
            await interaction.response.send_message("❌ หาช่อง Report ไม่เจอ", ephemeral=True)

class TicketCancelReasonModal(discord.ui.Modal, title="เหตุผลการยกเลิก"):
    reason = discord.ui.TextInput(label="เหตุผล", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        support_msg = get_support_mention()
        msg = f"{interaction.user.mention} รอยืนยันการ **ยกเลิก** อีกครั้งโดยแอดมิน {support_msg}\n**เหตุผล:** {self.reason.value}"
        view = AdminConfirmView(action="cancel", requester=interaction.user, reason=self.reason.value)
        await interaction.channel.send(msg, view=view)
        await interaction.response.send_message("ส่งคำขอยกเลิกแล้ว รอแอดมินยืนยัน...", ephemeral=True)

# --- VIEWS ---

class TransactionView(discord.ui.View):
    def __init__(self, auction_id):
        super().__init__(timeout=None)
        self.auction_id = str(auction_id)
    @discord.ui.button(label="✅ เสร็จสิ้นการซื้อขาย", style=discord.ButtonStyle.green, custom_id="trans_success")
    async def success_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        await interaction.response.defer()
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
        await interaction.followup.send("ปิดการขายเรียบร้อย ลบช่องใน 5 วินาที...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
        if str(interaction.channel_id) in data["active_auctions"]:
            del data["active_auctions"][str(interaction.channel_id)]
            save_data(data)
    @discord.ui.button(label="💰 กลางแอดมิน", style=discord.ButtonStyle.secondary, custom_id="trans_middleman")
    async def middleman_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction.get("winner_id") and not is_admin(interaction.user):
            return await no_permission(interaction)
        msg = "มีการเรียกแอดมินกลาง!"
        for sup_id in data["support_ids"]:
            msg += f" <@{sup_id}>"
        await interaction.channel.send(msg)
        if not interaction.response.is_done():
            await interaction.response.send_message("แจ้งเตือนแอดมินเรียบร้อยแล้ว", ephemeral=True)
    @discord.ui.button(label="ยกเลิกการประมูล ❌", style=discord.ButtonStyle.red, custom_id="trans_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        await interaction.response.send_modal(CancelReasonModal(auction))

class AuctionControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="ปิดการประมูล", style=discord.ButtonStyle.danger, custom_id="close_auction_manual")
    async def close_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        auction = data["active_auctions"].get(str(interaction.channel_id))
        if not auction: return
        if interaction.user.id != auction["owner_id"] and not is_admin(interaction.user):
            return await no_permission(interaction)
        await interaction.response.send_message("กำลังปิดการประมูล...", ephemeral=True)
        await end_auction_process(interaction.channel, auction)

class ApprovalView(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data
    @discord.ui.button(label="อนุมัติ", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user): return await no_permission(interaction)
        await interaction.response.defer(ephemeral=True)
        data["auction_count"] += 1
        count = data["auction_count"]
        save_data(data)
        category_id = data["setup"].get("category_id")
        category = interaction.guild.get_channel(category_id)
        if not category: return await interaction.followup.send("หมวดหมู่ประมูลไม่ถูกต้อง", ephemeral=True)
        channel_name = f"การประมูลครั้งที่-{count}-ราคา-{self.auction_data['start_price']}"
        try: channel = await interaction.guild.create_text_channel(channel_name, category=category)
        except Exception as e: return await interaction.followup.send(f"สร้างห้องไม่สำเร็จ: {e}", ephemeral=True)
        
        noti_role_id = data["setup"].get("noti_role")
        ping_msg = f"<@&{noti_role_id}>" if noti_role_id else "@everyone"
        
        msg_content = f"""# การประมูลครั้งที่ - {count}
โดย <@{self.auction_data['owner_id']}>
### ราคาเริ่มต้น : {self.auction_data['start_price']}
### บิดครั้งละ : {self.auction_data['bid_step']}
### ราคาปิดประมูล : {self.auction_data['bin_price']}
สิ่งที่ได้รับ : {self.auction_data['item']}
สิทธิ์ : {self.auction_data['rights']}
เพิ่มเติม : {self.auction_data['extra']}
เวลาปิดประมูล : <t:{self.auction_data['end_timestamp']}:R>
{ping_msg}"""
        
        valid_images = [img for img in self.auction_data['images'] if img]
        prefixed_images = [f"-# {url}" for url in valid_images]
        img_str = "\n".join(prefixed_images)
        msg_content += f"\n{img_str}"
        
        await channel.send(msg_content, view=AuctionControlView())
        data["active_auctions"][str(channel.id)] = {
            "count": count, "owner_id": self.auction_data['owner_id'], "owner_name": self.auction_data['owner_name'],
            "current_price": self.auction_data['start_price'], "bid_step": self.auction_data['bid_step'],
            "bin_price": self.auction_data['bin_price'], "end_timestamp": self.auction_data['end_timestamp'],
            "winner_id": None, "winner_name": None, "last_msg_id": None, "history": [], "status": "active"
        }
        save_data(data)
        await interaction.followup.send(f"อนุมัติแล้ว สร้างห้องที่ {channel.mention}", ephemeral=True)
        self.stop()
    @discord.ui.button(label="ไม่อนุมัติ", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user): return await no_permission(interaction)
        await interaction.response.send_modal(DenyReasonModal(self.auction_data['owner_id'], self.auction_data))

class ContinueSetupView(discord.ui.View):
    def __init__(self, first_step_data):
        super().__init__(timeout=None)
        self.first_step_data = first_step_data
    @discord.ui.button(label="กดกรอกข้อมูล 2", style=discord.ButtonStyle.primary)
    async def step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.response.send_modal(AuctionImagesModal(self.first_step_data))
        except discord.HTTPException as e: pass

class StartAuctionView(discord.ui.View):
    def __init__(self, label):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn"))
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data['custom_id'] == "start_auction_btn":
            await interaction.response.send_modal(AuctionDetailsModal())
        return True

# --- VIEWS (INFO) ---

class InfoSelectView(discord.ui.View):
    def __init__(self, info_data):
        super().__init__(timeout=None)
        self.data = info_data
        select = discord.ui.Select(
            placeholder=info_data['select_placeholder'],
            options=[
                discord.SelectOption(label=info_data['select_label1'], value="option1", description=f"ข้อมูลเกี่ยวกับ {info_data['select_label1']}"),
                discord.SelectOption(label=info_data['select_label2'], value="option2", description=f"ข้อมูลเกี่ยวกับ {info_data['select_label2']}")
            ],
            custom_id="info_select_menu"
        )
        select.callback = self.select_callback
        self.add_item(select)
    async def select_callback(self, interaction: discord.Interaction):
        selected_value = interaction.data['values'][0]
        title_text = ""
        description_text = ""
        if selected_value == "option1":
            title_text = f"ข้อมูล: {self.data['select_label1']}"
            description_text = self.data['info1']
        elif selected_value == "option2":
            title_text = f"ข้อมูล: {self.data['select_label2']}"
            description_text = self.data['info2']
        else:
            title_text = "❌ ไม่มีข้อมูล"
            description_text = "กรุณาเลือกตัวเลือกที่กำหนด"
        embed = discord.Embed(title=title_text, description=description_text, color=0x03e3fc)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- VIEWS (FORUM) ---

class ForumPostControlView(discord.ui.View):
    def __init__(self, buy_label="🛒 กดสั่งซื้อตรงนี้", report_label="🚨 รายงาน"):
        super().__init__(timeout=None)
        buy_btn = discord.ui.Button(label=buy_label, style=discord.ButtonStyle.green, custom_id="forum_buy_btn")
        buy_btn.callback = self.buy_callback
        self.add_item(buy_btn)
        report_btn = discord.ui.Button(label=report_label, style=discord.ButtonStyle.red, custom_id="forum_report_btn")
        report_btn.callback = self.report_callback
        self.add_item(report_btn)

    async def report_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReportModal())

    async def buy_callback(self, interaction: discord.Interaction):
        setup = data.get("forum_setup", {})
        category_id = setup.get("category_id")
        if not category_id: return await interaction.response.send_message("❌ ระบบขัดข้อง (Category not set)", ephemeral=True)
        category = interaction.guild.get_channel(category_id)
        if not category: return await interaction.response.send_message("❌ หาหมวดหมู่ Ticket ไม่เจอ", ephemeral=True)
        if interaction.channel.owner_id == interaction.user.id:
             return await interaction.response.send_message("❌ คุณเป็นเจ้าของโพสต์ ไม่สามารถกดสั่งซื้อได้", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        data["forum_ticket_count"] += 1
        count = data["forum_ticket_count"]
        save_data(data)
        channel_name = f"ID-{count}"
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.guild.me: discord.PermissionOverwrite(view_channel=True)}
        strict_allow = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True,
            attach_files=True, embed_links=True, add_reactions=True
        )
        overwrites[interaction.user] = strict_allow
        seller_id = interaction.channel.owner_id
        seller = interaction.guild.get_member(seller_id)
        if seller: overwrites[seller] = strict_allow
        ticket_channel = await interaction.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        data["active_forum_tickets"][str(ticket_channel.id)] = {
            "count": count, "thread_id": interaction.channel.id,
            "buyer_id": interaction.user.id, "seller_id": seller_id, "created_at": int(time.time())
        }
        save_data(data)
        msg = f"ช่องนี้เป็นช่องส่วนตัวสามารถทำธุรกรรมได้เลย **สามารถกลางแอดมินหรือไม่กลางก็ได้** หากชำระแล้วสามารถกดเสร็จสิ้นได้เลย\n{interaction.user.mention} (ผู้ซื้อ) - <@{seller_id}> (ผู้ขาย)"
        await ticket_channel.send(msg, view=ForumTicketControlView())
        await interaction.followup.send(f"สร้างห้องสั่งซื้อเรียบร้อยแล้ว: {ticket_channel.mention}", ephemeral=True)

class ForumTicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ เสร็จสิ้น", style=discord.ButtonStyle.green, custom_id="ft_finish")
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        support_msg = get_support_mention()
        msg = f"{interaction.user.mention} รอยืนยันการ **เสร็จสิ้น** อีกครั้งโดยแอดมิน {support_msg}"
        view = AdminConfirmView(action="finish", requester=interaction.user)
        await interaction.channel.send(msg, view=view)
        await interaction.response.send_message("ส่งคำขอจบงานแล้ว รอแอดมินยืนยัน...", ephemeral=True)
    @discord.ui.button(label="💰 กลางแอดมิน", style=discord.ButtonStyle.secondary, custom_id="ft_middleman")
    async def middleman_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket_data = data["active_forum_tickets"].get(str(interaction.channel_id))
        if ticket_data:
            try: await interaction.channel.edit(name=f"กลาง-ID-{ticket_data['count']}")
            except: pass
        support_msg = get_support_mention()
        await interaction.channel.send(f"มีการเรียกแอดมินกลาง! {support_msg}")
        await interaction.response.send_message("เรียกแอดมินกลางเรียบร้อย", ephemeral=True)
    @discord.ui.button(label="❌ ยกเลิก", style=discord.ButtonStyle.red, custom_id="ft_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCancelReasonModal())

class AdminConfirmView(discord.ui.View):
    def __init__(self, action, requester, reason=None):
        super().__init__(timeout=None)
        self.action = action
        self.requester = requester
        self.reason = reason
    @discord.ui.button(label="ยืนยัน (ปุ่มแอดมิน)", style=discord.ButtonStyle.primary, custom_id="admin_confirm_btn")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user) and not (interaction.user.id in data["support_ids"]):
             return await no_permission(interaction)
        await interaction.response.defer()
        channel_id = str(interaction.channel_id)
        ticket_data = data["active_forum_tickets"].get(channel_id)
        if not ticket_data: return await interaction.followup.send("❌ ข้อมูลห้องนี้ผิดพลาด หรือถูกลบไปแล้ว")
        
        thread_id = ticket_data.get("thread_id")
        try:
            thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
            if thread: await thread.delete()
        except Exception as e:
            print(f"Could not delete thread: {e}")
            await interaction.channel.send(f"⚠️ ไม่สามารถลบกระทู้ต้นทางได้ (อาจจะถูกลบไปแล้ว)")

        feedback_channel_id = data["setup"].get("feedback_channel")
        if feedback_channel_id:
            feed_channel = interaction.guild.get_channel(feedback_channel_id)
            if feed_channel:
                status_text = "สำเร็จเสร็จสิ้น ✅" if self.action == "finish" else "ยกเลิก ❌"
                color = discord.Color.green() if self.action == "finish" else discord.Color.red()
                embed = discord.Embed(title=f"📋 รายงาน Forum Ticket: ID-{ticket_data['count']}", color=color)
                embed.add_field(name="สถานะ", value=status_text, inline=False)
                embed.add_field(name="ดำเนินการโดย", value=interaction.user.mention, inline=True)
                embed.add_field(name="ผู้กดจบงาน", value=self.requester.mention, inline=True)
                embed.add_field(name="ผู้ซื้อ", value=f"<@{ticket_data['buyer_id']}>", inline=True)
                embed.add_field(name="ผู้ขาย", value=f"<@{ticket_data['seller_id']}>", inline=True)
                if self.reason: embed.add_field(name="เหตุผลยกเลิก", value=self.reason, inline=False)
                await feed_channel.send(embed=embed)

        await interaction.channel.send("✅ ยืนยันเรียบร้อย! กำลังลบห้องและกระทู้...", delete_after=5)
        await asyncio.sleep(3)
        await interaction.channel.delete()
        if channel_id in data["active_forum_tickets"]:
            del data["active_forum_tickets"][channel_id]
            save_data(data)

# --- EVENTS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)
    
    # Reload Views
    if "btn_label" in data["setup"]:
        bot.add_view(StartAuctionView(data["setup"]["btn_label"]))
    bot.add_view(TransactionView(0)) 
    bot.add_view(ForumPostControlView()) 
    bot.add_view(ForumTicketControlView()) 
    bot.add_view(AdminConfirmView(None, None)) 

@bot.event
async def on_thread_create(thread):
    forum_channel_id = data.get("forum_setup", {}).get("forum_channel_id")
    if forum_channel_id and thread.parent_id == forum_channel_id:
        await asyncio.sleep(1)
        setup = data["forum_setup"]
        buy_label = setup.get("buy_label", "🛒 กดสั่งซื้อตรงนี้")
        report_label = setup.get("report_label", "🚨 รายงาน")
        view = ForumPostControlView(buy_label, report_label)
        await thread.send("🛒 **กดสั่งซื้อสินค้า หรือ รายงานโพสต์ ได้ที่นี่** 👇", view=view)

@bot.event
async def on_message(message):
    if message.author.bot: return
    img_channel_id = data["setup"].get("image_channel")
    if img_channel_id and message.channel.id == img_channel_id:
        if message.author.id in pending_auctions:
            if message.attachments:
                full_data = pending_auctions[message.author.id]
                full_data["images_data"] = [] 
                full_data["images"] = []
                for attachment in message.attachments:
                    try:
                        file_bytes = await attachment.read()
                        full_data["images_data"].append({"data": file_bytes, "filename": attachment.filename})
                    except Exception as e: print(f"Error reading attachment: {e}")
                if message.author.id in pending_auctions: del pending_auctions[message.author.id]
                await message.channel.send("ได้รับรูปภาพแล้ว กำลังส่งคำขออนุมัติ... ✅", delete_after=5)
                await submit_to_approval(message.guild, full_data)
                await message.channel.set_permissions(message.author, overwrite=None)
                return
            else: return 

    channel_id = str(message.channel.id)
    if channel_id in data["active_auctions"] and data["active_auctions"][channel_id].get("status") != "ended":
        auction = data["active_auctions"][channel_id]
        content = message.content.strip()
        if content.startswith("บิด"):
            try: amount = int(content.replace("บิด", "").strip())
            except ValueError: return
            current = auction["current_price"]
            step = auction["bid_step"]
            bin_price = auction["bin_price"]
            min_next = current + step if len(auction["history"]) > 0 else current
            if amount < min_next: 
                 await message.reply("ราคาที่คุณบิดต่ำเกินไป❌", delete_after=10)
                 return
            prev_winner_id = auction["winner_id"]
            auction["current_price"] = amount
            auction["winner_id"] = message.author.id
            auction["winner_name"] = message.author.name
            auction["history"].append({"user": message.author.id, "price": amount})
            if auction["last_msg_id"]:
                try:
                    old_msg = await message.channel.fetch_message(auction["last_msg_id"])
                    await old_msg.delete()
                except: pass
            msg_text = f"# <@{message.author.id}> บิด {amount} บ.-"
            if prev_winner_id and prev_winner_id != message.author.id:
                msg_text += f"\n<@{prev_winner_id}> ถูกแซงแล้ว!"
            new_msg = await message.reply(msg_text)
            auction["last_msg_id"] = new_msg.id
            save_data(data)
            try: await message.channel.edit(name=f"การประมูลครั้งที่-{auction['count']}-ราคา-{amount}")
            except: pass
            if amount >= bin_price: await end_auction_process(message.channel, auction)
    await bot.process_commands(message)

# --- COMMANDS ---

@bot.command()
async def sync(ctx):
    if ctx.author.id != bot.owner_id and ctx.author.id not in data["admins"]:
        return await ctx.send("คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
    try:
        fmt = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(fmt)} commands.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.tree.command(name="ticketsforum", description="ตั้งค่าระบบ Tickets สำหรับ Forum")
@app_commands.describe(category="หมวดหมู่ที่จะสร้างห้อง Ticket", forum_channel="ช่อง Forum ที่จะให้บอททำงาน", report_channel="ช่องสำหรับส่ง Report", buy_label="ข้อความปุ่มซื้อ", report_label="ข้อความปุ่มรายงาน")
async def ticketsforum(interaction: discord.Interaction, category: discord.CategoryChannel, forum_channel: discord.ForumChannel, report_channel: discord.TextChannel, buy_label: str = "🛒 กดสั่งซื้อตรงนี้", report_label: str = "🚨 รายงาน"):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["forum_setup"] = {"category_id": category.id, "forum_channel_id": forum_channel.id, "report_channel_id": report_channel.id, "buy_label": buy_label, "report_label": report_label}
    save_data(data)
    await interaction.response.send_message(f"✅ ตั้งค่า Tickets Forum เรียบร้อย!\n- Forum: {forum_channel.mention}\n- Category สร้างห้อง: {category.mention}\n- Report: {report_channel.mention}", ephemeral=True)

@bot.tree.command(name="info", description="สร้างข้อความพร้อม Select Menu สำหรับแสดงข้อมูลเฉพาะผู้ใช้")
@app_commands.describe(channel="ช่องที่จะส่งข้อความไป", message="ข้อความหลัก", select_placeholder="ข้อความในช่องเลือก", select_label1="ตัวเลือก 1", select_label2="ตัวเลือก 2", info1="รายละเอียด 1", info2="รายละเอียด 2")
async def info_cmd(interaction: discord.Interaction, channel: discord.TextChannel, message: str, select_placeholder: str, select_label1: str, select_label2: str, info1: str, info2: str):
    if not is_admin(interaction.user): return await no_permission(interaction)
    await interaction.response.defer(ephemeral=True)
    info_data = {"select_placeholder": select_placeholder, "select_label1": select_label1, "select_label2": select_label2, "info1": info1, "info2": info2}
    view = InfoSelectView(info_data)
    try:
        await channel.send(message, view=view)
        await interaction.followup.send(f"ส่งข้อความพร้อมปุ่มไปยัง {channel.mention} เรียบร้อยแล้ว ✅", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="imagec", description="ตั้งค่าช่องสำหรับอัปโหลดรูปภาพ")
async def imagec(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["setup"]["image_channel"] = channel.id
    save_data(data)
    overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False, read_message_history=False)}
    for role in interaction.guild.roles:
        if role.permissions.administrator: continue
        overwrites[role] = discord.PermissionOverwrite(view_channel=False, read_message_history=False)
    await channel.edit(overwrites=overwrites)
    await interaction.response.send_message(f"ตั้งค่าช่องอัปโหลดรูปเป็น {channel.mention} และล็อคช่องเรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="resetdata", description="รีเซ็ตจำนวนครั้งการประมูลกลับเป็น 0")
async def resetdata(interaction: discord.Interaction):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["auction_count"] = 0
    data["forum_ticket_count"] = 0
    save_data(data)
    await interaction.response.send_message("รีเซ็ตจำนวนครั้งการประมูลและ Forum Tickets กลับเป็น 0 เรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="noti", description="ตั้งค่าบทบาทที่จะแจ้งเตือนเมื่อเปิดประมูล")
async def noti(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["setup"]["noti_role"] = role.id
    save_data(data)
    await interaction.response.send_message(f"ตั้งค่าแจ้งเตือนเป็น {role.mention} เรียบร้อยแล้ว ✅", ephemeral=True)

@bot.tree.command(name="addadmin", description="เพิ่มสมาชิกที่จะสามารถใช้คำสั่งแอดมินได้")
async def addadmin(interaction: discord.Interaction, user: discord.User):
    if not is_admin(interaction.user): return await no_permission(interaction)
    if user.id not in data["admins"]:
        data["admins"].append(user.id)
        save_data(data)
        if not interaction.response.is_done(): await interaction.response.send_message(f"เพิ่ม {user.mention} เป็นแอดมินเรียบร้อย ✅")
    else:
        if not interaction.response.is_done(): await interaction.response.send_message(f"{user.mention} เป็นแอดมินอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="supportadmin", description="เพิ่ม support admin (User หรือ Role)")
async def supportadmin(interaction: discord.Interaction, target: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction.user): return await no_permission(interaction)
    target_id = target.id if target else role.id if role else None
    if not target_id: return await interaction.response.send_message("กรุณาระบุ User หรือ Role", ephemeral=True)
    if target_id not in data["support_ids"]:
        data["support_ids"].append(target_id)
        save_data(data)
        name = target.mention if target else role.mention
        await interaction.response.send_message(f"เพิ่ม {name} เป็น Support Admin เรียบร้อย ✅")
    else: await interaction.response.send_message("มีอยู่ในรายการอยู่แล้ว", ephemeral=True)

@bot.tree.command(name="lock", description="ตั้งเวลาคูลดาวน์ก่อนล็อคห้อง (วินาที)")
async def lock_cmd(interaction: discord.Interaction, time_sec: int = 120):
    if not is_admin(interaction.user): return await no_permission(interaction)
    data["lock_time"] = time_sec
    save_data(data)
    await interaction.response.send_message(f"ตั้งเวลาคูลดาวน์ก่อนล็อคห้องเป็น {time_sec} วินาที ✅")

@bot.tree.command(name="setup", description="ตั้งค่าห้องเปิดประมูล")
async def setup(interaction: discord.Interaction, category: discord.CategoryChannel, channel: discord.TextChannel, message: str, approval_channel: discord.TextChannel, feedback_channel: discord.TextChannel = None, btn_label: str = "💰 เปิดประมูล", img_url: str = None):
    if not is_admin(interaction.user): return await no_permission(interaction)
    await interaction.response.defer(ephemeral=True)
    data["setup"] = {
        "category_id": category.id, "channel_id": channel.id, "approval_channel": approval_channel.id,
        "feedback_channel": feedback_channel.id if feedback_channel else None, "btn_label": btn_label,
        "noti_role": data["setup"].get("noti_role"), "image_channel": data["setup"].get("image_channel")
    }
    save_data(data)
    embed = discord.Embed(description=message, color=discord.Color.gold())
    if img_url: embed.set_image(url=img_url)
    view = StartAuctionView(btn_label)
    await channel.send(embed=embed, view=view)
    await interaction.followup.send("ตั้งค่าเรียบร้อยแล้ว ✅", ephemeral=True)

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    keep_alive() 
    if TOKEN: bot.run(TOKEN)
    else: print("Error: ไม่พบ TOKEN")
