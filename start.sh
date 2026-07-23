#!/usr/bin/env bash
# Start Trellis Window (LAN-reachable by default on 0.0.0.0:8775).
set -euo pipefail
cd "$(dirname "$0")"

HOST="${TRELLIS_WINDOW_HOST:-0.0.0.0}"
PORT="${TRELLIS_WINDOW_PORT:-8775}"

if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
  else
    python3 -m venv .venv
  fi
fi

# Install deps if uvicorn missing (covers empty/partial venv)
if ! .venv/bin/python -c "import uvicorn" 2>/dev/null; then
  echo "Installing dependencies from requirements.txt ..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install -r requirements.txt --python .venv/bin/python
  else
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "Trellis Window → http://${HOST}:${PORT}/  (local: http://127.0.0.1:${PORT}/)"
exec python -m uvicorn server.app:app --host "$HOST" --port "$PORT"
