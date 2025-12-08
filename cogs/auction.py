import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import re
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, get_files_from_urls, init_guild_data

class AuctionSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_auctions = {}
        self.bot.loop.create_task(self.auction_loop())

    async def auction_loop(self):
        while True:
            to_remove = []
            for chan_id, data in self.active_auctions.items():
                if not data['active']: 
                    to_remove.append(chan_id)
                    continue
                if datetime.datetime.now() >= data['end_time']:
                    await self.end_auction_logic(chan_id)
                    to_remove.append(chan_id)
            for rid in to_remove:
                if rid in self.active_auctions:
                    del self.active_auctions[rid]
            await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if message.channel.id in self.active_auctions and self.active_auctions[message.channel.id]['active']:
            content = message.content.strip()
            auction_data = self.active_auctions[message.channel.id]
            
            match = re.match(r'^(?:up|อัพ)\s*(\d+)', content, re.IGNORECASE)
            if match:
                amount = int(match.group(1))
                if amount > 999999: return 
                if message.author.id == auction_data['seller_id']: return

                start_price = auction_data['start_price']
                bid_step = auction_data['bid_step']
                current_price = auction_data['current_price']
                
                if amount <= current_price: return 
                if (amount - start_price) % bid_step != 0: return

                old_winner = auction_data['winner_id']
                auction_data['current_price'] = amount
                auction_data['winner_id'] = message.author.id
                
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
                        data = load_data()
                        init_guild_data(data, message.guild.id)
                        count = data["guilds"][str(message.guild.id)]["auction_count"]
                        new_name = f"ประมูลครั้งที่-{count}-ราคา-{amount}"
                        await message.channel.edit(name=new_name)
                        auction_data['last_rename'] = datetime.datetime.now().timestamp()
                    except: pass

    @app_commands.command(name="auction", description=MESSAGES["desc_auction"])
    async def auction(self, interaction: discord.Interaction, category: discord.CategoryChannel, channel_send: discord.TextChannel, message: str, approval_channel: discord.TextChannel, role_ping: discord.Role, log_channel: discord.TextChannel = None, btn_text: str = None, img_link: str = None):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(description=message, color=discord.Color.green())
        if img_link: embed.set_image(url=img_link)
        label = btn_text if btn_text else MESSAGES["auc_btn_default"]
        view = StartAuctionView(category, approval_channel, role_ping, log_channel, label, self)
        await channel_send.send(embed=embed, view=view)
        await interaction.followup.send(MESSAGES["cmd_success"], ephemeral=True)

    async def end_auction_logic(self, channel_id):
        if channel_id not in self.active_auctions: return
        auction_data = self.active_auctions[channel_id]
        auction_data['active'] = False
        channel = self.bot.get_channel(channel_id)
        if not channel: return
        
        data = load_data()
        guild_id = str(channel.guild.id)
        init_guild_data(data, guild_id)
        count = data["guilds"][guild_id]["auction_count"]
        lock_time = data["guilds"][guild_id]["lockdown_time"]

        winner_id, seller_id = auction_data['winner_id'], auction_data['seller_id']
        
        if winner_id is None:
            if auction_data['log_id']:
                log = self.bot.get_channel(auction_data['log_id'])
                if log:
                    embed = discord.Embed(description=MESSAGES["auc_end_no_bid"].format(count=count, seller=f"<@{seller_id}>"), color=discord.Color.yellow())
                    await log.send(embed=embed)
            await channel.delete()
            return

        winner_mention = f"<@{winner_id}>"
        winner_msg = await channel.send(MESSAGES["auc_end_winner"].format(winner=winner_mention, count=count, price=auction_data['current_price'], time=lock_time))
        
        await asyncio.sleep(lock_time)

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
        
        try: await winner_msg.delete()
        except: pass
        if auction_data.get('last_bid_msg_id'):
            try: await (await channel.fetch_message(auction_data['last_bid_msg_id'])).delete()
            except: pass

        embed = discord.Embed(description=MESSAGES["auc_lock_msg"].format(winner=winner_mention), color=discord.Color.green())
        embed.add_field(name="ปุ่มสำหรับผู้เปิดประมูล", value="ด้านล่าง")
        embed.set_image(url=auction_data['img_qr_url'])
        view = TransactionView(seller_id, winner_id, auction_data, self.bot, count)
        await channel.send(content=winner_mention, embed=embed, view=view)

    # ฟังก์ชันช่วยสร้าง Embed ตัวอย่าง
    async def create_preview_embed(self, auction_data):
        base_embed = discord.Embed(title="📝 ตัวอย่าง", color=discord.Color.blue())
        base_embed.add_field(name="👤 ผู้ขาย", value=f"<@{auction_data['seller_id']}>", inline=True)
        base_embed.add_field(name="📦 สินค้า", value=auction_data['item_name'], inline=False) 
        
        # เพิ่ม บ.-
        base_embed.add_field(name=MESSAGES["auc_lbl_start"], value=f"{auction_data['start_price']} บ.-", inline=True)
        base_embed.add_field(name=MESSAGES["auc_lbl_step"], value=f"{auction_data['bid_step']} บ.-", inline=True)
        base_embed.add_field(name=MESSAGES["auc_lbl_close"], value=f"{auction_data['close_price']} บ.-", inline=True)
        
        base_embed.add_field(name="⏱️ เวลา", value=f"{auction_data['duration_minutes']} นาที", inline=False)
        base_embed.add_field(name=MESSAGES["auc_lbl_rights"], value=f"```\n{auction_data['rights']}\n```", inline=False)
        base_embed.add_field(name=MESSAGES["auc_lbl_extra"], value=f"```\n{auction_data['extra_info']}\n```", inline=False)
        base_embed.add_field(name=MESSAGES["auc_lbl_link"], value=f"||{auction_data['download_link']}||", inline=False)
        
        # ใส่รูป QR เป็น Thumbnail
        base_embed.set_thumbnail(url=auction_data['img_qr_url'])
        return base_embed

    # ฟังก์ชันส่ง Preview ให้ผู้ใช้ (เรียกใช้ตอนสร้างเสร็จ หรือตอนแก้ไขเสร็จ)
    async def send_user_preview(self, channel, auction_data, old_preview_msg=None):
        if old_preview_msg:
            try: await old_preview_msg.delete()
            except: pass
            
        embed = await self.create_preview_embed(auction_data)
        files_to_send = await get_files_from_urls(auction_data["img_product_urls"])
        
        view = PreviewView(auction_data, channel, self)
        msg = await channel.send(embed=embed, files=files_to_send, view=view)
        return msg

    # Loop รับรูปภาพ
    async def wait_for_images(self, channel, user, auction_data, is_edit=False):
        def check_product(m): 
            return m.author.id == user.id and m.channel.id == channel.id and m.attachments

        def check_qr(m):
            if m.author.id != user.id or m.channel.id != channel.id: return False
            if not m.attachments: return False
            # กฎ: ส่งได้แค่ 1 รูป และต้องเป็นรูปภาพเท่านั้น
            if len(m.attachments) != 1: return False
            if not m.attachments[0].content_type.startswith('image'): return False
            return True

        try:
            # 1. รับรูปสินค้า (รูป/คลิป/gif)
            await channel.send(MESSAGES["auc_wait_img_1"].format(user=user.mention))
            msg1 = await self.bot.wait_for('message', check=check_product, timeout=300)
            auction_data["img_product_urls"] = [att.url for att in msg1.attachments]
            
            # 2. รับ QR Code (รูปภาพเท่านั้น 1 รูป)
            await channel.send(MESSAGES["auc_wait_img_2"])
            while True:
                msg2 = await self.bot.wait_for('message', timeout=300)
                if msg2.author.id != user.id or msg2.channel.id != channel.id: continue
                
                # Check เงื่อนไข
                if not msg2.attachments: continue # ถ้าไม่มีไฟล์ข้าม
                
                is_valid_qr = True
                if len(msg2.attachments) > 1:
                    await channel.send("⚠️ กรุณาส่ง QR Code/ช่องทางชำระเงิน เพียง **1 รูป** เท่านั้นครับ โปรดส่งใหม่", delete_after=10)
                    is_valid_qr = False
                elif not msg2.attachments[0].content_type or not msg2.attachments[0].content_type.startswith('image'):
                    await channel.send("⚠️ กรุณาส่งเป็นไฟล์ **รูปภาพ** เท่านั้นครับ (ห้ามเป็นวิดีโอ) โปรดส่งใหม่", delete_after=10)
                    is_valid_qr = False
                
                if is_valid_qr:
                    auction_data["img_qr_url"] = msg2.attachments[0].url
                    break

            await channel.send(MESSAGES["auc_img_received"])
            
            # ส่ง Preview แทนที่จะส่งหา Admin เลย
            await self.send_user_preview(channel, auction_data)

        except asyncio.TimeoutError:
            await channel.delete()


