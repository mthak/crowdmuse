#!/usr/bin/env bash
# Start FastAPI on PORT (default 8000), run pytest (includes live HTTP health check), then stop the server.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${VIRTUAL_ENV:-}" && -f "${ROOT}/../.cmuse/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "${ROOT}/../.cmuse/bin/activate"
fi

PORT="${PORT:-8000}"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
UV_PID=$!
cleanup() { kill "$UV_PID" 2>/dev/null || true; }
trap cleanup EXIT

sleep 2
python -m pytest tests/ -v --tb=short

echo "Done. (Uvicorn on http://127.0.0.1:${PORT} was stopped.) To keep the API running: python -m uvicorn app.main:app --reload --host 127.0.0.1 --port ${PORT}"
