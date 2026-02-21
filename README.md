# Reminder Commander — Backend

FastAPI backend with Celery workers, PostgreSQL, Redis, ElevenLabs TTS, and Twilio voice/WhatsApp.

---

## Current Status

All 6 phases complete. **32 tests pass.**

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | FastAPI + Celery + Docker infrastructure | ✅ |
| 2 | Auth (Google SSO + JWT), DB models, encryption | ✅ |
| 3 | Google Sheets OAuth integration | ✅ |
| 4 | Health Tracker — WhatsApp reminders via cron | ✅ |
| 5 | Warlord — voice calls for overdue sheet tasks | ✅ |
| 6 | Warlord UI support (trigger, interactions, debug APIs) | ✅ |

---

## Quick Start

```bash
# 1. Copy and fill environment file
cp .env.example .env   # then edit .env with real secrets

# 2. Run migrations
docker compose up -d postgres
docker compose exec api alembic upgrade head

# 3. Start everything
docker compose up --build
```

API: `http://localhost:8000`
Swagger: `http://localhost:8000/docs`
ngrok inspector: `http://localhost:4040`

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI (hot-reload via volume mount) |
| `postgres` | 5433 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 (Celery broker + audio store) |
| `celery_worker` | — | Processes async tasks |
| `celery_beat` | — | Fires scheduled tasks every 60s |
| `ngrok` | 4040 | Public tunnel for Twilio callbacks |

> **Port note:** If port 8000 is taken by another project, change `"8000:8000"` → `"8001:8000"` in `docker-compose.yml` and update `environment.ts` in the FE.

---

## Environment Variables

```env
# App
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# Database
POSTGRES_USER=commander
POSTGRES_PASSWORD=commander
POSTGRES_DB=commander
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# JWT
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Google OAuth (login)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Google Sheets OAuth
GOOGLE_SHEETS_REDIRECT_URI=http://localhost:8000/api/v1/sheets/callback

# Encryption key for tokens stored in DB
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=...

# Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_VOICE_FROM=+1XXXXXXXXXX     # Twilio phone number for voice calls

# ElevenLabs TTS
ELEVENLABS_API_KEY=sk_...          # needs Text to Speech → Access permission
ELEVENLABS_VOICE_ID=...            # voice ID from your ElevenLabs account

# Public URL (Twilio must be able to reach this)
BACKEND_URL=https://xxxx.ngrok-free.dev
NGROK_AUTHTOKEN=...
```

> **ElevenLabs key permissions:** Only "Text to Speech → Access" is needed. The model used is `eleven_turbo_v2_5` (required for free tier — `eleven_monolingual_v1` is deprecated and removed).

---

## API Routes

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/auth/google` | Redirect to Google login |
| GET | `/api/v1/auth/google/callback` | Handle Google OAuth callback |
| GET | `/api/v1/auth/me` | Get current user |
| POST | `/api/v1/auth/whatsapp/link` | Link WhatsApp phone number |

### Sheets
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/sheets/connect` | Start Google Sheets OAuth |
| GET | `/api/v1/sheets/callback` | Handle Sheets OAuth callback |
| GET | `/api/v1/sheets/` | List connected sheets |
| GET | `/api/v1/sheets/{id}/headers` | Get column headers from sheet row 1 |

### Rules
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rules/` | Create a tracker rule |
| GET | `/api/v1/rules/` | List rules for current user |
| PATCH | `/api/v1/rules/{id}` | Update rule prompt_text |
| DELETE | `/api/v1/rules/{id}` | Delete a rule |

### Warlord
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/warlord/trigger` | Immediately fire warlord scan (bypasses cron) |
| GET | `/api/v1/warlord/debug/{rule_id}` | Show raw sheet rows + missed tasks for a rule |

### Voice (Twilio callbacks)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/v1/voice/twiml/{call_uuid}` | TwiML: `<Play>` ElevenLabs audio or `<Say>` fallback |
| GET | `/api/v1/voice/audio/{call_uuid}` | Serve MP3 from Redis |
| POST | `/api/v1/voice/gather/{call_uuid}` | Log key press from caller |
| POST | `/api/v1/voice/status/{call_uuid}` | Handle call status; WhatsApp fallback on failure |

### Interactions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/interactions/` | List interaction logs (`?channel=voice`) |

