import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import datetime
import asyncio
import json
import aiohttp
import re

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
                    view = TicketLauncherView(msg_id, config)
                    self.bot.add_view(view, message_id=int(msg_id))
                    
                    if "console_msg_id" in config:
                        console_view = TicketConsoleView(msg_id)
                        self.bot.add_view(console_view, message_id=int(config["console_msg_id"]))
                except Exception as e:
                    print(f"Error restoring ticket v2 config {msg_id}: {e}")

        # 2. กู้คืน Active Tickets
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
            "launcher_style": "buttons",
            "dropdown_placeholder": "เลือกประเภทตั๋วที่ต้องการเปิด..."
        }
        
        # [UPDATED] ข้อความอธิบายขั้นตอนที่ 1
        desc = (
            "## 🛠️ ขั้นตอนที่ 1/2: ตั้งค่าหน้าตาและปุ่ม\n"
            "ในหน้านี้คุณจะต้องกำหนดข้อมูลพื้นฐานดังนี้:\n\n"
            "1. **ตั้งค่า Embed หลัก:** คือหน้าต่างข้อความที่จะแสดงให้ลูกค้าเห็น\n"
            "2. **ตั้งค่าปุ่ม (1-20):** กดที่ตัวเลขเพื่อกำหนดค่าของปุ่มนั้นๆ\n"
            "   - ข้อความในปุ่ม (เช่น สกิน, คอมมิชชั่น)\n"
            "   - ข้อความต้อนรับที่จะเด้งเมื่อเปิดห้อง\n"
            "   - หมวดหมู่ (Category ID) ที่จะให้สร้างห้อง\n\n"
            "*เมื่อตั้งค่าครบแล้ว ให้กดปุ่ม 'ถัดไป' สีเขียว*"
        )
        
        view = SetupStep1View(interaction.user.id)
        await interaction.response.send_message(desc, view=view, ephemeral=True)

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
                    
                    owner_ping = ""
                    try:
                        main_msg_id = str(ticket_info["main_msg_id"])
                        type_idx = str(ticket_info["type_idx"])
                        
                        if main_msg_id in data["ticket_v2_configs"]:
                            btn_config = data["ticket_v2_configs"][main_msg_id]["buttons"].get(type_idx)
                            if btn_config:
                                owner_id = btn_config.get("owner_id")
                                if owner_id:
                                    owner_ping = f"<@{owner_id}> "
                    except Exception as e:
                        print(f"Error fetching owner ID: {e}")

                    view = RushConfirmView(chan_id)
                    await message.reply(f"{owner_ping}🧾 **ได้รับสลิปแล้ว**\nแอดมินโปรดตรวจสอบและกดปุ่มด้านล่างเพื่อยืนยันการเร่งงาน", view=view)

# =========================
# Helpers: Rush Queue
# =========================
def _build_admin_pings(guild: discord.Guild, data: dict, guild_id: str):
    pings = []
    try:
        if "guilds" in data and guild_id in data["guilds"]:
            target_ids = set(data["guilds"][guild_id].get("admins", []) + data["guilds"][guild_id].get("supports", []))
        else:
            target_ids = set()
        for target_id in target_ids:
            role = guild.get_role(target_id)
            if role:
                pings.append(role.mention)
            else:
                pings.append(f"<@{target_id}>")
    except:
        pass
    return pings

def _is_valid_truemoney_gift_link(link: str) -> bool:
    # ตัวอย่าง: https://gift.truemoney.com/campaign/?v=XXXX
    link = link.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        return False
    if "gift.truemoney.com" not in link:
        return False
    if "campaign" not in link:
        return False
    return True

