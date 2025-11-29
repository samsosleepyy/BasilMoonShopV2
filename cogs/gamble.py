import discord
from discord import app_commands
from discord.ext import commands
import sys
import os
import random
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MESSAGES, load_data, save_data, is_admin_or_has_permission, get_files_from_urls
from utils import TrueMoneyGift

setup_cache = {}

class GambleSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gamble", description=MESSAGES["desc_gamble"])
    async def gamble(self, interaction: discord.Interaction):
        if not is_admin_or_has_permission(interaction): return await interaction.response.send_message(MESSAGES["no_permission"], ephemeral=True)
        setup_cache[interaction.user.id] = {"step": 1, "chances": [0.0] * 15, "prizes": [None] * 15}
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
    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่อง Log (แจ้งเตือนลูกค้า)")
    async def select_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["log_channel"] = select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label=MESSAGES["gam_btn_chance_1"], style=discord.ButtonStyle.secondary, row=1)
    async def config_chance_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "chance", 1))
    @discord.ui.button(label=MESSAGES["gam_btn_chance_2"], style=discord.ButtonStyle.secondary, row=1)
    async def config_chance_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "chance", 2))
    @discord.ui.button(label=MESSAGES["gam_btn_chance_3"], style=discord.ButtonStyle.secondary, row=1)
    async def config_chance_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "chance", 3))
    @discord.ui.button(label=MESSAGES["gam_btn_img_1"], style=discord.ButtonStyle.secondary, row=2)
    async def config_img_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "image", 1))
    @discord.ui.button(label=MESSAGES["gam_btn_img_2"], style=discord.ButtonStyle.secondary, row=2)
    async def config_img_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "image", 2))
    @discord.ui.button(label=MESSAGES["gam_btn_img_3"], style=discord.ButtonStyle.secondary, row=2)
    async def config_img_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GambleListModal(self.user_id, "image", 3))
    @discord.ui.button(label=MESSAGES["gam_setup_2_next"], style=discord.ButtonStyle.green, row=3)
    async def go_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if not setup_cache[self.user_id].get("log_channel"): return await interaction.response.send_message("❌ กรุณาเลือกช่อง Log ก่อน", ephemeral=True)
        view = GambleSetupView3(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_3_msg"], view=view)

class GambleListModal(discord.ui.Modal):
    def __init__(self, user_id, mode, part):
        title_key = "gam_modal_chance_title" if mode == "chance" else "gam_modal_img_title"
        super().__init__(title=MESSAGES[title_key].format(part=part))
        self.user_id = user_id
        self.mode = mode
        self.part = part
        self.start_idx = (part - 1) * 5
        self.inputs = []
        for i in range(5):
            idx = self.start_idx + i + 1
            lbl_key = "gam_lbl_c_prefix" if mode == "chance" else "gam_lbl_i_prefix"
            placeholder = "e.g. 10.5" if mode == "chance" else "https://..."
            required = False
            default_val = ""
            current_val = setup_cache[user_id]["chances" if mode=="chance" else "prizes"][idx-1]
            if current_val: default_val = str(current_val)
            item = discord.ui.TextInput(label=MESSAGES[lbl_key].format(n=idx), placeholder=placeholder, required=required, default=default_val)
            self.add_item(item)
            self.inputs.append(item)
    async def on_submit(self, interaction: discord.Interaction):
        cache = setup_cache[self.user_id]
        if self.mode == "chance":
            try:
                for i, item in enumerate(self.inputs):
                    val = item.value.strip()
                    cache["chances"][self.start_idx + i] = float(val) if val else 0.0
            except: return await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)
        else:
            for i, item in enumerate(self.inputs):
                val = item.value.strip()
                cache["prizes"][self.start_idx + i] = val if val else None
        await interaction.response.send_message(MESSAGES["cmd_success"], ephemeral=True)

