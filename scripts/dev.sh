#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' EXIT
PYTHONPATH=packages/research .venv/bin/uvicorn apps.api.app.main:app --reload --port 8000 &
npm --prefix apps/web run dev &
wait
