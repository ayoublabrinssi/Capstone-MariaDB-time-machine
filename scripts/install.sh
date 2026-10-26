#!/bin/sh
# Creates the schema and loads the revisions from data/raw/ into MariaDB.
# Week 2 fills this in. For now it creates the schema only.
set -e
cd "$(dirname "$0")/.."
scripts/db.sh < sql/01_schema.sql
echo "Schema created in database timemachine"
