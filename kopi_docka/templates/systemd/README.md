# Kopi-Docka Systemd Templates

This directory contains systemd unit file templates for running kopi-docka as a system service with automated scheduled backups.

## Available Templates

### 1. kopi-docka.service.template
Main daemon service that runs kopi-docka continuously. This service:
- Runs as a systemd Type=notify daemon
- Uses extensive security hardening (read-only filesystem, capability restrictions, etc.)
- Can be triggered by the timer or started manually
- Sends watchdog heartbeats to systemd for health monitoring
- Automatically restarts on failures

**Use this for:** Production scheduled backups via systemd timer

### 2. kopi-docka.timer.template
Timer unit that triggers the daemon service on a schedule. This timer:
- Default schedule: Daily at 02:00 AM
- Includes extensive OnCalendar syntax examples and documentation
- Persistent: Runs missed backups after system downtime
- RandomizedDelaySec: Adds 0-15 minute random delay to prevent thundering herd

**Use this for:** Automated scheduled backup runs

### 3. kopi-docka-backup.service.template
One-shot service for single backup runs. This service:
- Type=oneshot: Runs once and exits
- Simpler security profile than the daemon
- No lock files or state management

**Use this for:** Manual backup runs, cron integration, or testing

## Installation

### Quick Start

```bash
# 1. Install the unit files to /etc/systemd/system
sudo kopi-docka admin service write-units

# 2. Reload systemd to recognize new units
sudo systemctl daemon-reload

# 3. Enable and start the timer (for scheduled backups)
sudo systemctl enable --now kopi-docka.timer

# 4. Check timer status
systemctl list-timers kopi-docka.timer
```

### Interactive Management

For easy service management without knowing systemctl commands:

```bash
sudo kopi-docka admin service manage
```

This opens an interactive menu where you can:
- View service and timer status
- Configure backup schedule
- View logs
- Control services (start/stop/restart)

## Customization

### Method 1: Using systemctl edit (Recommended)

To customize settings without modifying the installed files:

```bash
# Edit service settings
sudo systemctl edit kopi-docka.service

# Edit timer schedule
sudo systemctl edit kopi-docka.timer
```

This creates override files in `/etc/systemd/system/kopi-docka.{service,timer}.d/` that take precedence over the main files.

**Example: Change backup schedule to 03:30 AM:**

```bash
sudo systemctl edit kopi-docka.timer
```

Add:
```ini
[Timer]
OnCalendar=
OnCalendar=*-*-* 03:30:00
```

Note: The first empty `OnCalendar=` clears the default value.

### Method 2: Using kopi-docka manage command

```bash
sudo kopi-docka admin service manage
```

Select "Timer konfigurieren" and choose your preferred schedule.

### Method 3: Direct file editing

You can directly edit `/etc/systemd/system/kopi-docka.timer` but this is not recommended as changes will be overwritten if you run `write-units` again.

## Timer Schedule Examples

The timer uses systemd's OnCalendar syntax. Here are common patterns:

### Daily Backups
```ini
OnCalendar=*-*-* 02:00:00          # Every day at 02:00 AM
OnCalendar=*-*-* 23:00:00          # Every day at 11 PM
OnCalendar=daily                   # Every day at midnight
```

### Weekly Backups
```ini
OnCalendar=Mon *-*-* 03:00:00      # Every Monday at 03:00
OnCalendar=Sun *-*-* 02:00:00      # Every Sunday at 02:00
OnCalendar=Mon,Wed,Fri *-*-* 02:00:00  # Mon/Wed/Fri at 02:00
```

### Multiple Times Per Day
```ini
OnCalendar=*-*-* 02:00,14:00:00    # 02:00 and 14:00 daily
OnCalendar=*-*-* 00,06,12,18:00:00 # Every 6 hours
```

### Testing Schedule Syntax

Before applying a schedule, test it with:

```bash
systemd-analyze calendar "*-*-* 03:00:00"
```

