import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio
import aiohttp
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, init_guild_data

class AuctionSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self.restore_auction_views())

    async def restore_auction_views(self):
        await self.bot.wait_until_ready()
        print("🔄 Restoring Auction Views...")
        data = load_data()
        count = 0
        if "active_auctions" in data:
            for msg_id, info in data["active_auctions"].items():
                try:
                    self.bot.add_view(AuctionView(msg_id), message_id=int(msg_id))
                    count += 1
                except Exception as e:
                    print(f"Error restoring auction {msg_id}: {e}")
        print(f"✅ Restored {count} active auctions.")

    @app_commands.command(name="auction", description=MESSAGES["desc_auction"])
    async def auction(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.send_modal(AuctionSetupModal())

# =========================================
# 1. SETUP MODALS
# =========================================
class AuctionSetupModal(discord.ui.Modal, title=MESSAGES["auc_step1_title"]):
    item_name = discord.ui.TextInput(label=MESSAGES["auc_lbl_item"], placeholder="ชื่อสินค้า", required=True)
    start_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_start"], placeholder=MESSAGES["auc_ph_start"], required=True)
    step_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_step"], placeholder=MESSAGES["auc_ph_step"], required=True)
    autobuy_price = discord.ui.TextInput(label=MESSAGES["auc_lbl_close"], placeholder=MESSAGES["auc_ph_close"], required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start = int(self.start_price.value)
            step = int(self.step_price.value)
            autobuy = int(self.autobuy_price.value) if self.autobuy_price.value else None
        except ValueError:
            return await interaction.response.send_message(MESSAGES["auc_err_num"], ephemeral=True)

        temp_data = {
            "name": self.item_name.value,
            "start": start,
            "step": step,
            "autobuy": autobuy
        }
        
        view = AuctionStep2View(temp_data)
        await interaction.response.send_message(MESSAGES["auc_prompt_step2"], view=view, ephemeral=True)

class AuctionStep2View(discord.ui.View):
    def __init__(self, temp_data):
        super().__init__(timeout=300)
        self.temp_data = temp_data

    @discord.ui.button(label=MESSAGES["auc_btn_step2"], style=discord.ButtonStyle.primary)
    async def go_step2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionSetupModal2(self.temp_data))

class AuctionSetupModal2(discord.ui.Modal, title=MESSAGES["auc_step2_title"]):
    end_time = discord.ui.TextInput(label=MESSAGES["auc_lbl_time"], placeholder=MESSAGES["auc_ph_time"], required=True)
    link = discord.ui.TextInput(label=MESSAGES["auc_lbl_link"], placeholder=MESSAGES["auc_ph_link"], required=True)
    rights = discord.ui.TextInput(label=MESSAGES["auc_lbl_rights"], placeholder=MESSAGES["auc_ph_rights"], required=True)
    # [FIXED] บังคับกรอก + Placeholder ตามที่ขอ
    extra = discord.ui.TextInput(label=MESSAGES["auc_lbl_extra"], style=discord.TextStyle.paragraph, required=True, placeholder="อธิบายสินค้าหรือกฎ")

    def __init__(self, temp_data):
        super().__init__()
        self.temp_data = temp_data

    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.end_time.value
        try:
            if ":" in time_str:
                h, m = map(int, time_str.split(":"))
                seconds = (h * 3600) + (m * 60)
            else:
                return await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)
        except:
            return await interaction.response.send_message(MESSAGES["auc_err_time"], ephemeral=True)

        self.temp_data.update({
            "end_seconds": seconds,
            "link": self.link.value,
            "rights": self.rights.value,
            "extra": self.extra.value 
        })

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        
        channel = await interaction.guild.create_text_channel(f"setup-auction-{interaction.user.name}", overwrites=overwrites)
        
        await channel.send(MESSAGES["auc_wait_img_1"].format(user=interaction.user.mention))
        await interaction.response.send_message(MESSAGES["auc_created_channel"].format(channel=channel.mention), ephemeral=True)

        def check(m): return m.author.id == interaction.user.id and m.channel.id == channel.id and m.attachments
        
        try:
            msg1 = await interaction.client.wait_for('message', check=check, timeout=300)
            img_item = msg1.attachments[0].url
            
            await channel.send(MESSAGES["auc_wait_img_2"])
            msg2 = await interaction.client.wait_for('message', check=check, timeout=300)
            img_pay = msg2.attachments[0].url
            
            await channel.send(MESSAGES["auc_img_received"])
            
            embed = discord.Embed(title=MESSAGES["auc_embed_request_title"], color=discord.Color.gold())
            embed.set_thumbnail(url=img_item)
            embed.add_field(name="สินค้า", value=self.temp_data["name"])
            embed.add_field(name="ราคาเริ่ม", value=f"{self.temp_data['start']:,}")
            
            full_data = self.temp_data
            full_data["img_item"] = img_item
            full_data["img_pay"] = img_pay
            full_data["owner_id"] = interaction.user.id
            
            view = AuctionAdminApproveView(full_data)
            await channel.send("ตรวจสอบความถูกต้อง แล้วกดอนุมัติเพื่อเริ่มประมูล", embed=embed, view=view)

        except asyncio.TimeoutError:
            await channel.delete()

