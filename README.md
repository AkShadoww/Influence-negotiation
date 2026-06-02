# INFLUENCE — Creator Negotiation Backend

Automated email-based negotiation funnel for Instagram creator brand deals.

## How It Works

1. A creator is seeded into the system (via `seed.py`) after they express interest from the outreach phase.
2. The backend scrapes the creator's Instagram Reels page (opens a Chrome tab, collects 12 view counts, closes the tab).
3. **Reply 1** (brand collab details) is sent automatically and the system waits for their rate.
4. When the creator replies with their rate, CPM-based pricing is computed from the scraped view stats and **Reply 2** (offer) is sent.
5. The backend monitors responses and handles: acceptance, counter-offers, high-rate rejections, delays, and follow-ups.
6. If no reply in **2 days**, a follow-up email is sent automatically (max 2 per stage, then closed).

## Negotiation States

```
INTERESTED → AWAITING_RATE → AWAITING_APPROVAL → AWAITING_DECISION → ACCEPTED
                                  (admin approves)                  → HIGH_RATE_REJECTED
                                                                    → DELAYED
                                                                    → CLOSED
```

## Offer Approval (human-in-the-loop)

When a creator shares their rate, the worker scrapes/refreshes their Instagram
stats, computes the 6 suggested offers, and **pushes them to the outreach
dashboard** (honoring that campaign's `max_cpm`). If `REQUIRE_OFFER_APPROVAL=true`
(default), the creator is parked in `AWAITING_APPROVAL` and **no offer email is
sent yet**.

An admin then opens the dashboard's *Creator Negotiation* view, picks (and
optionally edits) one of the 6 offers, and saves. On the next poll tick the
worker pulls that approved offer back (`GET /api/negotiation/offer`) and sends
**Reply 2 built from the exact offer the admin approved**.

Set `REQUIRE_OFFER_APPROVAL=false` to skip the gate and send Reply 2 immediately
(using an approved offer if one already exists, otherwise the computed Option
A/B/C). The gate only applies when `OUTREACH_API_URL` is configured and the
creator exists in the dashboard.

## Pricing (CPM-based)

Mirrors the Chrome extension formulas exactly:

| Option | Formula |
|---|---|
| A — Safe flat/video | `(p25_views / 1000) × CPM × (1 − risk_buffer)` |
| B — Flat + 20% bonus | flat × 1.2, view target rounded to nearest 25k |
| C — View guarantee | `(p75_views / 1000) × CPM` (full rate, no buffer) |

Claude is called only to validate the `budget_cap` — all core numbers come from the CPM formula.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
playwright install chrome
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, DATABASE_URL, Gmail credentials, INSTAGRAM_USER_DATA_DIR
```

### 3. Gmail OAuth2
- Go to Google Cloud Console → Enable Gmail API → Create OAuth2 credentials (Desktop app) → download as `credentials.json`
- First run opens a browser for OAuth consent; token saved to `token.json`

### 4. Instagram login
Set `INSTAGRAM_USER_DATA_DIR` to a Chrome profile directory where you are already logged into Instagram:
```
INSTAGRAM_USER_DATA_DIR=/home/youruser/.config/google-chrome/Default
```

### 5. Railway (PostgreSQL)
- Add a PostgreSQL plugin in your Railway project
- Railway auto-sets `DATABASE_URL` — copy it into your `.env` for local dev

### 6. Seed a creator
```bash
python influence_negotiation/seed.py \
  --email creator@example.com \
  --name "Alice" \
  --handle alicedesigns \
  --thread_id <gmail_thread_id_from_outreach> \
  --brand "Acme" \
  --deadline "March 15, 2026"
```

The Gmail thread ID comes from the existing outreach email thread (visible in Gmail URL).

`--brand` / `--deadline` set the campaign this creator belongs to, so one backend
can run deals for many brands at once. They're stored per-creator and used in that
creator's emails. Omit them to fall back to `BRAND_NAME` / `CAMPAIGN_DEADLINE` from
the environment (`config.DEFAULT_*`).

### 7. Run
```bash
python influence_negotiation/main.py
```

On Railway, the `Procfile` runs this automatically as a worker process.

## Running Tests
```bash
pytest tests/ -v   # 24 tests
```

## File Structure
```
influence_negotiation/
├── main.py              # Polling loop entry point
├── config.py            # All config from env vars
├── gmail_client.py      # Gmail API read/send
├── email_classifier.py  # Claude: classify creator intent
├── pricing_engine.py    # CPM-based pricing + Claude budget_cap review
├── negotiation_engine.py# State machine
├── templates.py         # Email templates
├── state_store.py       # PostgreSQL persistence
├── instagram_scraper.py # Playwright Chrome scraper
├── scraper_utils.py     # Pure math: percentile calc, K/M parsing
├── models.py            # Dataclasses and enums
└── seed.py              # CLI to add creators
tests/
├── test_email_classifier.py
├── test_pricing_engine.py
├── test_negotiation_engine.py
└── test_scraper_logic.py
```

## Contract Emails
Not yet implemented — will be added as a separate feature.
