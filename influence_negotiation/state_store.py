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
    creator_email               TEXT PRIMARY KEY,
    creator_name                TEXT NOT NULL,
    state                       TEXT NOT NULL DEFAULT 'INTERESTED',
    gmail_thread_id             TEXT,
    instagram_handle            TEXT,

    -- Per-campaign branding (NULL → fall back to config DEFAULT_*)
    brand_name                  TEXT,
    campaign_deadline           TEXT,

    -- Scraped Instagram stats
    scraped_p10                 NUMERIC(12,2),
    scraped_p25                 NUMERIC(12,2),
    scraped_p50                 NUMERIC(12,2),
    scraped_p75                 NUMERIC(12,2),
    scraped_reel_count          INTEGER,
    scraped_min_views           INTEGER,
    scraped_views_raw           TEXT,

    -- Offer details
    quoted_rate                 NUMERIC(10,2),
    our_offer_flat_per_video    NUMERIC(10,2),
    our_offer_b_flat            NUMERIC(10,2),
    our_offer_b_bonus           NUMERIC(10,2),
    our_offer_b_view_target     INTEGER,
    our_offer_c_views           INTEGER,
    our_offer_c_price           NUMERIC(10,2),
    budget_cap                  NUMERIC(10,2),
    video_count                 INTEGER,

    -- 6 AI-suggested offers (JSON array)
    suggested_offers_json       TEXT,

    follow_up_count             INTEGER NOT NULL DEFAULT 0,
    last_email_sent_at          TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Idempotent column additions for tables that already exist in production
_MIGRATIONS = [
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS scraped_min_views INTEGER",
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS scraped_views_raw TEXT",
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS suggested_offers_json TEXT",
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS brand_name TEXT",
    "ALTER TABLE negotiations ADD COLUMN IF NOT EXISTS campaign_deadline TEXT",
]


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
        for migration in _MIGRATIONS:
            cur.execute(migration)
    logger.info("Database initialised.")


def _f(row: dict, key: str) -> Optional[float]:
    v = row.get(key)
    return float(v) if v is not None else None


