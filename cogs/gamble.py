import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import random
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, get_files_from_urls

setup_cache = {}

class GambleSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gamble", description=MESSAGES["desc_gamble"])
    async def gamble(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        setup_cache[interaction.user.id] = {"step": 1, "chances": [0]*5, "prizes": [None]*5}
        view = GambleSetupView1(interaction.user.id)
        await interaction.response.send_message(MESSAGES["gam_setup_1_msg"], view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GambleSystem(bot))

# --- Setup Views ---
class GambleSetupView1(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่องกิจกรรม")
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["target_channel"] = select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label=MESSAGES["gam_setup_1_btn"], style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(GambleStep1Modal(self.user_id))

class GambleStep1Modal(discord.ui.Modal, title=MESSAGES["gam_modal_1_title"]):
    content = discord.ui.TextInput(label=MESSAGES["gam_lbl_content"], style=discord.TextStyle.paragraph)
    img1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_img1"])
    img2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_img2"])
    btn_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_btn_txt"])
    cost = discord.ui.TextInput(label=MESSAGES["gam_lbl_cost"], placeholder=MESSAGES["gam_ph_cost"])
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost_val = int(self.cost.value)
        except: return await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)
        cache = setup_cache[self.user_id]
        cache.update({"content": self.content.value,"img_main": self.img1.value,"img_gacha": self.img2.value,"btn_text": self.btn_text.value,"cost": cost_val})
        view = GambleSetupView2(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_2_msg"], view=view)

class GambleSetupView2(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่อง Log")
    async def select_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["log_channel"] = select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label=MESSAGES["gam_setup_2_btn_chance"], style=discord.ButtonStyle.secondary)
    async def config_chance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleChancesModal(self.user_id))
    @discord.ui.button(label=MESSAGES["gam_setup_2_btn_img"], style=discord.ButtonStyle.secondary)
    async def config_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleImagesModal(self.user_id))
    @discord.ui.button(label=MESSAGES["gam_setup_2_next"], style=discord.ButtonStyle.green)
    async def go_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if not setup_cache[self.user_id].get("log_channel"): return await interaction.response.send_message("❌ กรุณาเลือกช่อง Log ก่อน", ephemeral=True)
        view = GambleSetupView3(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_3_msg"], view=view)

class GambleChancesModal(discord.ui.Modal, title=MESSAGES["gam_modal_chance_title"]):
    c1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c1"], placeholder="e.g. 1")
    c2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c2"], placeholder="e.g. 5")
    c3 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c3"], placeholder="e.g. 10")
    c4 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c4"], placeholder="e.g. 30")
    c5 = discord.ui.TextInput(label=MESSAGES["gam_lbl_c5"], placeholder="e.g. 54")
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            chances = [float(self.c1.value), float(self.c2.value), float(self.c3.value), float(self.c4.value), float(self.c5.value)]
            if sum(chances) != 100: return await interaction.response.send_message("❌ ผลรวมต้องเท่ากับ 100%", ephemeral=True)
            setup_cache[self.user_id]["chances"] = chances
            await interaction.response.send_message("✅ บันทึกโอกาสแล้ว", ephemeral=True)
        except: await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)

class GambleImagesModal(discord.ui.Modal, title=MESSAGES["gam_modal_img_title"]):
    i1 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i1"])
    i2 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i2"])
    i3 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i3"])
    i4 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i4"])
    i5 = discord.ui.TextInput(label=MESSAGES["gam_lbl_i5"])
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        imgs = [self.i1.value, self.i2.value, self.i3.value, self.i4.value, self.i5.value]
        setup_cache[self.user_id]["prizes"] = imgs
        await interaction.response.send_message("✅ บันทึกรูปรางวัลแล้ว", ephemeral=True)

class GambleSetupView3(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    @discord.ui.button(label=MESSAGES["gam_setup_3_btn"], style=discord.ButtonStyle.primary)
    async def open_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GamblePaymentModal(self.user_id))

