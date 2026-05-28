"""
PostgreSQL-backed state store for creator negotiations.
Uses psycopg2 with DATABASE_URL from Railway.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

from config import DATABASE_URL
from models import Creator, NegotiationState

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS negotiations (
    creator_email              TEXT PRIMARY KEY,
    creator_name               TEXT NOT NULL,
    state                      TEXT NOT NULL DEFAULT 'INTERESTED',
    gmail_thread_id            TEXT,
    instagram_handle           TEXT,
    followers                  INTEGER,
    avg_views                  INTEGER,
    engagement_rate            NUMERIC(5,2),
    quoted_rate                NUMERIC(10,2),
    our_offer_flat             NUMERIC(10,2),
    our_offer_view_rate        NUMERIC(10,2),
    our_offer_view_target      INTEGER,
    our_offer_flat_bonus_threshold INTEGER,
    our_offer_flat_bonus_amount    NUMERIC(10,2),
    our_offer_video_count      INTEGER,
    budget_cap                 NUMERIC(10,2),
    follow_up_count            INTEGER NOT NULL DEFAULT 0,
    last_email_sent_at         TIMESTAMPTZ,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def get_connection() -> PgConnection:
    return psycopg2.connect(DATABASE_URL)


@contextmanager
def _cursor():
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def init_db() -> None:
    with _cursor() as cur:
        cur.execute(_CREATE_TABLE)
    logger.info("Database initialised.")


def _row_to_creator(row: dict) -> Creator:
    return Creator(
        creator_email=row["creator_email"],
        creator_name=row["creator_name"],
        state=NegotiationState(row["state"]),
        gmail_thread_id=row.get("gmail_thread_id"),
        instagram_handle=row.get("instagram_handle"),
        followers=row.get("followers"),
        avg_views=row.get("avg_views"),
        engagement_rate=float(row["engagement_rate"]) if row.get("engagement_rate") else None,
        quoted_rate=float(row["quoted_rate"]) if row.get("quoted_rate") else None,
        our_offer_flat=float(row["our_offer_flat"]) if row.get("our_offer_flat") else None,
        our_offer_view_rate=float(row["our_offer_view_rate"]) if row.get("our_offer_view_rate") else None,
        our_offer_view_target=row.get("our_offer_view_target"),
        our_offer_flat_bonus_threshold=row.get("our_offer_flat_bonus_threshold"),
        our_offer_flat_bonus_amount=float(row["our_offer_flat_bonus_amount"]) if row.get("our_offer_flat_bonus_amount") else None,
        our_offer_video_count=row.get("our_offer_video_count"),
        budget_cap=float(row["budget_cap"]) if row.get("budget_cap") else None,
        follow_up_count=row.get("follow_up_count", 0),
        last_email_sent_at=row.get("last_email_sent_at"),
        created_at=row.get("created_at", datetime.utcnow()),
        updated_at=row.get("updated_at", datetime.utcnow()),
    )


def upsert_creator(creator: Creator) -> None:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO negotiations (
                creator_email, creator_name, state, gmail_thread_id,
                instagram_handle, followers, avg_views, engagement_rate,
                quoted_rate, our_offer_flat, our_offer_view_rate, our_offer_view_target,
                our_offer_flat_bonus_threshold, our_offer_flat_bonus_amount,
                our_offer_video_count, budget_cap,
                follow_up_count, last_email_sent_at, created_at, updated_at
            ) VALUES (
                %(creator_email)s, %(creator_name)s, %(state)s, %(gmail_thread_id)s,
                %(instagram_handle)s, %(followers)s, %(avg_views)s, %(engagement_rate)s,
                %(quoted_rate)s, %(our_offer_flat)s, %(our_offer_view_rate)s, %(our_offer_view_target)s,
                %(our_offer_flat_bonus_threshold)s, %(our_offer_flat_bonus_amount)s,
                %(our_offer_video_count)s, %(budget_cap)s,
                %(follow_up_count)s, %(last_email_sent_at)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (creator_email) DO UPDATE SET
                creator_name = EXCLUDED.creator_name,
                state = EXCLUDED.state,
                gmail_thread_id = EXCLUDED.gmail_thread_id,
                instagram_handle = EXCLUDED.instagram_handle,
                followers = EXCLUDED.followers,
                avg_views = EXCLUDED.avg_views,
                engagement_rate = EXCLUDED.engagement_rate,
                quoted_rate = EXCLUDED.quoted_rate,
                our_offer_flat = EXCLUDED.our_offer_flat,
                our_offer_view_rate = EXCLUDED.our_offer_view_rate,
                our_offer_view_target = EXCLUDED.our_offer_view_target,
                our_offer_flat_bonus_threshold = EXCLUDED.our_offer_flat_bonus_threshold,
                our_offer_flat_bonus_amount = EXCLUDED.our_offer_flat_bonus_amount,
                our_offer_video_count = EXCLUDED.our_offer_video_count,
                budget_cap = EXCLUDED.budget_cap,
                follow_up_count = EXCLUDED.follow_up_count,
                last_email_sent_at = EXCLUDED.last_email_sent_at,
                updated_at = NOW()
            """,
            {
                "creator_email": creator.creator_email,
                "creator_name": creator.creator_name,
                "state": creator.state.value,
                "gmail_thread_id": creator.gmail_thread_id,
                "instagram_handle": creator.instagram_handle,
                "followers": creator.followers,
                "avg_views": creator.avg_views,
                "engagement_rate": creator.engagement_rate,
                "quoted_rate": creator.quoted_rate,
                "our_offer_flat": creator.our_offer_flat,
                "our_offer_view_rate": creator.our_offer_view_rate,
                "our_offer_view_target": creator.our_offer_view_target,
                "our_offer_flat_bonus_threshold": creator.our_offer_flat_bonus_threshold,
                "our_offer_flat_bonus_amount": creator.our_offer_flat_bonus_amount,
                "our_offer_video_count": creator.our_offer_video_count,
                "budget_cap": creator.budget_cap,
                "follow_up_count": creator.follow_up_count,
                "last_email_sent_at": creator.last_email_sent_at,
                "created_at": creator.created_at,
                "updated_at": datetime.utcnow(),
            },
        )


