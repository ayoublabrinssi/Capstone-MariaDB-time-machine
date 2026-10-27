#!/bin/sh
# Runs the database checks (tests/tests.sql) and the page tests
# (tests/test_app.py). Fails if any check fails. Run scripts/install.sh first.
set -e
cd "$(dirname "$0")/.."
out=$(scripts/db.sh -N < tests/tests.sql)
echo "$out"
n=$(echo "$out" | grep -c '^ok' || true)
if echo "$out" | grep -q '^not ok'; then
  echo "FAILED"
  exit 1
fi
echo "All $n database checks passed"
echo
# The page tests use the virtual environment from scripts/run.sh when it exists.
py=python3
[ -x .venv/bin/python ] && py=.venv/bin/python
"$py" -m unittest discover -s tests
