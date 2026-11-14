#!/bin/sh
# Looks under the table sizes of the measurements: how the versioned table
# grows, what is allocated and what is in use (scripts/growth.py), and writes
# results/growth.txt. Needs the database running and loaded.
# Takes a few seconds.
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r app/requirements.txt
fi
exec .venv/bin/python scripts/growth.py "$@"
