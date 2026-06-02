"""
Entry point for the Creator Negotiation Backend.
Polls Gmail every POLL_INTERVAL_MINUTES for new creator emails
and runs the follow-up scheduler on the same tick.
"""

import logging
import sys
import time

import gmail_client
import negotiation_engine
import state_store
from config import POLL_INTERVAL_MINUTES
from models import NegotiationState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def process_new_emails() -> None:
    """
    For each active creator, fetch unread emails in their Gmail thread
    and run the negotiation engine.
    """
    creators = state_store.get_active_creators()
    logger.info("Processing %d active creators", len(creators))

    for creator in creators:
        # Skip creators with no known thread yet
        if not creator.gmail_thread_id:
            # For INTERESTED creators with no thread, kick off Reply 1 directly
            if creator.state == NegotiationState.INTERESTED:
                logger.warning(
                    "Creator %s is INTERESTED but has no gmail_thread_id. "
                    "Assign one via seed_creator() or update the DB.",
                    creator.creator_email,
                )
            continue

        try:
            messages = gmail_client.get_unread_messages_in_thread(creator.gmail_thread_id)
        except Exception as e:
            logger.error("Gmail read error for %s: %s", creator.creator_email, e)
            continue

        for msg in messages:
            try:
                negotiation_engine.handle_incoming_email(creator, msg["body"])
                gmail_client.mark_as_read(msg["id"])
            except Exception as e:
                logger.error("Error processing message %s for %s: %s", msg["id"], creator.creator_email, e)


def run_once() -> None:
    process_new_emails()
    negotiation_engine.process_pending_approvals()
    negotiation_engine.run_followups()


def main() -> None:
    logger.info("Initialising database...")
    state_store.init_db()

    # Handle newly seeded INTERESTED creators (no thread yet — Reply 1 must come first)
    _send_initial_reply1()

    logger.info("Starting polling loop (interval=%dm)", POLL_INTERVAL_MINUTES)
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error("Unexpected error in polling loop: %s", e)
        logger.info("Sleeping %d minutes...", POLL_INTERVAL_MINUTES)
        time.sleep(POLL_INTERVAL_MINUTES * 60)


def _send_initial_reply1() -> None:
    """
    Send Reply 1 to any creator who was just seeded as INTERESTED
    and already has a gmail_thread_id (i.e. their outreach thread).
    """
    creators = state_store.get_active_creators()
    for creator in creators:
        if creator.state == NegotiationState.INTERESTED and creator.gmail_thread_id:
            logger.info("Sending Reply 1 to newly interested creator %s", creator.creator_email)
            try:
                negotiation_engine.handle_new_interest(creator)
            except Exception as e:
                logger.error("Failed to send Reply 1 to %s: %s", creator.creator_email, e)


if __name__ == "__main__":
    main()
