#!/bin/bash
#
# Nextcloud Post-Backup Hook
# Disables maintenance mode after backup
#

set -e  # Exit on error
set -u  # Exit on undefined variable

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Nextcloud post-backup hook"

# Disable maintenance mode
echo "Disabling Nextcloud maintenance mode..."
docker exec nextcloud php occ maintenance:mode --off

if [ $? -eq 0 ]; then
    echo "✓ Maintenance mode disabled successfully"
    exit 0
else
    echo "✗ Failed to disable maintenance mode"
    exit 1
fi
