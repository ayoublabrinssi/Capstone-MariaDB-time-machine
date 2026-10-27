#!/bin/sh
# Starts the time machine page on http://127.0.0.1:8000 (PORT=8001 to change).
# The first run makes a Python virtual environment in .venv and installs
# PyMySQL into it. Needs the database running and loaded:
#   docker compose up --wait && scripts/install.sh
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r app/requirements.txt
fi
exec .venv/bin/python app/server.py