class GamblePaymentModal(discord.ui.Modal, title=MESSAGES["gam_modal_pay_title"]):
    tm_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_tm_txt"])
    pp_text = discord.ui.TextInput(label=MESSAGES["gam_lbl_pp_txt"])
    phone = discord.ui.TextInput(label=MESSAGES["gam_lbl_phone"])
    qr = discord.ui.TextInput(label=MESSAGES["gam_lbl_qr"])
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cache = setup_cache[self.user_id]
        cache.update({"pay_tm": self.tm_text.value,"pay_pp": self.pp_text.value,"pay_phone": self.phone.value,"pay_qr": self.qr.value})
        raw_channel = cache["target_channel"]
        target_channel = interaction.guild.get_channel(raw_channel.id)
        if not target_channel:
             try: target_channel = await interaction.guild.fetch_channel(raw_channel.id)
             except: return await interaction.followup.send("❌ ไม่พบช่องที่เลือก", ephemeral=True)
        embed = discord.Embed(description=cache["content"], color=discord.Color.green())
        embed.set_image(url=cache["img_main"])
        view = GambleMainView(cache)
        try:
            await target_channel.send(embed=embed, view=view)
            await interaction.followup.send(MESSAGES["gam_setup_finish"], ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        del setup_cache[self.user_id]

# --- Front-end Views ---
class GambleMainView(discord.ui.View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config
        gacha_btn = discord.ui.Button(label=config["btn_text"], style=discord.ButtonStyle.green, custom_id="gacha_play", emoji="🎰")
        gacha_btn.callback = self.play_gacha
        self.add_item(gacha_btn)
        
        tm_btn = discord.ui.Button(label=MESSAGES["gam_opt_tm"], style=discord.ButtonStyle.red, custom_id="topup_tm", emoji="🧧")
        tm_btn.callback = self.topup_tm
        self.add_item(tm_btn)

        pp_btn = discord.ui.Button(label=MESSAGES["gam_opt_pp"], style=discord.ButtonStyle.blurple, custom_id="topup_pp", emoji="🏦")
        pp_btn.callback = self.topup_pp
        self.add_item(pp_btn)

    async def play_gacha(self, interaction: discord.Interaction):
        data = load_data()
        user_id = str(interaction.user.id)
        points = data["points"].get(user_id, 0)
        cost = self.config["cost"]
        if points < cost: return await interaction.response.send_message(MESSAGES["insufficient_points"].format(cost=cost), ephemeral=True)
        data["points"][user_id] = points - cost
        save_data(data)
        chances, prizes = self.config["chances"], self.config["prizes"]
        rand, cumulative, prize_index = random.uniform(0, 100), 0, 4
        for i, chance in enumerate(chances):
            cumulative += chance
            if rand <= cumulative:
                prize_index = i
                break
        embed_anim = discord.Embed(title=MESSAGES["play_anim_title"], color=discord.Color.gold())
        embed_anim.set_image(url=self.config["img_gacha"])
        await interaction.response.send_message(embed=embed_anim, ephemeral=True)
        await asyncio.sleep(2)
        embed_res = discord.Embed(title=MESSAGES["play_result_title"], description=MESSAGES["play_result_desc"].format(rank=prize_index+1),color=discord.Color.green())
        embed_res.set_image(url=prizes[prize_index])
        embed_res.set_footer(text=MESSAGES["point_balance"].format(points=data["points"][user_id]))
        await interaction.edit_original_response(embed=embed_res)

    async def topup_tm(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TopUpTMModal(self.config))

    async def topup_pp(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.config["pay_pp"], color=discord.Color.blue())
        embed.set_image(url=self.config["pay_qr"])
        view = PromptPayConfirmView(self.config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class TopUpTMModal(discord.ui.Modal, title=MESSAGES["top_tm_modal_title"]):
    link = discord.ui.TextInput(label=MESSAGES["top_tm_lbl_link"])
    def __init__(self, config):
        super().__init__()
        self.config = config
    async def on_submit(self, interaction: discord.Interaction):
        log_id = self.config["log_channel"].id
        log_channel = interaction.guild.get_channel(log_id)
        if log_channel: await log_channel.send(MESSAGES["top_tm_log"].format(user=interaction.user.mention, link=self.link.value))
        await interaction.response.send_message(MESSAGES["top_tm_sent"], ephemeral=True)

class PromptPayConfirmView(discord.ui.View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config
    @discord.ui.button(label=MESSAGES["top_pp_btn_confirm"], style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),interaction.user: discord.PermissionOverwrite(read_messages=True),interaction.guild.me: discord.PermissionOverwrite(read_messages=True)}
        for admin_id in data["admins"]:
            mem = interaction.guild.get_member(admin_id)
            if mem: overwrites[mem] = discord.PermissionOverwrite(read_messages=True)
        channel = await interaction.guild.create_text_channel(f"slip-{interaction.user.name}", overwrites=overwrites)
        await interaction.response.send_message(MESSAGES["top_slip_room_created"].format(channel=channel.mention), ephemeral=True)
        await channel.send(MESSAGES["top_slip_wait"].format(user=interaction.user.mention))
        def check(m): return m.author.id == interaction.user.id and m.channel.id == channel.id and m.attachments
        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=300)
            slip_url = msg.attachments[0].url
            await channel.send(MESSAGES["top_slip_received"])
            log_id = self.config["log_channel"].id
            log_channel = interaction.guild.get_channel(log_id)
            if log_channel:
                embed = discord.Embed(description=MESSAGES["top_slip_log_embed"].format(user=interaction.user.mention), color=discord.Color.orange())
                embed.set_image(url=slip_url)
                view = AdminSlipCheckView(interaction.user.id, channel.id)
                await log_channel.send(embed=embed, view=view)
        except asyncio.TimeoutError: await channel.delete()

class AdminSlipCheckView(discord.ui.View):
    def __init__(self, target_user_id, slip_channel_id):
        super().__init__(timeout=None)
        self.target_user_id, self.slip_channel_id = target_user_id, slip_channel_id
    @discord.ui.button(label=MESSAGES["top_btn_give_point"], style=discord.ButtonStyle.green)
    async def give_point(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGivePointModal(self.target_user_id, self.slip_channel_id))

class AdminGivePointModal(discord.ui.Modal, title=MESSAGES["top_modal_give_title"]):
    amount = discord.ui.TextInput(label=MESSAGES["top_lbl_amount"], placeholder="เช่น 100")
    def __init__(self, target_user_id, slip_channel_id):
        super().__init__()
        self.target_user_id, self.slip_channel_id = target_user_id, slip_channel_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            str_id = str(self.target_user_id)
            data = load_data()
            data["points"][str_id] = data["points"].get(str_id, 0) + amt
            save_data(data)
            try:
                target_user = await interaction.client.fetch_user(self.target_user_id)
                await target_user.send(MESSAGES["top_success_dm"].format(amount=amt))
            except: pass
            slip_channel = interaction.guild.get_channel(self.slip_channel_id)
            if slip_channel: await slip_channel.delete()
            await interaction.response.send_message(MESSAGES["cmd_success"], ephemeral=True)
        except ValueError: await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)
