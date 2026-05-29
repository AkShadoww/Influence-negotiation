import os
from dotenv import load_dotenv

load_dotenv()

# Gmail
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Scheduler
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
FOLLOWUP_DELAY_DAYS = int(os.getenv("FOLLOWUP_DELAY_DAYS", "2"))
MAX_FOLLOWUPS_PER_STAGE = int(os.getenv("MAX_FOLLOWUPS_PER_STAGE", "2"))

# Campaign
MANAGER_NAME = os.getenv("MANAGER_NAME", "Jennifer")
BRAND_NAME = os.getenv("BRAND_NAME", "Reve")
CAMPAIGN_DEADLINE = os.getenv("CAMPAIGN_DEADLINE", "February 05, 2026")

# Instagram Scraper (Playwright)
INSTAGRAM_USER_DATA_DIR = os.getenv("INSTAGRAM_USER_DATA_DIR", "/tmp/chrome-instagram-profile")
SCRAPER_HEADLESS = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
SCRAPER_NUM_REELS = int(os.getenv("SCRAPER_NUM_REELS", "12"))
SCRAPER_SCROLL_PAUSE_MS = int(os.getenv("SCRAPER_SCROLL_PAUSE_MS", "2000"))
SCRAPER_TIMEOUT_S = int(os.getenv("SCRAPER_TIMEOUT_S", "60"))

# CPM-based pricing (mirrors the Chrome extension defaults)
TARGET_CPM = float(os.getenv("TARGET_CPM", "15"))       # $ per 1000 views
RISK_BUFFER = float(os.getenv("RISK_BUFFER", "0.20"))   # 20% risk deduction
NUM_VIDEOS = int(os.getenv("NUM_VIDEOS", "2"))
BONUS_PERCENTAGE = float(os.getenv("BONUS_PERCENTAGE", "0.20"))   # 20% bonus on flat

# Reference accounts shown in Reply 1
REFERENCE_ACCOUNTS = [
    ("@danyel.design", "300k+ views"),
    ("@buttered_official", "100k views"),
    ("@ty200641", "100k+ views"),
    ("@thedesignely", "200k+ views"),
    ("@moonsol.design", "400k+ views"),
    ("@clovr.guy", "4.8M+ views"),
]
