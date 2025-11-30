#!/bin/bash
#
# Database Dump Pre-Backup Hook
# Creates a database dump before backup
#

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

BACKUP_DIR="/tmp/db-dumps"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="$BACKUP_DIR/dump_${TIMESTAMP}.sql"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting database dump hook"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create database dump
echo "Creating database dump..."
docker exec mariadb mysqldump \
    -u root \
    -p"${MYSQL_ROOT_PASSWORD:-changeme}" \
    --all-databases \
    --single-transaction \
    --quick \
    --lock-tables=false \
    > "$DUMP_FILE"

if [ $? -eq 0 ]; then
    echo "✓ Database dump created: $DUMP_FILE"
    echo "  Size: $(du -h "$DUMP_FILE" | cut -f1)"

    # Cleanup old dumps (keep last 3)
    echo "Cleaning up old dumps..."
    cd "$BACKUP_DIR"
    ls -t dump_*.sql | tail -n +4 | xargs -r rm -f
    echo "✓ Cleanup complete"

    exit 0
else
    echo "✗ Failed to create database dump"
    exit 1
fi
