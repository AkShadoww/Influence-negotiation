"""
CLI utility to manually add a creator to the negotiation funnel.

Usage:
  python seed.py \
    --email edgar@example.com \
    --name Edgar \
    --handle edgardesigns \
    --followers 85000 \
    --avg_views 45000 \
    --engagement 4.2 \
    --thread_id <gmail_thread_id>
"""

import argparse
import logging
import sys

import state_store
from models import NegotiationState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a creator into the negotiation funnel.")
    parser.add_argument("--email", required=True, help="Creator's email address")
    parser.add_argument("--name", required=True, help="Creator's first name")
    parser.add_argument("--handle", default=None, help="Instagram handle (without @)")
    parser.add_argument("--followers", type=int, default=None)
    parser.add_argument("--avg_views", type=int, default=None)
    parser.add_argument("--engagement", type=float, default=None, help="Engagement rate as percent e.g. 4.2")
    parser.add_argument(
        "--thread_id",
        default=None,
        help="Gmail thread ID from the existing outreach conversation",
    )
    args = parser.parse_args()

    state_store.init_db()
    creator = state_store.seed_creator(
        creator_email=args.email,
        creator_name=args.name,
        instagram_handle=args.handle,
        followers=args.followers,
        avg_views=args.avg_views,
        engagement_rate=args.engagement,
    )

    if args.thread_id:
        creator.gmail_thread_id = args.thread_id
        state_store.upsert_creator(creator)
        logger.info("Thread ID set to %s", args.thread_id)

    logger.info(
        "Creator seeded: %s (%s) | state=%s",
        creator.creator_name, creator.creator_email, creator.state.value,
    )
    logger.info("Run main.py to send Reply 1 and start the funnel.")


if __name__ == "__main__":
    main()
