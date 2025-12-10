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
    
    # [NEW] Auto-Load: กู้คืนเมนูทั้งหมดเมื่อบอทเริ่มทำงาน
    async def cog_load(self):
        self.bot.loop.create_task(self.restore_select_menus())

    # ฟังก์ชันกู้คืนเมนู (เรียกใช้ได้ทั้งตอนเริ่มบอท และตอน Restore)
    async def restore_select_menus(self):
        await self.bot.wait_until_ready()
        print("🔄 Restoring Select Menus...")
        data = load_data()
        count = 0
        if "select_menus" in data:
            for msg_id, options in data["select_menus"].items():
                try:
                    # สร้าง View เดิมกลับมา
                    view = SelectMenuMainView(options)
                    # สั่งให้บอทจำ View นี้ไว้ที่ข้อความเดิม
                    self.bot.add_view(view, message_id=int(msg_id))
                    count += 1
                except Exception as e:
                    print(f"Failed to restore select menu {msg_id}: {e}")
        print(f"✅ Restored {count} select menus.")

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

    @app_commands.command(name="edit-sm", description="แก้ไข Select Menu เดิม (ตัวเลือก + ข้อความหลัก)")
    async def edit_sm(self, interaction: discord.Interaction, message_link: str):
        if not is_admin_or_has_permission(interaction):
            return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)

        try:
            parts = message_link.split('/')
            msg_id = int(parts[-1])
            chan_id = int(parts[-2])
            
            channel = interaction.guild.get_channel(chan_id)
            if not channel: channel = await interaction.guild.fetch_channel(chan_id)
            target_msg = await channel.fetch_message(msg_id)
            
            current_embed = target_msg.embeds[0] if target_msg.embeds else None
            current_text = current_embed.description if current_embed else "..."
            current_image = current_embed.image.url if current_embed and current_embed.image else None
            
        except Exception as e:
            return await interaction.followup.send(f"❌ ไม่พบข้อความต้นฉบับ หรือลิ้งค์ผิด: {e}", ephemeral=True)
        
        data = load_data()
        
        if str(msg_id) in data["select_menus"]:
            current_options = data["select_menus"][str(msg_id)]
            msg_content = f"🛠️ **แก้ไข Select Menu**\n🔗 {message_link}\n(🟢=มีข้อมูลตัวเลือก, ⚫=ว่าง)"
        else:
            current_options = []
            msg_content = f"⚠️ **ไม่พบข้อมูลตัวเลือกเดิม (กู้คืน)**\nระบบจะให้คุณตั้งค่าใหม่ทับโพสต์เดิม\n🔗 {message_link}"

        setup_cache[interaction.user.id] = {
            "mode": "edit",
            "target_message_id": msg_id,
            "target_channel_id": chan_id,
            "options": current_options,
            "main_text": current_text,
            "main_image": current_image
        }
        
        view = SelectEditView(interaction.user.id, current_options)
        await interaction.followup.send(msg_content, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SelectSystem(bot))

# =========================================
# MODALS
# =========================================

class SelectEditMainModal(discord.ui.Modal, title="แก้ไขข้อความหลัก (Embed)"):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        cache = setup_cache.get(user_id)
        old_text = cache.get("main_text") or ""
        old_img = cache.get("main_image") or ""
        self.main_text = discord.ui.TextInput(label="เนื้อหาหลัก", style=discord.TextStyle.paragraph, default=old_text, required=True)
        self.main_image = discord.ui.TextInput(label="ลิ้งค์รูปภาพปก (Optional)", default=old_img, required=False)
        self.add_item(self.main_text)
        self.add_item(self.main_image)

    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache.get(self.user_id)
        if cache:
            cache["main_text"] = self.main_text.value
            cache["main_image"] = self.main_image.value if self.main_image.value.strip() else None
        await interaction.response.send_message("✅ อัปเดตข้อความในฉบับร่างแล้ว (อย่าลืมกด 'บันทึกการแก้ไข' เพื่อใช้งานจริง)", ephemeral=True)

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

