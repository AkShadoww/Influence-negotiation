"""
Pushes creator scrape data and 6 AI-suggested offers to the
Outreach Email Automation dashboard via its internal push endpoint.

Called after each Instagram scrape + offer computation cycle.
Safe to disable: if OUTREACH_API_URL is unset, this is a no-op.
"""

import json
import logging
from typing import List, Optional

import requests

from config import OUTREACH_API_TOKEN, OUTREACH_API_URL
from models import Creator

logger = logging.getLogger(__name__)


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if OUTREACH_API_TOKEN:
        headers["x-bot-token"] = OUTREACH_API_TOKEN
    return headers


def fetch_campaign_offer(
    instagram_handle: Optional[str],
    brand_name: Optional[str] = None,
) -> Optional[dict]:
    """
    Pull the campaign's admin-configured max_cpm and the admin's approved offer
    for this creator from the outreach dashboard (GET /api/negotiation/offer).

    Matched by instagram_handle, optionally narrowed by brand_name when the
    handle appears in multiple campaigns.

    Returns a dict like:
        {
          "found": bool,
          "max_cpm": float | None,
          "approved_offer": dict | None,   # the admin's selected/edited offer
          "selected_offer_id": str | None,
          "quoted_rate": float | None,
          "campaign": {...},
        }
    or None if sync is disabled, the creator has no handle, or the call fails.
    """
    if not OUTREACH_API_URL or not instagram_handle:
        return None

    params = {"instagram_handle": instagram_handle}
    if brand_name:
        params["brand_name"] = brand_name

    try:
        url = f"{OUTREACH_API_URL.rstrip('/')}/api/negotiation/offer"
        resp = requests.get(url, params=params, headers=_auth_headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("found"):
            return data  # {"ok": True, "found": False}
        return data
    except Exception as e:
        logger.warning("Outreach offer fetch failed for @%s: %s", instagram_handle, e)
        return None


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

    try:
        url = f"{OUTREACH_API_URL.rstrip('/')}/api/negotiation/push"
        resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=10)
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
