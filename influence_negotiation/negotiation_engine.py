"""
State machine that drives the creator negotiation funnel.
Decides what to do next based on creator state + incoming email intent.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import gmail_client
import pricing_engine
import state_store
import templates
from config import FOLLOWUP_DELAY_DAYS, MAX_FOLLOWUPS_PER_STAGE
from email_classifier import classify_email
from models import Creator, EmailIntent, NegotiationState

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
# Entry points
# ──────────────────────────────────────────────

def handle_new_interest(creator: Creator) -> None:
    """
    Called when a creator is first seeded as INTERESTED.
    Sends Reply 1 and moves them to AWAITING_RATE.
    """
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

    # Creator is still asking questions — resend details or just wait
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

    # UNKNOWN — log for human review, don't take action
    logger.warning(
        "UNKNOWN intent from %s — manual review needed. Body: %.200s",
        creator.creator_email, email_body,
    )


def _handle_rate_received(
    creator: Creator,
    extracted_rate: Optional[float],
    intent: EmailIntent,
) -> None:
    """Creator shared a rate. Compute offer and respond."""
    if extracted_rate:
        creator.quoted_rate = extracted_rate

    # Need metrics to compute offer
    if not (creator.followers and creator.avg_views):
        logger.warning(
            "Cannot compute offer for %s — missing Instagram metrics. Please update via seed_creator().",
            creator.creator_email,
        )
        return

    try:
        offer = pricing_engine.compute_offer(
            instagram_handle=creator.instagram_handle or creator.creator_email,
            followers=creator.followers,
            avg_views=creator.avg_views,
            engagement_rate=creator.engagement_rate or 0.0,
        )
    except Exception as e:
        logger.error("Pricing failed for %s: %s", creator.creator_email, e)
        return

    # Store offer details
    creator.our_offer_flat = offer.flat_rate
    creator.our_offer_view_rate = offer.view_based_rate
    creator.our_offer_view_target = offer.view_target
    creator.our_offer_flat_bonus_threshold = offer.flat_bonus_threshold_views
    creator.our_offer_flat_bonus_amount = offer.flat_bonus_amount
    creator.our_offer_video_count = offer.video_count
    creator.budget_cap = offer.budget_cap

    # If quoted rate is WAY above budget cap, reject immediately
    if extracted_rate and extracted_rate > offer.budget_cap * 1.5:
        subject, body = templates.high_rate_rejection(
            creator_name=creator.creator_name,
            quoted_rate=extracted_rate,
        )
        _send_and_update(creator, subject, body, NegotiationState.HIGH_RATE_REJECTED)
        return

    # Send our offer
    subject, body = templates.reply2(
        creator_name=creator.creator_name,
        flat_rate=offer.flat_rate,
        flat_bonus_threshold_views=offer.flat_bonus_threshold_views,
        flat_bonus_amount=offer.flat_bonus_amount,
        view_based_rate=offer.view_based_rate,
        view_target=offer.view_target,
        avg_views=creator.avg_views,
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
