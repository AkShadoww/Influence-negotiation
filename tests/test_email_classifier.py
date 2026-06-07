"""Tests for email_classifier — uses mocked Anthropic responses."""

import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

from models import EmailIntent


def _mock_response(intent: str, rate=None, notes="test"):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({"intent": intent, "extracted_rate": rate, "notes": notes}))]
    return msg


@patch("email_classifier._client")
def test_rate_shared(mock_client):
    mock_client.messages.create.return_value = _mock_response("RATE_SHARED", rate=500.0)
    from email_classifier import classify_email
    intent, rate, _ = classify_email("My rate is $500 per video.", "Alice")
    assert intent == EmailIntent.RATE_SHARED
    assert rate == 500.0


@patch("email_classifier._client")
def test_accepted(mock_client):
    mock_client.messages.create.return_value = _mock_response("ACCEPTED")
    from email_classifier import classify_email
    intent, rate, _ = classify_email("Sounds great, I'm in!", "Bob")
    assert intent == EmailIntent.ACCEPTED
    assert rate is None


@patch("email_classifier._client")
def test_not_interested(mock_client):
    mock_client.messages.create.return_value = _mock_response("NOT_INTERESTED")
    from email_classifier import classify_email
    intent, _, _ = classify_email("Thanks but I'll pass.", "Carol")
    assert intent == EmailIntent.NOT_INTERESTED


@patch("email_classifier._client")
def test_delay_request(mock_client):
    mock_client.messages.create.return_value = _mock_response("DELAY_REQUEST")
    from email_classifier import classify_email
    intent, _, _ = classify_email("I'm quite busy this month, let's talk next quarter.", "Dan")
    assert intent == EmailIntent.DELAY_REQUEST


@patch("email_classifier._client")
def test_asking_details(mock_client):
    mock_client.messages.create.return_value = _mock_response("ASKING_DETAILS")
    from email_classifier import classify_email
    intent, _, _ = classify_email("What exactly would the deliverables be?", "Eve")
    assert intent == EmailIntent.ASKING_DETAILS


@patch("email_classifier._client")
def test_unknown_on_bad_json(mock_client):
    msg = MagicMock()
    msg.content = [MagicMock(text="not json at all")]
    mock_client.messages.create.return_value = msg
    from email_classifier import classify_email
    intent, rate, _ = classify_email("some email", "Frank")
    assert intent == EmailIntent.UNKNOWN
    assert rate is None
