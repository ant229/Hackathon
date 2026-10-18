cd "$(dirname "$0")"; trap 'kill 0' EXIT; (cd api && uv sync && uv run uvicorn app.main:create_app --factory --port 8000) &
cd web && npm install && npm run dev