class AuctionAdminApproveView(discord.ui.View):
    def __init__(self, auction_data):
        super().__init__(timeout=None)
        self.auction_data = auction_data

    @discord.ui.button(label=MESSAGES["auc_btn_approve"], style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        data = self.auction_data
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=data["end_seconds"])
        timestamp = int(end_time.timestamp())
        
        embed = discord.Embed(title=MESSAGES["auc_embed_title"], color=discord.Color.purple())
        embed.set_image(url=data["img_item"])
        embed.description = f"**{data['name']}**\n\n" \
                            f"👑 <@{data['owner_id']}>\n" \
                            f"💰 {data['start']:,} บาท\n" \
                            f"➕ {data['step']:,} บาท\n" \
                            f"🛑 {data['autobuy']:,} บาท" if data['autobuy'] else ""
        
        embed.add_field(name="📜 สิทธิ์", value=data['rights'], inline=True)
        embed.add_field(name="ℹ️ เพิ่มเติม", value=data['extra'], inline=True)
        embed.add_field(name="⏳ ปิดประมูล", value=f"<t:{timestamp}:R>", inline=False)
        embed.set_footer(text=f"ปิดเวลา: {end_time.strftime('%H:%M')}")

        await interaction.followup.send("เลือกห้องที่จะลงประมูล:", view=AuctionChannelSelectView(data, embed))

class AuctionChannelSelectView(discord.ui.View):
    def __init__(self, auction_data, embed):
        super().__init__(timeout=60)
        self.auction_data = auction_data
        self.embed = embed

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text])
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        await interaction.response.defer()
        
        msg = await channel.send(embed=self.embed, view=AuctionView(None))
        
        saved_data = load_data()
        init_guild_data(saved_data, interaction.guild_id)
        saved_data["guilds"][str(interaction.guild_id)]["auction_count"] += 1
        count = saved_data["guilds"][str(interaction.guild_id)]["auction_count"]
        
        auction_info = self.auction_data.copy()
        auction_info["message_id"] = msg.id
        auction_info["channel_id"] = channel.id
        auction_info["count"] = count
        auction_info["current_bid"] = 0
        auction_info["winner_id"] = None
        auction_info["history"] = []
        auction_info["end_timestamp"] = int((datetime.datetime.now() + datetime.timedelta(seconds=self.auction_data["end_seconds"])).timestamp())
        
        saved_data["active_auctions"][str(msg.id)] = auction_info
        save_data(saved_data)
        
        await msg.edit(view=AuctionView(str(msg.id)))
        
        await interaction.followup.send(f"✅ เริ่มประมูลแล้วที่ {channel.mention}")
        try: await interaction.channel.delete() 
        except: pass

