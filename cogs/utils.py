import aiohttp
import re
import qrcode
import io
import discord
import base64
from config import KBANK_HOST, KBANK_CONSUMER_KEY, KBANK_CONSUMER_SECRET, KBANK_MERCHANT_ID

class TrueMoneyGift:
    def __init__(self, phone_number: str):
        self.phone_number = phone_number

    async def redeem(self, voucher_link: str):
        match = re.search(r'v=([a-zA-Z0-9]+)', voucher_link)
        if not match:
            return {"success": False, "message": "รูปแบบลิ้งค์ไม่ถูกต้อง"}
        
        voucher_id = match.group(1)
        url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_id}/redeem"
        payload = {"mobile": self.phone_number, "voucher_hash": voucher_id}
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        amount = float(data['data']['my_ticket']['amount_baht'])
                        owner_name = data['data']['owner_profile']['full_name']
                        return {"success": True, "amount": amount, "owner": owner_name}
                    else:
                        error_code = data.get('status', {}).get('code', '')
                        message = "เกิดข้อผิดพลาดไม่ทราบสาเหตุ"
                        if error_code == 'VOUCHER_OUT_OF_STOCK': message = "ซองนี้ถูกรับไปหมดแล้ว"
                        elif error_code == 'VOUCHER_NOT_FOUND': message = "ไม่พบซองของขวัญนี้"
                        elif error_code == 'VOUCHER_EXPIRED': message = "ซองหมดอายุ"
                        elif error_code == 'CANNOT_GET_OWN_VOUCHER': message = "ไม่สามารถรับซองของตัวเองได้"
                        return {"success": False, "message": message}
            except Exception as e:
                return {"success": False, "message": f"Connection Error: {e}"}

class KBankPromptPay:
    def __init__(self):
        self.token = None

    async def get_token(self):
        url = f"{KBANK_HOST}/oauth/token"
        auth_str = f"{KBANK_CONSUMER_KEY}:{KBANK_CONSUMER_SECRET}"
        auth_bytes = auth_str.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {base64_auth}"}
        data = {"grant_type": "client_credentials"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, data=data) as resp:
                    if resp.status == 200:
                        json_data = await resp.json()
                        self.token = json_data['access_token']
                        return True
            except: pass
            return False

    async def create_qr(self, amount: float, ref_id: str):
        if not self.token:
            if not await self.get_token(): return None

        url = f"{KBANK_HOST}/v1/qrpayment/request"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}", "x-test-mode": "true"}
        payload = {
            "partnerTxnUid": ref_id, "partnerSrcId": KBANK_CONSUMER_KEY, "partnerId": KBANK_MERCHANT_ID,
            "amount": amount, "reference1": ref_id, "generateQr": "true"
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('qrCode')
            except: pass
            return None

    def text_to_qr_image(self, qr_text):
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        arr = io.BytesIO()
        img.save(arr, format='PNG')
        arr.seek(0)
        return discord.File(arr, filename="kbank_qr.png")
