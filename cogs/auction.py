import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import re
import asyncio
import aiohttp
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, get_files_from_urls, init_guild_data

class AuctionSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_auctions = {}
        self.bot.loop.create_task(self.auction_loop())

    async def cog_load(self):
        await self.bot.wait_until_ready()
        print("🔄 Restoring Auction Views...")
        data = load_data()
        
        if "active_auctions" in data:
            for chan_id, auction_data in data["active_auctions"].items():
                try:
                    if isinstance(auction_data['end_time'], str):
                        auction_data['end_time'] = datetime.datetime.fromtimestamp(float(auction_data['end_time_ts']))
                    
                    self.active_auctions[int(chan_id)] = auction_data
                    
                    if auction_data.get('message_id'):
                        view = AuctionControlView(auction_data['seller_id'], self)
                        self.bot.add_view(view, message_id=auction_data['message_id'])
                        
                except Exception as e:
                    print(f"Failed to restore auction {chan_id}: {e}")
        
        print(f"✅ Restored {len(self.active_auctions)} active auctions.")

    async def save_active_auctions(self):
        data = load_data()
        serializable_auctions = {}
        for cid, adata in self.active_auctions.items():
            copy_data = adata.copy()
            copy_data['end_time_ts'] = copy_data['end_time'].timestamp()
            copy_data['end_time'] = str(copy_data['end_time'])
            serializable_auctions[str(cid)] = copy_data
            
        data["active_auctions"] = serializable_auctions
        save_data(data)

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
                    await self.save_active_auctions()
            await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if message.channel.id in self.active_auctions and self.active_auctions[message.channel.id]['active']:
            content = message.content.strip()
            auction_data = self.active_auctions[message.channel.id]
            
            match = re.match(r'^(?:up|อัพ|บิด)\s*(\d+)', content, re.IGNORECASE)
            if match:
                amount = int(match.group(1))
                if amount > 999999999: return 
                if message.author.id == auction_data['seller_id']: return

                start_price = auction_data['start_price']
                bid_step = auction_data['bid_step']
                current_price = auction_data['current_price']
                
                # Logic การบิด: ต้องมากกว่าราคาปัจจุบัน และ (ราคาที่บิด - ราคาเริ่ม) หาร step ลงตัว หรือ บิดมากกว่าราคาปัจจุบันบวก step
                # เพื่อความง่าย ใช้ logic: มากกว่าราคาปัจจุบัน และ (amount - current) >= step หรือลงตัวตาม step
                if amount <= current_price: return
                
                # Check Auto Buy
                is_autobuy = False
                if auction_data['close_price'] and amount >= auction_data['close_price']:
                    is_autobuy = True
                    amount = auction_data['close_price'] # Cap at auto buy

                old_winner = auction_data['winner_id']
                auction_data['current_price'] = amount
                auction_data['winner_id'] = message.author.id
                
                response_text = MESSAGES["auc_bid_response"].format(user=message.author.mention, amount=f"{amount:,}")
                if old_winner and old_winner != message.author.id: response_text += MESSAGES["auc_bid_outbid"].format(old_winner=f"<@{old_winner}>")
                
                if is_autobuy:
                    response_text += MESSAGES["auc_bid_autobuy"]
                    auction_data['end_time'] = datetime.datetime.now() # End immediately
                
                if auction_data.get('last_bid_msg_id'):
                    try: await (await message.channel.fetch_message(auction_data['last_bid_msg_id'])).delete()
                    except: pass
                
                sent_msg = await message.reply(response_text)
                auction_data['last_bid_msg_id'] = sent_msg.id
                
                await self.save_active_auctions()
                
                if (datetime.datetime.now().timestamp() - auction_data.get('last_rename', 0)) > 60:
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
        
        # Remove buttons from original embed
        try:
            msg = await channel.fetch_message(auction_data['message_id'])
            await msg.edit(view=None)
        except: pass

        if winner_id is None:
            if auction_data['log_id']:
                log = self.bot.get_channel(auction_data['log_id'])
                if log:
                    embed = discord.Embed(description=MESSAGES["auc_end_no_bid"].format(count=count, seller=f"<@{seller_id}>"), color=discord.Color.yellow())
                    await log.send(embed=embed)
            await channel.send("⚠️ **ปิดการประมูล (ไม่มีผู้เสนอราคา)**")
            await asyncio.sleep(10)
            await channel.delete()
            return

        winner_mention = f"<@{winner_id}>"
        winner_msg = await channel.send(MESSAGES["auc_end_winner"].format(winner=winner_mention, count=count, price=f"{auction_data['current_price']:,}", time=lock_time))
        
        await asyncio.sleep(lock_time)

        overwrites = {
            channel.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            channel.guild.get_member(seller_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            channel.guild.get_member(winner_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            channel.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        for admin_id in data["guilds"][guild_id]["admins"]:
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

        # Notify Winner via DM
        try:
            winner_user = await self.bot.fetch_user(winner_id)
            dm_embed = discord.Embed(title="🎉 คุณชนะการประมูล!", color=discord.Color.gold())
            dm_embed.add_field(name="สินค้า", value=auction_data["item_name"])
            dm_embed.add_field(name="ราคาจบ", value=f"{auction_data['current_price']:,} บาท")
            dm_embed.set_footer(text="โปรดชำระเงินในห้องประมูล")
            await winner_user.send(embed=dm_embed)
        except: pass

    async def create_final_style_embed(self, auction_data, is_preview=False, custom_end_timestamp=None):
        if custom_end_timestamp:
            timestamp = custom_end_timestamp
        else:
            duration = auction_data.get('duration_minutes', 60)
            end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)
            timestamp = int(end_time.timestamp())
        
        main_embed = discord.Embed(description=MESSAGES["auc_embed_title"], color=discord.Color.purple())
        main_embed.add_field(name="👤 ผู้เปิดประมูล", value=f"<@{auction_data['seller_id']}>", inline=True)
        main_embed.add_field(name="\u200b", value="\u200b", inline=True)
        main_embed.add_field(name="📦 " + MESSAGES["auc_lbl_item"], value=f"**{auction_data['item_name']}**", inline=False)
        main_embed.add_field(name="💰 " + MESSAGES["auc_lbl_start"], value=f"`{auction_data['start_price']:,} บ.-`", inline=True)
        main_embed.add_field(name="📈 " + MESSAGES["auc_lbl_step"], value=f"`{auction_data['bid_step']:,} บ.-`", inline=True)
        close_p = f"`{auction_data['close_price']:,} บ.-`" if auction_data['close_price'] else "ไม่มี"
        main_embed.add_field(name="🛎️ " + MESSAGES["auc_lbl_close"], value=close_p, inline=True)
        main_embed.add_field(name="📜 " + MESSAGES["auc_lbl_rights"], value=f"{auction_data['rights']}", inline=False)
        main_embed.add_field(name="ℹ️ " + MESSAGES["auc_lbl_extra"], value=f"{auction_data['extra_info']}", inline=False)
        main_embed.add_field(name="───────────────", value=f"⏰ **ปิดประมูล : <t:{timestamp}:R>**", inline=False)
        
        if is_preview:
            main_embed.title = "🔎 ตัวอย่างเมื่อเปิดประมูล (Preview)"
            main_embed.set_footer(text="นี่คือตัวอย่างการแสดงผล ข้อมูลจริงจะปรากฏเมื่อแอดมินอนุมัติ")
        return main_embed

    async def send_user_preview(self, channel, auction_data, old_preview_msg=None):
        if old_preview_msg:
            try: await old_preview_msg.delete()
            except: pass
        embed = await self.create_final_style_embed(auction_data, is_preview=True)
        files_to_send = await get_files_from_urls(auction_data["img_product_urls"])
        view = PreviewView(auction_data, channel, self)
        msg = await channel.send(embed=embed, files=files_to_send, view=view)
        return msg

    async def wait_for_images(self, channel, user, auction_data, is_edit=False):
        def check_product(m): return m.author.id == user.id and m.channel.id == channel.id and m.attachments
        try:
            await channel.send(MESSAGES["auc_wait_img_1"].format(user=user.mention))
            msg1 = await self.bot.wait_for('message', check=check_product, timeout=300)
            auction_data["img_product_urls"] = [att.url for att in msg1.attachments]
            
            await channel.send(MESSAGES["auc_wait_img_2"])
            while True:
                msg2 = await self.bot.wait_for('message', timeout=300)
                if msg2.author.id != user.id or msg2.channel.id != channel.id: continue
                if not msg2.attachments: continue
                if len(msg2.attachments) > 1: await channel.send("⚠️ กรุณาส่ง QR Code เพียง **1 รูป** เท่านั้นครับ", delete_after=10); continue
                if not msg2.attachments[0].content_type or not msg2.attachments[0].content_type.startswith('image'): await channel.send("⚠️ กรุณาส่งไฟล์ **รูปภาพ** เท่านั้นครับ", delete_after=10); continue
                auction_data["img_qr_url"] = msg2.attachments[0].url
                break
                
            await channel.send(MESSAGES["auc_img_received"])
            if is_edit:
                # ถ้าเป็นการแก้ไข ให้ส่ง Embed Preview แบบใหม่ให้ดู หรือจบกระบวนการ
                await channel.send("✅ อัปเดตรูปภาพเรียบร้อยแล้ว!")
                # Note: Logic การ update รูปในห้องประมูลจริงจะอยู่ที่ EditSelectionView
            else:
                await self.send_user_preview(channel, auction_data)
                
        except asyncio.TimeoutError: await channel.delete()

# --- Views ---
class StartAuctionView(discord.ui.View):
    def __init__(self, category, approval_channel, role_ping, log_channel, label, cog):
        super().__init__(timeout=None)
        self.category, self.approval_channel, self.role_ping, self.log_channel, self.cog = category, approval_channel, role_ping, log_channel, cog
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.green, custom_id="start_auction_btn")
        button.callback = self.start_callback
        self.add_item(button)
    async def start_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AuctionModalStep1(self.category, self.approval_channel, self.role_ping, self.log_channel, self.cog))

