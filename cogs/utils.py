import aiohttp
import re

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
