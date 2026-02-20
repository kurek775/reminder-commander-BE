### Stage 1: base ###
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


### Stage 2: development ###
FROM base AS development

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Source code is mounted via volume in development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


### Stage 3: production ###
FROM base AS production

# Run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY app/ ./app/

RUN chown -R appuser:appgroup /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
