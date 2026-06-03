"""Tests for negotiation_engine state transitions."""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

import negotiation_engine

from scraper_utils import ScrapedStats
from models import Creator, EmailIntent, NegotiationState
from pricing_engine import PriceOffer


def _make_creator(**kwargs) -> Creator:
    defaults = dict(
        creator_email="test@example.com",
        creator_name="Test Creator",
        state=NegotiationState.AWAITING_RATE,
        gmail_thread_id="thread_123",
        instagram_handle="testhandle",
        scraped_p25=40_000.0,
        scraped_p75=90_000.0,
        scraped_p10=15_000.0,
        scraped_p50=60_000.0,
        scraped_reel_count=12,
    )
    defaults.update(kwargs)
    return Creator(**defaults)


def _mock_offer() -> PriceOffer:
    return PriceOffer(
        flat_rate_per_video=480.0,
        flat_rate_total=960.0,
        option_b_flat=960.0,
        option_b_bonus=192.0,
        option_b_total=1152.0,
        option_b_view_target=75_000,
        option_c_guarantee_views=75_000,
        option_c_price=1125.0,
        budget_cap=1324.0,
        video_count=2,
        p25_views=40_000,
        p75_views=75_000,
        effective_cpm=12.0,
    )


def test_rate_shared_sends_offer():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate given")):
        with patch("pricing_engine.compute_offer_with_claude_review", return_value=_mock_offer()):
            creator = _make_creator()
            negotiation_engine.handle_incoming_email(creator, "My rate is $500 per video.")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.AWAITING_DECISION
    assert creator.quoted_rate == 500.0


def test_not_interested_closes():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.NOT_INTERESTED, None, "declining")):
        creator = _make_creator()
        negotiation_engine.handle_incoming_email(creator, "Thanks but I'll pass.")

    gmail_client.send_reply.assert_not_called()
    assert creator.state == NegotiationState.CLOSED


def test_acceptance():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.ACCEPTED, None, "agreed")):
        creator = _make_creator(state=NegotiationState.AWAITING_DECISION)
        negotiation_engine.handle_incoming_email(creator, "Sounds great, let's do it!")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.ACCEPTED


def test_high_rate_rejection():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 5000.0, "very high")):
        with patch("pricing_engine.compute_offer_with_claude_review", return_value=_mock_offer()):
            creator = _make_creator()
            negotiation_engine.handle_incoming_email(creator, "I charge $5000 per video.")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.HIGH_RATE_REJECTED


def test_delay_sends_delay_email():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.DELAY_REQUEST, None, "busy")):
        creator = _make_creator()
        negotiation_engine.handle_incoming_email(creator, "Not available this month.")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.DELAYED


def test_no_scraped_data_no_offer_sent():
    """If no Instagram data and scraping fails, no offer email is sent."""
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate")):
        with patch("instagram_scraper.scrape_creator_reels", return_value=None):
            creator = _make_creator(
                scraped_p25=None, scraped_p75=None,
                scraped_p10=None, scraped_p50=None,
            )
            negotiation_engine.handle_incoming_email(creator, "My rate is $500.")

    gmail_client.send_reply.assert_not_called()


# ── Offer approval gate ──────────────────────────────────────────────────────

def test_rate_with_approved_offer_emails_it():
    """If the admin has already approved an offer, Reply 2 uses it immediately."""
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    info = {"found": True, "approved_offer": {
        "offer_type": "video_flat", "flat_fee": 960, "num_videos": 2, "flat_per_video": 480,
    }}
    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate")), \
         patch("pricing_engine.compute_offer_with_claude_review", return_value=_mock_offer()), \
         patch.object(negotiation_engine, "_compute_and_push_offers"), \
         patch.object(negotiation_engine, "_campaign_info", return_value=info):
        creator = _make_creator()
        negotiation_engine.handle_incoming_email(creator, "My rate is $500.")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.AWAITING_DECISION


def test_rate_holds_for_approval_when_required():
    """With approval required and no offer approved yet, no email is sent and we wait."""
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    info = {"found": True, "approved_offer": None}
    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate")), \
         patch("pricing_engine.compute_offer_with_claude_review", return_value=_mock_offer()), \
         patch.object(negotiation_engine, "_compute_and_push_offers"), \
         patch.object(negotiation_engine, "_campaign_info", return_value=info), \
         patch("config.REQUIRE_OFFER_APPROVAL", True), \
         patch("config.OUTREACH_API_URL", "http://dashboard"):
        creator = _make_creator()
        negotiation_engine.handle_incoming_email(creator, "My rate is $500.")

    gmail_client.send_reply.assert_not_called()
    assert creator.state == NegotiationState.AWAITING_APPROVAL


