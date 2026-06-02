"""
Pricing engine: computes CPM-based offers from scraped Instagram view stats,
then uses Claude to produce a legacy 3-option offer AND 6 structured AI offers:
  - 3 view-based offers  (pay-per-view guarantees at different view tiers)
  - 3 video-count offers (flat fees for 1, 2, 3 videos)

All 6 offers are constrained by the campaign max_cpm.
Legacy CPM formulas mirror the Chrome extension (content.js).
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import List, Optional

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    BONUS_PERCENTAGE,
    DEFAULT_BRAND_NAME,
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
    flat_rate_per_video: float
    flat_rate_total: float

    # Option B — Flat + bonus (based on p25 + 20% bonus)
    option_b_flat: float
    option_b_bonus: float
    option_b_total: float
    option_b_view_target: int

    # Option C — View guarantee (based on p75)
    option_c_guarantee_views: int
    option_c_price: float

    # Meta
    budget_cap: float
    video_count: int
    p25_views: int
    p75_views: int
    effective_cpm: float


@dataclass
class SuggestedOffer:
    """One of 6 AI-suggested offers displayed in the outreach dashboard."""
    offer_id: str            # "view_1" | "view_2" | "view_3" | "video_1" | "video_2" | "video_3"
    offer_type: str          # "view_based" | "video_based"
    label: str               # Human-readable label
    num_videos: int
    flat_fee: float          # Total payment to creator
    flat_per_video: float    # Per-video equivalent
    view_guarantee: int      # Required view delivery (0 for flat video deals)
    cpm_applied: float       # Effective CPM used
    satisfies_creator_rate: bool  # True if flat_fee >= creator's quoted rate
    notes: str               # AI-generated strategic reasoning


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
    Uses the same formulas as the Chrome extension.
    """
    effective_cpm = TARGET_CPM * (1 - RISK_BUFFER)

    flat_per_video = (stats.p25 / 1000) * effective_cpm
    flat_total = flat_per_video * num_videos

    option_b_flat = flat_total
    option_b_bonus = option_b_flat * BONUS_PERCENTAGE
    option_b_total = option_b_flat + option_b_bonus

    tiered = _tiered_cpm(TARGET_CPM)
    raw_view_target = (option_b_total / tiered) * 1000
    option_b_view_target = _round_to_nearest(raw_view_target, 25_000)

    guarantee_views = _round_to_nearest(stats.p75, 25_000)
    option_c_price = (guarantee_views / 1000) * TARGET_CPM

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


