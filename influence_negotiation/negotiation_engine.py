"""
State machine that drives the creator negotiation funnel.
Decides what to do next based on creator state + incoming email intent.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
import gmail_client
import instagram_scraper
import outreach_sync
import pricing_engine
import state_store
import templates
from config import FOLLOWUP_DELAY_DAYS, MAX_CPM, MAX_FOLLOWUPS_PER_STAGE, NUM_VIDEOS
from email_classifier import classify_email
from models import Creator, EmailIntent, NegotiationState
from pricing_engine import PriceOffer
from scraper_utils import ScrapedStats

logger = logging.getLogger(__name__)

_UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(_UTC)


def _brand_ctx(creator: Creator) -> dict:
    """Per-campaign branding for email templates. None values fall back to config defaults."""
    return {
        "brand_name": creator.brand_name,
        "campaign_deadline": creator.campaign_deadline,
    }


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
# Scraping helpers
# ──────────────────────────────────────────────

def _scrape_and_store(creator: Creator) -> Optional[ScrapedStats]:
    """
    Scrape the creator's Instagram reels page, store percentile stats + raw views.
    Returns ScrapedStats or None if scraping failed.
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
    creator.scraped_min_views = min(stats.views) if stats.views else int(stats.p10)
    creator.scraped_views_raw = json.dumps(stats.views)
    state_store.upsert_creator(creator)
    return stats


def _campaign_info(creator: Creator) -> Optional[dict]:
    """Pull the campaign's max_cpm + admin-approved offer from the outreach dashboard."""
    return outreach_sync.fetch_campaign_offer(creator.instagram_handle, creator.brand_name)


def _effective_max_cpm(info: Optional[dict]) -> float:
    """Per-campaign max_cpm from the dashboard, falling back to the env default."""
    if info and info.get("max_cpm") is not None:
        try:
            return float(info["max_cpm"])
        except (TypeError, ValueError):
            pass
    return MAX_CPM


def _compute_and_push_offers(creator: Creator, stats: ScrapedStats) -> None:
    """
    Generate 6 AI-suggested offers and push them to the outreach dashboard.
    The max_cpm honors the campaign's dashboard setting when available, else env.
    """
    try:
        max_cpm = _effective_max_cpm(_campaign_info(creator))
        offers = pricing_engine.compute_six_offers(
            stats=stats,
            max_cpm=max_cpm,
            creator_quoted_rate=creator.quoted_rate,
            brand_name=creator.brand_name,
        )
        offers_list = pricing_engine.offers_to_dict_list(offers)
        creator.suggested_offers_json = json.dumps(offers_list)
        state_store.upsert_creator(creator)
        outreach_sync.push_creator_data(creator, offers_list)
    except Exception as e:
        logger.error("Offer computation/push failed for @%s: %s", creator.instagram_handle, e)


# ──────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────

