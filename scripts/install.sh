#!/bin/sh
# Builds the database from the fetched data, from zero:
#   1. fetch/prepare.py   data/raw/*.json  ->  data/load/*.tsv
#   2. sql/01_schema.sql  drops and creates the tables
#   3. sql/02_load.sql    loads the files with their real timestamps
#   4. the page's own database user, which may only read and add to the text cache
# Run scripts/fetch.sh first, or use the three articles that come with the
# repository:
#   scripts/install.sh            all 45 articles from data/raw/
#   scripts/install.sh --sample   Rabat, Ifrane and Asilah from data/sample/
set -e
cd "$(dirname "$0")/.."

source=full
if [ "${1:-}" = "--sample" ]; then
  source=sample
  python3 fetch/prepare.py --articles data/sample/articles.txt --raw data/sample
elif [ $# -gt 0 ]; then
  echo "Unknown option: $1 (scripts/install.sh or scripts/install.sh --sample)" >&2
  exit 2
else
  python3 fetch/prepare.py
fi
scripts/db.sh < sql/01_schema.sql
scripts/db.sh -t < sql/02_load.sql
echo "$source" > data/load/.source

scripts/page_user.sh
