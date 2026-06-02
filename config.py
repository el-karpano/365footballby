import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

DB_PATH = os.getenv("DB_PATH", "shop.db")

BACKUP_CHAT_ID = 456884878  # твой Telegram ID
