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
class PriceOffer:
    flat_rate: float
    flat_bonus_threshold_views: int
    flat_bonus_amount: float
    view_based_rate: float
    view_target: int
    video_count: int
    budget_cap: float


@dataclass
class Creator:
    creator_email: str
    creator_name: str
    state: NegotiationState = NegotiationState.INTERESTED
    gmail_thread_id: Optional[str] = None
    instagram_handle: Optional[str] = None
    followers: Optional[int] = None
    avg_views: Optional[int] = None
    engagement_rate: Optional[float] = None
    quoted_rate: Optional[float] = None
    our_offer_flat: Optional[float] = None
    our_offer_view_rate: Optional[float] = None
    our_offer_view_target: Optional[int] = None
    our_offer_flat_bonus_threshold: Optional[int] = None
    our_offer_flat_bonus_amount: Optional[float] = None
    our_offer_video_count: Optional[int] = None
    budget_cap: Optional[float] = None
    follow_up_count: int = 0
    last_email_sent_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
