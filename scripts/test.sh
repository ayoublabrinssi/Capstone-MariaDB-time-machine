#!/bin/sh
# Runs the database checks (tests/tests.sql), then the page tests
# (tests/test_app.py) and the tests of the download and prepare scripts
# (tests/test_fetch.py). Fails if any check fails. Run scripts/install.sh first.
set -e
cd "$(dirname "$0")/.."
# The checks expect as many articles as the list that was loaded has titles.
list=data/articles.txt
[ "$(cat data/load/.source 2>/dev/null)" = sample ] && list=data/sample/articles.txt
articles=$(grep -cv '^[[:space:]]*\(#\|$\)' "$list")
out=$( { echo "SET @articles = $articles;"; cat tests/tests.sql; } | scripts/db.sh -N)
echo "$out"
n=$(echo "$out" | grep -c '^ok' || true)
if echo "$out" | grep -q '^not ok'; then
  echo "FAILED"
  exit 1
fi
echo "All $n database checks passed"
echo
# The Python tests use the virtual environment from scripts/run.sh when it exists.
py=python3
[ -x .venv/bin/python ] && py=.venv/bin/python
"$py" -m unittest discover -s tests
