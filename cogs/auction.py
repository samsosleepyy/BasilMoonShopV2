import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import re
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, get_files_from_urls

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
            match = re.match(r'^บิด\s*(\d+)', content)
            if match:
                amount = int(match.group(1))
                if amount < auction_data['current_price'] + auction_data['bid_step']: return
                
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
                        g_data = load_data()
                        new_name = f"ประมูลครั้งที่-{g_data['auction_count']}-ราคา-{amount}"
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
        
        g_data = load_data()
        winner_id, seller_id = auction_data['winner_id'], auction_data['seller_id']
        
        if winner_id is None:
            if auction_data['log_id']:
                log = self.bot.get_channel(auction_data['log_id'])
                embed = discord.Embed(description=MESSAGES["auc_end_no_bid"].format(count=g_data['auction_count'], seller=f"<@{seller_id}>"), color=discord.Color.yellow())
                await log.send(embed=embed)
            await channel.delete()
            return

        winner_mention = f"<@{winner_id}>"
        winner_msg = await channel.send(MESSAGES["auc_end_winner"].format(winner=winner_mention, count=g_data['auction_count'], price=auction_data['current_price'], time=g_data['lockdown_time']))
        
        await asyncio.sleep(g_data['lockdown_time'])

        overwrites = {
            channel.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            channel.guild.get_member(seller_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            channel.guild.get_member(winner_id): discord.PermissionOverwrite(read_messages=True, send_messages=True),
            channel.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        for admin_id in g_data["admins"]:
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
        view = TransactionView(seller_id, winner_id, auction_data, self.bot)
        await channel.send(content=winner_mention, embed=embed, view=view)

# --- Auction Views ---
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
    start_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_start"], placeholder=MESSAGES["auc_ph_start"], required=True)
    bid_step = discord.ui.TextInput(label=MESSAGES["auc_lbl_step"], placeholder=MESSAGES["auc_ph_step"], required=True)
    close_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_close"], placeholder=MESSAGES["auc_ph_close"], required=True)
    item_name = discord.ui.TextInput(label=MESSAGES["auc_lbl_item"], required=True)
    def __init__(self, category, approval_channel, role_ping, log_channel, cog):
        super().__init__()
        self.category, self.approval_channel, self.role_ping, self.log_channel = category, approval_channel, role_ping, log_channel
        self.cog = cog
    async def on_submit(self, interaction: discord.Interaction):
        try:
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
    download_link = discord.ui.TextInput(label=MESSAGES["auc_lbl_link"], placeholder=MESSAGES["auc_ph_link"], required=True)
    rights = discord.ui.TextInput(label=MESSAGES["auc_lbl_rights"], placeholder=MESSAGES["auc_ph_rights"], required=True)
    extra_info = discord.ui.TextInput(label=MESSAGES["auc_lbl_extra"], placeholder=MESSAGES["auc_ph_extra"], required=False)
    end_time_str = discord.ui.TextInput(label=MESSAGES["auc_lbl_time"], placeholder=MESSAGES["auc_ph_time"], required=True)
    def __init__(self, auction_data, cog):
        super().__init__()
        self.auction_data, self.cog = auction_data, cog
    async def on_submit(self, interaction: discord.Interaction):
        try:
            h, m = map(int, self.end_time_str.value.split(':'))
            total_minutes = (h * 60) + m
            if total_minutes <= 0: raise ValueError
            self.auction_data.update({"download_link": self.download_link.value, "rights": self.rights.value,"extra_info": self.extra_info.value if self.extra_info.value else "-","duration_minutes": total_minutes, "seller_id": interaction.user.id})
            
            data = load_data()
            overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),interaction.user: discord.PermissionOverwrite(read_messages=True),interaction.guild.me: discord.PermissionOverwrite(read_messages=True)}
            for admin_id in data["admins"]:
                member = interaction.guild.get_member(admin_id)
                if member: overwrites[member] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await interaction.guild.create_text_channel(f"✧꒰ส่งรูปสินค้า📦-{interaction.user.name}꒱", overwrites=overwrites)
            await interaction.response.send_message(MESSAGES["auc_created_channel"].format(channel=channel.mention), ephemeral=True)
            self.cog.bot.loop.create_task(self.wait_for_images(channel, interaction.user, self.auction_data))
        except: await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)

    async def wait_for_images(self, channel, user, auction_data):
        def check(m): return m.author.id == user.id and m.channel.id == channel.id and m.attachments
        try:
            await channel.send(MESSAGES["auc_wait_img_1"].format(user=user.mention), delete_after=300)
            msg1 = await self.cog.bot.wait_for('message', check=check, timeout=300)
            auction_data["img_product_urls"] = [att.url for att in msg1.attachments]
            await channel.send(MESSAGES["auc_wait_img_2"])
            msg2 = await self.cog.bot.wait_for('message', check=check, timeout=300)
            auction_data["img_qr_url"] = msg2.attachments[0].url
            await channel.send(MESSAGES["auc_img_received"])
            
            approval_channel = self.cog.bot.get_channel(auction_data["approval_id"])
            if approval_channel:
                base_embed = discord.Embed(title=MESSAGES["auc_embed_request_title"], color=discord.Color.gold())
                base_embed.add_field(name="ผู้ขาย", value=f"<@{auction_data['seller_id']}>", inline=False)
                base_embed.add_field(name="สินค้า", value=auction_data['item_name'], inline=True)
                base_embed.add_field(name="ราคาเริ่ม", value=f"{auction_data['start_price']}", inline=True)
                base_embed.add_field(name="บิดครั้งละ", value=f"{auction_data['bid_step']}", inline=True)
                base_embed.add_field(name="ราคาปิด", value=f"{auction_data['close_price']}", inline=True)
                base_embed.add_field(name="สิทธิ์", value=f"{auction_data['rights']}", inline=True)
                base_embed.add_field(name="เวลาประมูล", value=f"{auction_data['duration_minutes']} นาที", inline=True)
                base_embed.add_field(name="ลิ้งค์สินค้า", value=f"{auction_data['download_link']}", inline=False)
                base_embed.add_field(name="เพิ่มเติม", value=f"{auction_data['extra_info']}", inline=False)
                base_embed.set_thumbnail(url=auction_data['img_qr_url'])
                files_to_send = await get_files_from_urls(auction_data["img_product_urls"])
                view = ApprovalView(auction_data, channel, self.cog)
                await approval_channel.send(embed=base_embed, files=files_to_send, view=view)
        except asyncio.TimeoutError: await channel.delete()

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
        data["auction_count"] += 1
        save_data(data)
        
        auction_channel = await interaction.guild.create_text_channel(f"ประมูลครั้งที่-{data['auction_count']}-ราคา-{self.auction_data['start_price']}", category=category)
        ping_role = interaction.guild.get_role(self.auction_data["role_ping_id"])
        if ping_role: await auction_channel.send(ping_role.mention, delete_after=5)
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=self.auction_data["duration_minutes"])
        timestamp = int(end_time.timestamp())
        main_embed = discord.Embed(description=MESSAGES["auc_embed_title"], color=discord.Color.purple())
        main_embed.add_field(name="ᯓ★ โดย", value=f"<@{self.auction_data['seller_id']}>", inline=False)
        main_embed.add_field(name="ᯓ★ ราคาเริ่มต้น", value=f"{self.auction_data['start_price']}", inline=True)
        main_embed.add_field(name="ᯓ★ บิดครั้งละ", value=f"{self.auction_data['bid_step']}", inline=True)
        main_embed.add_field(name="ᯓ★ ราคาปิดประมูล", value=f"{self.auction_data['close_price']}", inline=True)
        main_embed.add_field(name="ᯓ★ สิ่งที่ได้", value=f"{self.auction_data['item_name']}", inline=True)
        main_embed.add_field(name="ᯓ★ สิทธิ์", value=f"{self.auction_data['rights']}", inline=True)
        main_embed.add_field(name="ᯓ★ เพิ่มเติม", value=f"{self.auction_data['extra_info']}", inline=False)
        main_embed.add_field(name="-ˋˏ✄┈┈┈┈", value=f"**เวลาปิดประมูล : <t:{timestamp}:R>**", inline=False)
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
            embed.add_field(name="👤 ผู้ขาย", value=f"<@{self.auction_data['seller_id']}>", inline=True)
            embed.add_field(name="👮 ปฏิเสธโดย", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 เหตุผล", value=self.reason.value, inline=False)
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
    def __init__(self, seller_id, winner_id, auction_data, bot):
        super().__init__(timeout=None)
        self.seller_id, self.winner_id, self.auction_data, self.bot = seller_id, winner_id, auction_data, bot
    @discord.ui.button(label=MESSAGES["auc_btn_confirm"], style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        view = ConfirmFinalView(self.auction_data, interaction.channel, self.bot)
        await interaction.response.send_message(MESSAGES["auc_check_money"], view=view, ephemeral=True)
    @discord.ui.button(label=MESSAGES["auc_btn_cancel"], style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.seller_id and not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_modal(CancelReasonModal(self.auction_data, interaction.channel, self.bot))

class ConfirmFinalView(discord.ui.View):
    def __init__(self, auction_data, channel, bot):
        super().__init__(timeout=None)
        self.auction_data, self.channel, self.bot = auction_data, channel, bot
    @discord.ui.button(label=MESSAGES["auc_btn_double_confirm"], style=discord.ButtonStyle.green)
    async def double_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            winner = interaction.guild.get_member(self.auction_data['winner_id']) or await self.bot.fetch_user(self.auction_data['winner_id'])
            await winner.send(MESSAGES["auc_dm_content"].format(link=self.auction_data['download_link']))
            dm_msg = MESSAGES["auc_dm_success"]
        except: dm_msg = MESSAGES["auc_dm_fail"].format(user=f"<@{self.auction_data['winner_id']}>")
        await interaction.followup.send(f"{dm_msg}\nลบช่องใน 1 นาที...", ephemeral=True)
        if self.auction_data['log_id']:
            log = self.bot.get_channel(self.auction_data['log_id'])
            data = load_data()
            embed = discord.Embed(description=MESSAGES["auc_success_log"].format(count=data['auction_count'], seller=f"<@{self.auction_data['seller_id']}>", winner=f"<@{self.auction_data['winner_id']}>", price=self.auction_data['current_price']), color=discord.Color.green())
            files_to_send = await get_files_from_urls(self.auction_data["img_product_urls"])
            await log.send(embed=embed, files=files_to_send)
        await asyncio.sleep(60)
        if self.channel: await self.channel.delete()

class CancelReasonModal(discord.ui.Modal, title=MESSAGES["auc_modal_cancel_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["auc_lbl_deny_reason"], required=True)
    def __init__(self, auction_data, channel, bot):
        super().__init__()
        self.auction_data, self.channel, self.bot = auction_data, channel, bot
    async def on_submit(self, interaction: discord.Interaction):
        if self.auction_data['log_id']:
            log = self.bot.get_channel(self.auction_data['log_id'])
            data = load_data()
            embed = discord.Embed(description=MESSAGES["auc_cancel_log"].format(count=data['auction_count'], seller=f"<@{self.auction_data['seller_id']}>", user=interaction.user.mention, reason=self.reason.value), color=discord.Color.red())
            await log.send(embed=embed)
        await interaction.response.send_message(MESSAGES["auc_msg_cancel_success"], ephemeral=True)
        await asyncio.sleep(5)
        if self.channel: await self.channel.delete()

async def setup(bot):
    await bot.add_cog(AuctionSystem(bot))
