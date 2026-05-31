"""
Pushes creator scrape data and 6 AI-suggested offers to the
Outreach Email Automation dashboard via its internal push endpoint.

Called after each Instagram scrape + offer computation cycle.
Safe to disable: if OUTREACH_API_URL is unset, this is a no-op.
"""

import json
import logging
from typing import List

import requests

from config import OUTREACH_API_TOKEN, OUTREACH_API_URL
from models import Creator

logger = logging.getLogger(__name__)


def push_creator_data(creator: Creator, suggested_offers: List[dict]) -> bool:
    """
    POST scraped IG stats and 6 AI-suggested offers to the outreach backend.
    Matched by instagram_handle (= instagram_username in outreach creators table).
    Returns True on success, False if sync is disabled or the call fails.
    """
    if not OUTREACH_API_URL:
        logger.debug("OUTREACH_API_URL not configured — skipping outreach sync")
        return False

    payload = {
        "instagram_handle": creator.instagram_handle,
        "creator_email": creator.creator_email,
        "creator_name": creator.creator_name,
        "quoted_rate": creator.quoted_rate,
        "ig_scraped_data": {
            "p10": creator.scraped_p10,
            "p25": creator.scraped_p25,
            "p50": creator.scraped_p50,
            "p75": creator.scraped_p75,
            "reel_count": creator.scraped_reel_count,
            "min_views": creator.scraped_min_views,
            "views_raw": json.loads(creator.scraped_views_raw) if creator.scraped_views_raw else [],
        },
        "suggested_offers": suggested_offers,
    }

    headers = {"Content-Type": "application/json"}
    if OUTREACH_API_TOKEN:
        headers["x-bot-token"] = OUTREACH_API_TOKEN

    try:
        url = f"{OUTREACH_API_URL.rstrip('/')}/api/negotiation/push"
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info(
            "Synced @%s to outreach dashboard (%d offers)",
            creator.instagram_handle,
            len(suggested_offers),
        )
        return True
    except Exception as e:
        logger.warning("Outreach sync failed for @%s: %s", creator.instagram_handle, e)
        return False
