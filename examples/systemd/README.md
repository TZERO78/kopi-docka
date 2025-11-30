# Systemd Unit Files

Kopi-Docka automatically generates systemd unit files for you. You don't need to create them manually.

## Generate Unit Files

```bash
sudo kopi-docka write-units
```

This creates:
- `/etc/systemd/system/kopi-docka.service` - Main service
- `/etc/systemd/system/kopi-docka.timer` - Timer for scheduled backups
- `/etc/systemd/system/kopi-docka-backup.service` - One-shot backup service

## Enable Automatic Backups

```bash
# Enable timer (daily at 02:00 by default)
sudo systemctl enable --now kopi-docka.timer

# Check status
sudo systemctl status kopi-docka.timer
sudo systemctl list-timers | grep kopi-docka
```

## View Logs

```bash
# Live logs
sudo journalctl -u kopi-docka.service -f

# All logs
sudo journalctl -u kopi-docka.service

# Errors only
sudo journalctl -u kopi-docka.service -p err

# Last hour
sudo journalctl -u kopi-docka.service --since "1 hour ago"
```

## Customize Timer

Edit the timer schedule:

```bash
sudo systemctl edit kopi-docka.timer
```

Add your custom schedule:

```ini
[Timer]
# Examples:
OnCalendar=*-*-* 02:00:00        # Daily 2 AM (default)
OnCalendar=Mon *-*-* 03:00:00    # Mondays 3 AM
OnCalendar=*-*-* 00/6:00:00      # Every 6 hours
OnCalendar=Sun 04:00:00          # Sundays 4 AM
```

Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kopi-docka.timer
```

## Manual Backup

Trigger a one-time backup:

```bash
sudo systemctl start kopi-docka-backup.service
```

## Stop/Disable

```bash
# Stop timer
sudo systemctl stop kopi-docka.timer

# Disable automatic backups
sudo systemctl disable kopi-docka.timer

# Remove unit files
sudo rm /etc/systemd/system/kopi-docka.*
sudo systemctl daemon-reload
```

## Features

The generated unit files include:

- **sd_notify Support** - Status communication with systemd
- **Watchdog** - Automatic restart on failure (300s)
- **Security Hardening** - Process isolation, minimal privileges
- **PID Locking** - Prevents parallel backup runs
- **Structured Logging** - All logs in systemd journal
- **Automatic Restart** - On failure with 30s delay

See the full documentation: [docs/FEATURES.md](../../docs/FEATURES.md#4-systemd-integration)
