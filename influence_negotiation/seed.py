"""
CLI utility to add a creator to the negotiation funnel.
Instagram stats are scraped automatically via Playwright.

Usage:
  python seed.py \
    --email edgar@example.com \
    --name Edgar \
    --handle edgardesigns \
    --thread_id <gmail_thread_id>

Optional --no-scrape flag skips scraping (useful for testing without Chrome).
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
    parser.add_argument("--thread_id", default=None, help="Gmail thread ID from existing outreach thread")
    parser.add_argument("--no-scrape", action="store_true", help="Skip Instagram scraping now (will scrape when Reply 1 is sent)")
    args = parser.parse_args()

    state_store.init_db()
    creator = state_store.seed_creator(
        creator_email=args.email,
        creator_name=args.name,
        instagram_handle=args.handle,
    )

    if args.thread_id:
        creator.gmail_thread_id = args.thread_id
        state_store.upsert_creator(creator)
        logger.info("Thread ID set to %s", args.thread_id)

    if args.handle and not args.no_scrape:
        logger.info("Scraping Instagram stats for @%s...", args.handle)
        import instagram_scraper
        stats = instagram_scraper.scrape_creator_reels(args.handle)
        if stats:
            creator.scraped_p10 = stats.p10
            creator.scraped_p25 = stats.p25
            creator.scraped_p50 = stats.p50
            creator.scraped_p75 = stats.p75
            creator.scraped_reel_count = stats.count
            state_store.upsert_creator(creator)
            logger.info(
                "Scraped %d reels | p10=%.0f p25=%.0f p50=%.0f p75=%.0f",
                stats.count, stats.p10, stats.p25, stats.p50, stats.p75,
            )
        else:
            logger.warning("Scraping failed — will retry when Reply 1 is sent.")
    elif args.handle and args.no_scrape:
        logger.info("Skipping scrape (--no-scrape). Will scrape when Reply 1 is sent.")

    logger.info(
        "Creator seeded: %s (%s) | state=%s | handle=@%s",
        creator.creator_name, creator.creator_email,
        creator.state.value, args.handle or "—",
    )
    logger.info("Run main.py to send Reply 1 and start the funnel.")


if __name__ == "__main__":
    main()
