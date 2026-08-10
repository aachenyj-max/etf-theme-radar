FROM python:3.12-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY etf_theme_radar ./etf_theme_radar
COPY config ./config
COPY skills ./skills
COPY tools/backup_sqlite.py tools/restore_sqlite.py /usr/local/bin/

RUN pip install . \
    && useradd --create-home --uid 10001 radar \
    && mkdir -p /app/data \
    && chown -R radar:radar /app /usr/local/bin/backup_sqlite.py /usr/local/bin/restore_sqlite.py

USER radar
EXPOSE 8001

CMD ["python", "-m", "uvicorn", "etf_theme_radar.api:app", "--host", "0.0.0.0", "--port", "8001"]


FROM node:22-bookworm-slim AS frontend-deps

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci


FROM frontend-deps AS frontend-build

COPY frontend ./
RUN npm run build


FROM node:22-bookworm-slim AS frontend

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=frontend-build /app/frontend/.next ./.next
COPY --from=frontend-build /app/frontend/next.config.mjs ./next.config.mjs

USER node
EXPOSE 3000

CMD ["npm", "run", "start"]
