#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
if [ "$(id -u)" != 0 ]; then
  echo 'Run with sudo bash.'
  exit 1
fi
cd /mnt/apps/dockge/data/wbm-growth-engine
RELEASE_STAMP=$(date +%Y%m%d-%H%M%S)
RELEASE_BACKUPS=/mnt/weddings_backups/wbm-growth-engine/database
trap 'echo "Update stopped. Keep the output above; no automatic restore was attempted."' ERR
docker compose config --quiet
docker tag "$(docker inspect -f '{{.Image}}' wbm-growth-engine-app)" "wbm-growth-engine:before-v151-$RELEASE_STAMP"
docker compose build app
docker compose run --rm --no-deps --entrypoint python app -c "from pathlib import Path; assert '2026.09.09-admin-settings-v1.5.1' in Path('/app/app/config.py').read_text(), 'Expected Growth V1.5.1'; from app.account import change_password; from app.website import make_credentials"
mkdir -p "$RELEASE_BACKUPS"
RELEASE_DUMP="$RELEASE_BACKUPS/growth-before-v151-$RELEASE_STAMP.dump"
docker exec wbm-growth-engine-db pg_dump -U growthengine -d growthengine -Fc > "$RELEASE_DUMP.partial"
test -s "$RELEASE_DUMP.partial"
docker exec -i wbm-growth-engine-db pg_restore --list < "$RELEASE_DUMP.partial" > /dev/null
mv "$RELEASE_DUMP.partial" "$RELEASE_DUMP"
echo "Backup archive is readable: $RELEASE_DUMP"
docker compose up -d --no-deps app
for attempt in $(seq 1 60); do
  if curl -fsS --max-time 3 http://127.0.0.1:30110/api/health 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status")=="ok" and d.get("build")=="2026.09.09-admin-settings-v1.5.1" else 1)' 2>/dev/null; then
    echo 'Growth V1.5.1 is healthy. Open Admin or click the round profile button.'
    echo 'No existing password was changed. Booking was not rebuilt.'
    exit 0
  fi
  sleep 2
done
echo 'Growth did not pass the expected build/health check. Keep this output.'
exit 1