class StartAuctionView(discord.ui.View):
    def __init__(self, category, approval_channel, role_ping, log_channel, label, cog):
        super().__init__(timeout=None)
        self.category, self.approval_channel, self.role_ping, self.log_channel = category, approval_channel, role_ping, log_channel
        self.cog = cog
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn")
        button.callback = self.start_callback
        self.add_item(button)
    async def start_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AuctionModalStep1(self.category, self.approval_channel, self.role_ping, self.log_channel, self.cog))

class AuctionModalStep1(discord.ui.Modal, title=MESSAGES["auc_step1_title"]):
    def __init__(self, category, approval_channel, role_ping, log_channel, cog, default_data=None, preview_msg=None):
        super().__init__()
        self.category, self.approval_channel, self.role_ping, self.log_channel = category, approval_channel, role_ping, log_channel
        self.cog = cog
        self.default_data = default_data
        self.preview_msg = preview_msg

        # ใช้ค่า Default ถ้ามี (กรณีแก้ไข)
        d_start = str(default_data['start_price']) if default_data else ""
        d_step = str(default_data['bid_step']) if default_data else ""
        d_close = str(default_data['close_price']) if default_data else ""
        d_name = default_data['item_name'] if default_data else ""

        self.start_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_start"], placeholder=MESSAGES["auc_ph_start"], required=True, default=d_start)
        self.bid_step = discord.ui.TextInput(label=MESSAGES["auc_lbl_step"], placeholder=MESSAGES["auc_ph_step"], required=True, default=d_step)
        self.close_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_close"], placeholder=MESSAGES["auc_ph_close"], required=True, default=d_close)
        self.item_name = discord.ui.TextInput(label=MESSAGES["auc_lbl_item"], style=discord.TextStyle.paragraph, required=True, default=d_name)

        self.add_item(self.start_price)
        self.add_item(self.bid_step)
        self.add_item(self.close_price)
        self.add_item(self.item_name)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # ถ้ามี default_data แสดงว่าเป็นโหมดแก้ไข
            if self.default_data:
                self.default_data.update({
                    "start_price": int(self.start_price.value),
                    "bid_step": int(self.bid_step.value),
                    "close_price": int(self.close_price.value),
                    "item_name": self.item_name.value
                })
                # Refresh Preview
                await interaction.response.defer()
                await self.cog.send_user_preview(interaction.channel, self.default_data, self.preview_msg)
            else:
                # โหมดสร้างใหม่
                auction_data = {"start_price": int(self.start_price.value),"bid_step": int(self.bid_step.value),"close_price": int(self.close_price.value),"item_name": self.item_name.value,"category_id": self.category.id,"approval_id": self.approval_channel.id,"role_ping_id": self.role_ping.id,"log_id": self.log_channel.id if self.log_channel else None}
                view = Step2View(auction_data, self.cog)
                await interaction.response.send_message(MESSAGES["auc_prompt_step2"], view=view, ephemeral=True)
        except ValueError: await interaction.response.send_message(MESSAGES["auc_err_num"], ephemeral=True)

