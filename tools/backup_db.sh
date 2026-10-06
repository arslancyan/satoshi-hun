#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=backups}"
mkdir -p "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
file="$BACKUP_DIR/satoshi_hunt_$timestamp.dump"
pg_dump --format=custom --no-owner --file="$file" "$DATABASE_URL"
echo "BACKUP=$file"