class SelectEditOptionModal(discord.ui.Modal):
    def __init__(self, user_id, index, parent_view):
        super().__init__(title=f"แก้ไขตัวเลือกที่ {index+1}")
        self.user_id = user_id
        self.index = index
        self.parent_view = parent_view
        
        cache = setup_cache.get(user_id)
        old_data = next((o for o in cache["options"] if o["index"] == index), None)
        
        d_lbl = old_data["label"] if old_data else ""
        d_desc = old_data.get("description", "") if old_data else ""
        d_content = old_data["content"] if old_data else ""
        d_img = old_data.get("image", "") if old_data else ""

        self.lbl = discord.ui.TextInput(label="ชื่อตัวเลือก (ลบให้ว่างเพื่อลบปุ่ม)", default=d_lbl, required=False)
        self.desc = discord.ui.TextInput(label="คำอธิบาย", default=d_desc, required=False)
        self.content = discord.ui.TextInput(label="เนื้อหา (แสดงเมื่อกด)", style=discord.TextStyle.paragraph, default=d_content, required=False)
        self.img = discord.ui.TextInput(label="ลิ้งค์รูปภาพ", default=d_img, required=False)
        
        self.add_item(self.lbl)
        self.add_item(self.desc)
        self.add_item(self.content)
        self.add_item(self.img)

    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache.get(self.user_id)
        if not cache: return
        
        if not self.lbl.value.strip():
            cache["options"] = [opt for opt in cache["options"] if opt["index"] != self.index]
            for child in self.parent_view.children:
                if isinstance(child, discord.ui.Button) and child.label == str(self.index + 1):
                    child.style = discord.ButtonStyle.secondary
                    break
        else:
            if not self.content.value.strip():
                 return await interaction.response.send_message("❌ ต้องใส่เนื้อหา (Content) ด้วยครับ", ephemeral=True)

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

# =========================================
# VIEWS
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
            return await interaction.response.send_message("❌ ข้อมูลผิดพลาด (ลองใช้ /edit-sm เพื่อรีเฟรชเมนูนี้ดูครับ)", ephemeral=True)
            
        embed = discord.Embed(
            title=MESSAGES["sel_response_title"].format(label=selected_data["label"]),
            description=selected_data["content"],
            color=discord.Color.green()
        )
        if selected_data.get("image"):
            embed.set_image(url=selected_data["image"])
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

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

class SelectEditView(discord.ui.View):
    def __init__(self, user_id, current_options):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        existing_indices = {opt['index'] for opt in current_options}
        
        for i in range(20):
            row = i // 5
            style = discord.ButtonStyle.success if i in existing_indices else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=str(i+1), style=style, row=row)
            btn.callback = self.edit_callback(i)
            self.add_item(btn)

        edit_embed_btn = discord.ui.Button(label="✏️ แก้ไขข้อความหลัก", style=discord.ButtonStyle.primary, row=4)
        edit_embed_btn.callback = self.edit_embed_callback
        self.add_item(edit_embed_btn)

        finish_btn = discord.ui.Button(label="บันทึกการแก้ไข 💾", style=discord.ButtonStyle.success, row=4)
        finish_btn.callback = self.finish_callback
        self.add_item(finish_btn)

    def edit_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id: return
            await interaction.response.send_modal(SelectEditOptionModal(self.user_id, index, self))
        return callback
    
    async def edit_embed_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(SelectEditMainModal(self.user_id))

    async def finish_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return
        
        cache = setup_cache.get(self.user_id)
        if not cache: return
        
        if not cache["options"]:
             return await interaction.response.send_message("❌ ต้องเหลือตัวเลือกอย่างน้อย 1 ข้อ", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            channel = interaction.guild.get_channel(cache["target_channel_id"]) 
            if not channel: channel = await interaction.guild.fetch_channel(cache["target_channel_id"])
            msg = await channel.fetch_message(cache["target_message_id"])
        except:
            return await interaction.followup.send("❌ ไม่พบข้อความต้นฉบับ", ephemeral=True)
        
        sorted_options = sorted(cache["options"], key=lambda x: x['index'])
        
        new_text = cache.get("main_text") or "..."
        new_image = cache.get("main_image")
        
        new_embed = discord.Embed(description=new_text, color=discord.Color.blue())
        if new_image:
            new_embed.set_image(url=new_image)

        view = SelectMenuMainView(sorted_options)
        await msg.edit(embed=new_embed, view=view)
        
        data = load_data()
        data["select_menus"][str(msg.id)] = sorted_options
        save_data(data)
        
        await interaction.followup.send("✅ บันทึกการแก้ไขทั้งหมดเรียบร้อย!", ephemeral=True)
        del setup_cache[self.user_id]
