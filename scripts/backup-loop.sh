#!/bin/sh
set -eu

mkdir -p /backups/database

while true; do
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  temporary="/backups/database/growth-engine-${stamp}.dump.partial"
  final="/backups/database/growth-engine-${stamp}.dump"

  if pg_dump --format=custom --file="$temporary"; then
    mv "$temporary" "$final"
    (
      cd /backups/database
      sha256sum "$(basename "$final")" > "$(basename "$final").sha256"
    )
  else
    rm -f "$temporary"
  fi

  find /backups/database -type f -name 'growth-engine-*.dump' -mtime "+${BACKUP_RETENTION_DAYS:-60}" -delete
  find /backups/database -type f -name 'growth-engine-*.dump.sha256' -mtime "+${BACKUP_RETENTION_DAYS:-60}" -delete
  sleep 86400
done
