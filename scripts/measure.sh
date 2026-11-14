#!/bin/sh
# Runs the measurements (scripts/measure.py) with the page's virtual
# environment and writes results/measurements.txt. Needs the database
# running and loaded. Takes a few minutes.
#   scripts/measure.sh            run everything
#   scripts/measure.sh --out results/measurements-run2.txt   a repeat run, kept apart
#   scripts/measure.sh --clean    drop the scratch database it made
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r app/requirements.txt
fi
exec .venv/bin/python scripts/measure.py "$@"
