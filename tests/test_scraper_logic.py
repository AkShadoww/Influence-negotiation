"""
Tests for the pure Python logic in instagram_scraper:
percentile calculation and view count parsing — no browser required.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "influence_negotiation"))

# Import the private helpers directly (no playwright needed)
from scraper_utils import calculate_percentile as _calculate_percentile


def test_percentile_single_value():
    assert _calculate_percentile([5000], 0.25) == 5000
    assert _calculate_percentile([5000], 0.75) == 5000


def test_percentile_even_list():
    arr = [10, 20, 30, 40]
    # p50 = interpolated midpoint
    result = _calculate_percentile(arr, 0.5)
    assert 20 <= result <= 30


def test_percentile_p25_of_12_reels():
    # Simulate 12 reels sorted
    views = sorted([5000, 8000, 12000, 15000, 20000, 25000,
                    30000, 45000, 60000, 80000, 100000, 150000])
    p25 = _calculate_percentile(views, 0.25)
    p75 = _calculate_percentile(views, 0.75)
    assert p25 < p75
    assert views[0] <= p25 <= views[-1]


def test_percentile_p10_lower_than_p25():
    views = sorted([10000, 20000, 30000, 50000, 75000, 100000,
                    120000, 150000, 200000, 250000, 300000, 500000])
    p10 = _calculate_percentile(views, 0.10)
    p25 = _calculate_percentile(views, 0.25)
    assert p10 < p25


def test_percentile_empty_returns_zero():
    assert _calculate_percentile([], 0.5) == 0.0
