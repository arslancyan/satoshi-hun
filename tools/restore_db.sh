#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"
case "$BACKUP_FILE" in *.dump) ;; *) echo 'BACKUP_FILE must be a pg_dump custom-format .dump file' >&2; exit 2;; esac
printf 'This replaces objects in the target database. Type RESTORE-SATOSHI-HUNT to continue: '
read confirmation
[ "$confirmation" = "RESTORE-SATOSHI-HUNT" ] || { echo 'Restore cancelled.'; exit 1; }
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$BACKUP_FILE"
echo 'RESTORE COMPLETE'
