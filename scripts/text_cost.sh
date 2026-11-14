#!/bin/sh
# Measures what it would cost to keep the article text inside the versioned
# row instead of next to it (scripts/text_cost.py), and writes
# results/text_cost.txt. Needs the database running and loaded.
# Takes a few seconds.
#   scripts/text_cost.sh              Rabat
#   scripts/text_cost.sh Casablanca   another loaded article
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r app/requirements.txt
fi
exec .venv/bin/python scripts/text_cost.py "$@"
