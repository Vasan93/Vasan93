#!/usr/bin/env bash
# Restart the local dev backend (used during development, not in production).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"
PID=$(ss -lptn "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1)
[ -n "${PID:-}" ] && kill "$PID" 2>/dev/null && sleep 2
cd "$ROOT/backend"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" > /tmp/backend.log 2>&1 &
for _ in $(seq 1 30); do
  sleep 1
  curl -sf "http://localhost:$PORT/api/health" >/dev/null 2>&1 && { echo "backend up on :$PORT"; exit 0; }
done
echo "backend failed to start"; tail -20 /tmp/backend.log; exit 1
