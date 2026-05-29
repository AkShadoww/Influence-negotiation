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
