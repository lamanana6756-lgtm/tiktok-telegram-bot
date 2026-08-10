import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Base directory
BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"

# Ensure temporary directory exists
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# User agent for requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