class AuctionModalStep1(discord.ui.Modal, title=MESSAGES["auc_step1_title"]):
    def __init__(self, category, approval_channel, role_ping, log_channel, cog, default_data=None, preview_msg=None):
        super().__init__()
        self.category, self.approval_channel, self.role_ping, self.log_channel, self.cog, self.default_data, self.preview_msg = category, approval_channel, role_ping, log_channel, cog, default_data, preview_msg
        d_start = str(default_data['start_price']) if default_data else ""
        d_step = str(default_data['bid_step']) if default_data else ""
        d_close = str(default_data['close_price']) if default_data and default_data['close_price'] else ""
        d_name = str(default_data['item_name']) if default_data else ""
        self.start_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_start"], placeholder=MESSAGES["auc_ph_start"], required=True, default=d_start)
        self.bid_step = discord.ui.TextInput(label=MESSAGES["auc_lbl_step"], placeholder=MESSAGES["auc_ph_step"], required=True, default=d_step)
        self.close_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_close"], placeholder=MESSAGES["auc_ph_close"], required=False, default=d_close)
        self.item_name = discord.ui.TextInput(label=MESSAGES["auc_lbl_item"], style=discord.TextStyle.paragraph, required=True, default=d_name)
        self.add_item(self.start_price); self.add_item(self.bid_step); self.add_item(self.close_price); self.add_item(self.item_name)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            start = int(self.start_price.value)
            step = int(self.bid_step.value)
            close = int(self.close_price.value) if self.close_price.value else 0
            
            if self.default_data:
                self.default_data.update({"start_price": start,"bid_step": step,"close_price": close,"item_name": self.item_name.value})
                await interaction.response.defer()
                await self.cog.send_user_preview(interaction.channel, self.default_data, self.preview_msg)
            else:
                auction_data = {"start_price": start,"bid_step": step,"close_price": close,"item_name": self.item_name.value,"category_id": self.category.id,"approval_id": self.approval_channel.id,"role_ping_id": self.role_ping.id,"log_id": self.log_channel.id if self.log_channel else None}
                view = Step2View(auction_data, self.cog)
                await interaction.response.send_message(MESSAGES["auc_prompt_step2"], view=view, ephemeral=True)
        except ValueError: 
            if not interaction.response.is_done(): await interaction.response.send_message(MESSAGES["auc_err_num"], ephemeral=True)

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
        self.auction_data, self.cog, self.preview_msg = auction_data, cog, preview_msg
        d_link = str(auction_data.get("download_link", ""))
        d_rights = str(auction_data.get("rights", ""))
        d_extra = str(auction_data.get("extra_info", ""))
        d_time = ""
        if "duration_minutes" in auction_data: d_time = f"{auction_data['duration_minutes'] // 60:02d}:{auction_data['duration_minutes'] % 60:02d}"
        
        self.download_link = discord.ui.TextInput(label=MESSAGES["auc_lbl_link"], placeholder=MESSAGES["auc_ph_link"], required=True, default=d_link)
        self.rights = discord.ui.TextInput(label=MESSAGES["auc_lbl_rights"], placeholder=MESSAGES["auc_ph_rights"], required=True, default=d_rights)
        # [UPDATED] Mandatory + Placeholder
        self.extra_info = discord.ui.TextInput(label=MESSAGES["auc_lbl_extra"], placeholder="อธิบายสินค้าหรือกฎ", required=True, style=discord.TextStyle.paragraph, default=d_extra)
        self.end_time_str = discord.ui.TextInput(label=MESSAGES["auc_lbl_time"], placeholder=MESSAGES["auc_ph_time"], required=True, default=d_time)
        self.add_item(self.download_link); self.add_item(self.rights); self.add_item(self.extra_info); self.add_item(self.end_time_str)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            h, m = map(int, self.end_time_str.value.split(':'))
            total_minutes = (h * 60) + m
            if total_minutes <= 0: raise ValueError
            self.auction_data.update({"download_link": self.download_link.value, "rights": self.rights.value,"extra_info": self.extra_info.value,"duration_minutes": total_minutes, "seller_id": interaction.user.id})
            if self.preview_msg:
                await interaction.response.defer()
                await self.cog.send_user_preview(interaction.channel, self.auction_data, self.preview_msg)
            else:
                data = load_data()
                overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),interaction.user: discord.PermissionOverwrite(read_messages=True),interaction.guild.me: discord.PermissionOverwrite(read_messages=True)}
                for admin_id in data["guilds"][str(interaction.guild_id)]["admins"]: # Fix: load local admins
                    member = interaction.guild.get_member(admin_id)
                    if member: overwrites[member] = discord.PermissionOverwrite(read_messages=True)
                channel = await interaction.guild.create_text_channel(f"✧꒰ส่งรูปสินค้า📦-{interaction.user.name}꒱", overwrites=overwrites)
                await interaction.response.send_message(MESSAGES["auc_created_channel"].format(channel=channel.mention), ephemeral=True)
                self.cog.bot.loop.create_task(self.cog.wait_for_images(channel, interaction.user, self.auction_data))
        except: 
            if not interaction.response.is_done(): await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)

