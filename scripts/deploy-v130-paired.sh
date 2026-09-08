#!/usr/bin/env bash
# Run after pushing BOTH release folders to their corresponding GitHub repositories.
set -Eeuo pipefail
umask 077
GROWTH_STACK=/mnt/apps/dockge/data/wbm-growth-engine
BOOKING_STACK=/mnt/apps/dockge/data/bookingsystem2026
RELEASE_BACKUPS=/mnt/weddings_backups/wbm-growth-engine/database
RELEASE_STAMP=$(date +%Y%m%d-%H%M%S)
if [ "$(id -u)" != 0 ]; then
  echo 'Run this script with sudo bash.'
  exit 1
fi
trap 'echo "Deployment stopped. Keep the output above; no database restore or password change was attempted."' ERR
cd "$GROWTH_STACK"
docker compose config --quiet
docker compose -f "$BOOKING_STACK/compose.yaml" config --quiet
# Keep recoverable image references before rebuilding either application.
docker tag "$(docker inspect -f '{{.Image}}' wbm-growth-engine-app)" "wbm-growth-engine:before-v130-$RELEASE_STAMP"
docker tag "$(docker inspect -f '{{.Image}}' bookingsystem2026-app)" "bookingsystem2026:before-v841-$RELEASE_STAMP"
echo 'Building both apps before replacing either live container...'
docker compose build app
docker compose -f "$BOOKING_STACK/compose.yaml" build --no-cache app
# Fail if the pushed sources have not reached the built images.
docker compose run --rm --no-deps --entrypoint python app -c "from pathlib import Path; assert '2026.09.08-fill-my-dates-v1.3.0' in Path('/app/app/config.py').read_text(), 'Growth image is not V1.3.0'"
docker compose -f "$BOOKING_STACK/compose.yaml" run --rm --no-deps --entrypoint python app -c "from pathlib import Path; assert '2026.09.08-growth-availability-v8.41' in Path('/app/app/backup.py').read_text(), 'Booking image is not V8.41'"
mkdir -p "$RELEASE_BACKUPS"
backup_database() {
  local container=$1 database=$2 filename=$3
  docker exec "$container" pg_dump -U "$database" -d "$database" -Fc > "$filename.partial"
  test -s "$filename.partial"
  docker exec -i "$container" pg_restore --list < "$filename.partial" > /dev/null
  mv "$filename.partial" "$filename"
  echo "Database backup verified: $filename"
}
backup_database wbm-growth-engine-db growthengine "$RELEASE_BACKUPS/growth-before-v130-$RELEASE_STAMP.dump"
backup_database bookingsystem2026-db bookingapp "$RELEASE_BACKUPS/booking-before-v841-$RELEASE_STAMP.dump"
wait_health() {
  local port=$1 expected=$2
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$port/api/health" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status")=="ok" and d.get("build")==sys.argv[1] else 1)' "$expected" 2>/dev/null; then
      echo "Healthy: $expected"
      return
    fi
    sleep 2
  done
  echo "Health check failed on port $port. Deployment stopped."
  return 1
}
echo 'Updating Growth, then Booking...'
docker compose up -d --no-deps app
wait_health 30110 2026.09.08-fill-my-dates-v1.3.0
docker compose -f "$BOOKING_STACK/compose.yaml" up -d --no-deps app
wait_health 30049 2026.09.08-growth-availability-v8.41
echo 'Synchronising the latest Booking activity...'
docker compose -f "$BOOKING_STACK/compose.yaml" exec -T app python - <<'PY'
from app.growth_integration import sync_pending
result = sync_pending(maximum=100)
print(result)
if result['failed']:
    raise SystemExit('Apps are updated, but some records need a sync retry.')
if result['remaining']:
    print('More records remain; the next automatic sync will continue them.')
PY
echo 'Checking the live availability connection from Growth to Booking...'
docker compose exec -T app python - <<'PY_CHECK'
from app.gaps import booking_window, london_today
result = booking_window(london_today(), london_today())
print('Live availability connection OK; current packages:', len(result.packages))
PY_CHECK
echo 'Both apps updated. Refresh Growth: Fill my dates is ready.'
