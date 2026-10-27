#!/bin/sh
# Builds the database from the fetched data, from zero:
#   1. fetch/prepare.py   data/raw/*.json  ->  data/load/*.tsv
#   2. sql/01_schema.sql  drops and creates the tables
#   3. sql/02_load.sql    loads the files with their real timestamps
# Run scripts/fetch.sh first.
set -e
cd "$(dirname "$0")/.."
python3 fetch/prepare.py
scripts/db.sh < sql/01_schema.sql
scripts/db.sh -t < sql/02_load.sql