async def _try_truemoney_api_redeem(link: str, phone: str | None):
    """
    ยืนยัน/รับซองอั่งเปา TrueMoney เพื่ออัปคิวอัตโนมัติ

    ลำดับการทำงาน:
    1) ถ้ามี ENV TRUEWALLET_API_URL + TRUEWALLET_API_KEY -> เรียก API ภายนอกของคุณก่อน (กรณีคุณมี service ของตัวเอง)
    2) ถ้าไม่มี -> จะลองยิง TrueMoney Gift redeem endpoint ตรง ๆ (ต้องมี phone ผู้รับ)

    คืนค่า:
      (ok: bool, amount_baht: int|None, error_code: str|None)
    """

    def _extract_hash(url: str) -> str | None:
        url = url.strip()
        # รูปแบบหลัก: https://gift.truemoney.com/campaign/?v=HASH
        m = re.search(r"[?&]v=([a-zA-Z0-9]+)", url)
        if m:
            return m.group(1)
        # บางทีเป็น /campaign/?v=... หรือมี query อื่น ๆ
        return None

    # 1) เรียก API ภายนอก (ถ้าตั้งไว้)
    api_url = os.getenv("TRUEWALLET_API_URL", "").strip()
    api_key = os.getenv("TRUEWALLET_API_KEY", "").strip()
    if api_url and api_key:
        payload = {"link": link}
        if phone:
            payload["phone"] = phone
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        return (False, None, f"HTTP_{resp.status}")
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and (data.get("success") or data.get("ok") or data.get("status") in ["success", True]):
                        amt = None
                        try:
                            amt = int(data.get("amount") or data.get("amount_baht") or 0) or None
                        except:
                            amt = None
                        return (True, amt, None)
                    code = None
                    if isinstance(data, dict):
                        code = data.get("code") or data.get("error") or data.get("status")
                    return (False, None, str(code) if code else "API_REJECTED")
        except Exception as e:
            print(f"TrueWallet external API error: {e}")
            # ถ้า API ภายนอกล้ม ให้ลอง direct ต่อ (ถ้ามี phone)
            pass

    # 2) ยิง TrueMoney Gift โดยตรง (ต้องมี phone)
    if not phone:
        return (False, None, "MISSING_PHONE")

    voucher_hash = _extract_hash(link)
    if not voucher_hash:
        return (False, None, "INVALID_LINK")

    url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_hash}/redeem"
    payload = {"mobile": phone, "voucher_hash": voucher_hash}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                # TrueMoney บางครั้งตอบเป็น text/json ผสม
                data = await response.json(content_type=None)
                status_code = None
                if isinstance(data, dict):
                    status_code = (data.get("status") or {}).get("code") or data.get("code")

                if status_code == "SUCCESS":
                    amount = None
                    try:
                        amount = int(data["data"]["my_ticket"]["amount_baht"])
                    except Exception:
                        amount = None
                    return (True, amount, None)

                # กรณี error ที่พบบ่อย
                if status_code:
                    return (False, None, status_code)

                return (False, None, "UNKNOWN_RESPONSE")
    except aiohttp.ClientResponseError as e:
        return (False, None, f"HTTP_{e.status}")
    except Exception as e:
        print(f"TrueWallet direct redeem error: {e}")
        return (False, None, "REQUEST_FAILED")
    """
    api_url = os.getenv("TRUEWALLET_API_URL", "").strip()
    api_key = os.getenv("TRUEWALLET_API_KEY", "").strip()
    if not api_url or not api_key:
        return False

    payload = {"link": link}
    if phone:
        payload["phone"] = phone

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=20) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json(content_type=None)
                # รองรับหลายรูปแบบ response
                if isinstance(data, dict):
                    return bool(data.get("success") or data.get("ok") or data.get("status") in ["success", True])
    except Exception as e:
        print(f"TrueWallet API error: {e}")
    return False

async def _apply_rush_queue(interaction: discord.Interaction, data: dict, main_msg_id: int, type_idx: int, channel_override: discord.TextChannel | None = None):
    """
    อัปคิวเร่งงาน: เพิ่มตัวนับ rush_queue ของกิลด์, เปลี่ยนชื่อห้อง, ตั้ง is_rushing
    """
    channel = channel_override or interaction.channel
    guild_id = str(interaction.guild_id)

    if "guilds" not in data or guild_id not in data["guilds"]:
        return

    if "rush_queue" not in data["guilds"][guild_id]:
        data["guilds"][guild_id]["rush_queue"] = 0
    data["guilds"][guild_id]["rush_queue"] += 1
    count = data["guilds"][guild_id]["rush_queue"]

    # mark ticket rushing
    if "active_tickets_v2" in data and str(channel.id) in data["active_tickets_v2"]:
        data["active_tickets_v2"][str(channel.id)]["is_rushing"] = True
        data["active_tickets_v2"][str(channel.id)]["rush_method"] = "auto_or_admin"

    # เปลี่ยนชื่อช่อง (กันยาวเกิน)
    base_name = channel.name.split("-เร่ง-")[0]
    new_name = f"{base_name}-เร่ง-{count}"
    if len(new_name) > 95:
        new_name = new_name[:95]
    try:
        await channel.edit(name=new_name)
    except Exception as e:
        print(f"Rename rush channel failed: {e}")

    await channel.send(f"🚨 **เร่งงานสำเร็จ!** (ลำดับที่ {count})")

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
        
        # [UPDATED] ข้อความอธิบายขั้นตอนที่ 2
        desc = (
            "## 🛠️ ขั้นตอนที่ 2/2: การเงินและรูปแบบ\n"
            "ในหน้านี้จะเป็นการตั้งค่าเพิ่มเติม:\n\n"
            "1. **รูปแบบเมนู:** เลือกว่าจะให้แสดงเป็น `ปุ่มกด` หรือ `เมนูเลื่อนลง`\n"
            "2. **ข้อความรอเลือก:** (เฉพาะแบบเมนู ต้องกดถึงจะเห็น) ข้อความที่จะแสดงในช่องเลือกก่อนกด\n"
            "3. **ตั้งค่าราคา (ตามปุ่มที่เลือกไว้ในขั้นแรก):**\n"
            "   - ราคาเร่งงาน (เว้นว่างได้ถ้าไม่ต้องการ)\n"
            "   - รูป QR Code รับเงิน\n"
            "   - ID ผู้ใช้ที่จะให้เป็นเจ้าของตั๋ว"
        )
        
        view = SetupStep2View(self.user_id)
        await interaction.response.edit_message(content=desc, view=view)

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
        
        # แสดงปุ่ม Placeholder เฉพาะถ้าเป็น Dropdown
        style = cache.get("launcher_style", "buttons")
        if style == "dropdown":
            self.add_item(SetPlaceholderButton(user_id))
        
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
        
        dummy_view = TicketLauncherView(None) 
        msg = await main_channel.send(embed=embed, view=dummy_view) 
        
        final_config = {
            "channel_id": cache["target_channel"],
            "console_channel_id": cache["console_channel"],
            "console_msg_id": None,
            "log_channel_id": cache["log_channel"],
            "embed_data": cache["embed_data"],
            "buttons": cache["buttons"],
            "launcher_style": cache.get("launcher_style", "buttons"),
            "dropdown_placeholder": cache.get("dropdown_placeholder", "เลือกประเภทตั๋วที่ต้องการเปิด...")
        }
        
        new_view = TicketLauncherView(str(msg.id), final_config)
        await msg.edit(view=new_view)
        
        console_channel = interaction.guild.get_channel(cache["console_channel"])
        con_embed = discord.Embed(title="🎛️ Ticket Console", description="ควบคุมสถานะการเปิด/ปิดตั๋ว", color=discord.Color.dark_grey())
        con_view = TicketConsoleView(str(msg.id), cache["buttons"])
        con_msg = await console_channel.send(embed=con_embed, view=con_view)
        
        final_config["console_msg_id"] = str(con_msg.id)
        data = load_data()
        if "ticket_v2_configs" not in data: data["ticket_v2_configs"] = {}
        data["ticket_v2_configs"][str(msg.id)] = final_config
        save_data(data)
        
        await interaction.followup.send("✅ **Setup เสร็จสิ้น!**\nสร้างระบบ Ticket เรียบร้อยแล้วครับ", ephemeral=True)
        del setup_cache[self.user_id]

class SetPlaceholderButton(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="ตั้งค่าข้อความรอเลือก (Placeholder)", style=discord.ButtonStyle.primary, row=0)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(PlaceholderConfigModal(self.user_id))

class PlaceholderConfigModal(discord.ui.Modal, title="ตั้งค่าข้อความ Placeholder"):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        current = setup_cache.get(user_id, {}).get("dropdown_placeholder", "")
        self.text_inp = discord.ui.TextInput(label="ข้อความ", placeholder="เช่น เลือกบริการที่ต้องการ...", default=current, required=True)
        self.add_item(self.text_inp)

    async def on_submit(self, interaction: discord.Interaction):
        setup_cache[self.user_id]["dropdown_placeholder"] = self.text_inp.value
        await interaction.response.send_message(f"✅ ตั้งค่า Placeholder เป็น: `{self.text_inp.value}`", ephemeral=True)

class StyleSelectMenu(discord.ui.Select):
    def __init__(self, user_id):
        options = [
            discord.SelectOption(label="แบบปุ่มกด (Buttons)", value="buttons", emoji="🔘", description="ปุ่มกดเรียงกัน (กดง่าย)"),
            discord.SelectOption(label="แบบเมนูเลือก (Dropdown)", value="dropdown", emoji="🔻", description="เมนูเลื่อนลง (ประหยัดที่)")
        ]
        super().__init__(placeholder="เลือกรูปแบบปุ่มเปิดตั๋ว...", min_values=1, max_values=1, options=options, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        new_style = self.values[0]
        setup_cache[self.user_id]["launcher_style"] = new_style
        
        view = self.view
        placeholder_btn = next((item for item in view.children if isinstance(item, SetPlaceholderButton)), None)
        
        if new_style == "dropdown" and not placeholder_btn:
            view.add_item(SetPlaceholderButton(self.user_id))
        elif new_style == "buttons" and placeholder_btn:
            view.remove_item(placeholder_btn)
            
        await interaction.response.edit_message(view=view)

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
        
        rush_val = str(btn_data.get("rush_price", ""))
        pay_val = btn_data.get("pay_img", "")
        if rush_val == "0": rush_val = ""

        self.rush_price = discord.ui.TextInput(label="ราคาเร่ง (บาท) [ไม่บังคับ]", placeholder="เว้นว่างถ้าไม่ต้องการให้เร่งได้", default=rush_val, required=False)
        self.pay_img = discord.ui.TextInput(label="ลิ้งค์รูปชำระเงิน (QR) [ไม่บังคับ]", default=pay_val, required=False)

        tw_phone_val = btn_data.get("truemoney_wallet_phone", "") or ""
        self.truemoney_wallet_phone = discord.ui.TextInput(label="เบอร์ TrueMoney Wallet (ไม่บังคับ)", placeholder="เช่น 0800000000", default=str(tw_phone_val), required=False)
        self.owner_id = discord.ui.TextInput(label="ไอดีเจ้าของตั๋ว (User ID)", default=str(btn_data.get("owner_id", "")), required=True)
        self.emoji_inp = discord.ui.TextInput(label="อีโมจิ (Emoji)", placeholder="เช่น 🎫, 🔧", required=False, default=btn_data.get("emoji", ""))
        
        self.add_item(self.rush_price)
        self.add_item(self.pay_img)
        self.add_item(self.truemoney_wallet_phone)
        self.add_item(self.owner_id)
        self.add_item(self.emoji_inp)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            int(self.rush_price.value) if self.rush_price.value.strip() else 0
            int(self.owner_id.value)
        except: return await interaction.response.send_message("❌ ราคาและ ID ต้องเป็นตัวเลข", ephemeral=True)
        
        rush_val = int(self.rush_price.value) if self.rush_price.value.strip() else 0
        
        cache = setup_cache[self.user_id]
        cache["buttons"][self.index].update({
            "rush_price": rush_val,
            "pay_img": self.pay_img.value if self.pay_img.value.strip() else None,
            "truemoney_wallet_phone": self.truemoney_wallet_phone.value.strip() if self.truemoney_wallet_phone.value.strip() else None,
            "owner_id": int(self.owner_id.value),
            "emoji": self.emoji_inp.value if self.emoji_inp.value else None
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
                 self.add_item(TicketLauncherSelect(msg_id, config_data))
            else:
                sorted_keys = sorted([int(k) for k in buttons_config.keys()])
                for idx in sorted_keys:
                    key = str(idx) if str(idx) in buttons_config else idx
                    conf = buttons_config[key]
                    is_disabled = not conf["status"]
                    btn_style = discord.ButtonStyle.success if conf["status"] else discord.ButtonStyle.secondary
                    emoji = conf.get("emoji")
                    self.add_item(TicketButton(self.msg_id, idx, conf["label"], btn_style, is_disabled, emoji))

class TicketButton(discord.ui.Button):
    def __init__(self, msg_id, type_idx, label, style, disabled, emoji):
        super().__init__(label=label, style=style, disabled=disabled, emoji=emoji, custom_id=f"tkv2_launch_{msg_id}_{type_idx}")
        self.msg_id = msg_id
        self.type_idx = type_idx

    async def callback(self, interaction: discord.Interaction):
        await handle_ticket_creation(interaction, self.msg_id, self.type_idx)

class TicketLauncherSelect(discord.ui.Select):
    def __init__(self, msg_id, config_data):
        buttons_config = config_data.get("buttons", {})
        placeholder_text = config_data.get("dropdown_placeholder", "เลือกประเภทตั๋วที่ต้องการเปิด...")
        
        options = []
        sorted_keys = sorted([int(k) for k in buttons_config.keys()])
        for idx in sorted_keys:
            key = str(idx) if str(idx) in buttons_config else idx
            conf = buttons_config[key]
            
            status_text = "สถานะ : เปิดให้บริการ 🟢" if conf["status"] else "สถานะ : ปิดให้บริการ 🔴"
            emoji = conf.get("emoji") or "🎫"
            
            options.append(discord.SelectOption(
                label=conf["label"],
                value=str(idx),
                description=status_text,
                emoji=emoji
            ))
        super().__init__(placeholder=placeholder_text, options=options, custom_id=f"tkv2_select_{msg_id}")
        self.msg_id = msg_id

    async def callback(self, interaction: discord.Interaction):
        type_idx = int(self.values[0])
        await handle_ticket_creation(interaction, self.msg_id, type_idx)

async def handle_ticket_creation(interaction, msg_id, type_idx):
    data = load_data()
    if str(msg_id) not in data["ticket_v2_configs"]:
        return await interaction.response.send_message("❌ ไม่พบข้อมูล Config", ephemeral=True)
    
    config = data["ticket_v2_configs"][str(msg_id)]
    buttons_config = config["buttons"]
    key = str(type_idx) if str(type_idx) in buttons_config else type_idx
    btn_conf = buttons_config[key]
    
    if not btn_conf["status"]:
        return await interaction.response.send_message("🔴 ตั๋วนี้ถูกปิดใช้งานอยู่", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    category = interaction.guild.get_channel(btn_conf["category_id"])
    
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    # Backward compatible: older configs may not have "owner_id"
    owner_id = btn_conf.get("owner_id")
    if not owner_id:
        # Try reading from the main config block, otherwise fallback to guild owner
        main_cfg = data.get("ticket_v2_configs", {}).get(msg_id, {})
        owner_id = main_cfg.get("owner_id") or interaction.guild.owner_id
    owner_member = interaction.guild.get_member(owner_id) if owner_id else None
    if owner_member:
        overwrites[owner_member] = discord.PermissionOverwrite(read_messages=True)
        
    ticket_name = f"ticket-{interaction.user.name}"
    channel = await interaction.guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)
    
    embed = discord.Embed(description=btn_conf["message"], color=discord.Color.blue())
    if btn_conf["image"]: embed.set_image(url=btn_conf["image"])
    
    view = TicketInsideView(msg_id, type_idx)
    
    owner_ping = f"<@{owner_id}> " if owner_id else ""
    msg_content = f"{interaction.user.mention} {owner_ping}"
    
    await channel.send(content=msg_content, embed=embed, view=view)
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
                key = str(idx) if str(idx) in buttons_config else idx
                conf = buttons_config[key]
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
        self.check_and_add_buttons()

def check_and_add_buttons(self):
    # ปุ่มปิดตั๋ว (แอดมิน)
    close_btn = discord.ui.Button(label="ปิดตั๋ว (Admin)", style=discord.ButtonStyle.red, custom_id="tkv2_close")
    close_btn.callback = self.close_ticket
    self.add_item(close_btn)

    # ถ้ามีการตั้งค่าเร่งงาน ให้แสดง Select Menu เพื่อเลือกช่องทางชำระ
    data = load_data()
    try:
        str_main_msg_id = str(self.main_msg_id)
        str_type_idx = str(self.type_idx)

        if str_main_msg_id in data.get("ticket_v2_configs", {}):
            config = data["ticket_v2_configs"][str_main_msg_id]["buttons"]
            btn_conf = config.get(str_type_idx) or config.get(int(str_type_idx))

            if btn_conf:
                rush_price = btn_conf.get("rush_price", 0) or 0
                promptpay_img = btn_conf.get("pay_img")
                tw_phone = btn_conf.get("truemoney_wallet_phone")

                if rush_price > 0 and (promptpay_img or tw_phone):
                    self.add_item(RushMethodSelect(self.main_msg_id, self.type_idx))
    except Exception as e:
        print(f"Error checking rush select: {e}")

    async def close_ticket(self, interaction: discord.Interaction):
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
    async def rush_work(self, interaction: discord.Interaction):
        # Deprecated: ระบบเร่งงานเปลี่ยนเป็น Select Menu แล้ว
        await interaction.response.send_message("โปรดใช้เมนู **เร่งงาน** เพื่อเลือกช่องทางชำระเงินครับ", ephemeral=True)

class RushMethodSelect(discord.ui.Select):
    """Select Menu สำหรับเลือกช่องทางชำระเงินเร่งคิว"""
    def __init__(self, main_msg_id: int, type_idx: int):
        self.main_msg_id = main_msg_id
        self.type_idx = type_idx

        options = [
            discord.SelectOption(
                label="TrueMoney Wallet (อั่งเปา)",
                value="truewallet",
                description="วางลิ้งค์อั่งเปาเพื่ออัปคิวอัตโนมัติ",
                emoji="🟠"
            ),
            discord.SelectOption(
                label="QR Code PromptPay",
                value="promptpay",
                description="โอนผ่านพร้อมเพย์ แล้วกดปุ่มโอนเสร็จสิ้น",
                emoji="🟦"
            ),
        ]
        super().__init__(
            placeholder="🔥 เลือกช่องทางเร่งคิว...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id=f"tkv2_rush_select:{main_msg_id}:{type_idx}",
        )

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        str_main = str(self.main_msg_id)
        conf = data.get("ticket_v2_configs", {}).get(str_main, {}).get("buttons", {})
        key = str(self.type_idx) if str(self.type_idx) in conf else self.type_idx
        btn_conf = conf.get(key, {})

        price = int(btn_conf.get("rush_price", 0) or 0)
        promptpay_img = btn_conf.get("pay_img")
        tw_phone = btn_conf.get("truemoney_wallet_phone")

        if price <= 0:
            return await interaction.response.send_message("❌ ยังไม่ได้ตั้งค่าราคาเร่งงาน", ephemeral=True)

        if self.values[0] == "promptpay":
            if not promptpay_img:
                return await interaction.response.send_message("❌ ยังไม่ได้ตั้งค่ารูป QR PromptPay", ephemeral=True)

            embed = discord.Embed(
                title="🟦 เร่งคิวด้วย PromptPay",
                description=f"ยอดที่ต้องชำระ: **{price} บาท**\n\nโอนผ่าน QR แล้วกดปุ่ม **โอนเสร็จสิ้น** ด้านล่าง",
                color=discord.Color.blue()
            )
            embed.set_image(url=promptpay_img)
            view = PromptPayDoneView(self.main_msg_id, self.type_idx)
            await interaction.response.send_message(embed=embed, view=view)

        elif self.values[0] == "truewallet":
            if not tw_phone:
                # ยังไม่ได้ตั้งค่าเบอร์ แต่ยังให้ลองได้ (บาง API ไม่ต้องใช้เบอร์)
                pass
            await interaction.response.send_modal(TrueWalletAngpaoModal(self.main_msg_id, self.type_idx))


class PromptPayDoneView(discord.ui.View):
    def __init__(self, main_msg_id: int, type_idx: int):
        super().__init__(timeout=None)
        self.main_msg_id = main_msg_id
        self.type_idx = type_idx

    @discord.ui.button(label="โอนเสร็จสิ้น ✅", style=discord.ButtonStyle.success, custom_id="tkv2_promptpay_done")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        # แจ้งแอดมิน + ให้รอตรวจสอบ
        await interaction.response.send_message("✅ แจ้งเตือนไปที่แอดมินแล้ว กรุณารอการตอบกลับครับ", ephemeral=True)

        data = load_data()
        guild_id = str(interaction.guild_id)
        str_main = str(self.main_msg_id)

        conf = data.get("ticket_v2_configs", {}).get(str_main, {})
        btns = conf.get("buttons", {})
        key = str(self.type_idx) if str(self.type_idx) in btns else self.type_idx
        btn_conf = btns.get(key, {})
        price = int(btn_conf.get("rush_price", 0) or 0)

        pings = _build_admin_pings(interaction.guild, data, guild_id)
        content = f"{' '.join(pings)}\n🚨 มีผู้ใช้กด **โอนเสร็จสิ้น (PromptPay)**\nห้อง: {interaction.channel.mention}\nยอด: **{price} บาท**"

        # ส่งไป log_channel ถ้ามี
        log_id = conf.get("log_channel_id")
        target_chan = None
        if log_id:
            target_chan = interaction.guild.get_channel(int(log_id))
        if target_chan is None:
            target_chan = interaction.channel

        await target_chan.send(content, view=AdminRushApproveView(interaction.channel.id, self.main_msg_id, self.type_idx))

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary, custom_id="tkv2_promptpay_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class TrueWalletAngpaoModal(discord.ui.Modal, title="TrueMoney Wallet - ลิ้งค์อั่งเปา"):
    def __init__(self, main_msg_id: int, type_idx: int):
        super().__init__(timeout=None)
        self.main_msg_id = main_msg_id
        self.type_idx = type_idx

        self.angpao_link = discord.ui.TextInput(
            label="วางลิ้งค์อั่งเปา (TrueMoney Gift)",
            placeholder="เช่น https://gift.truemoney.com/campaign/?v=...",
            required=True
        )
        self.add_item(self.angpao_link)

    async def on_submit(self, interaction: discord.Interaction):
        link = self.angpao_link.value.strip()

        if not _is_valid_truemoney_gift_link(link):
            return await interaction.response.send_message("❌ ลิ้งค์อั่งเปาไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        data = load_data()
        str_main = str(self.main_msg_id)
        guild_id = str(interaction.guild_id)

        conf = data.get("ticket_v2_configs", {}).get(str_main, {})
        btns = conf.get("buttons", {})
        key = str(self.type_idx) if str(self.type_idx) in btns else self.type_idx
        btn_conf = btns.get(key, {})

        price = int(btn_conf.get("rush_price", 0) or 0)
        tw_phone = btn_conf.get("truemoney_wallet_phone")

        # พยายามตรวจสอบ/รับเงินผ่าน API ถ้าตั้งค่าไว้ (ENV)
        api_ok, amount_baht, err_code = await _try_truemoney_api_redeem(link, tw_phone)

        if api_ok:
            await _apply_rush_queue(interaction, data, self.main_msg_id, self.type_idx)
            save_data(data)
            msg = "✅ ยืนยันอั่งเปาสำเร็จ! อัปคิวเร่งงานให้อัตโนมัติแล้วครับ"
            if amount_baht is not None:
                msg = f"✅ ทำรายการสำเร็จ! ได้รับเงินจำนวน {amount_baht} บาท และอัปคิวให้อัตโนมัติแล้วครับ"
            return await interaction.followup.send(msg, ephemeral=True)

        # ถ้าเป็น error ชัดเจนจากระบบ TrueMoney ให้แจ้งผู้ใช้ทันที ไม่ต้องส่งแอดมิน
        if err_code in ["VOUCHER_OUT_OF_STOCK", "VOUCHER_EXPIRED", "TARGET_USER_NOT_FOUND"]:
            mapping = {
                "VOUCHER_OUT_OF_STOCK": "❌ ไม่สามารถรับได้: ซองอั่งเปานี้ถูกรับไปหมดแล้ว",
                "VOUCHER_EXPIRED": "❌ ไม่สามารถรับได้: ซองอั่งเปานี้หมดอายุแล้ว",
                "TARGET_USER_NOT_FOUND": "❌ ไม่สามารถรับได้: เบอร์โทรศัพท์ผู้รับไม่ถูกต้อง (ตรวจสอบเบอร์ TrueMoney ในหน้า setup)",
            }
            return await interaction.followup.send(mapping.get(err_code, f"❌ เกิดข้อผิดพลาดจากระบบ: {err_code}"), ephemeral=True)

        # ถ้าไม่สามารถยืนยันด้วย API -> แจ้งแอดมินแทน
        pings = _build_admin_pings(interaction.guild, data, guild_id)
        content = f"{' '.join(pings)}\n🟠 มีผู้ใช้ส่ง **ลิ้งค์อั่งเปา TrueMoney**\nห้อง: {interaction.channel.mention}\nยอดคาดหวัง: **{price} บาท**\nลิ้งค์: {link}"
        log_id = conf.get("log_channel_id")
        target_chan = interaction.guild.get_channel(int(log_id)) if log_id else None
        if target_chan is None:
            target_chan = interaction.channel

        await target_chan.send(content, view=AdminRushApproveView(interaction.channel.id, self.main_msg_id, self.type_idx))
        return await interaction.followup.send("✅ ส่งให้แอดมินตรวจสอบแล้ว กรุณารอการตอบกลับครับ", ephemeral=True)


class AdminRushApproveView(discord.ui.View):
    """ปุ่มให้แอดมินกดยืนยันการเร่งคิว (กรณี PromptPay/TrueWallet ที่ตรวจสอบอัตโนมัติไม่ได้)"""
    def __init__(self, chan_id: int, main_msg_id: int, type_idx: int):
        super().__init__(timeout=None)
        self.chan_id = chan_id
        self.main_msg_id = main_msg_id
        self.type_idx = type_idx

    @discord.ui.button(label="ยืนยันเร่งคิว ✅ (Admin)", style=discord.ButtonStyle.success, custom_id="tkv2_admin_rush_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        data = load_data()
        channel = interaction.guild.get_channel(self.chan_id)
        if channel is None:
            return await interaction.followup.send("❌ ไม่พบห้องตั๋วนี้แล้ว", ephemeral=True)

        # สร้าง context interaction ให้ใช้ฟังก์ชันเดียวกัน
        class _Tmp:
            guild_id = interaction.guild_id
            guild = interaction.guild
            channel = channel

        # ใช้ apply เดียวกัน
        await _apply_rush_queue(interaction, data, self.main_msg_id, self.type_idx, channel_override=channel)
        save_data(data)
        await interaction.followup.send("✅ ยืนยันและอัปคิวเรียบร้อย", ephemeral=True)

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
        main_config = data["ticket_v2_configs"][str(ticket_info["main_msg_id"])]["buttons"][str(ticket_info["type_idx"])]
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
        msg = f"🚨 **{interaction.channel.mention} เร่งงาน!** (ลำดับที่ {count})"
        await interaction.channel.send(msg)
