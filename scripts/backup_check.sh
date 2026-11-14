#!/bin/sh
# Backs up the article table two ways and restores each into a scratch
# database, to show what a backup of a versioned table really holds.
# A plain mariadb-dump carries only the current rows: the history is gone
# after a restore, with no warning. --dump-history carries every version and
# restores them with system_versioning_insert_history, the same switch the
# loader uses. Needs the database running and loaded.
#   scripts/backup_check.sh
set -e
cd "$(dirname "$0")/.."
CONTAINER="${CONTAINER:-timemachine-mariadb}"

in_container() {
  docker exec -i "$CONTAINER" sh -c 'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; '"$1"
}
versions() {
  in_container "mariadb -uroot -N -e 'SELECT COUNT(*) FROM $1.article FOR SYSTEM_TIME ALL'"
}

echo "article in timemachine: $(versions timemachine) versions"
for mode in plain history; do
  flag=""
  [ "$mode" = history ] && flag="--dump-history"
  db="timemachine_backup_$mode"
  in_container "mariadb-dump -uroot $flag timemachine article > /tmp/article_$mode.sql"
  in_container "mariadb -uroot -e 'DROP DATABASE IF EXISTS $db; CREATE DATABASE $db'"
  in_container "mariadb -uroot $db < /tmp/article_$mode.sql"
  size=$(in_container "wc -c < /tmp/article_$mode.sql")
  echo "mariadb-dump ${flag:-(no option)}: file $((size / 1024)) KB, restored table has $(versions "$db") versions"
done
same=$(in_container "mariadb -uroot -N -e \"SELECT COUNT(*) FROM timemachine.article FOR SYSTEM_TIME ALL a JOIN timemachine_backup_history.article FOR SYSTEM_TIME ALL b ON a.page_id = b.page_id AND a.row_end = b.row_end AND a.row_start = b.row_start AND a.rev_id = b.rev_id\"")
echo "versions identical after the --dump-history restore (same article, revision, start and end): $same"
in_container "mariadb -uroot -e 'DROP DATABASE timemachine_backup_plain; DROP DATABASE timemachine_backup_history'; rm -f /tmp/article_plain.sql /tmp/article_history.sql"
