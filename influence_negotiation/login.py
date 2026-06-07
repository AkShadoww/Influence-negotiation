"""
One-time Instagram login script.
Run this LOCALLY (not on Railway) with a headed browser.
It opens a real Chrome window, you log in manually, then it saves
the session (cookies + localStorage) to instagram_auth.json.

Usage:
  python influence_negotiation/login.py

After running, upload the session to Railway:
  python influence_negotiation/login.py --upload
"""

import argparse
import asyncio
import base64
import json
import os
import sys

from playwright.async_api import async_playwright

AUTH_FILE = os.path.join(os.path.dirname(__file__), "..", "instagram_auth.json")
AUTH_FILE = os.path.abspath(AUTH_FILE)


async def _do_login() -> None:
    print("\n[Login] Opening Chrome — please log into Instagram in the browser window.")
    print("[Login] Once logged in and you can see your feed, come back here and press Enter.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")

        # Wait for user to complete login
        input("[Login] Press Enter once you are fully logged into Instagram... ")

        # Save auth state
        await context.storage_state(path=AUTH_FILE)
        await browser.close()

    print(f"\n[Login] Session saved to: {AUTH_FILE}")
    print("[Login] Next step: run with --upload to encode it for Railway.\n")


def _encode_for_railway() -> None:
    if not os.path.exists(AUTH_FILE):
        print(f"[Error] {AUTH_FILE} not found. Run login.py first (without --upload).")
        sys.exit(1)

    with open(AUTH_FILE, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    print("\n" + "=" * 60)
    print("Copy the value below and add it as a Railway environment variable:")
    print("  Variable name:  INSTAGRAM_AUTH_B64")
    print("  Variable value: (the long string below)")
    print("=" * 60 + "\n")
    print(encoded)
    print("\n" + "=" * 60)
    print("Also set:  INSTAGRAM_AUTH_FILE=/tmp/instagram_auth.json")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Encode saved session for Railway")
    args = parser.parse_args()

    if args.upload:
        _encode_for_railway()
    else:
        asyncio.run(_do_login())
