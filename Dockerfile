# Production image for Render: Redis + Flask (gunicorn) + Next.js in one container.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates redis-server && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend
COPY backend ./backend
RUN pip install --no-cache-dir -e ./backend

# Frontend
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN cd frontend && npm run build

COPY start.sh ./start.sh

ENV REDIS_HOST=127.0.0.1 REDIS_PORT=6379 NODE_ENV=production
EXPOSE 3000
CMD ["./start.sh"]
