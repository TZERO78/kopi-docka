# Pre/Post Backup Hooks

[← Back to README](../README.md)

## Overview

Kopi-Docka supports custom hook scripts that run before and after backup and restore operations. This is perfect for:
- Enabling/disabling application maintenance mode
- Creating custom database dumps
- Sending notifications
- Running pre-flight checks
- Cleanup tasks

## Hook Types

| Hook Type | When It Runs | Failure Behavior |
|-----------|--------------|------------------|
| `pre_backup` | Before stopping containers | **Aborts backup** - containers not stopped |
| `post_backup` | After starting containers | **Warning only** - containers already running |
| `pre_restore` | Before restore begins | **Aborts restore** - no changes made |
| `post_restore` | After restore completes | **Warning only** - restore already done |

## Configuration

Add hooks to your config.json:

```json
{
  "backup": {
    "hooks": {
      "pre_backup": "/opt/hooks/pre-backup.sh",
      "post_backup": "/opt/hooks/post-backup.sh",
      "pre_restore": "/opt/hooks/pre-restore.sh",
      "post_restore": "/opt/hooks/post-restore.sh"
    }
  }
}
```

## Environment Variables

Your hook scripts receive these environment variables:

```bash
KOPI_DOCKA_HOOK_TYPE=pre_backup    # Hook type being executed
KOPI_DOCKA_UNIT_NAME=nextcloud     # Name of the backup unit (if applicable)
```

## Example: Nextcloud Maintenance Mode

### Hook Scripts

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

echo "Enabling Nextcloud maintenance mode..."
docker exec nextcloud php occ maintenance:mode --on

if [ $? -eq 0 ]; then
    echo "✓ Maintenance mode enabled"
    exit 0
else
    echo "✗ Failed to enable maintenance mode"
    exit 1
fi
```

**post-backup.sh:**
```bash
#!/bin/bash
set -e

echo "Disabling Nextcloud maintenance mode..."
docker exec nextcloud php occ maintenance:mode --off

if [ $? -eq 0 ]; then
    echo "✓ Maintenance mode disabled"
    exit 0
else
    echo "✗ Failed to disable maintenance mode"
    exit 1
fi
```

### Make Executable

```bash
chmod +x /opt/hooks/pre-backup.sh
chmod +x /opt/hooks/post-backup.sh
```

### Configure

```json
{
  "backup": {
    "hooks": {
      "pre_backup": "/opt/hooks/pre-backup.sh",
      "post_backup": "/opt/hooks/post-backup.sh"
    }
  }
}
```

## Example: Database Dump

Create a custom database dump before backup:

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

BACKUP_DIR="/tmp/db-dumps"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "Creating database dump..."
docker exec mariadb mysqldump \
    -u root \
    -p"${MYSQL_ROOT_PASSWORD}" \
    --all-databases \
    --single-transaction \
    > "$BACKUP_DIR/dump_${TIMESTAMP}.sql"

echo "✓ Database dump created: $BACKUP_DIR/dump_${TIMESTAMP}.sql"
```

**post-backup.sh:**
```bash
#!/bin/bash
set -e

BACKUP_DIR="/tmp/db-dumps"

# Cleanup old dumps (keep last 3)
echo "Cleaning up old database dumps..."
cd "$BACKUP_DIR"
ls -t dump_*.sql | tail -n +4 | xargs -r rm -f

echo "✓ Cleanup complete"
```

## Example: Telegram Notifications

Send notifications about backup status:

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

TELEGRAM_BOT_TOKEN="your-bot-token"
TELEGRAM_CHAT_ID="your-chat-id"
HOSTNAME=$(hostname)

MESSAGE="🔧 Backup starting on ${HOSTNAME}"

curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d text="${MESSAGE}" \
    -d parse_mode="HTML" > /dev/null

echo "✓ Telegram notification sent"
```

**post-backup.sh:**
```bash
#!/bin/bash

TELEGRAM_BOT_TOKEN="your-bot-token"
TELEGRAM_CHAT_ID="your-chat-id"
HOSTNAME=$(hostname)

if [ $? -eq 0 ]; then
    MESSAGE="✅ Backup completed successfully on ${HOSTNAME}"
else
    MESSAGE="❌ Backup failed on ${HOSTNAME}"
fi

curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d text="${MESSAGE}" \
    -d parse_mode="HTML" > /dev/null

echo "✓ Telegram notification sent"
```

## Example: Stop/Start Related Services

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

echo "Stopping Nginx reverse proxy..."
systemctl stop nginx

echo "Flushing Redis cache..."
docker exec redis redis-cli FLUSHALL

echo "✓ Related services prepared"
```

**post-backup.sh:**
```bash
#!/bin/bash
set -e

echo "Starting Nginx reverse proxy..."
systemctl start nginx

echo "Waiting for Nginx to be ready..."
sleep 3

echo "✓ Related services restored"
```

## Example: Multi-Unit Hooks

Use the `KOPI_DOCKA_UNIT_NAME` variable to run unit-specific commands:

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

UNIT_NAME="${KOPI_DOCKA_UNIT_NAME}"

case "$UNIT_NAME" in
    nextcloud)
        echo "Nextcloud: Enabling maintenance mode..."
        docker exec nextcloud php occ maintenance:mode --on
        ;;

    wordpress)
        echo "WordPress: Disabling cron..."
        docker exec wordpress wp cron event delete --all
        ;;

    gitlab)
        echo "GitLab: Creating backup marker..."
        docker exec gitlab touch /var/opt/gitlab/backup_in_progress
        ;;

    *)
        echo "No specific preparation for unit: $UNIT_NAME"
        ;;
