import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

_raw_admins = os.getenv("ADMIN_USER_IDS", "")
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip()]

PHOTOS_DIR: str = os.getenv("PHOTOS_DIR", "photos")
MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))

# Ensure photos directory exists
os.makedirs(PHOTOS_DIR, exist_ok=True)

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")