def import_replied_creators() -> None:
    """
    Pull creators who replied to outreach from the dashboard and seed any new
    ones into the funnel. Claude reads each creator's reply: if they declined,
    the negotiation is closed immediately; otherwise we kick off Reply 1.

    De-duped by email — creators already in our DB are skipped, so this is safe
    to run every poll tick.
    """
    if not config.AUTO_IMPORT_REPLIED:
        return

    items = outreach_sync.fetch_replied_creators()
    if not items:
        return

    imported = 0
    for item in items:
        email = (item.get("email") or "").strip()
        thread_id = (item.get("outreach_thread_id") or "").strip()
        if not email or not thread_id:
            continue
        try:
            if state_store.get_creator(email):
                continue  # already in the funnel

            name = (item.get("first_name") or item.get("full_name") or email.split("@")[0]).strip()
            handle = item.get("instagram_username") or None

            creator = state_store.seed_creator(
                creator_email=email,
                creator_name=name,
                instagram_handle=handle,
                brand_name=item.get("brand_name"),
            )
            creator.gmail_thread_id = thread_id
            state_store.upsert_creator(creator)

            # Read their outreach reply with Claude before pitching, so we don't
            # pitch someone who declined. Best-effort — if Gmail is unavailable we
            # proceed and let Reply 1 go out. Mark read so it isn't re-classified.
            intent = EmailIntent.UNKNOWN
            try:
                msgs = gmail_client.get_unread_messages_in_thread(thread_id)
                if msgs:
                    intent, _, _ = classify_email(msgs[0]["body"], creator.creator_name)
                for m in msgs:
                    gmail_client.mark_as_read(m["id"])
            except Exception as e:
                logger.warning("Could not read/mark thread %s for %s: %s", thread_id, email, e)

            if intent == EmailIntent.NOT_INTERESTED:
                creator.state = NegotiationState.CLOSED
                state_store.upsert_creator(creator)
                logger.info("Imported %s but they declined in outreach — closed", email)
                continue

            imported += 1
            logger.info("Imported replied creator %s (@%s) — Reply 1 will follow this tick", email, handle or "—")
        except Exception as e:
            logger.error("Failed to import replied creator %s: %s", email, e)

    if imported:
        # Reply 1 is sent by the initial-reply step that runs next in the poll tick
        # (per-creator error-isolated), so a bad scrape/send won't block the others.
        logger.info("Imported %d new replied creator(s) into the negotiation funnel", imported)


def handle_new_interest(creator: Creator) -> None:
    """
    Called when a creator is first seeded as INTERESTED.
    Sends Reply 1 immediately and moves them to AWAITING_RATE.

    Instagram is NOT scraped here. Every creator who replied to outreach gets
    Reply 1 right away (a quick Gmail send), instead of each one waiting behind a
    ~30-60s headless-Chrome scrape. The scrape happens lazily, per creator, when
    they actually share their rate (in _handle_rate_received).
    """
    subject, body = templates.reply1(creator_name=creator.creator_name, **_brand_ctx(creator))
    _send_and_update(creator, subject, body, NegotiationState.AWAITING_RATE, reset_followup=True)


