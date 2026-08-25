#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "Install Python 3.11+ first."; exit 1; }
command -v node >/dev/null || { echo "Install Node 20+ first (Homebrew: brew install node)."; exit 1; }
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
npm --prefix apps/web install
mkdir -p data/private
cp -n .env.example .env 2>/dev/null || true
.venv/bin/python scripts/seed_universe.py
.venv/bin/python -m pytest packages/research/tests -q
echo "PMOS ready. Run: make dev"