esac

echo "✓ Unit-specific preparation complete"
```

## Example: Health Checks

Run pre-flight checks before backup:

**pre-backup.sh:**
```bash
#!/bin/bash
set -e

echo "Running pre-flight checks..."

# Check disk space
FREE_SPACE=$(df /backup | awk 'NR==2 {print $4}')
REQUIRED_SPACE=10485760  # 10GB in KB

if [ "$FREE_SPACE" -lt "$REQUIRED_SPACE" ]; then
    echo "✗ Insufficient disk space: ${FREE_SPACE}KB available, ${REQUIRED_SPACE}KB required"
    exit 1
fi

# Check Docker daemon
if ! docker info > /dev/null 2>&1; then
    echo "✗ Docker daemon not accessible"
    exit 1
fi

# Check critical containers
CRITICAL_CONTAINERS="nextcloud mariadb redis"
for container in $CRITICAL_CONTAINERS; do
    if ! docker ps | grep -q "$container"; then
        echo "✗ Critical container not running: $container"
        exit 1
    fi
done

echo "✓ All pre-flight checks passed"
```

## Logging

All hook executions are logged to journald with stdout/stderr:

```bash
# View all hook logs
sudo journalctl -u kopi-docka.service | grep -i hook

# View specific hook type
sudo journalctl -u kopi-docka.service | grep "pre_backup"

# View hook output
sudo journalctl -u kopi-docka.service -o verbose | grep -A 10 "Hook.*stdout"
```

Example log output:
```
Executing pre_backup hook: /opt/hooks/pre-backup.sh
Hook pre_backup completed successfully in 2.3s
stdout: Enabling Nextcloud maintenance mode...
stdout: ✓ Maintenance mode enabled
```

## Error Handling

### Pre-Backup Hook Failure

If a pre-backup hook fails, the backup is **aborted**:

```bash
# Hook exits with non-zero
exit 1

# Result:
# → Backup aborted
# → Containers NOT stopped
# → No snapshots created
# → Error logged to journal
```

### Post-Backup Hook Failure

If a post-backup hook fails, a **warning** is logged but backup continues:

```bash
# Hook exits with non-zero
exit 1

# Result:
# → Warning logged
# → Containers already restarted
# → Snapshots already created
# → Backup marked successful (with warning)
```

## Best Practices

### 1. Always Use Shebang and Set Options

```bash
#!/bin/bash
set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure
```

### 2. Make Scripts Executable

```bash
chmod +x /opt/hooks/*.sh
```

### 3. Test Hooks Independently

```bash
# Test pre-backup hook
/opt/hooks/pre-backup.sh

# Test with environment variables
KOPI_DOCKA_HOOK_TYPE=pre_backup KOPI_DOCKA_UNIT_NAME=nextcloud /opt/hooks/pre-backup.sh
```

### 4. Add Timeout Protection

Use `timeout` command for operations that might hang:

```bash
#!/bin/bash
set -e

# Timeout after 60 seconds
timeout 60 docker exec nextcloud php occ maintenance:mode --on || {
    echo "✗ Timeout enabling maintenance mode"
    exit 1
}
```

### 5. Log Everything

```bash
#!/bin/bash
set -e

LOG_FILE="/var/log/kopi-docka-hooks.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting pre-backup hook for ${KOPI_DOCKA_UNIT_NAME}"
log "Enabling maintenance mode..."

# Your commands here

log "✓ Pre-backup hook completed"
```

### 6. Use Lock Files

Prevent concurrent hook executions:

```bash
#!/bin/bash
set -e

LOCK_FILE="/var/run/kopi-docka-hook.lock"

# Acquire lock
exec 200>"$LOCK_FILE"
flock -n 200 || {
    echo "✗ Hook already running"
    exit 1
}

# Your commands here

# Lock released automatically on script exit
```

### 7. Validate Environment

```bash
#!/bin/bash
set -e

# Check required variables
if [ -z "${KOPI_DOCKA_HOOK_TYPE:-}" ]; then
    echo "✗ KOPI_DOCKA_HOOK_TYPE not set"
    exit 1
fi

# Check required commands
for cmd in docker curl jq; do
    if ! command -v "$cmd" > /dev/null; then
        echo "✗ Required command not found: $cmd"
        exit 1
    fi
done
```

## Troubleshooting

### Hook Not Executing

**Check config:**
```bash
sudo kopi-docka show-config | grep hooks
```

**Check file exists:**
```bash
ls -l /opt/hooks/pre-backup.sh
```

**Check permissions:**
```bash
# Should be executable
chmod +x /opt/hooks/pre-backup.sh
```

### Hook Fails Silently

**Check logs:**
```bash
sudo journalctl -u kopi-docka.service | grep -i hook
```

**Test manually:**
```bash
sudo /opt/hooks/pre-backup.sh
echo $?  # Should be 0 for success
```

### Hook Times Out

Default timeout is 300 seconds (5 minutes). Adjust if needed:

```bash
# In your hook script
# Keep operations under 5 minutes
# Or split into multiple hooks
```

## Advanced Examples

See the `examples/hooks/` directory for more complete examples:

- `examples/hooks/nextcloud-maintenance.sh` - Full Nextcloud maintenance mode
- `examples/hooks/database-dump.sh` - Complete database dump workflow
- `examples/hooks/telegram-notify.sh` - Telegram notifications
- `examples/hooks/health-check.sh` - Comprehensive pre-flight checks

[← Back to README](../README.md)