def get_creator(email: str) -> Optional[Creator]:
    with _cursor() as cur:
        cur.execute("SELECT * FROM negotiations WHERE creator_email = %s", (email,))
        row = cur.fetchone()
        return _row_to_creator(row) if row else None


def get_active_creators() -> List[Creator]:
    """Return all creators not in a terminal state."""
    terminal = (NegotiationState.CLOSED.value, NegotiationState.ACCEPTED.value)
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM negotiations WHERE state NOT IN %s ORDER BY created_at ASC",
            (terminal,),
        )
        return [_row_to_creator(r) for r in cur.fetchall()]


def get_creators_needing_followup(cutoff: datetime) -> List[Creator]:
    """Return creators waiting for a reply whose last email was sent before cutoff."""
    waiting_states = (
        NegotiationState.AWAITING_RATE.value,
        NegotiationState.AWAITING_DECISION.value,
    )
    with _cursor() as cur:
        cur.execute(
            """
            SELECT * FROM negotiations
            WHERE state IN %s
              AND last_email_sent_at < %s
              AND follow_up_count < %s
            ORDER BY last_email_sent_at ASC
            """,
            (waiting_states, cutoff, 2),
        )
        return [_row_to_creator(r) for r in cur.fetchall()]


def seed_creator(
    creator_email: str,
    creator_name: str,
    instagram_handle: str = None,
    followers: int = None,
    avg_views: int = None,
    engagement_rate: float = None,
) -> Creator:
    """Convenience helper to manually add a creator to the funnel."""
    creator = Creator(
        creator_email=creator_email,
        creator_name=creator_name,
        state=NegotiationState.INTERESTED,
        instagram_handle=instagram_handle,
        followers=followers,
        avg_views=avg_views,
        engagement_rate=engagement_rate,
    )
    upsert_creator(creator)
    logger.info("Seeded creator %s (%s)", creator_name, creator_email)
    return creator
