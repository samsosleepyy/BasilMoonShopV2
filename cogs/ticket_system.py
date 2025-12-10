import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission

# Cache สำหรับ Setup
setup_cache = {}

class TicketSystemV2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self.restore_views())

    async def restore_views(self):
        await self.bot.wait_until_ready()
        print("🔄 Restoring Ticket V2 Views...")
        data = load_data()
        
        # 1. กู้คืน Main Launcher & Console
        if "ticket_v2_configs" in data:
            for msg_id, config in data["ticket_v2_configs"].items():
                try:
                    # Restore Launcher (ส่ง config ทั้งก้อนไป)
                    view = TicketLauncherView(msg_id, config)
                    self.bot.add_view(view, message_id=int(msg_id))
                    
                    # Restore Console
                    if "console_msg_id" in config:
                        console_view = TicketConsoleView(msg_id)
                        self.bot.add_view(console_view, message_id=int(config["console_msg_id"]))
                except Exception as e:
                    print(f"Error restoring ticket v2 config {msg_id}: {e}")

        # 2. กู้คืน Active Tickets (ปุ่มในห้อง)
        if "active_tickets_v2" in data:
            for chan_id, info in data["active_tickets_v2"].items():
                try:
                    view = TicketInsideView(info["main_msg_id"], info["type_idx"])
                    self.bot.add_view(view)
                except: pass
        
        print("✅ Ticket V2 Restored.")

    @app_commands.command(name="ticket", description="สร้างระบบ Ticket แบบมี Console และระบบเร่งงาน")
    async def ticket_v2(self, interaction: discord.Interaction, channel: discord.TextChannel, console_channel: discord.TextChannel, log_channel: discord.TextChannel = None):
        if not is_admin_or_has_permission(interaction): 
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        setup_cache[interaction.user.id] = {
            "target_channel": channel.id,
            "console_channel": console_channel.id,
            "log_channel": log_channel.id if log_channel else None,
            "embed_data": {"title": "Ticket Support", "desc": "กดปุ่มด้านล่างเพื่อเปิดตั๋ว", "image": None},
            "buttons": {},
            "launcher_style": "buttons" # ค่าเริ่มต้น
        }
        
        view = SetupStep1View(interaction.user.id)
        await interaction.response.send_message("🛠️ **Ticket Setup (Step 1/2)**\nตั้งค่าหน้าตา Embed และปุ่มกด", view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if not message.guild: return
        
        data = load_data()
        chan_id = str(message.channel.id)
        
        if "active_tickets_v2" in data and chan_id in data["active_tickets_v2"]:
            ticket_info = data["active_tickets_v2"][chan_id]
            if ticket_info.get("is_rushing") and message.attachments:
                att = message.attachments[0]
                if att.content_type and att.content_type.startswith("image/"):
                    view = RushConfirmView(chan_id)
                    await message.reply("🧾 **ได้รับสลิปแล้ว**\nแอดมินตรวจสอบและกดปุ่มด้านล่างเพื่อยืนยันการเร่งงาน", view=view)

async def setup(bot):
    await bot.add_cog(TicketSystemV2(bot))

# ====================================================
# 🛠️ SETUP VIEWS
# ====================================================

class SetupStep1View(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.add_item(SetMainEmbedButton(user_id))
        for i in range(20):
            row = (i // 5) + 1
            self.add_item(ConfigTypeButton(user_id, i, row))
            
    @discord.ui.button(label="ถัดไป ➡️", style=discord.ButtonStyle.green, row=0)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        cache = setup_cache.get(self.user_id)
        if not cache or not cache["buttons"]:
            return await interaction.response.send_message("❌ กรุณาตั้งค่าปุ่มอย่างน้อย 1 ปุ่ม", ephemeral=True)
        
        view = SetupStep2View(self.user_id)
        await interaction.response.edit_message(content="🛠️ **Ticket Setup (Step 2/2)**\nเลือกรูปแบบเมนู และตั้งค่าราคาเร่งงาน", view=view)

class SetMainEmbedButton(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="ตั้งค่า Embed หลัก", style=discord.ButtonStyle.primary, row=0)
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(MainEmbedModal(self.user_id))

class ConfigTypeButton(discord.ui.Button):
    def __init__(self, user_id, index, row):
        super().__init__(label=str(index+1), style=discord.ButtonStyle.secondary, row=row)
        self.user_id = user_id
        self.index = index
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(TypeConfigModal(self.user_id, self.index, self.view))

class MainEmbedModal(discord.ui.Modal, title="ตั้งค่า Embed หลัก"):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        data = setup_cache.get(user_id, {}).get("embed_data", {})
        self.title_inp = discord.ui.TextInput(label="หัวข้อ (Title)", default=data.get("title", ""), required=True)
        self.desc_inp = discord.ui.TextInput(label="เนื้อหา (Description)", style=discord.TextStyle.paragraph, default=data.get("desc", ""), required=True)
        self.img_inp = discord.ui.TextInput(label="ลิ้งค์รูปภาพ (Optional)", default=data.get("image") or "", required=False)
        self.add_item(self.title_inp)
        self.add_item(self.desc_inp)
        self.add_item(self.img_inp)
        
    async def on_submit(self, interaction: discord.Interaction):
        setup_cache[self.user_id]["embed_data"] = {
            "title": self.title_inp.value,
            "desc": self.desc_inp.value,
            "image": self.img_inp.value
        }
        await interaction.response.send_message("✅ บันทึก Embed หลักแล้ว", ephemeral=True)

class TypeConfigModal(discord.ui.Modal, title="ตั้งค่าปุ่ม"):
    def __init__(self, user_id, index, parent_view):
        super().__init__()
        self.user_id = user_id
        self.index = index
        self.parent_view = parent_view
        btn_data = setup_cache.get(user_id, {}).get("buttons", {}).get(index, {})
        self.label = discord.ui.TextInput(label="ชื่อปุ่ม (Title)", default=btn_data.get("label", ""), required=True)
        self.cat_id = discord.ui.TextInput(label="ไอดีหมวดหมู่ (Category ID)", default=str(btn_data.get("category_id", "")), required=True)
        self.msg_content = discord.ui.TextInput(label="ข้อความในห้อง (Message)", style=discord.TextStyle.paragraph, default=btn_data.get("message", ""), required=True)
        self.img_url = discord.ui.TextInput(label="ลิ้งค์รูปในห้อง (Optional)", default=btn_data.get("image") or "", required=False)
        self.add_item(self.label)
        self.add_item(self.cat_id)
        self.add_item(self.msg_content)
        self.add_item(self.img_url)

    async def on_submit(self, interaction: discord.Interaction):
        try: int(self.cat_id.value)
        except: return await interaction.response.send_message("❌ ID หมวดหมู่ต้องเป็นตัวเลข", ephemeral=True)
        cache = setup_cache[self.user_id]
        existing = cache["buttons"].get(self.index, {})
        existing.update({
            "label": self.label.value,
            "category_id": int(self.cat_id.value),
            "message": self.msg_content.value,
            "image": self.img_url.value,
            "status": True
        })
        cache["buttons"][self.index] = existing
        for child in self.parent_view.children:
            if isinstance(child, ConfigTypeButton) and child.index == self.index:
                child.style = discord.ButtonStyle.success
                break
        await interaction.response.edit_message(view=self.parent_view)

class SetupStep2View(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        cache = setup_cache.get(user_id)
        self.add_item(StyleSelectMenu(user_id))
        for idx, info in cache["buttons"].items():
            self.add_item(ConfigPriceButton(user_id, idx, info["label"]))

    @discord.ui.button(label="เสร็จสิ้น ✅", style=discord.ButtonStyle.success, row=4)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.defer()
        
        cache = setup_cache[self.user_id]
        main_channel = interaction.guild.get_channel(cache["target_channel"])
        embed_data = cache["embed_data"]
        
        embed = discord.Embed(title=embed_data["title"], description=embed_data["desc"], color=discord.Color.green())
        if embed_data["image"]: embed.set_image(url=embed_data["image"])
        
        # สร้าง View แบบ Dummy ไปก่อนเพื่อเอา ID
        dummy_view = TicketLauncherView(None) 
        msg = await main_channel.send(embed=embed, view=dummy_view) 
        
        # สร้าง config จริง
        final_config = {
            "channel_id": cache["target_channel"],
            "console_channel_id": cache["console_channel"],
            "console_msg_id": None, # รออัปเดต
            "log_channel_id": cache["log_channel"],
            "embed_data": cache["embed_data"],
            "buttons": cache["buttons"],
            "launcher_style": cache.get("launcher_style", "buttons")
        }
        
        # Update View ของจริงตาม Style ที่เลือก
        new_view = TicketLauncherView(str(msg.id), final_config)
        await msg.edit(view=new_view)
        
        # ส่ง Console
        console_channel = interaction.guild.get_channel(cache["console_channel"])
        con_embed = discord.Embed(title="🎛️ Ticket Console", description="ควบคุมสถานะการเปิด/ปิดตั๋ว", color=discord.Color.dark_grey())
        con_view = TicketConsoleView(str(msg.id), cache["buttons"])
        con_msg = await console_channel.send(embed=con_embed, view=con_view)
        
        # Save Data
        final_config["console_msg_id"] = str(con_msg.id)
        data = load_data()
        if "ticket_v2_configs" not in data: data["ticket_v2_configs"] = {}
        data["ticket_v2_configs"][str(msg.id)] = final_config
        save_data(data)
        
        await interaction.followup.send("✅ **Setup เสร็จสิ้น!**", ephemeral=True)
        del setup_cache[self.user_id]

class StyleSelectMenu(discord.ui.Select):
    def __init__(self, user_id):
        options = [
            discord.SelectOption(label="แบบปุ่มกด (Buttons)", value="buttons", emoji="🔘", description="ปุ่มกดเรียงกัน (กดง่าย)"),
            discord.SelectOption(label="แบบเมนูเลือก (Dropdown)", value="dropdown", emoji="🔻", description="เมนูเลื่อนลง (ประหยัดที่)")
        ]
        super().__init__(placeholder="เลือกรูปแบบปุ่มเปิดตั๋ว...", min_values=1, max_values=1, options=options, row=0)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["launcher_style"] = self.values[0]
        await interaction.response.defer()

class ConfigPriceButton(discord.ui.Button):
    def __init__(self, user_id, index, label):
        super().__init__(label=f"ตั้งค่า: {label}", style=discord.ButtonStyle.secondary)
        self.user_id = user_id
        self.index = index
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(PriceConfigModal(self.user_id, self.index, self.view))

class PriceConfigModal(discord.ui.Modal, title="ตั้งค่าการเร่งงาน"):
    def __init__(self, user_id, index, parent_view):
        super().__init__()
        self.user_id = user_id
        self.index = index
        self.parent_view = parent_view
        btn_data = setup_cache.get(user_id, {}).get("buttons", {}).get(index, {})
        self.rush_price = discord.ui.TextInput(label="ราคาเร่ง (บาท)", placeholder="ใส่ตัวเลขเท่านั้น", default=str(btn_data.get("rush_price", "")), required=True)
        self.pay_img = discord.ui.TextInput(label="ลิ้งค์รูปชำระเงิน (QR)", default=btn_data.get("pay_img", ""), required=True)
        self.owner_id = discord.ui.TextInput(label="ไอดีเจ้าของตั๋ว (User ID)", default=str(btn_data.get("owner_id", "")), required=True)
        self.add_item(self.rush_price)
        self.add_item(self.pay_img)
        self.add_item(self.owner_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            int(self.rush_price.value)
            int(self.owner_id.value)
        except: return await interaction.response.send_message("❌ ราคาและ ID ต้องเป็นตัวเลข", ephemeral=True)
        cache = setup_cache[self.user_id]
        cache["buttons"][self.index].update({
            "rush_price": int(self.rush_price.value),
            "pay_img": self.pay_img.value,
            "owner_id": int(self.owner_id.value)
        })
        for child in self.parent_view.children:
            if isinstance(child, ConfigPriceButton) and child.index == self.index:
                child.style = discord.ButtonStyle.success
                break
        await interaction.response.edit_message(view=self.parent_view)

# ====================================================
# 🎮 MAIN VIEWS (Launcher & Console)
# ====================================================

class TicketLauncherView(discord.ui.View):
    def __init__(self, msg_id, config_data=None):
        super().__init__(timeout=None)
        self.msg_id = msg_id
        
        if not config_data and msg_id:
            data = load_data()
            if "ticket_v2_configs" in data and msg_id in data["ticket_v2_configs"]:
                config_data = data["ticket_v2_configs"][msg_id]
        
        if config_data:
            buttons_config = config_data.get("buttons", {})
            style = config_data.get("launcher_style", "buttons")
            
            if style == "dropdown":
                 self.add_item(TicketLauncherSelect(msg_id, buttons_config))
            else:
                sorted_keys = sorted([int(k) for k in buttons_config.keys()])
                for idx in sorted_keys:
                    # [FIXED] รองรับทั้ง Key int และ str
                    conf = buttons_config[str(idx)] if str(idx) in buttons_config else buttons_config[idx]
                    
                    is_disabled = not conf["status"]
                    btn_style = discord.ButtonStyle.success if conf["status"] else discord.ButtonStyle.secondary
                    self.add_item(TicketButton(self.msg_id, idx, conf["label"], btn_style, is_disabled))

class TicketButton(discord.ui.Button):
    def __init__(self, msg_id, type_idx, label, style, disabled):
        super().__init__(label=label, style=style, disabled=disabled, custom_id=f"tkv2_launch_{msg_id}_{type_idx}")
        self.msg_id = msg_id
        self.type_idx = type_idx

    async def callback(self, interaction: discord.Interaction):
        await handle_ticket_creation(interaction, self.msg_id, self.type_idx)

class TicketLauncherSelect(discord.ui.Select):
    def __init__(self, msg_id, buttons_config):
        options = []
        sorted_keys = sorted([int(k) for k in buttons_config.keys()])
        for idx in sorted_keys:
            # [FIXED] รองรับทั้ง Key int และ str เพื่อแก้ KeyError '0'
            conf = buttons_config[str(idx)] if str(idx) in buttons_config else buttons_config[idx]
            
            status_text = "สถานะ : เปิดให้บริการ 🟢" if conf["status"] else "สถานะ : ปิดให้บริการ 🔴"
            options.append(discord.SelectOption(
                label=conf["label"],
                value=str(idx),
                description=status_text,
                emoji="🎫"
            ))
        super().__init__(placeholder="เลือกประเภทตั๋วที่ต้องการเปิด...", options=options, custom_id=f"tkv2_select_{msg_id}")
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        type_idx = int(self.values[0])
        await handle_ticket_creation(interaction, self.msg_id, type_idx)

async def handle_ticket_creation(interaction, msg_id, type_idx):
    data = load_data()
    if str(msg_id) not in data["ticket_v2_configs"]:
        return await interaction.response.send_message("❌ ไม่พบข้อมูล Config", ephemeral=True)
    
    config = data["ticket_v2_configs"][str(msg_id)]
    
    # [FIXED] รองรับ Key
    buttons_config = config["buttons"]
    btn_conf = buttons_config[str(type_idx)] if str(type_idx) in buttons_config else buttons_config[type_idx]
    
    if not btn_conf["status"]:
        return await interaction.response.send_message("🔴 ตั๋วนี้ถูกปิดใช้งานอยู่ครับ", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    category = interaction.guild.get_channel(btn_conf["category_id"])
    
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    owner_member = interaction.guild.get_member(btn_conf["owner_id"])
    if owner_member:
        overwrites[owner_member] = discord.PermissionOverwrite(read_messages=True)
        
    ticket_name = f"ticket-{interaction.user.name}"
    channel = await interaction.guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)
    
    embed = discord.Embed(description=btn_conf["message"], color=discord.Color.blue())
    if btn_conf["image"]: embed.set_image(url=btn_conf["image"])
    
    view = TicketInsideView(msg_id, type_idx)
    await channel.send(content=interaction.user.mention, embed=embed, view=view)
    await interaction.followup.send(f"✅ สร้างห้องแล้ว: {channel.mention}", ephemeral=True)
    
    if "active_tickets_v2" not in data: data["active_tickets_v2"] = {}
    data["active_tickets_v2"][str(channel.id)] = {
        "main_msg_id": msg_id,
        "type_idx": type_idx,
        "user_id": interaction.user.id,
        "guild_id": interaction.guild_id, 
        "is_rushing": False
    }
    save_data(data)

class TicketConsoleView(discord.ui.View):
    def __init__(self, msg_id, buttons_config=None):
        super().__init__(timeout=None)
        self.msg_id = msg_id
        if not buttons_config and msg_id:
            data = load_data()
            if "ticket_v2_configs" in data and msg_id in data["ticket_v2_configs"]:
                buttons_config = data["ticket_v2_configs"][msg_id]["buttons"]
        if buttons_config:
            sorted_keys = sorted([int(k) for k in buttons_config.keys()])
            for idx in sorted_keys:
                conf = buttons_config[str(idx)] if str(idx) in buttons_config else buttons_config[idx]
                status_emoji = "🟢" if conf["status"] else "🔴"
                label = f"{'ปิด' if conf['status'] else 'เปิด'} {conf['label']} {status_emoji}"
                style = discord.ButtonStyle.danger if conf["status"] else discord.ButtonStyle.success
                self.add_item(ConsoleToggleButton(self.msg_id, idx, label, style))

class ConsoleToggleButton(discord.ui.Button):
    def __init__(self, msg_id, type_idx, label, style):
        super().__init__(label=label, style=style, custom_id=f"tkv2_con_{msg_id}_{type_idx}")
        self.msg_id = msg_id
        self.type_idx = type_idx

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        config = data["ticket_v2_configs"][str(self.msg_id)]
        
        # [FIXED] รองรับ Key
        buttons_config = config["buttons"]
        key = str(self.type_idx) if str(self.type_idx) in buttons_config else self.type_idx
        
        current_status = buttons_config[key]["status"]
        new_status = not current_status
        buttons_config[key]["status"] = new_status
        save_data(data)
        
        new_con_view = TicketConsoleView(self.msg_id, config["buttons"])
        await interaction.response.edit_message(view=new_con_view)
        
        try:
            main_channel_id = config["channel_id"]
            channel = interaction.guild.get_channel(main_channel_id)
            if not channel: channel = await interaction.guild.fetch_channel(main_channel_id)
            msg = await channel.fetch_message(int(self.msg_id))
            
            status_text = ""
            for idx, conf in config["buttons"].items():
                s = "เปิดให้บริการ 🟢" if conf["status"] else "ปิดให้บริการ 🔴"
                status_text += f"• **{conf['label']}**: {s}\n"
            
            embed_data = config["embed_data"]
            new_embed = discord.Embed(title=embed_data["title"], description=f"{embed_data['desc']}\n\n{status_text}", color=discord.Color.green())
            if embed_data["image"]: new_embed.set_image(url=embed_data["image"])
            
            new_main_view = TicketLauncherView(self.msg_id, config)
            await msg.edit(embed=new_embed, view=new_main_view)
        except Exception as e:
            print(f"Failed to update main view: {e}")

# ====================================================
# 🎫 INSIDE TICKET VIEWS
# ====================================================

class TicketInsideView(discord.ui.View):
    def __init__(self, main_msg_id, type_idx):
        super().__init__(timeout=None)
        self.main_msg_id = main_msg_id
        self.type_idx = type_idx

    @discord.ui.button(label="ปิดตั๋ว (Admin)", style=discord.ButtonStyle.red, custom_id="tkv2_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): 
             return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.channel.delete()
        data = load_data()
        if str(interaction.channel.id) in data["active_tickets_v2"]:
            del data["active_tickets_v2"][str(interaction.channel.id)]
        
        target_guild_id = interaction.guild_id
        remaining_rush = False
        for cid, info in data["active_tickets_v2"].items():
            g_id = info.get("guild_id")
            if g_id and int(g_id) == target_guild_id and info.get("is_rushing"):
                remaining_rush = True
                break
                
        if not remaining_rush:
            if str(target_guild_id) in data["guilds"]:
                data["guilds"][str(target_guild_id)]["rush_queue"] = 0
        
        save_data(data)

    @discord.ui.button(label="เร่งงาน 🔥", style=discord.ButtonStyle.primary, custom_id="tkv2_rush")
    async def rush_work(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        config = data["ticket_v2_configs"][str(self.main_msg_id)]["buttons"]
        
        # [FIXED] รองรับ Key
        key = str(self.type_idx) if str(self.type_idx) in config else self.type_idx
        btn_conf = config[key]
        
        price = btn_conf["rush_price"]
        img_url = btn_conf["pay_img"]
        embed = discord.Embed(title="🔥 บริการเร่งงาน", description=f"ค่าบริการ: **{price} บาท**\nโปรดโอนเงินและส่งสลิปในห้องนี้", color=discord.Color.orange())
        embed.set_image(url=img_url)
        view = RushPaymentView()
        msg = await interaction.channel.send(embed=embed, view=view)
        
        if str(interaction.channel.id) in data["active_tickets_v2"]:
            data["active_tickets_v2"][str(interaction.channel.id)]["is_rushing"] = True
            data["active_tickets_v2"][str(interaction.channel.id)]["rush_msg_id"] = msg.id
            save_data(data)
        await interaction.response.defer()

class RushPaymentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        data = load_data()
        if str(interaction.channel.id) in data["active_tickets_v2"]:
            data["active_tickets_v2"][str(interaction.channel.id)]["is_rushing"] = False
            save_data(data)

class RushConfirmView(discord.ui.View):
    def __init__(self, chan_id):
        super().__init__(timeout=None)
        self.chan_id = chan_id
    @discord.ui.button(label="ยืนยันการโอน ✅ (Admin Only)", style=discord.ButtonStyle.success)
    async def confirm_slip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction): 
             return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        await interaction.response.defer()
        data = load_data()
        ticket_info = data["active_tickets_v2"].get(str(interaction.channel.id))
        if not ticket_info: return
        
        # [FIXED] รองรับ Key
        config = data["ticket_v2_configs"][str(ticket_info["main_msg_id"])]["buttons"]
        key = str(ticket_info["type_idx"]) if str(ticket_info["type_idx"]) in config else ticket_info["type_idx"]
        main_config = config[key]
        
        owner_id = main_config["owner_id"]
        try:
            rush_msg_id = ticket_info.get("rush_msg_id")
            if rush_msg_id:
                rush_msg = await interaction.channel.fetch_message(rush_msg_id)
                await rush_msg.delete()
        except: pass
        try: await interaction.message.delete()
        except: pass
        guild_id = str(interaction.guild_id)
        if "rush_queue" not in data["guilds"][guild_id]: data["guilds"][guild_id]["rush_queue"] = 0
        data["guilds"][guild_id]["rush_queue"] += 1
        count = data["guilds"][guild_id]["rush_queue"]
        save_data(data)
        new_name = f"{interaction.channel.name}-เร่ง-{count}"
        await interaction.channel.edit(name=new_name)
        msg = f"<@{owner_id}> 🚨 **{interaction.channel.mention} เร่งงาน!** มาทำเร็วววววว (ลำดับที่ {count})"
        await interaction.channel.send(msg)
