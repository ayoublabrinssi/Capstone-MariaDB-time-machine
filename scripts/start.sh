#!/bin/sh
# One command from a fresh clone to the page on http://127.0.0.1:8000:
#   1. checks Docker, Docker Compose and Python 3
#   2. makes .env with a random root password, if there is none
#   3. starts MariaDB and waits until it is ready
#   4. downloads the history from Wikipedia, if it is not on disk yet (about 15 min)
#   5. builds and loads the database, if it is not loaded yet
#   6. runs the tests
#   7. starts the page
# Before step 1 it asks which data to download: the fixed date, 26 Oct 2026
# (default; the data the tests and results were made on), or the newest edits.
# Run it again any time: the steps already done are skipped.
#
#   scripts/start.sh                  everything
#   scripts/start.sh --data fixed     the fixed date, 26 Oct 2026, without asking
#   scripts/start.sh --data newest    every edit up to today, without asking
#   scripts/start.sh --refetch        download the data again
#   scripts/start.sh --reload         build and load the database again
#   scripts/start.sh --no-tests       skip step 6
#   PORT=8001 scripts/start.sh        the page on another port
set -e
cd "$(dirname "$0")/.."

reload=0
tests=1
data=""
refetch=0
while [ $# -gt 0 ]; do
  case "$1" in
    --reload) reload=1 ;;
    --no-tests) tests=0 ;;
    --refetch) refetch=1 ;;
    --data)
      shift
      case "$1" in fixed|newest) data="$1" ;; *) echo "--data takes fixed or newest" >&2; exit 2 ;; esac ;;
    -h|--help) awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see scripts/start.sh --help)" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n== %s\n' "$1"; }
q() { scripts/db.sh -N -e "$1" </dev/null; }
fail() { printf '\nStopped: %s\n' "$1" >&2; exit 1; }

# The one question, asked first so the rest runs on its own.
want=$(grep -cv '^[[:space:]]*\(#\|$\)' data/articles.txt)
have=0
for f in data/raw/*.json; do
  [ -f "$f" ] && [ "$f" != data/raw/manifest.json ] && have=$((have + 1))
done
fetch=1
if [ "$have" -ge "$want" ] && [ -z "$data" ] && [ "$refetch" = 0 ]; then
  fetch=0
elif [ -z "$data" ]; then
  data=fixed
  if [ -t 0 ]; then
    echo "Which data should be downloaded from Wikipedia?"
    echo "  1  Fixed date, 26 Oct 2026 (default). The data the tests and the results in"
    echo "     this repository were made on. Choose this to compare with the test results."
    echo "  2  Newest, every edit up to today. Results may differ from the test results"
    echo "     and the numbers in the README."
    printf "Choose 1 or 2 [1]: "
    read -r answer
    [ "$answer" = 2 ] && data=newest
  fi
fi

step "1/7 Checking the tools"
command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install Docker Desktop, or Colima on a Mac."
docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Start Docker Desktop, or run: colima start"
docker compose version >/dev/null 2>&1 || fail "Docker Compose is missing. It comes with Docker Desktop; with Colima, install docker-compose."
command -v python3 >/dev/null 2>&1 || fail "Python 3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || fail "Python 3.8 or newer is needed."
python3 -m venv --help >/dev/null 2>&1 || fail "The Python venv module is missing (on Debian or Ubuntu: apt install python3-venv)."
echo "Docker, Compose and $(python3 --version) are ready."

step "2/7 Settings"
if [ -f .env ]; then
  echo ".env is there, kept as it is."
else
  password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  sed "s/^MARIADB_ROOT_PASSWORD=.*/MARIADB_ROOT_PASSWORD=$password/" .env.example > .env
  echo "Made .env with a random root password (git-ignored)."
fi

step "3/7 Starting MariaDB"
docker compose up -d --wait
q 'SELECT 1' >/dev/null 2>&1 || fail "MariaDB is up but refuses the password in .env.
The database volume was probably made with another password. To start over:
  docker compose down -v && scripts/start.sh"
echo "MariaDB $(q 'SELECT VERSION()') is ready."

step "4/7 Data"
if [ "$fetch" = 0 ]; then
  echo "All $want articles are already downloaded. To change the data: --data newest or --data fixed."
else
  echo "Downloading the $data data from Wikipedia: about 15 minutes for all $want articles."
  echo "Articles already on disk with this data are skipped. Stop it any time, the next run goes on."
  force=""
  [ "$refetch" = 1 ] && force="--force"
  if [ "$data" = fixed ]; then
    scripts/fetch.sh --snapshot data/snapshot.tsv $force
  else
    scripts/fetch.sh $force
  fi
  reload=1
fi

step "5/7 Loading the database"
loaded=$(q "SELECT COUNT(*) FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = 'timemachine' AND TABLE_NAME IN ('page', 'article', 'article_period', 'revision_text')")
if [ "$loaded" = 4 ] && [ "$reload" = 0 ] && [ "$(q 'SELECT COUNT(*) FROM page')" -gt 0 ]; then
  echo "Already loaded. Use --reload to build it again."
else
  scripts/install.sh
fi

if [ "$tests" = 1 ]; then
  step "6/7 Tests"
  # The page tests use .venv; run.sh makes it the same way on its first start.
  if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    .venv/bin/pip install --quiet -r app/requirements.txt
  fi
  scripts/test.sh
else
  step "6/7 Tests skipped"
fi

step "7/7 The page"
exec scripts/run.sh
