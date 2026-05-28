"""Tests for negotiation_engine state transitions."""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

# Import negotiation_engine once after conftest stubs are in place
import negotiation_engine

from models import Creator, EmailIntent, NegotiationState, PriceOffer


def _make_creator(**kwargs) -> Creator:
    defaults = dict(
        creator_email="test@example.com",
        creator_name="Test Creator",
        state=NegotiationState.AWAITING_RATE,
        gmail_thread_id="thread_123",
        instagram_handle="testhandle",
        followers=80000,
        avg_views=40000,
        engagement_rate=4.5,
    )
    defaults.update(kwargs)
    return Creator(**defaults)


def _mock_offer() -> PriceOffer:
    return PriceOffer(
        flat_rate=800, flat_bonus_threshold_views=150000, flat_bonus_amount=300,
        view_based_rate=600, view_target=80000, video_count=2, budget_cap=960,
    )


def test_rate_shared_sends_offer():
    import gmail_client
    import state_store
    gmail_client.send_reply = MagicMock()
    state_store.upsert_creator = MagicMock()

    # Patch the names as they exist in negotiation_engine's own namespace
    with patch.object(negotiation_engine, "classify_email", return_value=(EmailIntent.RATE_SHARED, 500.0, "rate given")):
        with patch("pricing_engine.compute_offer", return_value=_mock_offer()):
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
        with patch("pricing_engine.compute_offer", return_value=_mock_offer()):
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
