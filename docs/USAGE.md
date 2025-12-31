[← Back to README](../README.md)

# Usage

## CLI Structure (v6.0.0+)

Kopi-Docka features a simplified CLI with primary commands and an `advanced` subcommand for power users.

```
kopi-docka
├── setup              # Complete setup wizard
├── backup             # Run backup
├── restore            # Interactive restore wizard
├── disaster-recovery  # Create DR bundle
├── dry-run            # Simulate backup (preview)
├── doctor             # System health check
├── version            # Show version
└── advanced           # Advanced tools (Config, Repo, System)
    ├── config         # Configuration management
    │   ├── show
    │   ├── new
    │   ├── edit
    │   └── reset
    ├── repo           # Repository management
    │   ├── init
    │   ├── status
    │   ├── maintenance
    │   ├── change-password
    │   └── ...
    ├── service        # Systemd service
    │   ├── daemon
    │   └── write-units
    ├── system         # Dependencies
    │   └── show-deps
    └── snapshot       # Snapshots & units
        ├── list
        └── estimate-size
```

**Note:** For backward compatibility, `admin` is still supported as a hidden alias for `advanced`.

---

## CLI Commands Reference

### Primary Commands

| Command | Description |
|---------|-------------|
| `setup` | **Master setup wizard** - Complete initial setup (Deps + Config + Init) |
| `backup` | **Full backup** - All units with selected scope |
| `restore` | **Interactive restore wizard** |
| `show-docker-config <snapshot-id>` | **Extract docker_config** - Manual restore helper for FULL scope backups |
| `disaster-recovery` | Create encrypted DR bundle |
| `dry-run` | Simulate backup (no changes, preview) |
| `doctor` | **System health check** - Dependencies, config, backend, repository |
| `version` | Show Kopi-Docka version |

### Advanced Config Commands

| Command | Description |
|---------|-------------|
| `advanced config show` | Show config (secrets masked) |
| `advanced config new` | **Config wizard** - Interactive backend & config creation |
| `advanced config edit` | Open config in editor ($EDITOR or nano) |
| `advanced config reset` | ⚠️ Reset config (new password!) |

### Advanced Repo Commands

| Command | Description |
|---------|-------------|
| `advanced repo init` | Initialize or connect to repository |
| `advanced repo status` | Show repository status |
| `advanced repo maintenance` | Run repository maintenance (cleanup/optimize) |
| `advanced repo change-password` | Safely change repository password |
| `advanced repo which-config` | Show active Kopia config file |
| `advanced repo set-default` | Set as default Kopia config |
| `advanced repo selftest` | Create ephemeral test repository |
| `advanced repo init-path PATH` | Create repository at specific path |

### Advanced Service Commands

| Command | Description |
|---------|-------------|
| `advanced service daemon` | Run as systemd daemon |
| `advanced service write-units` | Generate systemd unit files |

### Advanced System Commands

| Command | Description |
|---------|-------------|
| `advanced system show-deps` | Show manual installation guide for dependencies |

### Advanced Snapshot Commands

| Command | Description |
|---------|-------------|
| `advanced snapshot list` | Show backup units (containers/stacks) |
| `advanced snapshot list --snapshots` | Show all snapshots in repo |
| `advanced snapshot estimate-size` | Calculate backup size |

### Legacy/Hidden Commands

For backward compatibility, these commands still work but are hidden from `--help`:

- **Wrapper commands** (use `advanced` subcommands instead):
  - `check` → Use `doctor` instead
  - `show-deps` → Use `advanced system show-deps`
  - `init` → Use `advanced repo init`
  - `repo-*` → Use `advanced repo` subcommands
  - `change-password` → Use `advanced repo change-password`
  - `daemon` → Use `advanced service daemon`
- **Legacy alias**: `admin` → Use `advanced` instead

**Note:** The `install-deps` command was removed in v5.5.0. Dependencies must be installed manually or using [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten).

### Backup Options

| Option | Description |
|--------|-------------|
| `--scope minimal` | Volumes only (fast) |
| `--scope standard` | Volumes + recipes + networks (default) |
| `--scope full` | Complete system backup |
| `--unit NAME` | Backup specific unit(s) only |
| `--update-recovery` | Update DR bundle after backup |
| `--dry-run` | Simulate only (no changes) |

