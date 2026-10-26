#!/bin/sh
# Opens the mariadb client inside the container, on the timemachine database.
# The root password is read inside the container from MARIADB_ROOT_PASSWORD
# (set by compose from .env), so it is never stored in this repo.
#
#   scripts/db.sh                         interactive prompt
#   scripts/db.sh < sql/01_schema.sql     run one file
#   scripts/db.sh -t < sql/queries.sql    with extra client options
#
# Other container or database: CONTAINER=name DB=name scripts/db.sh
CONTAINER="${CONTAINER:-timemachine-mariadb}"
DB="${DB:-timemachine}"

if [ -t 0 ]; then tty="-it"; else tty="-i"; fi
exec docker exec $tty "$CONTAINER" \
  sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot "$@"' sh "$DB" "$@"
