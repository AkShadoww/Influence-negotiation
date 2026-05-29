from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class NegotiationState(str, Enum):
    INTERESTED = "INTERESTED"
    REPLY1_SENT = "REPLY1_SENT"
    AWAITING_RATE = "AWAITING_RATE"
    OFFER_SENT = "OFFER_SENT"
    AWAITING_DECISION = "AWAITING_DECISION"
    ACCEPTED = "ACCEPTED"
    HIGH_RATE_REJECTED = "HIGH_RATE_REJECTED"
    DELAYED = "DELAYED"
    CLOSED = "CLOSED"


class EmailIntent(str, Enum):
    RATE_SHARED = "RATE_SHARED"
    ACCEPTED = "ACCEPTED"
    COUNTER_OFFER = "COUNTER_OFFER"
    ASKING_DETAILS = "ASKING_DETAILS"
    HIGH_RATE = "HIGH_RATE"
    NOT_INTERESTED = "NOT_INTERESTED"
    DELAY_REQUEST = "DELAY_REQUEST"
    UNKNOWN = "UNKNOWN"


@dataclass
class Creator:
    creator_email: str
    creator_name: str
    state: NegotiationState = NegotiationState.INTERESTED
    gmail_thread_id: Optional[str] = None
    instagram_handle: Optional[str] = None

    # Scraped Instagram stats (populated by instagram_scraper)
    scraped_p10: Optional[float] = None
    scraped_p25: Optional[float] = None
    scraped_p50: Optional[float] = None
    scraped_p75: Optional[float] = None
    scraped_reel_count: Optional[int] = None

    # Computed offer (populated by pricing_engine)
    quoted_rate: Optional[float] = None
    our_offer_flat_per_video: Optional[float] = None
    our_offer_b_flat: Optional[float] = None
    our_offer_b_bonus: Optional[float] = None
    our_offer_b_view_target: Optional[int] = None
    our_offer_c_views: Optional[int] = None
    our_offer_c_price: Optional[float] = None
    budget_cap: Optional[float] = None
    video_count: Optional[int] = None

    follow_up_count: int = 0
    last_email_sent_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
