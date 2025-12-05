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
            "target_channel_id": channel.id,
            "main_text": text,
            "main_image": imagelink,
            "options": [] # List of dicts {label, desc, content, image}
        }
        
        view = SelectSetupView(interaction.user.id)
        await interaction.response.send_message(MESSAGES["sel_setup_msg"], view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SelectSystem(bot))

# =========================================
# SETUP VIEWS
# =========================================
class SelectSetupView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        # Generate Buttons 1-20 (4 rows of 5)
        for i in range(20):
            row = i // 5
            btn = discord.ui.Button(label=str(i+1), style=discord.ButtonStyle.secondary, row=row, custom_id=f"sel_btn_{i}")
            btn.callback = self.create_callback(i)
            self.add_item(btn)

        # Finish Button
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
        
        # Send Main Message
        channel = interaction.guild.get_channel(cache["target_channel_id"])
        if not channel:
            return await interaction.followup.send("❌ ไม่พบช่องเป้าหมาย", ephemeral=True)
            
        embed = discord.Embed(description=cache["main_text"], color=discord.Color.blue())
        if cache["main_image"]:
            embed.set_image(url=cache["main_image"])
            
        # Create View with Select Menu
        # Convert options list to proper structure (fill empty slots if any logic needed, but here list is dynamic)
        # Sort options based on index? We just append. If strict order 1-20 needed, we should use dict or list with fixed size.
        # Current modal appends. Let's fix modal to insert at index.
        
        # Sort options by index for display order
        sorted_options = sorted(cache["options"], key=lambda x: x['index'])
        
        view = SelectMenuMainView(sorted_options)
        msg = await channel.send(embed=embed, view=view)
        
        # Save to DB
        data = load_data()
        data["select_menus"][str(msg.id)] = sorted_options
        save_data(data)
        
        await interaction.followup.send(MESSAGES["sel_finish_success"], ephemeral=True)
        del setup_cache[self.user_id]

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
        
        # Update or Add option
        new_option = {
            "index": self.index,
            "label": self.lbl.value,
            "description": self.desc.value,
            "content": self.content.value,
            "image": self.img.value
        }
        
        # Remove existing if updating same index
        cache["options"] = [opt for opt in cache["options"] if opt["index"] != self.index]
        cache["options"].append(new_option)
        
        # Update Button Color to Green indicating "Set"
        for child in self.parent_view.children:
            if isinstance(child, discord.ui.Button) and child.label == str(self.index + 1):
                child.style = discord.ButtonStyle.success
                break
        
        await interaction.response.edit_message(view=self.parent_view)

# =========================================
# MAIN VIEW
# =========================================
class SelectMenuMainView(discord.ui.View):
    def __init__(self, options_data):
        super().__init__(timeout=None)
        self.options_data = options_data
        
        # Create Select Options
        discord_options = []
        for opt in options_data:
            discord_options.append(discord.SelectOption(
                label=opt["label"],
                description=opt.get("description"),
                value=str(opt["index"])
            ))
            
        # Create Select Menu
        select = discord.ui.Select(
            placeholder=MESSAGES["sel_placeholder"],
            options=discord_options,
            custom_id="custom_select_menu"
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_idx = int(interaction.data["values"][0])
        
        # Find data
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