# =========================================
# 3. AUCTION INTERFACE (BID / EDIT / REPORT)
# =========================================
class AuctionView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="ลงราคา (Bid)", style=discord.ButtonStyle.green, emoji="💸", custom_id="auc_bid")
    async def bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        msg_id = str(interaction.message.id)
        if msg_id not in data["active_auctions"]:
            return await interaction.response.send_message(MESSAGES["auc_no_data"], ephemeral=True)
        
        auc = data["active_auctions"][msg_id]
        if datetime.datetime.now().timestamp() > auc["end_timestamp"]:
            return await interaction.response.send_message("❌ หมดเวลาประมูลแล้ว", ephemeral=True)

        await interaction.response.send_modal(BidModal(msg_id, auc))

    @discord.ui.button(label="แก้ไข (Admin)", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="auc_edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        msg_id = str(interaction.message.id)
        view = AuctionEditView(msg_id)
        await interaction.response.send_message("⚙️ **เมนูแก้ไขการประมูล**", view=view, ephemeral=True)

    @discord.ui.button(label="ปิดประมูล", style=discord.ButtonStyle.danger, emoji="🛑", custom_id="auc_close")
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.response.defer()
        # เรียก Logic จบประมูลเต็มรูปแบบ
        await self.end_auction(interaction.message.id, interaction.guild)

    # [NEW] ปุ่มรายงาน (Report)
    @discord.ui.button(label="รายงาน", style=discord.ButtonStyle.red, emoji="🚨", custom_id="auc_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        msg_id = str(interaction.message.id)
        if msg_id in data["active_auctions"]:
            auc = data["active_auctions"][msg_id]
            # เจ้าของห้ามกดรายงานตัวเอง
            if interaction.user.id == auc["owner_id"]:
                return await interaction.response.send_message("❌ คุณไม่สามารถรายงานการประมูลของตัวเองได้", ephemeral=True)
        
        await interaction.response.send_modal(AuctionReportModal(msg_id))

    # [FIXED] คืนค่า Logic จบประมูลแบบเต็ม (Full Logic)
    async def end_auction(self, message_id, guild):
        data = load_data()
        msg_id = str(message_id)
        if msg_id not in data["active_auctions"]: return
        
        auc = data["active_auctions"][msg_id]
        channel = guild.get_channel(auc["channel_id"])
        
        try:
            msg = await channel.fetch_message(int(msg_id))
        except:
            # ถ้าหาข้อความไม่เจอ (อาจโดนลบ) ให้ลบข้อมูลทิ้งเลย
            del data["active_auctions"][msg_id]
            save_data(data)
            return

        # ปิดปุ่ม
        await msg.edit(view=None)

        if not auc["winner_id"]:
            # ไม่มีคนบิด
            await channel.send(MESSAGES["auc_end_no_bid"].format(count=auc["count"], seller=f"<@{auc['owner_id']}>"))
        else:
            # มีผู้ชนะ
            winner = guild.get_member(auc["winner_id"])
            price = auc["current_bid"]
            
            # ประกาศผู้ชนะ
            await channel.send(MESSAGES["auc_end_winner"].format(count=auc["count"], winner=winner.mention, price=f"{price:,}", time=60))
            
            # สร้างห้องปิดดีล (Deal Channel)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                winner: discord.PermissionOverwrite(read_messages=True),
                guild.get_member(auc['owner_id']): discord.PermissionOverwrite(read_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            deal_chan_name = f"deal-auc-{auc['count']}"
            deal_chan = await guild.create_text_channel(deal_chan_name, overwrites=overwrites)
            
            # ส่งข้อมูลการชำระเงิน
            embed = discord.Embed(title="💸 ชำระเงิน", description=f"ยอดปิดประมูล: **{price:,} บาท**\nกรุณาโอนเงินผ่านช่องทางด้านล่าง", color=discord.Color.green())
            embed.set_image(url=auc["img_pay"])
            
            await deal_chan.send(content=f"{winner.mention} <@{auc['owner_id']}>", embed=embed)
            await deal_chan.send(MESSAGES["auc_lock_msg"].format(winner=winner.mention))

            # ส่ง DM หาผู้ชนะ (ถ้าเปิด DM)
            try:
                dm_embed = discord.Embed(title="🎉 คุณชนะการประมูล!", color=discord.Color.gold())
                dm_embed.add_field(name="สินค้า", value=auc["name"])
                dm_embed.add_field(name="ราคาจบ", value=f"{price:,} บาท")
                dm_embed.add_field(name="ลิ้งค์ดาวน์โหลด/ข้อมูล", value=f"||{auc['link']}||", inline=False)
                dm_embed.set_footer(text="ขอบคุณที่ใช้บริการครับ")
                await winner.send(embed=dm_embed)
            except:
                await deal_chan.send(f"⚠️ ไม่สามารถส่ง DM หา {winner.mention} ได้ (โปรดรับสินค้าในห้องนี้แทน)")
                await deal_chan.send(f"📦 **ข้อมูลสินค้า:** ||{auc['link']}||")

        # ลบออกจาก Active
        del data["active_auctions"][msg_id]
        save_data(data)

# [NEW] Modal รายงานการประมูล
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
        
        # Ping Logic (Admin + Support)
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

        # Send Log to Current Channel (for context) & Log Channel (if config exists)
        await interaction.channel.send(content=f"{ping_msg} **มีการรายงานเข้ามา!**", embed=embed)

# =========================================
# 4. EDIT SYSTEM
# =========================================
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
        await self.process_image_edit(interaction, "img_item")

    @discord.ui.button(label="แก้ไขรูปชำระเงิน", style=discord.ButtonStyle.primary, emoji="💳")
    async def edit_payment_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_image_edit(interaction, "img_pay")

    @discord.ui.button(label="ย้อนกลับ", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AuctionEditView(self.message_id)
        await interaction.response.edit_message(content="⚙️ **เมนูแก้ไขการประมูล**", view=view)

    async def process_image_edit(self, interaction: discord.Interaction, key):
        # [CRITICAL] Defer immediately to prevent interaction fail
        await interaction.response.defer(ephemeral=True) 
        
        await interaction.followup.send("📤 **กรุณาส่งรูปภาพใหม่มาในช่องนี้** (ภายใน 60 วินาที...)", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.attachments

        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=60.0)
            new_url = msg.attachments[0].url
            
            data = load_data()
            if self.message_id in data["active_auctions"]:
                data["active_auctions"][self.message_id][key] = new_url
                save_data(data)
                
                auc = data["active_auctions"][self.message_id]
                try:
                    channel = interaction.guild.get_channel(auc["channel_id"])
                    auction_msg = await channel.fetch_message(int(self.message_id))
                    
                    # Update embed if it's item image
                    if key == "img_item":
                        embed = auction_msg.embeds[0]
                        embed.set_image(url=new_url)
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
    # [FIXED] บังคับกรอก + Placeholder
    extra = discord.ui.TextInput(label="เพิ่มเติม", required=True, style=discord.TextStyle.paragraph, placeholder="อธิบายสินค้าหรือกฎ")

    def __init__(self, message_id, current_data):
        super().__init__()
        self.message_id = message_id
        self.name.default = current_data.get("name", "")
        self.rights.default = current_data.get("rights", "")
        self.extra.default = current_data.get("extra", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        data = load_data()
        if self.message_id in data["active_auctions"]:
            auc = data["active_auctions"][self.message_id]
            auc["name"] = self.name.value
            auc["rights"] = self.rights.value
            auc["extra"] = self.extra.value
            save_data(data)
            
            try:
                channel = interaction.guild.get_channel(auc["channel_id"])
                msg = await channel.fetch_message(int(self.message_id))
                embed = msg.embeds[0]
                
                embed.description = f"**{auc['name']}**\n\n" \
                                    f"👑 **ผู้เปิดประมูล:** <@{auc['owner_id']}>\n" \
                                    f"💰 **ราคาเริ่มต้น:** {auc['start']:,} บาท\n" \
                                    f"➕ **บิดขั้นต่ำ:** {auc['step']:,} บาท\n" \
                                    f"🛑 **ซื้อทันที (Auto Buy):** {auc['autobuy']:,} บาท" if auc['autobuy'] else ""
                
                for i, field in enumerate(embed.fields):
                    if "สิทธิ์" in field.name:
                        embed.set_field_at(i, name="📜 สิทธิ์", value=auc["rights"], inline=True)
                    if "เพิ่มเติม" in field.name:
                        embed.set_field_at(i, name="ℹ️ เพิ่มเติม", value=auc["extra"], inline=True)
                
                await msg.edit(embed=embed)
                await interaction.followup.send("✅ **แก้ไขข้อมูลเรียบร้อย!**", ephemeral=True)
            except:
                await interaction.followup.send("⚠️ บันทึกแล้ว แต่หาข้อความเดิมไม่เจอ", ephemeral=True)

class BidModal(discord.ui.Modal, title="เสนอราคา (Bid)"):
    amount = discord.ui.TextInput(label="จำนวนเงิน", placeholder="ใส่จำนวนเงินที่ต้องการบิด...", required=True)

    def __init__(self, message_id, auc_data):
        super().__init__()
        self.message_id = message_id
        self.auc_data = auc_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bid_amount = int(self.amount.value)
        except:
            return await interaction.response.send_message("❌ ใส่ตัวเลขเท่านั้น", ephemeral=True)

        data = load_data()
        if self.message_id not in data["active_auctions"]:
            return await interaction.response.send_message("❌ ประมูลจบไปแล้ว", ephemeral=True)
        
        auc = data["active_auctions"][self.message_id]
        
        min_next_bid = auc["current_bid"] + auc["step"] if auc["current_bid"] > 0 else auc["start"]
        if bid_amount < min_next_bid:
            return await interaction.response.send_message(f"❌ ต้องบิดขั้นต่ำ **{min_next_bid:,}** บาท", ephemeral=True)

        auc["current_bid"] = bid_amount
        auc["winner_id"] = interaction.user.id
        auc["history"].append({"user": interaction.user.id, "amount": bid_amount, "time": str(datetime.datetime.now())})
        
        is_autobuy = False
        if auc["autobuy"] and bid_amount >= auc["autobuy"]:
            is_autobuy = True
        
        save_data(data)
        
        await interaction.response.send_message(f"✅ **บิดสำเร็จ!** ราคาปัจจุบัน: **{bid_amount:,}** บาท", ephemeral=True)
        
        try:
            channel = interaction.guild.get_channel(auc["channel_id"])
            msg = await channel.fetch_message(int(self.message_id))
            await msg.channel.send(f"💸 **{interaction.user.mention}** เสนอราคา **{bid_amount:,}** บาท!")
            
            # [CRITICAL] Trigger End Auction if Auto-buy reached
            if is_autobuy:
                cog = interaction.client.get_cog("AuctionSystem")
                if cog: await cog.end_auction(self.message_id, interaction.guild)
                
        except Exception as e:
            print(f"Bid Error: {e}")

async def setup(bot):
    await bot.add_cog(AuctionSystem(bot))
