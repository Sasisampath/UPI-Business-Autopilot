# Single-container shared preview: Next.js web app on $PORT, FastAPI on 127.0.0.1:8000 behind it.
# NOT built or run in CI yet (no Docker daemon was available where this was written); build it once
# locally before relying on it:  docker build -t upi-autopilot-preview . && docker run --env-file .env.preview -p 3000:3000 upi-autopilot-preview
FROM node:22-bookworm-slim AS web
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/api/requirements.txt services/api/requirements-integrations.txt services/api/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r services/api/requirements.txt -r services/api/requirements-integrations.txt
COPY services/api services/api
COPY infra/start-preview.sh infra/start-preview.sh
COPY --from=web /app/apps/web apps/web
ENV PYTHON=/opt/venv/bin/python PORT=3000 NODE_ENV=production
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 3000
CMD ["infra/start-preview.sh"]
