"""
State machine that drives the creator negotiation funnel.
Decides what to do next based on creator state + incoming email intent.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import gmail_client
import instagram_scraper
import pricing_engine
import state_store
import templates
from config import FOLLOWUP_DELAY_DAYS, MAX_FOLLOWUPS_PER_STAGE, NUM_VIDEOS
from email_classifier import classify_email
from scraper_utils import ScrapedStats
from models import Creator, EmailIntent, NegotiationState
from pricing_engine import PriceOffer

logger = logging.getLogger(__name__)

_UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(_UTC)


def _send_and_update(
    creator: Creator,
    subject: str,
    body: str,
    new_state: NegotiationState,
    reset_followup: bool = False,
) -> None:
    """Send an email to the creator then persist the updated state."""
    if creator.gmail_thread_id:
        gmail_client.send_reply(
            thread_id=creator.gmail_thread_id,
            to_email=creator.creator_email,
            subject=subject,
            body=body,
        )
    else:
        logger.warning("No thread_id for %s — cannot send reply.", creator.creator_email)
        return

    creator.state = new_state
    creator.last_email_sent_at = _now()
    if reset_followup:
        creator.follow_up_count = 0
    state_store.upsert_creator(creator)
    logger.info("State → %s for %s", new_state.value, creator.creator_email)


# ──────────────────────────────────────────────
# Scraping helper
# ──────────────────────────────────────────────

def _scrape_and_store(creator: Creator) -> Optional[ScrapedStats]:
    """
    Scrape the creator's Instagram reels page (opens/closes a Chrome tab),
    store the percentile stats on the creator object.
    Returns the ScrapedStats or None if scraping failed.
    """
    if not creator.instagram_handle:
        logger.warning("No Instagram handle for %s — cannot scrape", creator.creator_email)
        return None

    stats = instagram_scraper.scrape_creator_reels(creator.instagram_handle)
    if not stats:
        return None

    creator.scraped_p10 = stats.p10
    creator.scraped_p25 = stats.p25
    creator.scraped_p50 = stats.p50
    creator.scraped_p75 = stats.p75
    creator.scraped_reel_count = stats.count
    state_store.upsert_creator(creator)
    return stats


# ──────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────

def handle_new_interest(creator: Creator) -> None:
    """
    Called when a creator is first seeded as INTERESTED.
    Sends Reply 1 and moves them to AWAITING_RATE.
    Instagram stats are scraped proactively so pricing is ready when they reply.
    """
    # Scrape in the background so we have data when they send their rate
    if creator.instagram_handle and not creator.scraped_p25:
        logger.info("Pre-scraping @%s before sending Reply 1", creator.instagram_handle)
        _scrape_and_store(creator)

    subject, body = templates.reply1(creator_name=creator.creator_name)
    _send_and_update(creator, subject, body, NegotiationState.AWAITING_RATE, reset_followup=True)


def handle_incoming_email(creator: Creator, email_body: str) -> None:
    """
    Process an incoming email from a creator and take the appropriate action.
    This is the main dispatch function called by the polling loop.
    """
    intent, extracted_rate, notes = classify_email(email_body, creator.creator_name)
    logger.info(
        "Creator %s | state=%s | intent=%s | notes=%s",
        creator.creator_email, creator.state.value, intent.value, notes,
    )

    # Ignore emails in terminal states
    if creator.state in (NegotiationState.CLOSED, NegotiationState.ACCEPTED):
        logger.info("Ignoring email — creator is in terminal state %s", creator.state)
        return

    if intent == EmailIntent.NOT_INTERESTED:
        creator.state = NegotiationState.CLOSED
        state_store.upsert_creator(creator)
        logger.info("Closing negotiation for %s (not interested)", creator.creator_email)
        return

    if intent == EmailIntent.DELAY_REQUEST:
        subject, body = templates.delay_email(creator_name=creator.creator_name)
        _send_and_update(creator, subject, body, NegotiationState.DELAYED)
        return

    if intent == EmailIntent.ASKING_DETAILS:
        if creator.state in (NegotiationState.AWAITING_RATE, NegotiationState.REPLY1_SENT):
            subject, body = templates.reply1(creator_name=creator.creator_name)
            _send_and_update(creator, subject, body, NegotiationState.AWAITING_RATE, reset_followup=True)
        return

    if intent in (EmailIntent.RATE_SHARED, EmailIntent.HIGH_RATE, EmailIntent.COUNTER_OFFER):
        _handle_rate_received(creator, extracted_rate, intent)
        return

    if intent == EmailIntent.ACCEPTED:
        _handle_acceptance(creator)
        return

    logger.warning(
        "UNKNOWN intent from %s — manual review needed. Body: %.200s",
        creator.creator_email, email_body,
    )


def _handle_rate_received(
    creator: Creator,
    extracted_rate: Optional[float],
    intent: EmailIntent,
) -> None:
    """Creator shared a rate. Scrape IG data (if not already done), compute offer, respond."""
    if extracted_rate:
        creator.quoted_rate = extracted_rate

    # Scrape if not already done
    stats = None
    if creator.scraped_p25:
        # Re-use existing scraped data
        stats = ScrapedStats(
            handle=creator.instagram_handle or "",
            views=[],
            p10=creator.scraped_p10 or 0,
            p25=creator.scraped_p25,
            p50=creator.scraped_p50 or 0,
            p75=creator.scraped_p75 or 0,
            count=creator.scraped_reel_count or 0,
        )
        logger.info("Using cached scraped stats for @%s", creator.instagram_handle)
    elif creator.instagram_handle:
        logger.info("Scraping @%s now (rate received)", creator.instagram_handle)
        stats = _scrape_and_store(creator)

    if not stats:
        logger.warning(
            "Cannot compute offer for %s — no Instagram data. "
            "Set instagram_handle via seed.py and ensure Chrome is logged in.",
            creator.creator_email,
        )
        return

    try:
        offer: PriceOffer = pricing_engine.compute_offer_with_claude_review(stats, num_videos=NUM_VIDEOS)
    except Exception as e:
        logger.error("Pricing failed for %s: %s", creator.creator_email, e)
        return

    # Store offer on creator record
    creator.our_offer_flat_per_video = offer.flat_rate_per_video
    creator.our_offer_b_flat = offer.option_b_flat
    creator.our_offer_b_bonus = offer.option_b_bonus
    creator.our_offer_b_view_target = offer.option_b_view_target
    creator.our_offer_c_views = offer.option_c_guarantee_views
    creator.our_offer_c_price = offer.option_c_price
    creator.budget_cap = offer.budget_cap
    creator.video_count = offer.video_count

    # If quoted rate is WAY above budget cap, reject immediately
    if extracted_rate and extracted_rate > offer.budget_cap * 1.5:
        subject, body = templates.high_rate_rejection(
            creator_name=creator.creator_name,
            quoted_rate=extracted_rate,
        )
        _send_and_update(creator, subject, body, NegotiationState.HIGH_RATE_REJECTED)
        return

    # Build Reply 2 using scraped view data
    subject, body = templates.reply2(
        creator_name=creator.creator_name,
        flat_rate=offer.option_b_flat,
        flat_bonus_threshold_views=offer.option_b_view_target,
        flat_bonus_amount=offer.option_b_bonus,
        view_based_rate=offer.option_c_price,
        view_target=offer.option_c_guarantee_views,
        avg_views=int(stats.p50),
        video_count=offer.video_count,
    )
    _send_and_update(
        creator, subject, body,
        NegotiationState.AWAITING_DECISION,
        reset_followup=True,
    )


def _handle_acceptance(creator: Creator) -> None:
    subject, body = templates.acceptance_confirmation(creator_name=creator.creator_name)
    _send_and_update(creator, subject, body, NegotiationState.ACCEPTED)


# ──────────────────────────────────────────────
# Follow-up scheduler
# ──────────────────────────────────────────────

def run_followups() -> None:
    """
    Check all creators who are waiting for a reply.
    If FOLLOWUP_DELAY_DAYS have passed, send the appropriate follow-up email.
    """
    cutoff = _now() - timedelta(days=FOLLOWUP_DELAY_DAYS)
    creators = state_store.get_creators_needing_followup(cutoff)
    logger.info("Follow-up check: %d creators overdue", len(creators))

    for creator in creators:
        if creator.follow_up_count >= MAX_FOLLOWUPS_PER_STAGE:
            creator.state = NegotiationState.CLOSED
            state_store.upsert_creator(creator)
            logger.info("Closing %s — max follow-ups reached", creator.creator_email)
            continue

        if creator.state == NegotiationState.AWAITING_RATE:
            subject, body = templates.followup1(creator_name=creator.creator_name)
            new_state = NegotiationState.AWAITING_RATE
        elif creator.state == NegotiationState.AWAITING_DECISION:
            subject, body = templates.followup2(creator_name=creator.creator_name)
            new_state = NegotiationState.AWAITING_DECISION
        else:
            continue

        creator.follow_up_count += 1
        _send_and_update(creator, subject, body, new_state)
