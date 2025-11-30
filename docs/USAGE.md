[← Back to README](../README.md)

# Usage

## CLI Commands Reference

### Setup & Configuration

| Command | Description |
|---------|-------------|
| `setup` | **Master setup wizard** - Complete initial setup (Deps + Config + Init) |
| `new-config` | **Config wizard** - Interactive backend selection & config creation |
| `show-config` | Show config (secrets masked) |
| `edit-config` | Open config in editor ($EDITOR or nano) |
| `reset-config` | ⚠️ Reset config (new password!) |
| `change-password` | Safely change repository password |
| `status` | **Show backend status** (disk space, connectivity, ping) |

### System & Dependencies
| Command | Description |
|---------|-------------|
| `check` | Verify all dependencies |
| `check --verbose` | Show detailed system info |
| `install-deps` | Auto-install missing dependencies |
| `show-deps` | Show manual installation guide |
| `version` | Show Kopi-Docka version |

### Repository
| Command | Description |
|---------|-------------|
| `init` | Initialize/connect repository |
| `repo-status` | Show repository status |
| `repo-which-config` | Show active Kopia config file |
| `repo-maintenance` | Run repository maintenance (cleanup/optimize) |

### Backup & Restore
| Command | Description |
|---------|-------------|
| `list --units` | Show backup units (containers/stacks) |
| `list --snapshots` | Show all snapshots in repo |
| `dry-run` | Simulate backup (no changes) |
| `dry-run --unit NAME` | Simulate specific unit |
| `estimate-size` | Calculate backup size |
| `backup` | **Full backup** (all units, default scope: standard) |
| `backup --scope minimal` | Backup volumes only (fast) |
| `backup --scope standard` | Backup volumes + recipes + networks (default) |
| `backup --scope full` | Complete system backup (everything) |
| `backup --unit NAME` | Backup specific unit(s) only |
| `backup --update-recovery` | Update DR bundle after backup |
| `restore` | **Interactive restore wizard** |
| `disaster-recovery` | Create DR bundle manually |

### Service & Automation
| Command | Description |
|---------|-------------|
| `daemon` | Run as systemd daemon |
| `write-units` | Generate systemd unit files |

**💡 All commands require `sudo` (except: `version`, `show-deps`, `show-config`)**

---

## Usage

### Basic Operations

```bash
# What will be backed up?
sudo kopi-docka list --units

# Test run (no changes)
sudo kopi-docka dry-run

# Back up everything
sudo kopi-docka backup

# Backup specific units only
sudo kopi-docka backup --unit webapp --unit database

# Repository status
sudo kopi-docka repo-status

# Backend status (disk space, connectivity)
sudo kopi-docka status

# Show all snapshots
sudo kopi-docka list --snapshots
```

### Disaster Recovery

**Create bundle (manual):**
```bash
sudo kopi-docka disaster-recovery
# Copy bundle to safe location: USB/phone/cloud!
```

**Automatic DR bundle with every backup:**
```json
{
  "backup": {
    "update_recovery_bundle": true,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3
  }
}
```

```bash
sudo kopi-docka backup
# Bundle is automatically created/updated
```

**In emergency (on NEW server):**
```bash
# 1. Install Kopi-Docka
pipx install kopi-docka

# 2. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in bundle.tar.gz.enc \
  -out bundle.tar.gz

# 3. Extract
tar -xzf bundle.tar.gz
cd kopi-docka-recovery-*/

# 4. Auto-reconnect to repository
sudo ./recover.sh

# 5. Restore services
sudo kopi-docka restore

# 6. Start containers
cd /tmp/kopia-restore-*/recipes/
docker compose up -d
```

### Automatic Backups (systemd)

**For detailed info see README.md - Systemd Integration section**

```bash
# Generate systemd units
sudo kopi-docka write-units

# Enable timer (daily 02:00)
sudo systemctl enable --now kopi-docka.timer

# Check status
sudo systemctl status kopi-docka.timer
sudo systemctl list-timers | grep kopi-docka

# Show logs
sudo journalctl -u kopi-docka.service -f
```

**Features:**
- ✅ sd_notify - Status communication with systemd
- ✅ Watchdog - Automatic restart on failure
- ✅ PID lock - Prevents parallel backups
- ✅ Security hardening - Process isolation
- ✅ Structured logs - systemd journal
- ✅ Flexible scheduling - OnCalendar, Persistent, RandomDelay

---

## How It Works

### 1. Discovery
- Detects running containers and volumes
- Groups into **backup units** (Compose stacks preferred, otherwise standalone)
- Captures `docker-compose.yml` (if present) and `docker inspect`
- Redacts secrets from ENV vars (`PASS`, `SECRET`, `KEY`, `TOKEN`, `API`, `AUTH`)

### 2. Backup Pipeline (Cold)
1. Generate **backup_id** (e.g., `2025-01-31T23-59-59Z`)
2. **Stop** containers (`docker stop -t <stop_timeout>`)
3. **Snapshot recipes** → Kopia with tags: `{type: recipe, unit, backup_id, timestamp}`
4. **Snapshot volumes** (parallel, up to `parallel_workers`) via tar stream → Kopia `--stdin`
   Tags: `{type: volume, unit, volume, backup_id, timestamp, size_bytes}`
5. **Start** containers (waits for healthcheck if present)
6. **Apply retention** policies (daily/weekly/monthly/yearly)
7. Optional: **Create DR bundle** and rotate

### 3. Restore (On ANY Server!)
1. Get DR bundle from safe storage
2. Deploy new server (any Linux distro)
3. Install Kopi-Docka
4. Decrypt bundle & run `./recover.sh` → auto-reconnects
5. `kopi-docka restore` → interactive wizard restores everything
6. `docker compose up -d` → services online!

---

## Kopia Integration

**Kopi-Docka uses a separate Kopia profile** → No conflicts with existing Kopia backups!

```bash
# Your personal Kopia backups (unchanged)
~/.config/kopia/repository.config           # Default profile
kopia snapshot create /home/user/documents  # Works as always

# Kopi-Docka's separate profile
~/.config/kopia/repository-kopi-docka.config
sudo kopi-docka backup                      # Separate config

# Both run independently - zero conflicts!
```

**Benefits:**
- ✅ Existing Kopia backups remain unchanged
- ✅ Different repositories, schedules, retention policies
- ✅ Both can run simultaneously
- ✅ Kopia remains unmodified - we're just a wrapper

---

[← Back to README](../README.md)