class PreviewView(discord.ui.View):
    def __init__(self, auction_data, temp_channel, cog):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel, self.cog = auction_data, temp_channel, cog
    @discord.ui.button(label="✅ ยืนยัน (ส่งให้แอดมิน)", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        approval_channel = self.cog.bot.get_channel(self.auction_data["approval_id"])
        if approval_channel:
            base_embed = await self.cog.create_final_style_embed(self.auction_data, is_preview=False)
            base_embed.title = MESSAGES["auc_embed_request_title"]
            base_embed.color = discord.Color.gold()
            files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
            view = ApprovalView(self.auction_data, self.temp_channel, self.cog)
            await approval_channel.send(embed=base_embed, files=files_to_send, view=view)
        await interaction.followup.send("ส่งคำขอให้แอดมินเรียบร้อยแล้วครับ! โปรดรอการอนุมัติ", ephemeral=True)
        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)
    @discord.ui.button(label="✏️ แก้ไข", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EditSelectionView(self.auction_data, self.temp_channel, self.cog, interaction.message)
        await interaction.response.edit_message(view=view)

class EditSelectionView(discord.ui.View):
    def __init__(self, auction_data, temp_channel, cog, message):
        super().__init__(timeout=None)
        self.auction_data, self.temp_channel, self.cog, self.message = auction_data, temp_channel, cog, message
    @discord.ui.button(label="แก้ไขฟอร์ม 1 (ราคา/ชื่อ)", style=discord.ButtonStyle.secondary)
    async def edit_form1(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuctionModalStep1(None, None, None, None, self.cog, default_data=self.auction_data, preview_msg=self.message)
        await interaction.response.send_modal(modal)
    @discord.ui.button(label="แก้ไขฟอร์ม 2 (ลิ้งค์/เวลา)", style=discord.ButtonStyle.secondary)
    async def edit_form2(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuctionModalStep2(self.auction_data, self.cog, preview_msg=self.message)
        await interaction.response.send_modal(modal)
    @discord.ui.button(label="แก้ไขรูปภาพ", style=discord.ButtonStyle.secondary)
    async def edit_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("กรุณาส่งรูปสินค้าใหม่ และตามด้วยรูป QR Code ใหม่ครับ", ephemeral=True)
        try: await self.message.delete()
        except: pass
        self.cog.bot.loop.create_task(self.cog.wait_for_images(self.temp_channel, interaction.user, self.auction_data, is_edit=True))

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
        main_embed = await self.cog.create_final_style_embed(self.auction_data, is_preview=False, custom_end_timestamp=timestamp)
        embed_msg = await auction_channel.send(embed=main_embed)
        
        files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
        view = AuctionControlView(self.auction_data['seller_id'], self.cog)
        if files_to_send:
            await auction_channel.send(files=files_to_send, view=view)
            msg_id = embed_msg.id
        else:
            await embed_msg.edit(view=view)
            msg_id = embed_msg.id
        
        self.auction_data.update({'channel_id': auction_channel.id, 'current_price': self.auction_data['start_price'],'end_time': end_time, 'winner_id': None, 'message_id': msg_id, 'active': True, 'last_bid_msg_id': None})
        self.cog.active_auctions[auction_channel.id] = self.auction_data
        await self.cog.save_active_auctions()
        
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
    
    @discord.ui.button(label=MESSAGES["auc_btn_force_close"], style=discord.ButtonStyle.red, custom_id="auc_force_close")
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id or is_admin_or_has_permission(interaction):
            if interaction.channel_id in self.cog.active_auctions:
                self.cog.active_auctions[interaction.channel_id]['end_time'] = datetime.datetime.now()
                await interaction.response.send_message(MESSAGES["auc_closing"], ephemeral=True)
            else: await interaction.response.send_message(MESSAGES["auc_no_data"], ephemeral=True)
        else: await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)

    @discord.ui.button(label="แก้ไข (Admin)", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="auc_edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        msg_id = str(interaction.message.id)
        view = AuctionEditView(msg_id)
        await interaction.response.send_message("⚙️ **เมนูแก้ไขการประมูล**", view=view, ephemeral=True)

    # [NEW] ปุ่มรายงาน
    @discord.ui.button(label="รายงาน", style=discord.ButtonStyle.red, emoji="🚨", custom_id="auc_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.seller_id:
            return await interaction.response.send_message("❌ คุณไม่สามารถรายงานประมูลของตัวเองได้", ephemeral=True)
        await interaction.response.send_modal(AuctionReportModal(str(interaction.message.id)))

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
            embed = discord.Embed(description=MESSAGES["auc_cancel_log"].format(count=self.count, seller=f"<@{self.auction_data['seller_id']}>", user=interaction.user.mention, reason=self.reason.value), color=discord.Color.red())
            await log.send(embed=embed)
        await interaction.response.send_message(MESSAGES["auc_msg_cancel_success"], ephemeral=True)
        await self.channel.send(MESSAGES["msg_channel_ready_delete"], view=AdminCloseView())

class AdminCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🗑️ ปิดห้อง", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

# =========================================
# EDIT & REPORT SYSTEMS (NEW)
# =========================================
class AuctionReportModal(discord.ui.Modal, title="รายงานการประมูล"):
    reason = discord.ui.TextInput(label="เหตุผล", required=True, placeholder="ระบุเหตุผลที่ต้องการรายงาน...")
    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ ส่งคำร้องรายงานเรียบร้อยแล้ว", ephemeral=True)
        data = load_data()
        guild_id = str(interaction.guild_id)
        init_guild_data(data, guild_id)
        pings = []
        target_ids = set(data["guilds"][guild_id]["admins"] + data["guilds"][guild_id]["supports"])
        for tid in target_ids:
            role = interaction.guild.get_role(tid)
            if role: pings.append(role.mention)
            else: pings.append(f"<@{tid}>")
        ping_msg = " ".join(pings) if pings else "@here"
        
        embed = discord.Embed(title="🚨 มีการรายงานการประมูล", color=discord.Color.red())
        embed.add_field(name="🔗 ลิ้งค์ประมูล", value=f"https://discord.com/channels/{interaction.guild_id}/{interaction.channel_id}/{self.message_id}", inline=False)
        embed.add_field(name="👤 ผู้รายงาน", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
        embed.timestamp = datetime.datetime.now()
        await interaction.channel.send(content=f"{ping_msg} **มีการรายงานเข้ามา!**", embed=embed)

class AuctionEditView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=180)
        self.message_id = message_id
    @discord.ui.button(label="แก้ไขข้อมูล (ข้อความ)", style=discord.ButtonStyle.primary, emoji="📝")
    async def edit_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.message_id not in data["active_auctions"]:
            return await interaction.response.send_message("❌ ไม่พบข้อมูลประมูลนี้แล้ว", ephemeral=True)
        auc = data["active_auctions"][self.message_id]
        await interaction.response.send_modal(AuctionEditModal(self.message_id, auc))
    @discord.ui.button(label="แก้ไขรูปภาพ", style=discord.ButtonStyle.success, emoji="🖼️")
    async def edit_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AuctionEditImageView(self.message_id)
        await interaction.response.send_message("🖼️ **เลือกรูปที่ต้องการแก้ไข:**", view=view, ephemeral=True)
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ ยกเลิกการแก้ไขแล้ว", view=None)

class AuctionEditImageView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=180)
        self.message_id = message_id
    @discord.ui.button(label="แก้ไขรูปสินค้า", style=discord.ButtonStyle.primary, emoji="📦")
    async def edit_product_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_image_edit(interaction, "img_product_urls")
    @discord.ui.button(label="แก้ไขรูปชำระเงิน", style=discord.ButtonStyle.primary, emoji="💳")
    async def edit_payment_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_image_edit(interaction, "img_qr_url")
    @discord.ui.button(label="ย้อนกลับ", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AuctionEditView(self.message_id)
        await interaction.response.edit_message(content="⚙️ **เมนูแก้ไขการประมูล**", view=view)

    async def process_image_edit(self, interaction: discord.Interaction, key):
        await interaction.response.defer(ephemeral=True) 
        await interaction.followup.send("📤 **กรุณาส่งรูปภาพใหม่มาในช่องนี้** (ภายใน 60 วินาที...)", ephemeral=True)
        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.attachments
        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60.0)
            new_urls = [att.url for att in msg.attachments]
            new_val = new_urls if key == "img_product_urls" else new_urls[0]
            
            data = load_data()
            if self.message_id in data["active_auctions"]:
                data["active_auctions"][self.message_id][key] = new_val
                save_data(data)
                
                # Update Embed (Live)
                auc = data["active_auctions"][self.message_id]
                try:
                    channel = interaction.guild.get_channel(auc["channel_id"])
                    auction_msg = await channel.fetch_message(int(self.message_id))
                    if key == "img_product_urls":
                        embed = auction_msg.embeds[0]
                        embed.set_image(url=new_val[0]) # Show first image
                        await auction_msg.edit(embed=embed)
                    await interaction.followup.send("✅ **อัปเดตเลูปภาพเรียบร้อยแล้ว!**", ephemeral=True)
                    try: await msg.delete() 
                    except: pass
                except Exception as e:
                    await interaction.followup.send(f"⚠️ บันทึกแล้ว แต่อัปเดตข้อความเดิมไม่ได้: {e}", ephemeral=True)
            else:
                await interaction.followup.send("❌ ไม่พบข้อมูลประมูล", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⌛ **หมดเวลาส่งรูป** (ยกเลิกการแก้ไข)", ephemeral=True)

class AuctionEditModal(discord.ui.Modal, title="แก้ไขรายละเอียด"):
    name = discord.ui.TextInput(label="ชื่อสินค้า", required=True)
    rights = discord.ui.TextInput(label="สิทธิ์", required=True)
    extra = discord.ui.TextInput(label="เพิ่มเติม", required=True, style=discord.TextStyle.paragraph, placeholder="อธิบายสินค้าหรือกฎ")
    def __init__(self, message_id, current_data):
        super().__init__()
        self.message_id = message_id
        self.name.default = current_data.get("item_name", "")
        self.rights.default = current_data.get("rights", "")
        self.extra.default = current_data.get("extra_info", "")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        if self.message_id in data["active_auctions"]:
            auc = data["active_auctions"][self.message_id]
            auc["item_name"] = self.name.value
            auc["rights"] = self.rights.value
            auc["extra_info"] = self.extra.value
            save_data(data)
            try:
                channel = interaction.guild.get_channel(auc["channel_id"])
                msg = await channel.fetch_message(int(self.message_id))
                embed = msg.embeds[0]
                # Rebuild Description with new Name
                embed.description = f"**{auc['item_name']}**\n\n" \
                                    f"👑 **ผู้เปิดประมูล:** <@{auc['owner_id']}>\n" \
                                    f"💰 **ราคาเริ่มต้น:** {auc['start_price']:,} บาท\n" \
                                    f"➕ **บิดขั้นต่ำ:** {auc['bid_step']:,} บาท\n" \
                                    f"🛑 **ซื้อทันที (Auto Buy):** {auc['close_price']:,} บาท" if auc['close_price'] else ""
                
                for i, field in enumerate(embed.fields):
                    if "สิทธิ์" in field.name: embed.set_field_at(i, name="📜 สิทธิ์", value=auc["rights"], inline=True)
                    if "เพิ่มเติม" in field.name: embed.set_field_at(i, name="ℹ️ เพิ่มเติม", value=auc["extra_info"], inline=True)
                
                await msg.edit(embed=embed)
                await interaction.followup.send("✅ **แก้ไขข้อมูลเรียบร้อย!**", ephemeral=True)
            except: await interaction.followup.send("⚠️ บันทึกแล้ว แต่หาข้อความเดิมไม่เจอ", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AuctionSystem(bot))
