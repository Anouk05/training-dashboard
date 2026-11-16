#!/bin/bash
# Start the Training Dashboard: API on :8765, web app on http://localhost:5173
cd "$(dirname "$0")"
.venv/bin/uvicorn app.backend.main:app --port 8765 --reload --reload-dir app/backend &
API=$!
trap "kill $API" EXIT
npm --prefix app/web run dev