### Webhook
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/webhook/whatsapp` | Inbound WhatsApp from Twilio |

---

## Warlord — How It Works

1. **Celery beat** fires `scan_warlord_sheets` every 60s (or immediately via `POST /warlord/trigger`)
2. Queries all active `warlord` rules matching the current cron schedule (bypassed when `force=True`)
3. Reads the linked Google Sheet — looks for rows where **deadline < today** and **done ≠ TRUE**
4. For each missed task:
   - Calls **ElevenLabs** to generate MP3 audio → stores in Redis (`voice_audio:{uuid}`, TTL 1h)
   - Stores call context in Redis (`voice_ctx:{uuid}` — user, rule, task name, message)
   - Initiates **Twilio voice call** → Twilio fetches TwiML from `/voice/twiml/{uuid}`
   - TwiML plays ElevenLabs audio (or `<Say>` fallback if ElevenLabs failed) + `<Gather>` for key press
   - On call failure → **WhatsApp fallback** via `send_whatsapp()`

### Sheet Layout (fixed columns)
| Col A | Col B | Col C |
|-------|-------|-------|
| Task name | Deadline (`YYYY-MM-DD`) | Done (`TRUE`/`FALSE`) |

Row 1 = headers (skipped by scanner).

### Voice message template
Set `prompt_text` on the rule to customise the spoken message. Supports placeholders:
- `{task_name}` — the task name from column A
- `{deadline}` — the deadline date from column B

Leave blank for the default: `"{task_name} was due on {deadline}. Complete it now."`

---

## Database Models

| Model | Table | Key fields |
|-------|-------|------------|
| `User` | `users` | `email`, `google_id`, `whatsapp_phone` |
| `SheetIntegration` | `sheet_integrations` | `google_sheet_id`, encrypted tokens |
| `TrackerRule` | `tracker_rules` | `rule_type` (`health_tracker`/`warlord`), `cron_schedule`, `prompt_text` |
| `InteractionLog` | `interaction_logs` | `direction`, `channel` (`whatsapp`/`voice`), `status` |

Migrations live in `alembic/versions/`. Run `alembic upgrade head` to apply.

---

## Running Tests Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests use SQLite in-memory + mocked external services. No Docker needed for tests.

---

## Project Structure

```
app/
  main.py                    # App factory, routers, CORS, lifespan
  core/
    config.py                # Pydantic Settings (reads .env)
    deps.py                  # get_current_user dependency
    encryption.py            # Fernet encrypt/decrypt
    logging.py               # JSON structured logging
  api/v1/routes/
    health.py
    auth.py
    sheets.py
    rules.py
    webhook.py
    voice.py                 # Twilio voice callbacks + Redis audio serving
    warlord.py               # Trigger + debug endpoints
    interactions.py          # Interaction log listing
  models/
    user.py
    sheet_integration.py
    tracker_rule.py
    interaction_log.py
  schemas/
    rule.py                  # TrackerRuleCreate / Update / Response
  services/
    elevenlabs_service.py    # generate_audio() → MP3 bytes
    twilio_service.py        # make_voice_call(), send_whatsapp()
    sheets_service.py        # OAuth, get_warlord_tasks(), append_to_sheet()
    rules_service.py         # CRUD for TrackerRule
  worker/
    celery_app.py            # Celery instance wired to Redis
    tasks.py                 # check_and_send_reminders, scan_warlord_sheets
  db/
    base.py                  # AsyncEngine, SessionLocal, Base, get_db
alembic/                     # DB migration scripts
tests/
  conftest.py                # Fixtures: db_session, db_client, auth headers
  test_health.py
  test_auth.py
  test_models.py
  test_sheets.py
  test_rules.py
  test_webhook.py
  test_warlord.py            # Voice endpoint tests with MockRedis
```

---

## Known Issues / Gotchas

- **`docker restart` does not re-read `.env`** — always use `docker compose up -d <service>` to pick up env changes
- **ElevenLabs model:** `eleven_monolingual_v1` is removed from the free tier; use `eleven_turbo_v2_5`
- **Voice fallback:** If ElevenLabs fails, the call still goes through using Twilio `<Say>` TTS
- **ngrok static domain:** The `docker-compose.yml` ngrok service uses `--domain=tandy-unhit-opportunistically.ngrok-free.dev`. Update if your domain changes
- **Port conflict:** `postgres` maps to host port `5433` (not 5432) to avoid conflicts with local installs
