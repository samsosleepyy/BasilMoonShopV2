import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission

setup_cache = {}

class SelectSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="select-menu", description=MESSAGES["desc_selectmenu"])
    async def select_menu(self, interaction: discord.Interaction, channel: discord.TextChannel, text: str, imagelink: str = None):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        setup_cache[interaction.user.id] = {
            "mode": "create",
            "target_channel_id": channel.id,
            "main_text": text,
            "main_image": imagelink,
            "options": [] 
        }
        
        view = SelectSetupView(interaction.user.id)
        await interaction.response.send_message(MESSAGES["sel_setup_msg"], view=view, ephemeral=True)

    @app_commands.command(name="edit-sm", description="แก้ไขตัวเลือกใน Select Menu เดิม (เพิ่ม/ลบ)")
    async def edit_sm(self, interaction: discord.Interaction, message_link: str):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        # 1. แกะลิ้งค์เพื่อหา ID
        try:
            # Format: https://discord.com/channels/GUILD/CHANNEL/MESSAGE
            parts = message_link.split('/')
            msg_id = int(parts[-1])
            chan_id = int(parts[-2])
        except:
            return await interaction.response.send_message("❌ ลิ้งค์ข้อความไม่ถูกต้อง", ephemeral=True)
        
        data = load_data()
        if str(msg_id) not in data["select_menus"]:
            return await interaction.response.send_message("❌ ไม่พบข้อมูล Select Menu นี้ในฐานข้อมูล", ephemeral=True)
        
        current_options = data["select_menus"][str(msg_id)]
        
        # 2. โหลดข้อมูลเข้า Cache
        setup_cache[interaction.user.id] = {
            "mode": "edit",
            "target_message_id": msg_id,
            "target_channel_id": chan_id,
            "options": current_options # ก๊อปปี้ข้อมูลเดิมมา
        }
        
        # 3. สร้าง View โดยปุ่มไหนมีข้อมูลให้เป็นสีเขียว
        view = SelectEditView(interaction.user.id, current_options)
        await interaction.response.send_message(f"🛠️ **แก้ไข Select Menu**\n🔗 {message_link}\n(🟢=มีข้อมูล, ⚫=ว่าง)", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SelectSystem(bot))

