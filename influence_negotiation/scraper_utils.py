"""
Pure Python utilities shared by instagram_scraper and tests.
No Playwright dependency — safe to import anywhere.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class ScrapedStats:
    handle: str
    views: List[int]
    p10: float
    p25: float
    p50: float
    p75: float
    count: int


def calculate_percentile(sorted_arr: list, p: float) -> float:
    """
    Interpolated percentile — mirrors calculatePercentile() in content.js.
    sorted_arr must already be sorted ascending.
    """
    n = len(sorted_arr)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_arr[0])
    index = p * (n - 1)
    lower = int(index)
    upper = min(lower + 1, n - 1)
    weight = index % 1
    return sorted_arr[lower] * (1 - weight) + sorted_arr[upper] * weight


def parse_view_count(text: str) -> float:
    """
    Mirrors parseViewCount() in content.js.
    '1.2K' → 1200, '4.5M' → 4_500_000, '85000' → 85000.
    """
    text = text.strip().upper()
    if text.endswith("K"):
        return float(text[:-1]) * 1_000
    if text.endswith("M"):
        return float(text[:-1]) * 1_000_000
    return float(text)


def compute_stats_from_views(handle: str, views: List[int]) -> ScrapedStats:
    """Build a ScrapedStats from a raw view list."""
    sorted_views = sorted(views)
    return ScrapedStats(
        handle=handle,
        views=views,
        p10=calculate_percentile(sorted_views, 0.10),
        p25=calculate_percentile(sorted_views, 0.25),
        p50=calculate_percentile(sorted_views, 0.50),
        p75=calculate_percentile(sorted_views, 0.75),
        count=len(views),
    )
