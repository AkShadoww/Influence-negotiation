"""Tests for pricing_engine — uses mocked Anthropic responses and real CPM math."""

import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

# Import ScrapedStats from conftest stub (real playwright unavailable in sandbox)
from scraper_utils import ScrapedStats


def _make_stats(p10=20000, p25=40000, p50=60000, p75=90000, count=12) -> ScrapedStats:
    return ScrapedStats(
        handle="testhandle",
        views=[p10, p25, p50, p75] * 3,
        p10=p10, p25=p25, p50=p50, p75=p75,
        count=count,
    )


def test_compute_offer_basic_cpm_math():
    """Option A flat/video = (p25 / 1000) * TARGET_CPM * (1 - RISK_BUFFER)."""
    from pricing_engine import compute_offer
    import config
    stats = _make_stats(p25=40_000)
    offer = compute_offer(stats, num_videos=2)

    expected_flat_per_video = (40_000 / 1000) * config.TARGET_CPM * (1 - config.RISK_BUFFER)
    assert abs(offer.flat_rate_per_video - expected_flat_per_video) < 0.01


def test_compute_offer_option_b_includes_bonus():
    """Option B total = flat + 20% bonus."""
    from pricing_engine import compute_offer
    stats = _make_stats(p25=40_000)
    offer = compute_offer(stats, num_videos=2)

    assert abs(offer.option_b_total - (offer.option_b_flat + offer.option_b_bonus)) < 0.01
    assert abs(offer.option_b_bonus - offer.option_b_flat * 0.20) < 0.01


def test_compute_offer_option_c_no_risk_buffer():
    """Option C uses full TARGET_CPM (no risk buffer) on p75 views."""
    from pricing_engine import compute_offer
    import config
    stats = _make_stats(p75=90_000)
    offer = compute_offer(stats)
    # guarantee_views = round_to_nearest(90000, 25000) = 75000
    # option_c_price = (75000 / 1000) * 15 = 1125
    assert offer.option_c_guarantee_views % 25_000 == 0
    expected = (offer.option_c_guarantee_views / 1000) * config.TARGET_CPM
    assert abs(offer.option_c_price - expected) < 0.01


def test_compute_offer_budget_cap_above_option_b():
    from pricing_engine import compute_offer
    stats = _make_stats()
    offer = compute_offer(stats)
    assert offer.budget_cap > offer.option_b_total


def test_compute_offer_view_target_rounded_to_25k():
    from pricing_engine import compute_offer
    stats = _make_stats(p25=50_000)
    offer = compute_offer(stats)
    assert offer.option_b_view_target % 25_000 == 0


@patch("pricing_engine._client")
def test_claude_review_adjusts_budget_cap(mock_client):
    """Claude can override budget_cap — other fields stay unchanged."""
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps({"budget_cap": 9999.0, "notes": "test override"}))]
    )
    from pricing_engine import compute_offer_with_claude_review
    stats = _make_stats()
    offer = compute_offer_with_claude_review(stats)
    assert offer.budget_cap == 9999.0


@patch("pricing_engine._client")
def test_claude_review_falls_back_on_bad_json(mock_client):
    """If Claude returns garbage, we keep the computed offer unchanged."""
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="not json")]
    )
    from pricing_engine import compute_offer, compute_offer_with_claude_review
    stats = _make_stats()
    original = compute_offer(stats)
    reviewed = compute_offer_with_claude_review(stats)
    assert abs(reviewed.budget_cap - original.budget_cap) < 0.01
