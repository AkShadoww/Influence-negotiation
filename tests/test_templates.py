"""Tests for per-campaign branding in email templates."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

import templates
from config import DEFAULT_BRAND_NAME, DEFAULT_CAMPAIGN_DEADLINE, DEFAULT_MANAGER_NAME


def test_reply1_uses_per_campaign_brand_and_deadline():
    subject, body = templates.reply1(
        creator_name="Alice",
        brand_name="Acme",
        campaign_deadline="March 15, 2026",
        manager_name="Dana",
    )
    assert subject == "Re: Acme x Alice Collaboration"
    assert "with Acme integrated effortlessly" in body
    assert "posted by March 15, 2026" in body
    assert body.strip().endswith("- Dana")
    # The default brand must NOT leak in when an override is supplied.
    assert DEFAULT_BRAND_NAME not in subject


def test_reply1_falls_back_to_defaults_when_none():
    subject, body = templates.reply1(creator_name="Bob")
    assert subject == f"Re: {DEFAULT_BRAND_NAME} x Bob Collaboration"
    assert f"posted by {DEFAULT_CAMPAIGN_DEADLINE}" in body
    assert body.strip().endswith(f"- {DEFAULT_MANAGER_NAME}")


def test_reply2_uses_per_campaign_brand():
    subject, body = templates.reply2(
        creator_name="Carol",
        flat_rate=1000,
        flat_bonus_threshold_views=75_000,
        flat_bonus_amount=200,
        view_based_rate=1125,
        view_target=75_000,
        avg_views=60_000,
        video_count=2,
        brand_name="Globex",
    )
    assert subject == "Re: Globex x Carol Collaboration"
    assert "engaging content around Globex" in body


def test_followup_and_terminal_templates_respect_brand():
    for fn in (
        templates.followup1,
        templates.followup2,
        templates.delay_email,
        templates.acceptance_confirmation,
    ):
        subject, _ = fn(creator_name="Dev", brand_name="Initech")
        assert subject == "Re: Initech x Dev Collaboration"

    subject, _ = templates.high_rate_rejection(
        creator_name="Dev", quoted_rate=5000, brand_name="Initech",
    )
    assert subject == "Re: Initech x Dev Collaboration"
