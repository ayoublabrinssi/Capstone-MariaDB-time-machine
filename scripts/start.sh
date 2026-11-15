#!/bin/sh
# One command from a fresh clone to the page on http://127.0.0.1:8000:
#   1. checks Docker, Docker Compose and Python 3
#   2. makes .env with a random root password, if there is none
#   3. starts MariaDB and waits until it is ready
#   4. downloads the history from Wikipedia, if it is not on disk yet (about 15 min)
#   5. builds and loads the database, if it is not loaded yet
#   6. runs the tests
#   7. starts the page
# Before step 1 it asks which data to use: the quick sample of three articles
# that comes with the repository (default, no download), all 45 articles at the
# fixed date, 26 Oct 2026 (the data the tests and results were made on), or all
# 45 articles with the newest edits.
# Run it again any time: the steps already done are skipped.
#
#   scripts/start.sh                  everything
#   scripts/start.sh --data sample    Rabat, Ifrane and Asilah from data/sample/: no download, about a minute
#   scripts/start.sh --data fixed     all 45 articles at the fixed date, 26 Oct 2026, without asking
#   scripts/start.sh --data newest    all 45 articles, every edit up to today, without asking
#   scripts/start.sh --refetch        download the data again
#   scripts/start.sh --reload         build and load the database again
#   scripts/start.sh --no-tests       skip step 6
#   scripts/start.sh --no-page        stop after the tests (used by CI)
#   PORT=8001 scripts/start.sh        the page on another port
set -e
cd "$(dirname "$0")/.."

reload=0
tests=1
page=1
data=""
refetch=0
while [ $# -gt 0 ]; do
  case "$1" in
    --reload) reload=1 ;;
    --no-tests) tests=0 ;;
    --no-page) page=0 ;;
    --refetch) refetch=1 ;;
    --data)
      shift
      case "$1" in fixed|newest|sample) data="$1" ;; *) echo "--data takes sample, fixed or newest" >&2; exit 2 ;; esac ;;
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
current=$(cat data/load/.source 2>/dev/null || true)   # what scripts/install.sh loaded last: sample or full
fetch=1
if [ "$data" = sample ]; then
  fetch=0
elif [ "$have" -ge "$want" ] && [ -z "$data" ] && [ "$refetch" = 0 ]; then
  fetch=0
elif [ "$current" = sample ] && [ -z "$data" ] && [ "$refetch" = 0 ]; then
  data=sample   # the sample is loaded and nothing else was asked for: keep it
  fetch=0
elif [ -z "$data" ]; then
  data=sample
  fetch=0
  if [ -t 0 ]; then
    echo "Which data should the time machine hold?"
    echo "  1  Quick (default): Rabat, Ifrane and Asilah, which come with the repository."
    echo "     No download, ready in about a minute. The other 42 cities are missing."
    echo "  2  Full, fixed date: all 45 articles as they were on 26 Oct 2026, the data the"
    echo "     tests and the results in this repository were made on. About 15 minutes of download."
    echo "  3  Full, newest: all 45 articles with every edit up to today. Same download; results"
    echo "     may differ from the test results and the numbers in the README."
    echo "  Help: stop with Ctrl+C and run scripts/start.sh --help"
    printf "Choose 1, 2 or 3 [1]: "
    read -r answer
    case "$answer" in
      2) data=fixed; fetch=1 ;;
      3) data=newest; fetch=1 ;;
    esac
  fi
fi
source=full
[ "$data" = sample ] && source=sample

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
  page_password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  sed -e "s/^MARIADB_ROOT_PASSWORD=.*/MARIADB_ROOT_PASSWORD=$password/" \
      -e "s/^PAGE_DB_PASSWORD=.*/PAGE_DB_PASSWORD=$page_password/" .env.example > .env
  echo "Made .env with two random passwords, one for root and one for the page's user (git-ignored)."
fi

step "3/7 Starting MariaDB"
docker compose up -d --wait
q 'SELECT 1' >/dev/null 2>&1 || fail "MariaDB is up but refuses the password in .env.
The database volume was probably made with another password. To start over:
  docker compose down -v && scripts/start.sh"
echo "MariaDB $(q 'SELECT VERSION()') is ready."

step "4/7 Data"
if [ "$data" = sample ]; then
  echo "Using the sample in data/sample/: Rabat, Ifrane and Asilah, as they were on 26 Oct 2026. No download."
  echo "For all $want articles: scripts/start.sh --data fixed"
elif [ "$fetch" = 0 ]; then
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
  WHERE TABLE_SCHEMA = 'timemachine'
    AND TABLE_NAME IN ('page', 'article', 'article_period', 'revision_text', 'exact_text')")
[ "$current" = "$source" ] || reload=1     # the other data set is loaded, or none
if [ "$loaded" = 5 ] && [ "$reload" = 0 ] && [ "$(q 'SELECT COUNT(*) FROM page')" -gt 0 ]; then
  echo "Already loaded ($source data). Use --reload to build it again."
  scripts/page_user.sh
elif [ "$source" = sample ]; then
  scripts/install.sh --sample
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

if [ "$page" = 0 ]; then
  step "7/7 The page is not started (--no-page). Start it with scripts/run.sh"
  exit 0
fi
step "7/7 The page"
exec scripts/run.sh
