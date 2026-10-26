#!/bin/sh
# Downloads the revision history of the articles in data/articles.txt from
# the Wikipedia API into data/raw/ (one JSON file per article, git-ignored).
# Needs python3 only. Run again to continue: finished articles are skipped.
#
#   scripts/fetch.sh                  one revision per quarter per article (the default set)
#   scripts/fetch.sh --every year     a quick small set
#   scripts/fetch.sh --limit 3        first 3 articles only
set -e
cd "$(dirname "$0")/.."
exec python3 fetch/fetch.py --articles data/articles.txt --out data/raw "$@"
