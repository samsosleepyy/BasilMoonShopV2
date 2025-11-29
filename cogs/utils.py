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
        # 1. ดึง Voucher ID จากลิ้งค์ (รองรับทั้งแบบยาวและแบบสั้น)
        match = re.search(r'v=([a-zA-Z0-9]+)', voucher_link)
        if not match:
            return {"success": False, "message": "รูปแบบลิ้งค์ไม่ถูกต้อง"}
        
        voucher_id = match.group(1)
        
        # 2. เตรียมข้อมูลยิงไป TrueMoney
        url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_id}/redeem"
        payload = {
            "mobile": self.phone_number,
            "voucher_hash": voucher_id
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }

        # 3. ยิง Request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
                    
                    if resp.status == 200:
                        # สำเร็จ! ดึงจำนวนเงินออกมา
                        amount = float(data['data']['my_ticket']['amount_baht'])
                        owner_name = data['data']['owner_profile']['full_name']
                        return {
                            "success": True,
                            "amount": amount,
                            "owner": owner_name
                        }
                    else:
                        # ไม่สำเร็จ (อ่าน Error code)
                        error_code = data.get('status', {}).get('code', '')
                        message = "เกิดข้อผิดพลาดไม่ทราบสาเหตุ"
                        
                        if error_code == 'VOUCHER_OUT_OF_STOCK':
                            message = "ซองนี้ถูกรับไปหมดแล้ว"
                        elif error_code == 'VOUCHER_NOT_FOUND':
                            message = "ไม่พบซองของขวัญนี้"
                        elif error_code == 'VOUCHER_EXPIRED':
                            message = "ซองหมดอายุ"
                        elif error_code == 'CANNOT_GET_OWN_VOUCHER':
                            message = "ไม่สามารถรับซองของตัวเองได้"
                            
                        return {"success": False, "message": message}
                        
            except Exception as e:
                return {"success": False, "message": f"Connection Error: {e}"}


# ... (Class TrueMoneyGift เดิม เก็บไว้เหมือนเดิม) ...

class KBankPromptPay:
    def __init__(self):
        self.token = None

    async def get_token(self):
        url = f"{KBANK_HOST}/oauth/token"
        # สร้าง Basic Auth จาก Key:Secret
        auth_str = f"{KBANK_CONSUMER_KEY}:{KBANK_CONSUMER_SECRET}"
        auth_bytes = auth_str.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64_auth}"
        }
        data = {"grant_type": "client_credentials"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    json_data = await resp.json()
                    self.token = json_data['access_token']
                    return True
                return False

    async def create_qr(self, amount: float, ref_id: str):
        # ถ้ายังไม่มี Token หรือ Token หมดอายุ ให้ขอใหม่
        if not self.token:
            success = await self.get_token()
            if not success: return None

        url = f"{KBANK_HOST}/v1/qrpayment/request"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "x-test-mode": "true" # ใส่เฉพาะตอนใช้ Sandbox
        }
        
        payload = {
            "partnerTxnUid": ref_id,
            "partnerSrcId": KBANK_CONSUMER_KEY,
            "partnerId": KBANK_MERCHANT_ID,
            "amount": amount,
            "reference1": ref_id, # ใส่รหัสอ้างอิง
            "generateQr": "true"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # ได้ QR String มา (ไม่ใช่รูป)
                    return data.get('qrCode') 
                else:
                    print(f"KBank Error: {await resp.text()}")
                    return None

    def text_to_qr_image(self, qr_text):
        # แปลงข้อความ KBank ให้กลายเป็นไฟล์รูปภาพที่ Discord ส่งได้
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_text)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # บันทึกลง Memory (RAM) ไม่ต้องลงไฟล์จริง
        arr = io.BytesIO()
        img.save(arr, format='PNG')
        arr.seek(0)
        return discord.File(arr, filename="kbank_qr.png")
