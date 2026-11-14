#!/bin/sh
# Who can change history? Asks the server, in two parts, and prints its answers.
#
#   1. On the running server (secure_timestamp = NO, the default): what a user
#      with ordinary write rights on one database may do to a versioned table.
#   2. On a second, throwaway server started with --secure-timestamp=YES: the
#      same statements as root.
#
# Works on a scratch database (timemachine_trust), a scratch user and a scratch
# container, and removes all three at the end. Needs the database running.
#   scripts/trust_check.sh
set -e
cd "$(dirname "$0")/.."
CONTAINER="${CONTAINER:-timemachine-mariadb}"
LOCKED="timemachine-trust"
secret=$(python3 -c 'import secrets; print(secrets.token_hex(12))')   # scratch passwords, hex only

root() { docker exec -i "$CONTAINER" sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot -N "$@"' sh "$@"; }
writer() { docker exec -i -e MYSQL_PWD="$secret" "$CONTAINER" mariadb -utm_trust_writer -N timemachine_trust; }
locked() { docker exec -i -e MYSQL_PWD="$secret" "$LOCKED" mariadb -uroot -N "$@"; }

cleanup() {
  docker rm -f "$LOCKED" >/dev/null 2>&1 || true
  root -e "DROP DATABASE IF EXISTS timemachine_trust; DROP USER IF EXISTS 'tm_trust_writer'@'%'" 2>/dev/null || true
}
trap cleanup EXIT

# Sends one statement (plus what it needs before it) and prints the server's
# answer on one line: "accepted", or the error number and message.
ask() {
  label=$1; client=$2; sql=$3
  if answer=$(printf '%s\n' "$sql" | $client 2>&1); then
    answer=accepted
  else
    answer=$(printf '%s\n' "$answer" | sed -n 's/^ERROR \([0-9]*\) ([^)]*) at line [0-9]*: /error \1: /p' | head -n 1)
  fi
  printf '  %-46s %s\n' "$label" "$answer"
}

TABLE="CREATE TABLE price (
  item VARCHAR(20) NOT NULL PRIMARY KEY, mad DECIMAL(6,2),
  row_start TIMESTAMP(6) AS ROW START INVISIBLE, row_end TIMESTAMP(6) AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end)) WITH SYSTEM VERSIONING;
INSERT INTO price (item, mad) VALUES ('tea', 14.00);"
FAKE_PAST="SET @@system_versioning_insert_history = 1;
INSERT INTO price (item, mad, row_start, row_end) VALUES ('sugar', 1.00, '2015-01-01 00:00:00', '2016-01-01 00:00:00');"
FUTURE="SET @@timestamp = UNIX_TIMESTAMP('2030-01-01 00:00:00'); UPDATE price SET mad = 16.00 WHERE item = 'tea';"
SHOW="SET time_zone = '+00:00';
SELECT CONCAT('    ', RPAD(item, 6, ' '), LPAD(mad, 6, ' '), '   ', row_start, '  to  ', row_end)
FROM price FOR SYSTEM_TIME ALL ORDER BY row_start;"

cleanup
root -e "CREATE DATABASE timemachine_trust;
CREATE USER 'tm_trust_writer'@'%' IDENTIFIED BY '$secret';
GRANT SELECT, INSERT, UPDATE, DELETE ON timemachine_trust.* TO 'tm_trust_writer'@'%'"
printf '%s\n' "$TABLE" | root timemachine_trust

echo "1. $(root -e "SELECT CONCAT('MariaDB ', VERSION(), ', secure_timestamp = ', @@secure_timestamp)") (the default)"
echo "   A user with SELECT, INSERT, UPDATE and DELETE on one database, nothing else:"
ask "an ordinary UPDATE" writer "UPDATE price SET mad = 15.00 WHERE item = 'tea';"
ask "DELETE HISTORY" writer "DELETE HISTORY FROM price;"
ask "INSERT a version dated 2015" writer "$FAKE_PAST"
ask "UPDATE with the session clock set to 2030" writer "$FUTURE"
echo "   What the table holds now (item, price, row_start to row_end):"
printf '%s\n' "$SHOW" | root timemachine_trust
echo "   The 2015 version never happened, and the last version starts in 2030."
root -e "GRANT DELETE HISTORY ON timemachine_trust.* TO 'tm_trust_writer'@'%'"
ask "DELETE HISTORY after GRANT DELETE HISTORY" writer "DELETE HISTORY FROM price;"

image=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")
docker run -d --name "$LOCKED" -e MARIADB_ROOT_PASSWORD="$secret" "$image" --secure-timestamp=YES >/dev/null
ready=0
for _ in $(seq 1 90); do
  if docker exec "$LOCKED" healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "The second server did not start within 90 seconds." >&2; exit 1; }
locked -e "CREATE DATABASE timemachine_trust"
printf '%s\n' "$TABLE" | locked timemachine_trust

echo
echo "2. A second server started with --secure-timestamp=YES, the same statements as root:"
ask "an ordinary UPDATE" "locked timemachine_trust" "UPDATE price SET mad = 15.00 WHERE item = 'tea';"
ask "INSERT a version dated 2015" "locked timemachine_trust" "$FAKE_PAST"
ask "UPDATE with the session clock set to 2030" "locked timemachine_trust" "$FUTURE"
echo "   What the table holds now:"
printf '%s\n' "$SHOW" | locked timemachine_trust
echo "   Only the server clock writes system time here. It also means history cannot be"
echo "   imported: load it first on a server without the option, then restart with it."