# =========================================
# 1. SETUP VIEW (CREATE)
# =========================================
class SelectSetupView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        for i in range(20):
            row = i // 5
            btn = discord.ui.Button(label=str(i+1), style=discord.ButtonStyle.secondary, row=row, custom_id=f"sel_btn_{i}")
            btn.callback = self.create_callback(i)
            self.add_item(btn)

        finish_btn = discord.ui.Button(label="เสร็จสิ้น ✅", style=discord.ButtonStyle.success, row=4)
        finish_btn.callback = self.finish_callback
        self.add_item(finish_btn)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id: return
            await interaction.response.send_modal(SelectOptionModal(self.user_id, index, self))
        return callback

    async def finish_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        
        cache = setup_cache.get(self.user_id)
        if not cache or not cache["options"]:
            return await interaction.response.send_message(MESSAGES["sel_finish_error"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.guild.get_channel(cache["target_channel_id"])
        if not channel:
            return await interaction.followup.send("❌ ไม่พบช่องเป้าหมาย", ephemeral=True)
            
        embed = discord.Embed(description=cache["main_text"], color=discord.Color.blue())
        if cache["main_image"]:
            embed.set_image(url=cache["main_image"])
            
        sorted_options = sorted(cache["options"], key=lambda x: x['index'])
        
        view = SelectMenuMainView(sorted_options)
        msg = await channel.send(embed=embed, view=view)
        
        data = load_data()
        data["select_menus"][str(msg.id)] = sorted_options
        save_data(data)
        
        await interaction.followup.send(MESSAGES["sel_finish_success"], ephemeral=True)
        del setup_cache[self.user_id]


# =========================================
# 2. EDIT VIEW (UPDATE)
# =========================================
class SelectEditView(discord.ui.View):
    def __init__(self, user_id, current_options):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        # สร้าง Map ของ Index ที่มีข้อมูลอยู่แล้ว
        existing_indices = {opt['index'] for opt in current_options}
        
        for i in range(20):
            row = i // 5
            # ถ้ามีข้อมูลอยู่แล้ว ให้เป็นสีเขียว (Success), ถ้าไม่มีเป็นสีเทา (Secondary)
            style = discord.ButtonStyle.success if i in existing_indices else discord.ButtonStyle.secondary
            
            btn = discord.ui.Button(label=str(i+1), style=style, row=row)
            btn.callback = self.edit_callback(i)
            self.add_item(btn)

        finish_btn = discord.ui.Button(label="บันทึกการแก้ไข 💾", style=discord.ButtonStyle.primary, row=4)
        finish_btn.callback = self.finish_callback
        self.add_item(finish_btn)

    def edit_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id: return
            await interaction.response.send_modal(SelectEditOptionModal(self.user_id, index, self))
        return callback

    async def finish_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        
        cache = setup_cache.get(self.user_id)
        if not cache: return
        
        if not cache["options"]:
             return await interaction.response.send_message("❌ ต้องเหลือตัวเลือกอย่างน้อย 1 ข้อ", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        # ดึง Message เดิมมาแก้
        try:
            channel = interaction.guild.get_channel(cache["target_channel_id"]) or await interaction.guild.fetch_channel(cache["target_channel_id"])
            msg = await channel.fetch_message(cache["target_message_id"])
        except:
            return await interaction.followup.send("❌ ไม่พบข้อความต้นฉบับ (อาจถูกลบไปแล้ว)", ephemeral=True)
        
        sorted_options = sorted(cache["options"], key=lambda x: x['index'])
        
        # อัปเดต View ใหม่
        view = SelectMenuMainView(sorted_options)
        await msg.edit(view=view)
        
        # บันทึกลง Database
        data = load_data()
        data["select_menus"][str(msg.id)] = sorted_options
        save_data(data)
        
        await interaction.followup.send("✅ บันทึกการแก้ไขเรียบร้อย!", ephemeral=True)
        del setup_cache[self.user_id]


# =========================================
# MODALS
# =========================================

# Modal สำหรับ "สร้างใหม่" (บังคับกรอก)
class SelectOptionModal(discord.ui.Modal):
    def __init__(self, user_id, index, parent_view):
        super().__init__(title=MESSAGES["sel_modal_title"].format(n=index+1))
        self.user_id = user_id
        self.index = index
        self.parent_view = parent_view
        
        self.lbl = discord.ui.TextInput(label=MESSAGES["sel_lbl_label"], required=True)
        self.desc = discord.ui.TextInput(label=MESSAGES["sel_lbl_desc"], required=False)
        self.content = discord.ui.TextInput(label=MESSAGES["sel_lbl_content"], style=discord.TextStyle.paragraph, placeholder=MESSAGES["sel_ph_content"], required=True)
        self.img = discord.ui.TextInput(label=MESSAGES["sel_lbl_image"], required=False)
        
        self.add_item(self.lbl)
        self.add_item(self.desc)
        self.add_item(self.content)
        self.add_item(self.img)

    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache.get(self.user_id)
        if not cache: return
        
        new_option = {
            "index": self.index,
            "label": self.lbl.value,
            "description": self.desc.value,
            "content": self.content.value,
            "image": self.img.value
        }
        
        cache["options"] = [opt for opt in cache["options"] if opt["index"] != self.index]
        cache["options"].append(new_option)
        
        for child in self.parent_view.children:
            if isinstance(child, discord.ui.Button) and child.label == str(self.index + 1):
                child.style = discord.ButtonStyle.success
                break
        
        await interaction.response.edit_message(view=self.parent_view)

# Modal สำหรับ "แก้ไข" (ดึงข้อมูลเดิมมาใส่ + ลบได้)
class SelectEditOptionModal(discord.ui.Modal):
    def __init__(self, user_id, index, parent_view):
        super().__init__(title=f"แก้ไข/ลบ ตัวเลือกที่ {index+1}")
        self.user_id = user_id
        self.index = index
        self.parent_view = parent_view
        
        # หาข้อมูลเดิม (ถ้ามี)
        cache = setup_cache.get(user_id)
        old_data = next((o for o in cache["options"] if o["index"] == index), None)
        
        # ตั้งค่า Default (ถ้ามีของเดิมก็ใส่ไป)
        d_lbl = old_data["label"] if old_data else ""
        d_desc = old_data.get("description", "") if old_data else ""
        d_content = old_data["content"] if old_data else ""
        d_img = old_data.get("image", "") if old_data else ""

        # Note: required=False เพื่อให้ลบข้อความได้ (การลบข้อความ = ลบตัวเลือก)
        self.lbl = discord.ui.TextInput(label="ชื่อตัวเลือก (ลบให้ว่างเพื่อลบปุ่ม)", default=d_lbl, required=False)
        self.desc = discord.ui.TextInput(label="คำอธิบาย", default=d_desc, required=False)
        self.content = discord.ui.TextInput(label="เนื้อหา", style=discord.TextStyle.paragraph, default=d_content, required=False)
        self.img = discord.ui.TextInput(label="ลิ้งค์รูปภาพ", default=d_img, required=False)
        
        self.add_item(self.lbl)
        self.add_item(self.desc)
        self.add_item(self.content)
        self.add_item(self.img)

    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache.get(self.user_id)
        if not cache: return
        
        # เช็คว่าผู้ใช้ลบข้อมูลออกหมดหรือไม่
        if not self.lbl.value.strip():
            # === กรณีลบ ===
            # เอาออกจาก List
            cache["options"] = [opt for opt in cache["options"] if opt["index"] != self.index]
            
            # เปลี่ยนสีปุ่มกลับเป็นสีเทา
            for child in self.parent_view.children:
                if isinstance(child, discord.ui.Button) and child.label == str(self.index + 1):
                    child.style = discord.ButtonStyle.secondary
                    break
        else:
            # === กรณีเพิ่ม/แก้ไข ===
            new_option = {
                "index": self.index,
                "label": self.lbl.value,
                "description": self.desc.value,
                "content": self.content.value,
                "image": self.img.value
            }
            cache["options"] = [opt for opt in cache["options"] if opt["index"] != self.index]
            cache["options"].append(new_option)
            
            # เปลี่ยนสีปุ่มเป็นสีเขียว
            for child in self.parent_view.children:
                if isinstance(child, discord.ui.Button) and child.label == str(self.index + 1):
                    child.style = discord.ButtonStyle.success
                    break
        
        await interaction.response.edit_message(view=self.parent_view)

# =========================================
# MAIN VIEW (FRONTEND)
# =========================================
class SelectMenuMainView(discord.ui.View):
    def __init__(self, options_data):
        super().__init__(timeout=None)
        self.options_data = options_data
        
        if not options_data: return 

        discord_options = []
        for opt in options_data:
            discord_options.append(discord.SelectOption(
                label=opt["label"],
                description=opt.get("description")[:100] if opt.get("description") else None,
                value=str(opt["index"])
            ))
            
        select = discord.ui.Select(
            placeholder=MESSAGES["sel_placeholder"],
            options=discord_options,
            custom_id="custom_select_menu"
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_idx = int(interaction.data["values"][0])
        selected_data = next((item for item in self.options_data if item["index"] == selected_idx), None)
        
        if not selected_data:
            return await interaction.response.send_message("❌ ข้อมูลผิดพลาด", ephemeral=True)
            
        embed = discord.Embed(
            title=MESSAGES["sel_response_title"].format(label=selected_data["label"]),
            description=selected_data["content"],
            color=discord.Color.green()
        )
        if selected_data.get("image"):
            embed.set_image(url=selected_data["image"])
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
