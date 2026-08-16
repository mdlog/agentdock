#!/usr/bin/env bash
# Snapshot the database that holds the catalogue and every task.
#
# Re-syncing the 256k catalogue from 8004scan takes about an hour and leans on a
# sponsor's rate limit; the tasks and audit trail cannot be re-derived at all.
# Keeps the last 7 snapshots, which is enough to survive the judging window.
set -euo pipefail

DEST="${BACKUP_DIR:-$HOME/.agentdock-backups}"
KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

docker exec agentdock-mongo mongodump --db agentdock --archive --gzip > "$DEST/agentdock-$STAMP.archive.gz"

# Refuse to keep a snapshot that is suspiciously small: a truncated dump that
# looks like a backup is worse than an obvious failure.
SIZE=$(stat -c %s "$DEST/agentdock-$STAMP.archive.gz")
if [ "$SIZE" -lt 1000000 ]; then
  echo "Dump is only ${SIZE} bytes — refusing to keep it" >&2
  rm -f "$DEST/agentdock-$STAMP.archive.gz"
  exit 1
fi

ls -1t "$DEST"/agentdock-*.archive.gz | tail -n "+$((KEEP + 1))" | xargs -r rm -f
echo "Backed up ${SIZE} bytes to $DEST/agentdock-$STAMP.archive.gz"
