# INFLUENCE — Creator Negotiation Backend

Automated email-based negotiation funnel for Instagram creator brand deals.

## How It Works

1. A creator is seeded into the system (manually via `seed.py`) after they express interest from the outreach phase.
2. The backend sends **Reply 1** (brand collab details) and waits for their rate.
3. When the creator replies with their rate, Claude computes a personalised performance-based offer and sends **Reply 2**.
4. The backend monitors responses and handles: acceptance, counter-offers, high-rate rejections, delays, and follow-ups.
5. If no reply in **2 days**, a follow-up email is sent automatically (max 2 per stage, then closed).

## Negotiation States

```
INTERESTED → REPLY1_SENT → AWAITING_RATE → OFFER_SENT → AWAITING_DECISION → ACCEPTED
                                                                           → HIGH_RATE_REJECTED
                                                                           → DELAYED
                                                                           → CLOSED
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, DATABASE_URL, and Gmail credentials
```

### 3. Gmail OAuth2 setup
- Go to Google Cloud Console → Create a project
- Enable the Gmail API
- Create OAuth2 credentials (Desktop app) → download as `credentials.json`
- First run will open a browser for OAuth consent; token saved to `token.json`

### 4. Railway (PostgreSQL)
- Add a PostgreSQL plugin in your Railway project
- Railway auto-sets `DATABASE_URL` — copy it into your `.env` for local dev

### 5. Seed a creator
```bash
python influence_negotiation/seed.py \
  --email creator@example.com \
  --name "Alice" \
  --handle alicedesigns \
  --followers 85000 \
  --avg_views 45000 \
  --engagement 4.2 \
  --thread_id <gmail_thread_id_from_outreach>
```

The Gmail thread ID is the `threadId` from the existing outreach email thread (visible in Gmail URL or via the API).

### 6. Run
```bash
python influence_negotiation/main.py
```

On Railway, the `Procfile` runs this automatically as a worker process.

## Running Tests
```bash
pytest tests/ -v
```

## File Structure
```
influence_negotiation/
├── main.py              # Polling loop entry point
├── config.py            # All config from env vars
├── gmail_client.py      # Gmail API read/send
├── email_classifier.py  # Claude: classify creator intent
├── pricing_engine.py    # Claude: compute price offer
├── negotiation_engine.py# State machine
├── templates.py         # Email templates
├── state_store.py       # PostgreSQL persistence
├── models.py            # Dataclasses and enums
└── seed.py              # CLI to add creators
tests/
├── test_email_classifier.py
├── test_pricing_engine.py
└── test_negotiation_engine.py
```

## Contract Emails
Not yet implemented — will be added as a separate feature.
