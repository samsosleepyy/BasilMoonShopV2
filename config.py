# config.py
import json
import os

DATA_FILE = "data.json"

# ก๊อปปี้ MESSAGES ทั้งหมดมาวางที่นี่
MESSAGES = {
    "no_permission": "🚫 คุณไม่มีสิทธิ์ใช้คำสั่งนี้",
    # ... (ข้อความอื่นๆ ทั้งหมด) ...
}

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "admins": [], "supports": [], "auction_count": 0, "ticket_count": 0,
            "ticket_configs": {}, "lockdown_time": 0, "points": {} 
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