This shows when the timer would trigger:
```
  Original form: *-*-* 03:00:00
Normalized form: *-*-* 03:00:00
    Next elapse: Mon 2025-12-22 03:00:00 UTC
       (in UTC): Mon 2025-12-22 03:00:00 UTC
```

## Customizing Backup Path

The service units default to `/backup` as the backup storage location. If your backups are stored elsewhere:

**Option 1: Edit the service file**
```bash
sudo systemctl edit kopi-docka.service
```

Add:
```ini
[Service]
ReadWritePaths=/your/custom/path /var/lib/docker /var/run/docker.sock /var/log /run/kopi-docka
```

**Option 2: Modify your kopi-docka config**

Edit `/etc/kopi-docka/config.json` and set `backup.base_path` to your desired location. The service will use this path automatically.

## Monitoring and Troubleshooting

### Check Service Status
```bash
# Service status
systemctl status kopi-docka.service

# Timer status
systemctl status kopi-docka.timer

# List all timers and their next run times
systemctl list-timers
```

### View Logs
```bash
# Follow live logs
journalctl -u kopi-docka.service -f

# Last 50 lines
journalctl -u kopi-docka.service -n 50

# Logs since 1 hour ago
journalctl -u kopi-docka.service --since "1 hour ago"

# Only errors
journalctl -u kopi-docka.service -p err

# Logs for specific date
journalctl -u kopi-docka.service --since "2025-12-20" --until "2025-12-21"
```

### Manual Backup Run
```bash
# Using the daemon service (will acquire lock)
sudo systemctl start kopi-docka.service

# Using the one-shot service (alternative)
sudo systemctl start kopi-docka-backup.service

# Or directly via CLI
sudo kopi-docka backup
```

### Disable Scheduled Backups
```bash
# Stop and disable the timer
sudo systemctl stop kopi-docka.timer
sudo systemctl disable kopi-docka.timer

# Service will no longer run automatically
# You can still run backups manually
```

## Security Notes

The service units include extensive security hardening:

- **NoNewPrivileges**: Prevents privilege escalation
- **ProtectSystem=strict**: Filesystem is read-only except specified paths
- **ProtectHome=read-only**: Home directories are read-only
- **PrivateTmp**: Service has its own /tmp directory
- **CapabilityBoundingSet**: All capabilities removed
- **SystemCallFilter**: Only allows necessary system calls
- **ProtectKernelTunables/Modules**: Prevents kernel modifications

These settings follow systemd security best practices. If you encounter permission issues, check:

1. **Backup path**: Ensure it's listed in `ReadWritePaths=`
2. **Docker socket**: Should be at `/var/run/docker.sock`
3. **Log path**: If using file logging, ensure path is in `ReadWritePaths=`

## Advanced Usage

### Running Multiple Backup Profiles

If you need multiple backup schedules or configurations:

1. Copy and rename the unit files:
   ```bash
   sudo cp /etc/systemd/system/kopi-docka.service /etc/systemd/system/kopi-docka-hourly.service
   sudo cp /etc/systemd/system/kopi-docka.timer /etc/systemd/system/kopi-docka-hourly.timer
   ```

2. Edit the new units to use different configs or schedules

3. Enable both timers:
   ```bash
   sudo systemctl enable --now kopi-docka.timer
   sudo systemctl enable --now kopi-docka-hourly.timer
   ```

### Integration with systemd-email

To receive email notifications on backup failures:

```bash
# Install systemd email notification
sudo apt install systemd-email  # Debian/Ubuntu

# Create override
sudo systemctl edit kopi-docka.service
```

Add:
```ini
[Service]
OnFailure=status-email@%n.service
```

## Links

- [Kopi-Docka Documentation](https://github.com/TZERO78/kopi-docka)
- [systemd Timer Documentation](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)
- [systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [systemd OnCalendar Syntax](https://www.freedesktop.org/software/systemd/man/systemd.time.html#Calendar%20Events)