def handle_incoming_email(creator: Creator, email_body: str) -> None:
    """
    Process an incoming email from a creator and take the appropriate action.
    """
    intent, extracted_rate, notes = classify_email(email_body, creator.creator_name)
    logger.info(
        "Creator %s | state=%s | intent=%s | notes=%s",
        creator.creator_email, creator.state.value, intent.value, notes,
    )

    if creator.state in (NegotiationState.CLOSED, NegotiationState.ACCEPTED):
        logger.info("Ignoring email — creator is in terminal state %s", creator.state)
        return

    if intent == EmailIntent.NOT_INTERESTED:
        creator.state = NegotiationState.CLOSED
        state_store.upsert_creator(creator)
        logger.info("Closing negotiation for %s (not interested)", creator.creator_email)
        return

    if intent == EmailIntent.DELAY_REQUEST:
        subject, body = templates.delay_email(creator_name=creator.creator_name, **_brand_ctx(creator))
        _send_and_update(creator, subject, body, NegotiationState.DELAYED)
        return

    if intent == EmailIntent.ASKING_DETAILS:
        if creator.state in (NegotiationState.AWAITING_RATE, NegotiationState.REPLY1_SENT):
            subject, body = templates.reply1(creator_name=creator.creator_name, **_brand_ctx(creator))
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
    """Creator shared a rate. Scrape IG data if needed, compute offers, respond."""
    if extracted_rate:
        creator.quoted_rate = extracted_rate

    stats = None
    if creator.scraped_p25:
        stats = ScrapedStats(
            handle=creator.instagram_handle or "",
            views=json.loads(creator.scraped_views_raw) if creator.scraped_views_raw else [],
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

    # Recompute 6 offers now that we have the creator's quoted rate
    _compute_and_push_offers(creator, stats)

    try:
        offer: PriceOffer = pricing_engine.compute_offer_with_claude_review(
            stats, num_videos=NUM_VIDEOS, brand_name=creator.brand_name,
        )
    except Exception as e:
        logger.error("Pricing failed for %s: %s", creator.creator_email, e)
        return

    creator.our_offer_flat_per_video = offer.flat_rate_per_video
    creator.our_offer_b_flat = offer.option_b_flat
    creator.our_offer_b_bonus = offer.option_b_bonus
    creator.our_offer_b_view_target = offer.option_b_view_target
    creator.our_offer_c_views = offer.option_c_guarantee_views
    creator.our_offer_c_price = offer.option_c_price
    creator.budget_cap = offer.budget_cap
    creator.video_count = offer.video_count

    if extracted_rate and extracted_rate > offer.budget_cap * 1.5:
        subject, body = templates.high_rate_rejection(
            creator_name=creator.creator_name,
            quoted_rate=extracted_rate,
            **_brand_ctx(creator),
        )
        _send_and_update(creator, subject, body, NegotiationState.HIGH_RATE_REJECTED)
        return

    # Decide what to email. Priority:
    #   1. The exact offer an admin approved in the dashboard.
    #   2. Hold for approval (if required + dashboard configured + creator known there).
    #   3. Fall back to the computed Option A/B/C offer.
    info = _campaign_info(creator)
    approved = info.get("approved_offer") if info else None
    if approved:
        logger.info("Using admin-approved offer for %s", creator.creator_email)
        _send_offer_email(creator, approved)
        return

    found_in_outreach = bool(info and info.get("found"))
    if config.REQUIRE_OFFER_APPROVAL and config.OUTREACH_API_URL and found_in_outreach:
        creator.state = NegotiationState.AWAITING_APPROVAL
        state_store.upsert_creator(creator)
        logger.info(
            "Rate received for %s — holding for admin offer approval in dashboard",
            creator.creator_email,
        )
        return

    subject, body = templates.reply2(
        creator_name=creator.creator_name,
        flat_rate=offer.option_b_flat,
        flat_bonus_threshold_views=offer.option_b_view_target,
        flat_bonus_amount=offer.option_b_bonus,
        view_based_rate=offer.option_c_price,
        view_target=offer.option_c_guarantee_views,
        avg_views=int(stats.p50),
        video_count=offer.video_count,
        **_brand_ctx(creator),
    )
    _send_and_update(
        creator, subject, body,
        NegotiationState.AWAITING_DECISION,
        reset_followup=True,
    )


def _handle_acceptance(creator: Creator) -> None:
    subject, body = templates.acceptance_confirmation(creator_name=creator.creator_name, **_brand_ctx(creator))
    _send_and_update(creator, subject, body, NegotiationState.ACCEPTED)


def _send_offer_email(creator: Creator, offer: dict) -> None:
    """Email the single offer an admin approved in the dashboard, then await the decision."""
    subject, body = templates.reply2_approved(
        creator_name=creator.creator_name,
        offer=offer,
        **_brand_ctx(creator),
    )
    _send_and_update(creator, subject, body, NegotiationState.AWAITING_DECISION, reset_followup=True)


def process_pending_approvals() -> None:
    """
    For creators holding in AWAITING_APPROVAL, check whether an admin has approved
    an offer in the outreach dashboard yet. If so, send Reply 2 with that offer.
    Runs every poll tick alongside email processing.
    """
    creators = [
        c for c in state_store.get_active_creators()
        if c.state == NegotiationState.AWAITING_APPROVAL
    ]
    if not creators:
        return
    logger.info("Approval check: %d creator(s) awaiting admin approval", len(creators))
    for creator in creators:
        info = _campaign_info(creator)
        approved = info.get("approved_offer") if info else None
        if approved:
            logger.info("Offer approved for %s — sending Reply 2", creator.creator_email)
            _send_offer_email(creator, approved)


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
            subject, body = templates.followup1(creator_name=creator.creator_name, **_brand_ctx(creator))
            new_state = NegotiationState.AWAITING_RATE
        elif creator.state == NegotiationState.AWAITING_DECISION:
            subject, body = templates.followup2(creator_name=creator.creator_name, **_brand_ctx(creator))
            new_state = NegotiationState.AWAITING_DECISION
        else:
            continue

        creator.follow_up_count += 1
        _send_and_update(creator, subject, body, new_state)