class Step2View(discord.ui.View):
    def __init__(self, auction_data, cog):
        super().__init__(timeout=None)
        self.auction_data, self.cog = auction_data, cog
    @discord.ui.button(label=MESSAGES["auc_btn_step2"], style=discord.ButtonStyle.primary)
    async def open_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionModalStep2(self.auction_data, self.cog))

class AuctionModalStep2(discord.ui.Modal, title=MESSAGES["auc_step2_title"]):
    def __init__(self, auction_data, cog, preview_msg=None):
        super().__init__()
        self.auction_data, self.cog = auction_data, cog
        self.preview_msg = preview_msg
        
        # Default values
        d_link = auction_data.get("download_link", "")
        d_rights = auction_data.get("rights", "")
        d_extra = auction_data.get("extra_info", "-")
        # แปลงนาทีกลับเป็น HH:MM
        d_time = ""
        if "duration_minutes" in auction_data:
            h = auction_data["duration_minutes"] // 60
            m = auction_data["duration_minutes"] % 60
            d_time = f"{h:02d}:{m:02d}"

        self.download_link = discord.ui.TextInput(label=MESSAGES["auc_lbl_link"], placeholder=MESSAGES["auc_ph_link"], required=True, default=d_link)
        self.rights = discord.ui.TextInput(label=MESSAGES["auc_lbl_rights"], placeholder=MESSAGES["auc_ph_rights"], required=True, default=d_rights)
        self.extra_info = discord.ui.TextInput(label=MESSAGES["auc_lbl_extra"], placeholder=MESSAGES["auc_ph_extra"], required=False, style=discord.TextStyle.paragraph, default=d_extra)
        self.end_time_str = discord.ui.TextInput(label=MESSAGES["auc_lbl_time"], placeholder=MESSAGES["auc_ph_time"], required=True, default=d_time)

        self.add_item(self.download_link)
        self.add_item(self.rights)
        self.add_item(self.extra_info)
        self.add_item(self.end_time_str)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            h, m = map(int, self.end_time_str.value.split(':'))
            total_minutes = (h * 60) + m
            if total_minutes <= 0: raise ValueError
            
            self.auction_data.update({
                "download_link": self.download_link.value, 
                "rights": self.rights.value,
                "extra_info": self.extra_info.value if self.extra_info.value else "-",
                "duration_minutes": total_minutes, 
                "seller_id": interaction.user.id
            })
            
            if self.preview_msg:
                # แก้ไขเสร็จ Refresh Preview
                await interaction.response.defer()
                await self.cog.send_user_preview(interaction.channel, self.auction_data, self.preview_msg)
            else:
                # สร้างใหม่ -> สร้างห้องส่งรูป
                data = load_data()
                overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),interaction.user: discord.PermissionOverwrite(read_messages=True),interaction.guild.me: discord.PermissionOverwrite(read_messages=True)}
                for admin_id in data["admins"]:
                    member = interaction.guild.get_member(admin_id)
                    if member: overwrites[member] = discord.PermissionOverwrite(read_messages=True)
                
                channel = await interaction.guild.create_text_channel(f"✧꒰ส่งรูปสินค้า📦-{interaction.user.name}꒱", overwrites=overwrites)
                await interaction.response.send_message(MESSAGES["auc_created_channel"].format(channel=channel.mention), ephemeral=True)
                self.cog.bot.loop.create_task(self.cog.wait_for_images(channel, interaction.user, self.auction_data))
        except: await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)


