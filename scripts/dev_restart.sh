#!/usr/bin/env bash
# Restart the local dev backend. Development convenience, not a production entrypoint.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"

# The bracket keeps the pattern from matching this script's own command line.
pkill -f "uvicorn[ ]app.main:app .*--port ${PORT}" 2>/dev/null
for _ in $(seq 1 10); do
  curl -sf "http://localhost:$PORT/api/health" >/dev/null 2>&1 || break
  sleep 1
done

cd "$ROOT/backend"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > /tmp/backend.log 2>&1 &
for _ in $(seq 1 30); do
  sleep 1
  curl -sf "http://localhost:$PORT/api/health" >/dev/null 2>&1 && { echo "backend up on :$PORT (pid $!)"; exit 0; }
done
echo "backend failed to start"; tail -20 /tmp/backend.log; exit 1
