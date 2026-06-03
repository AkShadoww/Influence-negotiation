"""
Railway startup script — runs before main.py.
Decodes INSTAGRAM_AUTH_B64 env var → instagram_auth.json on disk,
then launches the negotiation backend.
"""

import base64
import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def decode_auth() -> None:
    auth_b64 = os.getenv("INSTAGRAM_AUTH_B64", "").strip()
    auth_file = os.getenv("INSTAGRAM_AUTH_FILE", "/tmp/instagram_auth.json")

    if not auth_b64:
        logger.warning(
            "INSTAGRAM_AUTH_B64 is not set. Instagram scraping will be disabled. "
            "Run login.py locally and follow the --upload instructions."
        )
        return

    try:
        decoded = base64.b64decode(auth_b64)
        os.makedirs(os.path.dirname(auth_file), exist_ok=True)
        with open(auth_file, "wb") as f:
            f.write(decoded)
        logger.info("Instagram auth session decoded to %s", auth_file)
    except Exception as e:
        logger.error("Failed to decode INSTAGRAM_AUTH_B64: %s", e)


def decode_gmail_auth() -> None:
    """
    Materialise Gmail OAuth files from base64 env vars (Railway has no browser to
    run the OAuth flow). token.json is what makes Gmail work headlessly; generate
    it once locally, then set GMAIL_TOKEN_B64 (and optionally GMAIL_CREDENTIALS_B64).
    """
    targets = [
        ("GMAIL_CREDENTIALS_B64", os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")),
        ("GMAIL_TOKEN_B64", os.getenv("GMAIL_TOKEN_FILE", "token.json")),
    ]
    for env_name, path in targets:
        b64 = os.getenv(env_name, "").strip()
        if not b64:
            continue
        try:
            decoded = base64.b64decode(b64)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "wb") as f:
                f.write(decoded)
            logger.info("Wrote %s from %s", path, env_name)
        except Exception as e:
            logger.error("Failed to decode %s: %s", env_name, e)

    if not os.getenv("GMAIL_TOKEN_B64", "").strip():
        logger.warning(
            "GMAIL_TOKEN_B64 is not set — Gmail will fail (no token.json, and the "
            "OAuth browser flow can't run on Railway). Generate token.json locally "
            "and set GMAIL_TOKEN_B64. Sending/reading email is disabled until then."
        )


def install_playwright_browser() -> None:
    """Ensure Chromium is installed (Railway build may not have run playwright install)."""
    result = subprocess.run(
        ["playwright", "install", "chromium", "--with-deps"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        logger.info("Playwright Chromium ready.")
    else:
        logger.warning("playwright install returned non-zero: %s", result.stderr[:200])


if __name__ == "__main__":
    decode_auth()
    decode_gmail_auth()
    install_playwright_browser()

    # Hand off to main.py
    here = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(here, "main.py")
    os.execv(sys.executable, [sys.executable, main_py])
