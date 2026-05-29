"""
Instagram Reels scraper using Playwright.
Ports the view-extraction logic from the Chrome extension (content.js).

Design:
- Maintains a single Browser instance across all creators (open new tab, scrape, close tab).
- Requires a persistent Chrome user-data-dir so Instagram login is preserved.
- Navigates to /@handle/reels, scrolls until NUM_REELS view counts are collected,
  then returns ScrapedStats.
"""

import asyncio
import logging
import time
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from config import (
    INSTAGRAM_USER_DATA_DIR,
    SCRAPER_HEADLESS,
    SCRAPER_NUM_REELS,
    SCRAPER_SCROLL_PAUSE_MS,
    SCRAPER_TIMEOUT_S,
)
from scraper_utils import ScrapedStats, calculate_percentile, compute_stats_from_views

logger = logging.getLogger(__name__)


# ── Shared browser instance (created once per process) ──────────────────────

_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_playwright = None


async def _get_context() -> BrowserContext:
    global _browser, _context, _playwright
    if _context is not None:
        return _context

    _playwright = await async_playwright().start()
    _context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=INSTAGRAM_USER_DATA_DIR,
        headless=SCRAPER_HEADLESS,
        channel="chrome",          # use system Chrome so cookies/login persist
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        viewport={"width": 1280, "height": 900},
    )
    logger.info("Chrome browser launched (persistent context: %s)", INSTAGRAM_USER_DATA_DIR)
    return _context


async def _close_context() -> None:
    global _context, _playwright
    if _context:
        await _context.close()
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


# ── Core scraping ────────────────────────────────────────────────────────────

# Ported directly from content.js — runs inside the browser page
_EXTRACT_VIEWS_JS = """
() => {
  function parseViewCount(str) {
    str = str.trim().toUpperCase();
    if (str.includes('K')) return parseFloat(str) * 1000;
    if (str.includes('M')) return parseFloat(str) * 1000000;
    return parseFloat(str);
  }

  const seen = new Set();
  const views = [];

  const reelLinks = document.querySelectorAll("a[href*='/reel/']");
  reelLinks.forEach(link => {
    const reelId = (link.href.split('/reel/')[1] || '').split('/')[0];
    if (!reelId || seen.has(reelId)) return;
    seen.add(reelId);

    const container = link.parentElement;
    if (!container) return;

    const spans = container.querySelectorAll('span');
    const candidates = [];
    for (const span of spans) {
      const text = span.textContent.trim();
      const lower = text.toLowerCase();
      if (lower.includes('liked') || lower.includes('like by') ||
          lower.includes('comment') || lower.includes('share') ||
          lower.includes('like')) continue;
      if (/^[\\d.]+[KM]?$/.test(text)) {
        const v = parseViewCount(text);
        if (v >= 1000) candidates.push(v);
      }
    }
    if (candidates.length > 0) {
      views.push(Math.max(...candidates));
    }
  });

  return views;
}
"""


async def scrape_creator_reels_async(handle: str) -> Optional[ScrapedStats]:
    """
    Open a new browser tab, navigate to /@handle/reels, scroll to collect
    SCRAPER_NUM_REELS view counts, then close the tab.
    Returns ScrapedStats or None on failure.
    """
    handle = handle.lstrip("@")
    url = f"https://www.instagram.com/{handle}/reels/"

    ctx = await _get_context()
    page: Page = await ctx.new_page()
    logger.info("Opened new tab for @%s", handle)

    try:
        await page.goto(url, timeout=SCRAPER_TIMEOUT_S * 1000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)   # let reels grid render

        views: list[int] = []
        deadline = time.time() + SCRAPER_TIMEOUT_S
        scroll_attempts = 0

        while len(views) < SCRAPER_NUM_REELS and time.time() < deadline:
            raw = await page.evaluate(_EXTRACT_VIEWS_JS)
            views = [int(v) for v in raw if v > 0]
            logger.debug("@%s — scraped %d views so far", handle, len(views))

            if len(views) >= SCRAPER_NUM_REELS:
                break

            # Scroll down to load more reels
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await page.wait_for_timeout(SCRAPER_SCROLL_PAUSE_MS)
            scroll_attempts += 1

            if scroll_attempts > 20:
                logger.warning("@%s — hit scroll limit with only %d reels", handle, len(views))
                break

        if not views:
            logger.error("@%s — could not scrape any views", handle)
            return None

        # Use only the first SCRAPER_NUM_REELS (newest)
        views = views[:SCRAPER_NUM_REELS]
        stats = compute_stats_from_views(handle, views)
        logger.info(
            "@%s scrape complete: %d reels | p10=%.0f p25=%.0f p50=%.0f p75=%.0f",
            handle, stats.count, stats.p10, stats.p25, stats.p50, stats.p75,
        )
        return stats

    except Exception as e:
        logger.error("Scrape failed for @%s: %s", handle, e)
        return None
    finally:
        await page.close()
        logger.info("Closed tab for @%s", handle)


def scrape_creator_reels(handle: str) -> Optional[ScrapedStats]:
    """Synchronous wrapper for use in the negotiation engine."""
    return asyncio.run(scrape_creator_reels_async(handle))


async def scrape_creators_batch(handles: list[str]) -> dict[str, Optional[ScrapedStats]]:
    """Scrape multiple creators sequentially (one tab at a time)."""
    results = {}
    for handle in handles:
        results[handle] = await scrape_creator_reels_async(handle)
    return results