# --- Preview Views ---

class PreviewView(discord.ui.View):
    def __init__(self, auction_data, temp_channel, cog):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel, self.cog = auction_data, temp_channel, cog

    @discord.ui.button(label="✅ ยืนยัน (ส่งให้แอดมิน)", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # ส่งไปหาแอดมิน
        approval_channel = self.cog.bot.get_channel(self.auction_data["approval_id"])
        if approval_channel:
            base_embed = await self.cog.create_preview_embed(self.auction_data)
            base_embed.title = MESSAGES["auc_embed_request_title"] # เปลี่ยน Title
            base_embed.color = discord.Color.gold()
            
            files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
            view = ApprovalView(self.auction_data, self.temp_channel, self.cog)
            await approval_channel.send(embed=base_embed, files=files_to_send, view=view)
        
        await interaction.followup.send("ส่งคำขอให้แอดมินเรียบร้อยแล้วครับ! โปรดรอการอนุมัติ", ephemeral=True)
        # ปิดการกดปุ่มซ้ำ
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="✏️ แก้ไข", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        # เปลี่ยน View เป็น EditSelectionView
        view = EditSelectionView(self.auction_data, self.temp_channel, self.cog, interaction.message)
        await interaction.response.edit_message(view=view)

class EditSelectionView(discord.ui.View):
    def __init__(self, auction_data, temp_channel, cog, message):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel, self.cog, self.message = auction_data, temp_channel, cog, message

    @discord.ui.button(label="แก้ไขฟอร์ม 1 (ราคา/ชื่อ)", style=discord.ButtonStyle.secondary)
    async def edit_form1(self, interaction: discord.Interaction, button: discord.ui.Button):
        # เปิด Modal Step 1 พร้อมข้อมูลเดิม
        modal = AuctionModalStep1(None, None, None, None, self.cog, default_data=self.auction_data, preview_msg=self.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="แก้ไขฟอร์ม 2 (ลิ้งค์/เวลา)", style=discord.ButtonStyle.secondary)
    async def edit_form2(self, interaction: discord.Interaction, button: discord.ui.Button):
        # เปิด Modal Step 2 พร้อมข้อมูลเดิม
        modal = AuctionModalStep2(self.auction_data, self.cog, preview_msg=self.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="แก้ไขรูปภาพ", style=discord.ButtonStyle.secondary)
    async def edit_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("กรุณาส่งรูปสินค้าใหม่ และตามด้วยรูป QR Code ใหม่ครับ", ephemeral=True)
        # ลบ Preview เก่าทิ้งเลยเพื่อไม่ให้งง
        try: await self.message.delete()
        except: pass
        
        # เริ่ม Loop รับรูปใหม่
        self.cog.bot.loop.create_task(self.cog.wait_for_images(self.temp_channel, interaction.user, self.auction_data, is_edit=True))


# --- Admin Approval View (คงเดิม แต่ปรับนิดหน่อย) ---
class ApprovalView(discord.ui.View):
    def __init__(self, auction_data, temp_channel, cog):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel, self.cog = auction_data, temp_channel, cog
    @discord.ui.button(label=MESSAGES["auc_btn_approve"], style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.temp_channel: await self.temp_channel.delete()
        category = interaction.guild.get_channel(self.auction_data["category_id"])
        
        data = load_data()
        init_guild_data(data, interaction.guild_id)
        data["guilds"][str(interaction.guild_id)]["auction_count"] += 1
        count = data["guilds"][str(interaction.guild_id)]["auction_count"]
        save_data(data)
        
        auction_channel = await interaction.guild.create_text_channel(f"ประมูลครั้งที่-{count}-ราคา-{self.auction_data['start_price']}", category=category)
        ping_role = interaction.guild.get_role(self.auction_data["role_ping_id"])
        if ping_role: await auction_channel.send(ping_role.mention, delete_after=5)
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=self.auction_data["duration_minutes"])
        timestamp = int(end_time.timestamp())
        
        main_embed = discord.Embed(description=MESSAGES["auc_embed_title"], color=discord.Color.purple())
        
        main_embed.add_field(name="👤 ผู้เปิดประมูล", value=f"<@{self.auction_data['seller_id']}>", inline=True)
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="📦 " + MESSAGES["auc_lbl_item"], value=f"**{self.auction_data['item_name']}**", inline=False)
        
        # เพิ่ม บ.-
        main_embed.add_field(name="💰 " + MESSAGES["auc_lbl_start"], value=f"`{self.auction_data['start_price']} บ.-`", inline=True)
        main_embed.add_field(name="📈 " + MESSAGES["auc_lbl_step"], value=f"`{self.auction_data['bid_step']} บ.-`", inline=True)
        main_embed.add_field(name="🛎️ " + MESSAGES["auc_lbl_close"], value=f"`{self.auction_data['close_price']} บ.-`", inline=True)
        
        main_embed.add_field(name="📜 " + MESSAGES["auc_lbl_rights"], value=f"{self.auction_data['rights']}", inline=False)
        main_embed.add_field(name="ℹ️ " + MESSAGES["auc_lbl_extra"], value=f"{self.auction_data['extra_info']}", inline=False)
        main_embed.add_field(name="───────────────", value=f"⏰ **ปิดประมูล : <t:{timestamp}:R>**", inline=False)
        
        files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
        view = AuctionControlView(self.auction_data['seller_id'], self.cog)
        msg = await auction_channel.send(embed=main_embed, view=view)
        if files_to_send: await auction_channel.send(files=files_to_send)
        
        self.auction_data.update({'channel_id': auction_channel.id, 'current_price': self.auction_data['start_price'],'end_time': end_time, 'winner_id': None, 'message_id': msg.id, 'active': True, 'last_bid_msg_id': None})
        self.cog.active_auctions[auction_channel.id] = self.auction_data
        
        await interaction.followup.send(MESSAGES["auc_admin_approve_log"].format(channel=auction_channel.mention))
        self.stop()

    @discord.ui.button(label=MESSAGES["auc_btn_deny"], style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyModal(self.auction_data, self.temp_channel, self.cog))

