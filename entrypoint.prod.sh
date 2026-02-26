#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
while ! python -c "
import socket, os
s = socket.socket()
try:
    s.connect((os.environ.get('POSTGRES_HOST','postgres'), int(os.environ.get('POSTGRES_PORT','5432'))))
    s.close()
except Exception:
    raise SystemExit(1)
" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
