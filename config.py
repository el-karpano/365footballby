import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

DB_PATH = os.getenv("DB_PATH", "E:/python_works/365football/shop.db")

BACKUP_CHAT_ID = 456884878  # твой Telegram ID
BACKUP_INTERVAL = 60 * 60   # каждый час