class DenyModal(discord.ui.Modal, title=MESSAGES["auc_modal_deny_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["auc_lbl_deny_reason"], required=True)
    def __init__(self, auction_data, temp_channel, cog):
        super().__init__()
        self.auction_data, self.temp_channel, self.cog = auction_data, temp_channel, cog
    async def on_submit(self, interaction: discord.Interaction):
        if self.temp_channel: await self.temp_channel.delete()
        if self.auction_data["log_id"]:
            log_chan = self.cog.bot.get_channel(self.auction_data["log_id"])
            embed = discord.Embed(title=MESSAGES["auc_log_deny_title"], color=discord.Color.red())
            embed.add_field(name="ผู้ขาย", value=f"<@{self.auction_data['seller_id']}>", inline=True)
            embed.add_field(name="ปฏิเสธโดย", value=interaction.user.mention, inline=True)
            embed.add_field(name="เหตุผล", value=self.reason.value, inline=False)
            embed.timestamp = datetime.datetime.now()
            await log_chan.send(embed=embed)
        await interaction.response.send_message(MESSAGES["auc_deny_msg"], ephemeral=True)

class AuctionControlView(discord.ui.View):
    def __init__(self, seller_id, cog):
        super().__init__(timeout=None)
        self.seller_id, self.cog = seller_id, cog
    @discord.ui.button(label=MESSAGES["auc_btn_force_close"], style=discord.ButtonStyle.red)
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id or is_admin_or_has_permission(interaction):
            if interaction.channel_id in self.cog.active_auctions:
                self.cog.active_auctions[interaction.channel_id]['end_time'] = datetime.datetime.now()
                await interaction.response.send_message(MESSAGES["auc_closing"], ephemeral=True)
            else: await interaction.response.send_message(MESSAGES["auc_no_data"], ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)

class TransactionView(discord.ui.View):
    def __init__(self, seller_id, winner_id, auction_data, bot, count):
        super().__init__(timeout=None)
        self.seller_id, self.winner_id, self.auction_data, self.bot, self.count = seller_id, winner_id, auction_data, bot, count

    @discord.ui.button(label=MESSAGES["auc_btn_confirm"], style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ConfirmFinalView(self.auction_data, interaction.channel, self.bot, self.count)
        await interaction.response.send_message(MESSAGES["auc_check_money"], view=view, ephemeral=True)
    @discord.ui.button(label=MESSAGES["auc_btn_cancel"], style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_modal(CancelReasonModal(self.auction_data, interaction.channel, self.bot, self.count))

class ConfirmFinalView(discord.ui.View):
    def __init__(self, auction_data, channel, bot, count):
        super().__init__(timeout=None)
        self.auction_data, self.channel, self.bot, self.count = auction_data, channel, bot, count
    @discord.ui.button(label=MESSAGES["auc_btn_double_confirm"], style=discord.ButtonStyle.green)
    async def double_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            winner = interaction.guild.get_member(self.auction_data['winner_id']) or await self.bot.fetch_user(self.auction_data['winner_id'])
            await winner.send(MESSAGES["auc_dm_content"].format(link=self.auction_data['download_link']))
            dm_msg = MESSAGES["auc_dm_success"]
        except: dm_msg = MESSAGES["auc_dm_fail"].format(user=f"<@{self.auction_data['winner_id']}>")
        await interaction.followup.send(f"{dm_msg}\n{MESSAGES['msg_channel_ready_delete']}", ephemeral=True)
        
        if self.auction_data['log_id']:
            log = self.bot.get_channel(self.auction_data['log_id'])
            data = load_data()
            embed = discord.Embed(description=MESSAGES["auc_success_log"].format(count=self.count, seller=f"<@{self.auction_data['seller_id']}>", winner=f"<@{self.auction_data['winner_id']}>", price=self.auction_data['current_price']), color=discord.Color.green())
            files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
            await log.send(embed=embed, files=files_to_send)
        
        await self.channel.send(MESSAGES["msg_channel_ready_delete"], view=AdminCloseView())

class CancelReasonModal(discord.ui.Modal, title=MESSAGES["auc_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["auc_lbl_deny_reason"], required=True)
    def __init__(self, auction_data, channel, bot, count):
        super().__init__()
        self.auction_data, self.channel, self.bot, self.count = auction_data, channel, bot, count
    async def on_submit(self, interaction: discord.Interaction):
        if self.auction_data['log_id']:
            log = self.bot.get_channel(self.auction_data['log_id'])
            data = load_data()
            embed = discord.Embed(description=MESSAGES["auc_cancel_log"].format(count=self.count, seller=f"<@{self.auction_data['seller_id']}>", user=interaction.user.mention, reason=self.reason.value), color=discord.Color.red())
            await log.send(embed=embed)
        await interaction.response.send_message(MESSAGES["auc_msg_cancel_success"], ephemeral=True)
        
        await self.channel.send(MESSAGES["msg_channel_ready_delete"], view=AdminCloseView())

async def setup(bot):
    await bot.add_cog(AuctionSystem(bot))
