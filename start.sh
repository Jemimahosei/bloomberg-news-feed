#!/bin/sh
# One container for Render: Redis, the Flask API, and the Next.js frontend.
set -e
redis-server --daemonize yes --save "" --appendonly no
cd /app/backend
gunicorn --bind 127.0.0.1:8000 --workers 1 "app:create_app()" &
cd /app/frontend
export BACKEND_API_URL="http://127.0.0.1:8000"
exec npx next start -H 0.0.0.0 -p "${PORT:-3000}"
