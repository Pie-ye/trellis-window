#!/usr/bin/env bash
# Start Trellis Window (LAN-reachable by default on 0.0.0.0:8775).
set -euo pipefail
cd "$(dirname "$0")"

HOST="${TRELLIS_WINDOW_HOST:-0.0.0.0}"
PORT="${TRELLIS_WINDOW_PORT:-8775}"

if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install -r requirements.txt --python .venv/bin/python
  else
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install -r requirements.txt
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "Trellis Window → http://${HOST}:${PORT}/  (e.g. http://192.168.68.69:${PORT}/)"
exec uvicorn server.app:app --host "$HOST" --port "$PORT"
