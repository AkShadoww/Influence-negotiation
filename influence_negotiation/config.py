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

# Campaign defaults.
# These are FALLBACKS only. Brand name and deadline are per-campaign and are
# stored per-creator (set at seed time via seed.py --brand / --deadline, or
# sourced from the originating outreach campaign). A creator's own values take
# precedence; these env vars are used only when a creator was seeded without them.
DEFAULT_MANAGER_NAME = os.getenv("MANAGER_NAME", "Jennifer")
DEFAULT_BRAND_NAME = os.getenv("BRAND_NAME", "Reve")
DEFAULT_CAMPAIGN_DEADLINE = os.getenv("CAMPAIGN_DEADLINE", "February 05, 2026")

# Instagram Scraper (Playwright)
# Auth file is written by startup.py from INSTAGRAM_AUTH_B64 env var
INSTAGRAM_AUTH_FILE = os.getenv("INSTAGRAM_AUTH_FILE", "/tmp/instagram_auth.json")
SCRAPER_HEADLESS = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
SCRAPER_NUM_REELS = int(os.getenv("SCRAPER_NUM_REELS", "12"))
SCRAPER_SCROLL_PAUSE_MS = int(os.getenv("SCRAPER_SCROLL_PAUSE_MS", "2000"))
SCRAPER_TIMEOUT_S = int(os.getenv("SCRAPER_TIMEOUT_S", "60"))

# CPM-based pricing (mirrors the Chrome extension defaults)
TARGET_CPM = float(os.getenv("TARGET_CPM", "15"))       # $ per 1000 views
RISK_BUFFER = float(os.getenv("RISK_BUFFER", "0.20"))   # 20% risk deduction
NUM_VIDEOS = int(os.getenv("NUM_VIDEOS", "2"))
BONUS_PERCENTAGE = float(os.getenv("BONUS_PERCENTAGE", "0.20"))   # 20% bonus on flat

# Max CPM cap used when generating the 6 AI-suggested offers.
# Can be overridden per-campaign via the outreach dashboard (OUTREACH_API_URL).
# Defaults to TARGET_CPM so legacy behaviour is unchanged.
MAX_CPM = float(os.getenv("MAX_CPM", str(TARGET_CPM)))

# Outreach Email Automation integration
# Set OUTREACH_API_URL to enable pushing IG data + offers to the dashboard,
# and pulling the campaign's max_cpm + the admin's approved offer back.
OUTREACH_API_URL = os.getenv("OUTREACH_API_URL", "")
OUTREACH_API_TOKEN = os.getenv("OUTREACH_API_TOKEN", "")

# Human-in-the-loop approval gate.
# When True, after a creator shares their rate the worker computes + pushes the
# 6 offers and then WAITS for an admin to approve one in the outreach dashboard
# before sending Reply 2 (the offer email). When False, Reply 2 is sent
# immediately — using the approved offer if one already exists, else the
# computed Option A/B/C. Requires OUTREACH_API_URL to be set to have any effect.
REQUIRE_OFFER_APPROVAL = os.getenv("REQUIRE_OFFER_APPROVAL", "true").lower() == "true"

# Reference accounts shown in Reply 1
REFERENCE_ACCOUNTS = [
    ("@danyel.design", "300k+ views"),
    ("@buttered_official", "100k views"),
    ("@ty200641", "100k+ views"),
    ("@thedesignely", "200k+ views"),
    ("@moonsol.design", "400k+ views"),
    ("@clovr.guy", "4.8M+ views"),
]