class GambleSetupView3(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    @discord.ui.select(placeholder=MESSAGES["gam_setup_3_select_mode"], options=[
        discord.SelectOption(label=MESSAGES["gam_mode_unlimited"], value="unlimited", description="ของรางวัลไม่มีวันหมด", emoji="🔄"),
        discord.SelectOption(label=MESSAGES["gam_mode_limited"], value="limited", description="ของรางวัลจะหมดเมื่อมีคนสุ่มได้", emoji="⛔")
    ])
    async def select_mode(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["gacha_mode"] = select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label=MESSAGES["gam_setup_3_btn"], style=discord.ButtonStyle.primary)
    async def open_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "gacha_mode" not in setup_cache[self.user_id]: return await interaction.response.send_message(MESSAGES["gam_err_select_mode"], ephemeral=True)
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
        cache = setup_cache[self.user_id]
        cache.update({"pay_tm": self.tm_text.value,"pay_pp": self.pp_text.value,"pay_phone": self.phone.value,"pay_qr": self.qr.value})
        
        # [NEW] Go to Step 4 (Approval Channel)
        view = GambleSetupView4(self.user_id)
        await interaction.response.edit_message(content=MESSAGES["gam_setup_4_msg"], view=view)

class GambleSetupView4(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="เลือกช่องอนุมัติสลิป")
    async def select_approval(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if interaction.user.id != self.user_id: return
        setup_cache[self.user_id]["approval_channel"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="เสร็จสิ้น ✅", style=discord.ButtonStyle.success)
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        if "approval_channel" not in setup_cache[self.user_id]:
             return await interaction.response.send_message("❌ กรุณาเลือกช่องอนุมัติก่อน", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        cache = setup_cache[self.user_id]
        
        # Send Main Embed
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
        
        gacha_btn = discord.ui.Button(label=config["btn_text"], style=discord.ButtonStyle.green, custom_id="gacha_play", emoji="🎰", row=0)
        gacha_btn.callback = self.play_gacha
        self.add_item(gacha_btn)
        
        tm_btn = discord.ui.Button(label=MESSAGES["gam_opt_tm"], style=discord.ButtonStyle.red, custom_id="topup_tm", emoji="🧧", row=0)
        tm_btn.callback = self.topup_tm
        self.add_item(tm_btn)

        pp_btn = discord.ui.Button(label=MESSAGES["gam_opt_pp"], style=discord.ButtonStyle.blurple, custom_id="topup_pp", emoji="🏦", row=0)
        pp_btn.callback = self.topup_pp
        self.add_item(pp_btn)

        # [NEW] Check Point & Stock Buttons
        check_pt_btn = discord.ui.Button(label=MESSAGES["gam_btn_check_point"], style=discord.ButtonStyle.gray, emoji="💰", row=1)
        check_pt_btn.callback = self.check_point
        self.add_item(check_pt_btn)

        check_stock_btn = discord.ui.Button(label=MESSAGES["gam_btn_check_stock"], style=discord.ButtonStyle.gray, emoji="📦", row=1)
        check_stock_btn.callback = self.check_stock
        self.add_item(check_stock_btn)

    async def check_point(self, interaction: discord.Interaction):
        data = load_data()
        points = data["points"].get(str(interaction.user.id), 0)
        embed = discord.Embed(title=MESSAGES["gam_my_point_title"], description=MESSAGES["gam_my_point_desc"].format(points=points), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def check_stock(self, interaction: discord.Interaction):
        data = load_data()
        msg_id = str(interaction.message.id)
        claimed_map = data.get("claimed_prizes", {}).get(msg_id, {}) # {index: user_id}
        
        game_mode = self.config.get("gacha_mode", "unlimited")
        prizes = self.config["prizes"]
        
        desc = ""
        for i, prize_url in enumerate(prizes):
            if not prize_url: continue
            
            status = MESSAGES["gam_stock_available"]
            if game_mode == "limited" and str(i) in claimed_map:
                winner_id = claimed_map[str(i)]
                status = MESSAGES["gam_stock_claimed"].format(user=f"<@{winner_id}>")
            
            desc += f"**{i+1}.** {status}\n"
            
        embed = discord.Embed(title=MESSAGES["gam_stock_title"], description=desc, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def play_gacha(self, interaction: discord.Interaction):
        data = load_data()
        user_id = str(interaction.user.id)
        points = data["points"].get(user_id, 0)
        cost = self.config["cost"]
        if points < cost: return await interaction.response.send_message(MESSAGES["insufficient_points"].format(cost=cost), ephemeral=True)
        
        data["points"][user_id] = points - cost
        save_data(data)
        
        chances, prizes = self.config["chances"], self.config["prizes"]
        game_mode = self.config.get("gacha_mode", "unlimited")
        msg_id = str(interaction.message.id)
        claimed_map = data.get("claimed_prizes", {}).get(msg_id, {}) # {index: user_id}
        
        valid_indices = []
        valid_weights = []
        
        for i in range(15):
            if chances[i] > 0 and prizes[i]: 
                if game_mode == "limited" and str(i) in claimed_map:
                    continue 
                valid_indices.append(i)
                valid_weights.append(chances[i])
        
        if not valid_indices:
            data["points"][user_id] += cost
            save_data(data)
            return await interaction.response.send_message(MESSAGES["gam_err_out_of_stock"], ephemeral=True)

        prize_index = random.choices(valid_indices, weights=valid_weights, k=1)[0]
        
        if game_mode == "limited":
            if "claimed_prizes" not in data: data["claimed_prizes"] = {}
            if msg_id not in data["claimed_prizes"]: data["claimed_prizes"][msg_id] = {}
            data["claimed_prizes"][msg_id][str(prize_index)] = user_id
            save_data(data)

        embed_anim = discord.Embed(title=MESSAGES["play_anim_title"], color=discord.Color.gold())
        embed_anim.set_image(url=self.config["img_gacha"])
        await interaction.response.send_message(embed=embed_anim, ephemeral=True)
        await asyncio.sleep(2)
        
        embed_res = discord.Embed(
            title=MESSAGES["play_result_title"], 
            description=MESSAGES["play_result_desc"].format(rank=prize_index+1),
            color=discord.Color.green()
        )
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
        await interaction.response.defer(ephemeral=True)
        tm_link = self.link.value.strip()
        target_phone = self.config.get("pay_phone", "")
        if not target_phone: return await interaction.followup.send("❌ ระบบยังไม่ได้ตั้งค่าเบอร์รับเงิน", ephemeral=True)
        
        redeemer = TrueMoneyGift(target_phone)
        result = await redeemer.redeem(tm_link)
        if result["success"]:
            amount = int(result["amount"])
            points_to_give = amount
            data = load_data()
            str_id = str(interaction.user.id)
            data["points"][str_id] = data["points"].get(str_id, 0) + points_to_give
            save_data(data)
            embed = discord.Embed(description=MESSAGES["tm_auto_success"].format(amount=amount, points=points_to_give), color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_id = self.config["log_channel"].id
            log_channel = interaction.guild.get_channel(log_id)
            if log_channel:
                log_embed = discord.Embed(title=MESSAGES["tm_log_auto_title"], color=discord.Color.gold())
                log_embed.add_field(name="ผู้เติม", value=interaction.user.mention, inline=True)
                log_embed.add_field(name="จำนวนเงิน", value=f"{amount} บาท", inline=True)
                log_embed.set_footer(text=f"Link: {tm_link}")
                await log_channel.send(embed=log_embed)
        else: await interaction.followup.send(MESSAGES["tm_err_generic"].format(error=result["message"]), ephemeral=True)

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
            
            # [FIX] Send to APPROVAL CHANNEL
            app_id = self.config["approval_channel"].id
            app_channel = interaction.guild.get_channel(app_id)
            
            if app_channel:
                embed = discord.Embed(title=MESSAGES["top_slip_embed_title"], color=discord.Color.orange())
                embed.add_field(name="👤 ผู้ใช้", value=interaction.user.mention, inline=True)
                embed.set_image(url=slip_url)
                
                # Pass necessary IDs including slip_url for Deny log
                view = AdminSlipCheckView(interaction.user.id, channel.id, self.config["log_channel"].id, slip_url)
                await app_channel.send(embed=embed, view=view)
        except asyncio.TimeoutError: await channel.delete()

class AdminSlipCheckView(discord.ui.View):
    def __init__(self, target_user_id, slip_channel_id, log_channel_id, slip_url):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.slip_channel_id = slip_channel_id
        self.log_channel_id = log_channel_id
        self.slip_url = slip_url

    @discord.ui.button(label=MESSAGES["top_btn_approve"], style=discord.ButtonStyle.green)
    async def give_point(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGivePointModal(self.target_user_id, self.slip_channel_id, self.log_channel_id))

    @discord.ui.button(label=MESSAGES["top_btn_deny"], style=discord.ButtonStyle.red)
    async def deny_slip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminDenySlipModal(self.target_user_id, self.slip_channel_id, self.log_channel_id, self.slip_url))

class AdminGivePointModal(discord.ui.Modal, title=MESSAGES["top_modal_approve_title"]):
    amount = discord.ui.TextInput(label=MESSAGES["top_lbl_amount"], placeholder="เช่น 100")
    def __init__(self, target_user_id, slip_channel_id, log_channel_id):
        super().__init__()
        self.target_user_id, self.slip_channel_id, self.log_channel_id = target_user_id, slip_channel_id, log_channel_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            str_id = str(self.target_user_id)
            data = load_data()
            data["points"][str_id] = data["points"].get(str_id, 0) + amt
            save_data(data)
            
            # Log & Notify User
            log_chan = interaction.guild.get_channel(self.log_channel_id)
            if log_chan:
                user_mention = f"<@{self.target_user_id}>"
                embed = discord.Embed(description=MESSAGES["log_approve_desc"].format(amount=amt), color=discord.Color.green())
                await log_chan.send(content=MESSAGES["log_approve_msg"].format(user=user_mention), embed=embed)
            
            slip_channel = interaction.guild.get_channel(self.slip_channel_id)
            if slip_channel: await slip_channel.delete()
            await interaction.response.send_message(MESSAGES["cmd_success"], ephemeral=True)
        except ValueError: await interaction.response.send_message(MESSAGES["msg_error_num"], ephemeral=True)

class AdminDenySlipModal(discord.ui.Modal, title=MESSAGES["top_modal_deny_title"]):
    reason = discord.ui.TextInput(label=MESSAGES["top_lbl_reason"])
    def __init__(self, target_user_id, slip_channel_id, log_channel_id, slip_url):
        super().__init__()
        self.target_user_id, self.slip_channel_id, self.log_channel_id, self.slip_url = target_user_id, slip_channel_id, log_channel_id, slip_url
    async def on_submit(self, interaction: discord.Interaction):
        # Log & Notify User
        log_chan = interaction.guild.get_channel(self.log_channel_id)
        if log_chan:
            user_mention = f"<@{self.target_user_id}>"
            embed = discord.Embed(title=MESSAGES["log_deny_title"], description=MESSAGES["log_deny_reason"].format(reason=self.reason.value), color=discord.Color.red())
            embed.set_image(url=self.slip_url)
            await log_chan.send(content=MESSAGES["log_deny_msg"].format(user=user_mention), embed=embed)
        
        slip_channel = interaction.guild.get_channel(self.slip_channel_id)
        if slip_channel: await slip_channel.delete()
        await interaction.response.send_message(MESSAGES["cmd_success"], ephemeral=True)
