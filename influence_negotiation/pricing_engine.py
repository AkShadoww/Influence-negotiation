"""
Uses Claude to compute a personalised performance-based price offer
for a creator based on their Instagram metrics.
"""

import json
import logging
import re

import anthropic

from config import ANTHROPIC_API_KEY, BRAND_NAME, CLAUDE_MODEL
from models import PriceOffer

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = f"""You are a pricing strategist for a social media marketing agency called INFLUENCE.
You create performance-based deal structures for Instagram creator collaborations with the brand {BRAND_NAME} (an AI image generation tool).

Given a creator's metrics, propose a fair offer with two options:
1. Flat Rate + Performance Bonus
2. View-Based Deal

Pricing guidelines:
- Nano creators (<10k followers): flat $200–$400, view target 20k–40k
- Micro creators (10k–100k followers): flat $400–$1,000, view target 40k–100k
- Mid-tier (100k–500k followers): flat $800–$2,000, view target 100k–300k
- Macro (500k–1M followers): flat $1,500–$4,000, view target 300k–600k
- Mega (1M+): flat $3,000+, view target 600k+

Engagement rate and avg_views matter more than raw follower count.
budget_cap should be ~20% above the flat_rate (max we'd pay a creator who counters).

Return ONLY this JSON, no other text:
{{
  "flat_rate": <number>,
  "flat_bonus_threshold_views": <number>,
  "flat_bonus_amount": <number>,
  "view_based_rate": <number>,
  "view_target": <number>,
  "video_count": <integer, usually 2 or 3>,
  "budget_cap": <number>
}}"""


def compute_offer(
    instagram_handle: str,
    followers: int,
    avg_views: int,
    engagement_rate: float,
) -> PriceOffer:
    """
    Compute a price offer for a creator using their Instagram metrics.
    Returns a PriceOffer dataclass.
    """
    prompt = (
        f"Creator: @{instagram_handle}\n"
        f"Followers: {followers:,}\n"
        f"Average views per Reel: {avg_views:,}\n"
        f"Engagement rate: {engagement_rate:.2f}%\n"
        f"Brand: {BRAND_NAME}\n\n"
        "Compute a fair performance-based deal offer."
    )

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        offer = PriceOffer(
            flat_rate=float(data["flat_rate"]),
            flat_bonus_threshold_views=int(data["flat_bonus_threshold_views"]),
            flat_bonus_amount=float(data["flat_bonus_amount"]),
            view_based_rate=float(data["view_based_rate"]),
            view_target=int(data["view_target"]),
            video_count=int(data["video_count"]),
            budget_cap=float(data["budget_cap"]),
        )
        logger.info(
            "Computed offer for @%s: flat=$%.0f view_rate=$%.0f cap=$%.0f",
            instagram_handle, offer.flat_rate, offer.view_based_rate, offer.budget_cap,
        )
        return offer
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error("Failed to parse pricing response for @%s: %s", instagram_handle, e)
        raise ValueError(f"Pricing engine returned invalid response: {e}") from e
    except anthropic.APIError as e:
        logger.error("Anthropic API error during pricing: %s", e)
        raise
