#!/bin/bash
#
# Nextcloud Pre-Backup Hook
# Enables maintenance mode before backup
#

set -e  # Exit on error
set -u  # Exit on undefined variable

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Nextcloud pre-backup hook"

# Enable maintenance mode
echo "Enabling Nextcloud maintenance mode..."
docker exec nextcloud php occ maintenance:mode --on

if [ $? -eq 0 ]; then
    echo "✓ Maintenance mode enabled successfully"
    exit 0
else
    echo "✗ Failed to enable maintenance mode"
    exit 1
fi