def compute_offer_with_claude_review(
    stats: ScrapedStats,
    num_videos: int = NUM_VIDEOS,
    brand_name: Optional[str] = None,
) -> PriceOffer:
    """
    Compute the CPM-based offer, then pass it to Claude for a sanity check.
    Claude may adjust the budget_cap or flag anomalies.
    Returns the (possibly adjusted) PriceOffer.
    """
    brand_name = brand_name or DEFAULT_BRAND_NAME
    offer = compute_offer(stats, num_videos)

    system_prompt = f"""You are a pricing advisor for INFLUENCE, a social media marketing agency.
You have been given a CPM-based price offer computed from an Instagram creator's scraped view statistics.
Brand: {brand_name}. Target CPM: ${TARGET_CPM}. Risk buffer: {RISK_BUFFER*100:.0f}%.

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


# ── Six-offer generation ────────────────────────────────────────────────────────────────────────────

def _build_raw_six_offers(
    stats: ScrapedStats,
    max_cpm: float,
    creator_quoted_rate: Optional[float],
) -> List[SuggestedOffer]:
    """
    Pre-compute 6 offers without Claude. These are fed to Claude for annotation.

    View-based (creator paid when view target is met):
      view_1 Conservative: min_views x effective_cpm
      view_2 Standard:     p25_views x effective_cpm
      view_3 Optimistic:   p50_views x effective_cpm

    Video-count flat (pay regardless of views):
      video_1: 1 video  x p25/1000 x effective_cpm
      video_2: 2 videos x p25/1000 x effective_cpm
      video_3: 3 videos x p25/1000 x effective_cpm
    """
    effective_cpm = max_cpm * (1 - RISK_BUFFER)
    min_views = min(stats.views) if stats.views else int(stats.p10)

    def satisfies(fee: float) -> bool:
        return creator_quoted_rate is not None and fee >= creator_quoted_rate

    view_tiers = [
        ("view_1", "Conservative View Deal", max(_round_to_nearest(min_views, 25_000), 25_000)),
        ("view_2", "Standard View Deal",     max(_round_to_nearest(int(stats.p25), 25_000), 25_000)),
        ("view_3", "Optimistic View Deal",   max(_round_to_nearest(int(stats.p50), 25_000), 25_000)),
    ]

    offers: List[SuggestedOffer] = []

    for offer_id, label, view_count in view_tiers:
        fee = round((view_count / 1000) * effective_cpm, 2)
        offers.append(SuggestedOffer(
            offer_id=offer_id,
            offer_type="view_based",
            label=label,
            num_videos=1,
            flat_fee=fee,
            flat_per_video=fee,
            view_guarantee=view_count,
            cpm_applied=round(effective_cpm, 2),
            satisfies_creator_rate=satisfies(fee),
            notes="",
        ))

    flat_per_vid = round((stats.p25 / 1000) * effective_cpm, 2)
    for num_vids in [1, 2, 3]:
        total = round(flat_per_vid * num_vids, 2)
        plural = "s" if num_vids > 1 else ""
        offers.append(SuggestedOffer(
            offer_id=f"video_{num_vids}",
            offer_type="video_based",
            label=f"{num_vids} Video{plural} Flat Deal",
            num_videos=num_vids,
            flat_fee=total,
            flat_per_video=flat_per_vid,
            view_guarantee=0,
            cpm_applied=round(effective_cpm, 2),
            satisfies_creator_rate=satisfies(total),
            notes="",
        ))

    return offers


def compute_six_offers(
    stats: ScrapedStats,
    max_cpm: float,
    creator_quoted_rate: Optional[float] = None,
    brand_name: Optional[str] = None,
) -> List[SuggestedOffer]:
    """
    Generate 6 AI-annotated deal offers constrained by max_cpm.
    Returns 3 view-based + 3 video-count-based offers.
    Claude adds a strategic one-line note to each offer.
    Falls back to unannotated offers if the Claude call fails.
    """
    brand_name = brand_name or DEFAULT_BRAND_NAME
    offers = _build_raw_six_offers(stats, max_cpm, creator_quoted_rate)

    summary_lines = []
    for o in offers:
        if o.offer_type == "view_based":
            summary_lines.append(
                f"  {o.offer_id}: {o.label} — ${o.flat_fee:.2f} for {o.view_guarantee:,} views "
                f"@ CPM ${o.cpm_applied:.2f} | satisfies_creator_rate={o.satisfies_creator_rate}"
            )
        else:
            summary_lines.append(
                f"  {o.offer_id}: {o.label} — ${o.flat_fee:.2f} flat ({o.num_videos} video{'s' if o.num_videos > 1 else ''}) "
                f"@ CPM ${o.cpm_applied:.2f} | satisfies_creator_rate={o.satisfies_creator_rate}"
            )

    rate_ctx = f"${creator_quoted_rate:.2f}" if creator_quoted_rate else "not yet received"

    system_prompt = f"""You are a pricing strategist for INFLUENCE, a social media marketing agency.
Brand: {brand_name}. Max CPM budget: ${max_cpm}. Risk buffer: {RISK_BUFFER*100:.0f}%.

Review these 6 influencer deal offers and add a brief strategic note (max 15 words) for each.
Focus on: budget efficiency, creator satisfaction, risk vs reward.

Return ONLY a raw JSON array with exactly 6 objects. Each object must have:
  "offer_id": string (unchanged from input)
  "notes": string

No markdown, no extra keys, no preamble."""

    user_msg = (
        f"Creator @{stats.handle} | views p10={stats.p10:.0f} p25={stats.p25:.0f} "
        f"p50={stats.p50:.0f} p75={stats.p75:.0f} | reels={stats.count}\n"
        f"Creator quoted rate: {rate_ctx}\n\n"
        "Offers:\n" + "\n".join(summary_lines)
    )

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        notes_list = json.loads(raw)
        notes_map = {item["offer_id"]: item.get("notes", "") for item in notes_list if "offer_id" in item}
        for offer in offers:
            if offer.offer_id in notes_map:
                offer.notes = notes_map[offer.offer_id]
        logger.info("Claude annotated 6 offers for @%s", stats.handle)
    except Exception as e:
        logger.warning("Claude offer annotation skipped (%s) — returning offers without notes", e)

    return offers


def offers_to_dict_list(offers: List[SuggestedOffer]) -> list:
    """Convert a list of SuggestedOffer to plain dicts for JSON serialization."""
    return [asdict(o) for o in offers]
