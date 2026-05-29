"""
Pricing engine: computes CPM-based offer from scraped Instagram view stats,
then uses Claude to produce a final structured offer with narrative context.

CPM formulas mirror the Chrome extension (content.js):
  effective_CPM = TARGET_CPM * (1 - RISK_BUFFER)
  Option A flat/video = (p25_views / 1000) * effective_CPM
  Option B flat       = (p25_views / 1000) * effective_CPM * NUM_VIDEOS
  Option B bonus      = flat * BONUS_PERCENTAGE
  Option B view_target = round((flat+bonus) / tiered_CPM * 1000, -4)
  Option C flat       = (p75_views / 1000) * TARGET_CPM   (no risk buffer — guarantee)
"""

import json
import logging
import math
import re
from dataclasses import dataclass

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    BONUS_PERCENTAGE,
    BRAND_NAME,
    CLAUDE_MODEL,
    NUM_VIDEOS,
    RISK_BUFFER,
    TARGET_CPM,
)
from scraper_utils import ScrapedStats

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@dataclass
class PriceOffer:
    # Option A — Safe flat rate (based on p25)
    flat_rate_per_video: float     # per-video flat
    flat_rate_total: float         # flat_rate_per_video * num_videos

    # Option B — Flat + bonus (based on p25 + 20% bonus)
    option_b_flat: float           # flat fee for all videos
    option_b_bonus: float          # bonus amount
    option_b_total: float          # flat + bonus
    option_b_view_target: int      # view target for bonus to unlock

    # Option C — View guarantee (based on p75)
    option_c_guarantee_views: int  # total view guarantee
    option_c_price: float          # price at full CPM

    # Meta
    budget_cap: float              # max we'd pay if creator counters (option_b_total * 1.2)
    video_count: int
    p25_views: int
    p75_views: int
    effective_cpm: float


def _tiered_cpm(target_cpm: float) -> float:
    """Mirrors getCalculateOption() in content.js."""
    if 2 <= target_cpm <= 10:
        return 1.0
    elif target_cpm <= 20:
        return 5.0
    elif target_cpm <= 30:
        return 10.0
    return 20.0


def _round_to_nearest(value: float, nearest: int) -> int:
    return int(round(value / nearest) * nearest)


def compute_offer(stats: ScrapedStats, num_videos: int = NUM_VIDEOS) -> PriceOffer:
    """
    Compute a CPM-based price offer from scraped view stats.
    Uses the same formulas as the Chrome extension, then asks Claude
    to validate and add a narrative budget_cap adjustment.
    """
    effective_cpm = TARGET_CPM * (1 - RISK_BUFFER)

    # Option A — safe flat rate
    flat_per_video = (stats.p25 / 1000) * effective_cpm
    flat_total = flat_per_video * num_videos

    # Option B — flat + 20% bonus
    option_b_flat = flat_total
    option_b_bonus = option_b_flat * BONUS_PERCENTAGE
    option_b_total = option_b_flat + option_b_bonus

    tiered = _tiered_cpm(TARGET_CPM)
    raw_view_target = (option_b_total / tiered) * 1000
    option_b_view_target = _round_to_nearest(raw_view_target, 25_000)

    # Option C — view guarantee at full CPM (no risk buffer)
    guarantee_views = _round_to_nearest(stats.p75, 25_000)
    option_c_price = (guarantee_views / 1000) * TARGET_CPM

    # Budget cap — 15% above option B total (what we'd stretch to if creator counters)
    budget_cap = option_b_total * 1.15

    offer = PriceOffer(
        flat_rate_per_video=round(flat_per_video, 2),
        flat_rate_total=round(flat_total, 2),
        option_b_flat=round(option_b_flat, 2),
        option_b_bonus=round(option_b_bonus, 2),
        option_b_total=round(option_b_total, 2),
        option_b_view_target=option_b_view_target,
        option_c_guarantee_views=guarantee_views,
        option_c_price=round(option_c_price, 2),
        budget_cap=round(budget_cap, 2),
        video_count=num_videos,
        p25_views=int(stats.p25),
        p75_views=int(stats.p75),
        effective_cpm=round(effective_cpm, 2),
    )

    logger.info(
        "@%s offer | A=$%.0f/video | B=$%.0f+$%.0f bonus @%d views | C=$%.0f @%d views | cap=$%.0f",
        stats.handle,
        offer.flat_rate_per_video,
        offer.option_b_flat,
        offer.option_b_bonus,
        offer.option_b_view_target,
        offer.option_c_price,
        offer.option_c_guarantee_views,
        offer.budget_cap,
    )
    return offer


def compute_offer_with_claude_review(stats: ScrapedStats, num_videos: int = NUM_VIDEOS) -> PriceOffer:
    """
    Compute the CPM-based offer, then pass it to Claude for a sanity check.
    Claude may adjust the budget_cap or flag anomalies.
    Returns the (possibly adjusted) PriceOffer.
    """
    offer = compute_offer(stats, num_videos)

    system_prompt = f"""You are a pricing advisor for INFLUENCE, a social media marketing agency.
You have been given a CPM-based price offer computed from an Instagram creator's scraped view statistics.
Brand: {BRAND_NAME}. Target CPM: ${TARGET_CPM}. Risk buffer: {RISK_BUFFER*100:.0f}%.

Review the offer. If the numbers look reasonable, return them unchanged.
If there is a clear anomaly (e.g. the creator has viral outliers inflating p75, or p25 is suspiciously low),
adjust budget_cap only. Do not change Option A/B/C prices.

Return ONLY valid JSON matching this schema exactly:
{{
  "budget_cap": <number>,
  "notes": "<one sentence reasoning>"
}}"""

    user_msg = f"""Creator: @{stats.handle}
Reels analyzed: {stats.count}
Views (sorted low→high): {sorted(stats.views)}
p10={stats.p10:.0f}  p25={stats.p25:.0f}  p50={stats.p50:.0f}  p75={stats.p75:.0f}

Computed offer:
  Option A flat/video: ${offer.flat_rate_per_video:.2f}
  Option B flat: ${offer.option_b_flat:.2f} + ${offer.option_b_bonus:.2f} bonus @ {offer.option_b_view_target:,} views
  Option C: ${offer.option_c_price:.2f} for {offer.option_c_guarantee_views:,} views
  Budget cap (auto): ${offer.budget_cap:.2f}"""

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        adjusted_cap = float(data.get("budget_cap", offer.budget_cap))
        notes = data.get("notes", "")
        if adjusted_cap != offer.budget_cap:
            logger.info("Claude adjusted budget_cap: $%.0f → $%.0f (%s)", offer.budget_cap, adjusted_cap, notes)
            offer.budget_cap = round(adjusted_cap, 2)
    except Exception as e:
        logger.warning("Claude review skipped (%s) — using computed offer as-is", e)

    return offer