### Restore Options

| Option | Description |
|--------|-------------|
| `--yes` / `-y` | Non-interactive mode - skips all prompts, uses automatic defaults |
| `--force-recreate-networks` | Always recreate existing networks (stops/restarts attached containers) |
| `--no-recreate-networks` | Never recreate existing networks during restore |

**Non-interactive restore (`--yes`) behavior:**
- Selects newest backup session automatically
- Restores first available unit
- Skips confirmation prompts
- Recreates networks automatically on conflict (unless `--no-recreate-networks` is set)
- Restores all volumes without prompting
- Uses default directory for configs, auto-backup on conflict

**Example: CI/CD restore test**
```bash
sudo kopi-docka restore --yes
```

**💡 Most commands require `sudo` (except: `version`, `doctor`)**

---

## Usage Examples

### Basic Operations

```bash
# System health check
sudo kopi-docka doctor

# What will be backed up?
sudo kopi-docka admin snapshot list

# Test run (no changes)
sudo kopi-docka dry-run

# Back up everything
sudo kopi-docka backup

# Backup specific units only
sudo kopi-docka backup --unit webapp --unit database

# Repository status
sudo kopi-docka admin repo status

# Show all snapshots
sudo kopi-docka admin snapshot list --snapshots
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

```bash
# Generate systemd units
sudo kopi-docka admin service write-units

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
6. **Apply retention** policies (latest/hourly/daily/weekly/monthly/annual)
7. Optional: **Create DR bundle** and rotate

### 3. Restore (On ANY Server!)
1. Get DR bundle from safe storage
2. Deploy new server (any Linux distro)
3. Install Kopi-Docka
4. Decrypt bundle & run `./recover.sh` → auto-reconnects
5. `kopi-docka restore` → interactive wizard restores everything
6. `docker compose up -d` → services online!

### 4. Retention Policies (Direct Mode vs TAR Mode)

**Since v5.0,** Kopi-Docka uses **Direct Mode** by default for volume backups (faster, more efficient). This affects how retention policies are applied.

**Direct Mode (Default since v5.0):**
- Volume snapshots are created from actual Docker mountpoints
- Example path: `/var/lib/docker/volumes/myproject_data/_data`
- Retention policies are applied to these **actual mountpoints**
- Recipe and network snapshots use stable staging paths: `/var/cache/kopi-docka/staging/recipes/<unit-name>/`

**TAR Mode (Legacy):**
- Volume snapshots are created via tar streams
- Uses virtual paths like `volumes/myproject`
- Retention policies are applied to these **virtual paths**

**Why this matters:**
- ✅ Retention policies (e.g., `latest: 3`) work correctly in both modes
- ✅ Old volume backups are automatically deleted per your retention settings
- ✅ Recipe and network metadata retention works correctly (fixed in v5.3.0)
- ⚠️ Mixed repositories (old TAR + new Direct backups) maintain both snapshot types

**No action required** - retention policies are automatically applied to the correct paths based on your backup format setting. This was a critical bug fix in v5.3.0.

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

## Exit Safety & Signal Handling

**Kopi-Docka features a robust two-layer exit safety system** that ensures graceful cleanup when operations are interrupted (Ctrl+C, `systemctl stop`, etc.).

### What Happens on Interrupt?

When you press **Ctrl+C** or send **SIGTERM** during a backup/restore/DR operation:

1. **Process Layer**: All running subprocesses (docker, kopia, openssl, hooks) are automatically terminated
   - First: SIGTERM sent to all tracked processes (graceful shutdown)
   - After 5s: SIGKILL sent to any surviving processes (force kill)
   - Prevents zombie processes and resource leaks

2. **Strategy Layer**: Context-aware cleanup based on operation type
   - **During Backup**: Containers are automatically restarted (LIFO order) → **no downtime**
   - **During Restore**: Containers remain stopped for data safety, temp files cleaned
   - **During DR Bundle**: Temp directories and incomplete archives removed

### Signal Behavior by Operation

