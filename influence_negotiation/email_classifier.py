"""
Uses Claude to classify the intent of a creator's incoming email.
"""

import json
import logging
import re
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from models import EmailIntent

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are an assistant for a social media marketing agency that negotiates brand deals with Instagram creators.

Your job is to classify a creator's email reply into exactly ONE of the following intent labels:

RATE_SHARED       - The creator has mentioned their price or rate (e.g. "I charge $500 per video", "my rate is $1000")
ACCEPTED          - The creator has agreed to the proposed deal or terms
COUNTER_OFFER     - The creator is negotiating, proposing modified terms (different rate, fewer videos, etc.)
ASKING_DETAILS    - The creator is interested but asking questions without sharing a rate
HIGH_RATE         - The creator's stated rate is clearly very high (use context: if they quote a very large number)
NOT_INTERESTED    - The creator is declining or not interested
DELAY_REQUEST     - The creator says they're busy, not available now, or wants to revisit later
UNKNOWN           - None of the above labels clearly apply

Return ONLY a JSON object in this exact format, no other text:
{
  "intent": "<LABEL>",
  "extracted_rate": <number or null>,
  "notes": "<brief one-line reasoning>"
}

extracted_rate should be the per-video dollar amount if the creator mentioned a rate, otherwise null."""


def classify_email(email_body: str, creator_name: str = "") -> tuple[EmailIntent, Optional[float], str]:
    """
    Classify the intent of a creator's email.
    Returns: (intent, extracted_rate_or_None, notes)
    """
    prompt = f"Creator name: {creator_name}\n\nCreator's email:\n{email_body}"

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip any markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        intent = EmailIntent(data.get("intent", "UNKNOWN"))
        rate = data.get("extracted_rate")
        rate = float(rate) if rate is not None else None
        notes = data.get("notes", "")
        logger.info("Classified email from %s: intent=%s rate=%s", creator_name, intent, rate)
        return intent, rate, notes
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("Failed to parse classifier response: %s", e)
        return EmailIntent.UNKNOWN, None, "parse error"
    except anthropic.APIError as e:
        logger.error("Anthropic API error during classification: %s", e)
        return EmailIntent.UNKNOWN, None, "api error"
