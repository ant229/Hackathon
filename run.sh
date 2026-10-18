#!/usr/bin/env bash
#
# Park LU: verify (compile) and run the local app.
#
#   ./run.sh              install deps, compile-check both sides, then run both servers
#   ./run.sh --run        skip the checks, just install and run (fast)
#   ./run.sh --check      only verify (API tests + web typecheck/lint/build); don't run
#   ./run.sh --help
#
# Starts the FastAPI backend on :8000 and the Next.js frontend on :3000.
# Ctrl-C stops both. Requires uv (https://docs.astral.sh/uv) and Node/npm.

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
MODE="all"   # all | run | check

for arg in "$@"; do
  case "$arg" in
    --run) MODE="run" ;;
    --check) MODE="check" ;;
    -h|--help)
      sed -n '4,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

note() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mError: %s\033[0m\n' "$1" >&2; exit 1; }

# --- prerequisites -----------------------------------------------------------
command -v uv  >/dev/null 2>&1 || fail "uv not found. Install from https://docs.astral.sh/uv/"
command -v npm >/dev/null 2>&1 || fail "npm not found. Install Node.js (https://nodejs.org)"

# --- install dependencies ----------------------------------------------------
note "Installing API dependencies (uv sync)"
( cd api && uv sync )

note "Installing web dependencies (npm install)"
( cd web && npm install --no-audit --no-fund )

# --- verify / compile --------------------------------------------------------
if [ "$MODE" != "run" ]; then
  note "API: tests (uv run pytest)"
  ( cd api && uv run pytest -q )

  note "Web: typecheck, lint, contrast (npm run check)"
  ( cd web && npm run check )

  note "Web: production build (npm run build)"
  ( cd web && npm run build )

  printf '\n\033[32mAll checks passed.\033[0m\n'
fi

[ "$MODE" = "check" ] && exit 0

# --- run both servers --------------------------------------------------------
# Kill the whole process group on exit so neither server is orphaned.
trap 'printf "\nStopping Park LU...\n"; kill 0 2>/dev/null' EXIT INT TERM

note "Starting API on http://localhost:${API_PORT}  (docs at /docs)"
( cd api && exec uv run uvicorn app.main:create_app --factory --port "${API_PORT}" ) &

note "Starting web on http://localhost:${WEB_PORT}"
( cd web && exec npm run dev -- --port "${WEB_PORT}" ) &

printf '\nPark LU is starting. Open http://localhost:%s  (Ctrl-C to stop both)\n' "${WEB_PORT}"
wait
