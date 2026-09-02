#!/bin/bash
# Raspberry Pi 上の本プロジェクト（.env 含む）を tar.gz に退避する簡易バックアップ
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

tar -czf "$DEST/door-locker-$STAMP.tar.gz" \
  -C "$ROOT" \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='backups' \
  --exclude='*.log' \
  .

echo "Backup written: $DEST/door-locker-$STAMP.tar.gz"
# 古いバックアップを14日分残す
find "$DEST" -name 'door-locker-*.tar.gz' -mtime +14 -delete 2>/dev/null || true