def test_rate_sends_legacy_offer_when_approval_disabled():
    """With approval disabled and nothing approved, fall back to computed Option A/B/C."""
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    info = {"found": True, "approved_offer": None}
    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate")), \
         patch("pricing_engine.compute_offer_with_claude_review", return_value=_mock_offer()), \
         patch.object(negotiation_engine, "_compute_and_push_offers"), \
         patch.object(negotiation_engine, "_campaign_info", return_value=info), \
         patch("config.REQUIRE_OFFER_APPROVAL", False):
        creator = _make_creator()
        negotiation_engine.handle_incoming_email(creator, "My rate is $500.")

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.AWAITING_DECISION


def test_process_pending_approvals_sends_when_approved():
    """A held creator gets Reply 2 once an admin approves an offer."""
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    creator = _make_creator(state=NegotiationState.AWAITING_APPROVAL)
    state_store.get_active_creators = MagicMock(return_value=[creator])

    info = {"found": True, "approved_offer": {
        "offer_type": "view_based", "flat_fee": 1125, "view_guarantee": 75_000,
    }}
    with patch.object(negotiation_engine, "_campaign_info", return_value=info):
        negotiation_engine.process_pending_approvals()

    gmail_client.send_reply.assert_called_once()
    assert creator.state == NegotiationState.AWAITING_DECISION


# ── Auto-import of replied creators (outreach → negotiation bridge) ───────────

def test_import_replied_seeds_and_leaves_for_reply1():
    import state_store
    import gmail_client
    state_store.get_creator = MagicMock(return_value=None)
    seeded = _make_creator(state=NegotiationState.INTERESTED)
    state_store.seed_creator = MagicMock(return_value=seeded)
    state_store.upsert_creator = MagicMock()
    gmail_client.get_unread_messages_in_thread = MagicMock(return_value=[{"id": "m1", "body": "Hi, I'm interested!"}])
    gmail_client.mark_as_read = MagicMock()

    item = {"email": "new@example.com", "first_name": "New", "instagram_username": "newh",
            "outreach_thread_id": "T1", "brand_name": "Acme"}
    with patch.object(negotiation_engine.outreach_sync, "fetch_replied_creators", return_value=[item]), \
         patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.ASKING_DETAILS, None, "")), \
         patch("config.AUTO_IMPORT_REPLIED", True):
        negotiation_engine.import_replied_creators()

    state_store.seed_creator.assert_called_once()
    # Left INTERESTED with the thread set — the initial-reply step sends Reply 1 next.
    assert seeded.state == NegotiationState.INTERESTED
    assert seeded.gmail_thread_id == "T1"
    gmail_client.mark_as_read.assert_called_once_with("m1")


def test_import_replied_closes_decliner():
    import state_store
    import gmail_client
    state_store.get_creator = MagicMock(return_value=None)
    seeded = _make_creator(state=NegotiationState.INTERESTED)
    state_store.seed_creator = MagicMock(return_value=seeded)
    state_store.upsert_creator = MagicMock()
    gmail_client.get_unread_messages_in_thread = MagicMock(return_value=[{"id": "m9", "body": "No thanks"}])
    gmail_client.mark_as_read = MagicMock()

    item = {"email": "no@example.com", "first_name": "No", "instagram_username": "noh",
            "outreach_thread_id": "T2", "brand_name": "Acme"}
    with patch.object(negotiation_engine.outreach_sync, "fetch_replied_creators", return_value=[item]), \
         patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.NOT_INTERESTED, None, "")), \
         patch("config.AUTO_IMPORT_REPLIED", True):
        negotiation_engine.import_replied_creators()

    assert seeded.state == NegotiationState.CLOSED


def test_import_replied_skips_existing():
    import state_store
    state_store.get_creator = MagicMock(return_value=_make_creator())  # already in the funnel
    state_store.seed_creator = MagicMock()

    item = {"email": "exists@example.com", "outreach_thread_id": "T3"}
    with patch.object(negotiation_engine.outreach_sync, "fetch_replied_creators", return_value=[item]), \
         patch("config.AUTO_IMPORT_REPLIED", True):
        negotiation_engine.import_replied_creators()

    state_store.seed_creator.assert_not_called()


def test_import_replied_isolates_per_creator_errors():
    """A failure on one creator must not abort the whole import."""
    import state_store
    import gmail_client
    state_store.get_creator = MagicMock(return_value=None)
    state_store.seed_creator = MagicMock(side_effect=RuntimeError("db blip"))
    items = [
        {"email": "a@example.com", "outreach_thread_id": "T1"},
        {"email": "b@example.com", "outreach_thread_id": "T2"},
    ]
    with patch.object(negotiation_engine.outreach_sync, "fetch_replied_creators", return_value=items), \
         patch("config.AUTO_IMPORT_REPLIED", True):
        negotiation_engine.import_replied_creators()  # must not raise

    assert state_store.seed_creator.call_count == 2  # tried both despite the first failing