def _row_to_creator(row: dict) -> Creator:
    return Creator(
        creator_email=row["creator_email"],
        creator_name=row["creator_name"],
        state=NegotiationState(row["state"]),
        gmail_thread_id=row.get("gmail_thread_id"),
        instagram_handle=row.get("instagram_handle"),
        brand_name=row.get("brand_name"),
        campaign_deadline=row.get("campaign_deadline"),
        scraped_p10=_f(row, "scraped_p10"),
        scraped_p25=_f(row, "scraped_p25"),
        scraped_p50=_f(row, "scraped_p50"),
        scraped_p75=_f(row, "scraped_p75"),
        scraped_reel_count=row.get("scraped_reel_count"),
        scraped_min_views=row.get("scraped_min_views"),
        scraped_views_raw=row.get("scraped_views_raw"),
        quoted_rate=_f(row, "quoted_rate"),
        our_offer_flat_per_video=_f(row, "our_offer_flat_per_video"),
        our_offer_b_flat=_f(row, "our_offer_b_flat"),
        our_offer_b_bonus=_f(row, "our_offer_b_bonus"),
        our_offer_b_view_target=row.get("our_offer_b_view_target"),
        our_offer_c_views=row.get("our_offer_c_views"),
        our_offer_c_price=_f(row, "our_offer_c_price"),
        budget_cap=_f(row, "budget_cap"),
        video_count=row.get("video_count"),
        suggested_offers_json=row.get("suggested_offers_json"),
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
                creator_email, creator_name, state, gmail_thread_id, instagram_handle,
                brand_name, campaign_deadline,
                scraped_p10, scraped_p25, scraped_p50, scraped_p75, scraped_reel_count,
                scraped_min_views, scraped_views_raw,
                quoted_rate, our_offer_flat_per_video,
                our_offer_b_flat, our_offer_b_bonus, our_offer_b_view_target,
                our_offer_c_views, our_offer_c_price, budget_cap, video_count,
                suggested_offers_json,
                follow_up_count, last_email_sent_at, created_at, updated_at
            ) VALUES (
                %(creator_email)s, %(creator_name)s, %(state)s, %(gmail_thread_id)s, %(instagram_handle)s,
                %(brand_name)s, %(campaign_deadline)s,
                %(scraped_p10)s, %(scraped_p25)s, %(scraped_p50)s, %(scraped_p75)s, %(scraped_reel_count)s,
                %(scraped_min_views)s, %(scraped_views_raw)s,
                %(quoted_rate)s, %(our_offer_flat_per_video)s,
                %(our_offer_b_flat)s, %(our_offer_b_bonus)s, %(our_offer_b_view_target)s,
                %(our_offer_c_views)s, %(our_offer_c_price)s, %(budget_cap)s, %(video_count)s,
                %(suggested_offers_json)s,
                %(follow_up_count)s, %(last_email_sent_at)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (creator_email) DO UPDATE SET
                creator_name = EXCLUDED.creator_name,
                state = EXCLUDED.state,
                gmail_thread_id = EXCLUDED.gmail_thread_id,
                instagram_handle = EXCLUDED.instagram_handle,
                brand_name = EXCLUDED.brand_name,
                campaign_deadline = EXCLUDED.campaign_deadline,
                scraped_p10 = EXCLUDED.scraped_p10,
                scraped_p25 = EXCLUDED.scraped_p25,
                scraped_p50 = EXCLUDED.scraped_p50,
                scraped_p75 = EXCLUDED.scraped_p75,
                scraped_reel_count = EXCLUDED.scraped_reel_count,
                scraped_min_views = EXCLUDED.scraped_min_views,
                scraped_views_raw = EXCLUDED.scraped_views_raw,
                quoted_rate = EXCLUDED.quoted_rate,
                our_offer_flat_per_video = EXCLUDED.our_offer_flat_per_video,
                our_offer_b_flat = EXCLUDED.our_offer_b_flat,
                our_offer_b_bonus = EXCLUDED.our_offer_b_bonus,
                our_offer_b_view_target = EXCLUDED.our_offer_b_view_target,
                our_offer_c_views = EXCLUDED.our_offer_c_views,
                our_offer_c_price = EXCLUDED.our_offer_c_price,
                budget_cap = EXCLUDED.budget_cap,
                video_count = EXCLUDED.video_count,
                suggested_offers_json = EXCLUDED.suggested_offers_json,
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
                "brand_name": creator.brand_name,
                "campaign_deadline": creator.campaign_deadline,
                "scraped_p10": creator.scraped_p10,
                "scraped_p25": creator.scraped_p25,
                "scraped_p50": creator.scraped_p50,
                "scraped_p75": creator.scraped_p75,
                "scraped_reel_count": creator.scraped_reel_count,
                "scraped_min_views": creator.scraped_min_views,
                "scraped_views_raw": creator.scraped_views_raw,
                "quoted_rate": creator.quoted_rate,
                "our_offer_flat_per_video": creator.our_offer_flat_per_video,
                "our_offer_b_flat": creator.our_offer_b_flat,
                "our_offer_b_bonus": creator.our_offer_b_bonus,
                "our_offer_b_view_target": creator.our_offer_b_view_target,
                "our_offer_c_views": creator.our_offer_c_views,
                "our_offer_c_price": creator.our_offer_c_price,
                "budget_cap": creator.budget_cap,
                "video_count": creator.video_count,
                "suggested_offers_json": creator.suggested_offers_json,
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
    terminal = (NegotiationState.CLOSED.value, NegotiationState.ACCEPTED.value)
    with _cursor() as cur:
        cur.execute(
            "SELECT * FROM negotiations WHERE state NOT IN %s ORDER BY created_at ASC",
            (terminal,),
        )
        return [_row_to_creator(r) for r in cur.fetchall()]


def get_creators_needing_followup(cutoff: datetime) -> List[Creator]:
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
    brand_name: str = None,
    campaign_deadline: str = None,
) -> Creator:
    """Add a creator to the funnel. Instagram stats will be scraped automatically.

    brand_name / campaign_deadline are the campaign this creator belongs to.
    Leave them None to fall back to the config DEFAULT_* values.
    """
    creator = Creator(
        creator_email=creator_email,
        creator_name=creator_name,
        state=NegotiationState.INTERESTED,
        instagram_handle=instagram_handle,
        brand_name=brand_name,
        campaign_deadline=campaign_deadline,
    )
    upsert_creator(creator)
    logger.info(
        "Seeded creator %s (%s) @%s | brand=%s",
        creator_name, creator_email, instagram_handle or "—", brand_name or "(default)",
    )
    return creator
