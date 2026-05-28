"""Tests for pricing_engine — uses mocked Anthropic responses."""

import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))


def _mock_offer_response(**overrides):
    defaults = {
        "flat_rate": 800,
        "flat_bonus_threshold_views": 150000,
        "flat_bonus_amount": 300,
        "view_based_rate": 600,
        "view_target": 80000,
        "video_count": 2,
        "budget_cap": 960,
    }
    defaults.update(overrides)
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(defaults))]
    return msg


@patch("pricing_engine._client")
def test_compute_offer_returns_price_offer(mock_client):
    mock_client.messages.create.return_value = _mock_offer_response()
    from pricing_engine import compute_offer
    from models import PriceOffer
    offer = compute_offer("testhandle", followers=80000, avg_views=40000, engagement_rate=4.5)
    assert isinstance(offer, PriceOffer)
    assert offer.flat_rate == 800.0
    assert offer.budget_cap == 960.0
    assert offer.video_count == 2


@patch("pricing_engine._client")
def test_compute_offer_nano_creator(mock_client):
    mock_client.messages.create.return_value = _mock_offer_response(
        flat_rate=250, view_target=25000, budget_cap=300
    )
    from pricing_engine import compute_offer
    offer = compute_offer("nanohandle", followers=5000, avg_views=3000, engagement_rate=6.0)
    assert offer.flat_rate == 250.0
    assert offer.view_target == 25000


@patch("pricing_engine._client")
def test_compute_offer_bad_json_raises(mock_client):
    import pytest
    msg = MagicMock()
    msg.content = [MagicMock(text="invalid json")]
    mock_client.messages.create.return_value = msg
    from pricing_engine import compute_offer
    with pytest.raises(ValueError):
        compute_offer("badhandle", 10000, 5000, 3.0)
