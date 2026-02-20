# Reminder Commander — Backend

FastAPI backend for the Reminder Commander application. Provides a REST API, async PostgreSQL persistence, and background task processing via Celery + Redis.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/) v2+
- Python 3.12+ (for running tests locally without Docker)

---

## Quick Start (Docker)

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Build and start all services
docker compose up --build

# 3. Verify the API is running
curl http://localhost:8000/api/v1/health
```

Swagger UI is available at: `http://localhost:8000/docs`

---

## Running Tests Locally

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests with coverage
pytest --cov=app
```

---

## Services

| Service         | Port  | Description                         |
|----------------|-------|-------------------------------------|
| `api`           | 8000  | FastAPI application (hot-reload)    |
| `postgres`      | 5432  | PostgreSQL 16 database              |
| `redis`         | 6379  | Redis 7 (broker + result backend)   |
| `celery_worker` | —     | Celery worker for async tasks       |
| `celery_beat`   | —     | Celery beat scheduler               |

---

## Environment Variables

All variables are defined in `.env` (copy from `.env.example`):

| Variable            | Default       | Description                        |
|--------------------|---------------|------------------------------------|
| `APP_ENV`           | `development` | Application environment            |
| `APP_PORT`          | `8000`        | API port                           |
| `LOG_LEVEL`         | `INFO`        | Logging level                      |
| `POSTGRES_USER`     | `commander`   | Database user                      |
| `POSTGRES_PASSWORD` | `commander`   | Database password                  |
| `POSTGRES_DB`       | `commander`   | Database name                      |
| `POSTGRES_HOST`     | `postgres`    | Database host (Docker service name)|
| `POSTGRES_PORT`     | `5432`        | Database port                      |
| `REDIS_HOST`        | `redis`       | Redis host (Docker service name)   |
| `REDIS_PORT`        | `6379`        | Redis port                         |
| `CORS_ORIGINS`      | `["http://localhost:4200"]` | Allowed CORS origins  |

---

## Project Structure

```
app/
  main.py              # FastAPI app factory, CORS, lifespan
  core/
    config.py          # Pydantic Settings (reads .env)
    logging.py         # JSON structured logging
  api/v1/routes/
    health.py          # GET /api/v1/health
  schemas/
    health.py          # HealthResponse Pydantic model
  worker/
    celery_app.py      # Celery app wired to Redis
    tasks.py           # Background tasks (ping placeholder)
tests/
  conftest.py          # Session-scoped AsyncClient fixture
  test_health.py       # Health endpoint tests
```

---

## Dev Workflow

```bash
# Start only infrastructure (postgres + redis)
docker compose up postgres redis

# Run API locally with hot-reload
uvicorn app.main:app --reload

# Lint
ruff check app/ tests/

# Type check
mypy app/
```