| Operation | Ctrl+C / SIGTERM Behavior | Result |
|-----------|---------------------------|--------|
| **Backup** | Containers auto-restart in reverse order | ✅ Services back online |
| **Restore** | Containers stay stopped, temp cleanup | ⚠️ Manual restart required |
| **Disaster Recovery** | Temp `/tmp/kopi-docka-recovery-*` deleted | ✅ Clean state |
| **Repository Ops** | Kopia processes terminated | ✅ No orphaned locks |
| **Hooks** | Hook processes killed after timeout | ✅ No hung scripts |

### Example: Backup Interrupted

```bash
sudo kopi-docka backup
# ... backup running ...
# Press Ctrl+C

# Output:
Received SIGINT - starting emergency cleanup...
EMERGENCY: Terminating 3 tracked process(es)...
  SIGTERM -> docker stop webapp (PID 12345)
  SIGTERM -> kopia snapshot create (PID 12346)
ServiceContinuity: Restarting 2 container(s)...
  Starting webapp...
  [OK] webapp started
Cleanup complete, exiting with code 130

# Check status:
docker ps
# All containers are UP! No manual intervention needed.
```

### Example: Restore Interrupted

```bash
sudo kopi-docka restore
# ... restore running ...
# Press Ctrl+C

# Output:
Received SIGINT - starting emergency cleanup...
DataSafety: Containers remain STOPPED for safety:
  - webapp
  - database
Manually restart: docker start <container_name>
Cleanup complete, exiting with code 130

# Containers intentionally stay stopped to prevent data corruption
# You must manually verify and restart:
docker start webapp database
```

### Signal Types

| Signal | Source | Behavior | Exit Code |
|--------|--------|----------|-----------|
| **SIGINT** | Ctrl+C, `kill -2` | Graceful cleanup → exit | 130 |
| **SIGTERM** | `systemctl stop`, `kill -15` | Graceful cleanup → exit | 143 |
| **SIGKILL** | `kill -9` (force) | ⚠️ NOT catchable - no cleanup! | 137 |

**⚠️ IMPORTANT**: Always use **SIGTERM** (`systemctl stop`, `kill -15`) instead of SIGKILL (`kill -9`). SIGKILL cannot be caught and will leave containers stopped and processes orphaned.

### systemd Integration

When running as a systemd service, Kopi-Docka communicates its cleanup status:

```bash
# systemd knows cleanup is in progress
sudo systemctl stop kopi-docka.service
# ServiceContinuity handler restarts containers automatically
# systemd receives "STOPPING=1" notification
# Watchdog timer is reset during cleanup
```

**Features:**
- ✅ `sd_notify(STOPPING=1)` sent at cleanup start
- ✅ Watchdog timer reset before handler execution
- ✅ Works without systemd (graceful fallback)

### Troubleshooting

**Problem**: Container failed to restart after Ctrl+C during backup
```bash
# Check logs
sudo journalctl -u kopi-docka.service | grep "ServiceContinuity"
# Look for: "[FAILED] container_name: <error>"

# Manual restart
docker start <container_name>
```

**Problem**: Zombie processes after abort
```bash
# Should NOT happen - but if it does:
ps aux | grep kopia | grep defunct
# Report issue: https://github.com/TZERO78/kopi-docka/issues
```

**Problem**: Temp directories not cleaned
```bash
# Should NOT happen with SafeExitManager - but if it does:
ls -la /tmp/kopi-docka-*
sudo rm -rf /tmp/kopi-docka-*
```

### Best Practices

1. **Use SIGTERM, not SIGKILL**
   ```bash
   # Good
   sudo systemctl stop kopi-docka.service
   kill -15 <pid>

   # Bad - no cleanup!
   kill -9 <pid>
   ```

2. **Check logs after interrupt**
   ```bash
   sudo journalctl -u kopi-docka.service -n 50
   ```

3. **Verify containers after backup abort**
   ```bash
   docker ps  # Should show all containers UP
   ```

4. **After restore abort, manually verify before restart**
   ```bash
   # Restore was interrupted - check data integrity first
   docker volume inspect <volume_name>
   # Then manually restart
   docker start <container_name>
   ```

---

[← Back to README](../README.md)
