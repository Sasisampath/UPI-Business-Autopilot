#!/usr/bin/env bash
# Starts the shared preview as ONE service: the API on 127.0.0.1 (never exposed) and the web app on
# $PORT. The hosting platform terminates HTTPS in front of $PORT. Refuses to start if not locked down.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PREVIEW_MODE=true DEMO_MODE=true
PY="${PYTHON:-python3}"

cd "$ROOT/services/api"
"$PY" -m app.preflight
"$PY" -m app.seed
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cd "$ROOT/apps/web"
npx next start -H 0.0.0.0 -p "${PORT:-3000}" &
WEB_PID=$!

trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT INT TERM
wait -n "$API_PID" "$WEB_PID"   # if either process stops, stop the service so the platform restarts it
exit 1
