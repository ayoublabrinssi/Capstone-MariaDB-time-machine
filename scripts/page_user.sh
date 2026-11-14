#!/bin/sh
# Makes the database user the page connects as. The page never uses root:
# timemachine_page may read the timemachine database and add rows to one
# table, exact_text. Nothing else: no UPDATE, no DELETE, no DELETE HISTORY.
# The password is PAGE_DB_PASSWORD in .env; one is made there if it is missing.
# scripts/install.sh and scripts/start.sh run this; it can be run again any time.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "No .env: copy .env.example to .env first." >&2; exit 1; }
if ! grep -q '^PAGE_DB_PASSWORD=..*' .env; then
  printf 'PAGE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')" >> .env
  echo "Added PAGE_DB_PASSWORD to .env."
fi
password=$(sed -n 's/^PAGE_DB_PASSWORD=//p' .env | head -n 1)
# The password goes into the statement below as text, so only plain characters pass.
case "$password" in
  *[!A-Za-z0-9_-]*) echo "PAGE_DB_PASSWORD in .env may only hold letters, digits, - and _." >&2; exit 1 ;;
esac
scripts/db.sh <<SQL
CREATE OR REPLACE USER 'timemachine_page'@'%' IDENTIFIED BY '$password';
GRANT SELECT ON timemachine.* TO 'timemachine_page'@'%';
GRANT INSERT ON timemachine.exact_text TO 'timemachine_page'@'%';
SQL
echo "The page's user timemachine_page is ready: SELECT on timemachine, INSERT on exact_text only."
