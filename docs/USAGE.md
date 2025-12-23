[← Back to README](../README.md)

# Usage

## CLI Structure (v3.4+)

Kopi-Docka features a simplified CLI with **"The Big 6"** top-level commands and an `admin` subcommand for advanced operations.

```
kopi-docka
├── setup              # Complete setup wizard
├── backup             # Run backup
├── restore            # Interactive restore wizard
├── disaster-recovery  # Create DR bundle
├── dry-run            # Simulate backup (preview)
├── doctor             # System health check
├── version            # Show version
└── admin              # Advanced administration
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
    │   ├── install-deps
    │   └── show-deps
    └── snapshot       # Snapshots & units
        ├── list
        └── estimate-size
```

---

## CLI Commands Reference

### Top-Level Commands ("The Big 6")

| Command | Description |
|---------|-------------|
| `setup` | **Master setup wizard** - Complete initial setup (Deps + Config + Init) |
| `backup` | **Full backup** - All units with selected scope |
| `restore` | **Interactive restore wizard** |
| `disaster-recovery` | Create encrypted DR bundle |
| `dry-run` | Simulate backup (no changes, preview) |
| `doctor` | **System health check** - Dependencies, config, backend, repository |
| `version` | Show Kopi-Docka version |

### Admin Config Commands

| Command | Description |
|---------|-------------|
| `admin config show` | Show config (secrets masked) |
| `admin config new` | **Config wizard** - Interactive backend & config creation |
| `admin config edit` | Open config in editor ($EDITOR or nano) |
| `admin config reset` | ⚠️ Reset config (new password!) |

### Admin Repo Commands

| Command | Description |
|---------|-------------|
| `admin repo init` | Initialize/connect repository |
| `admin repo status` | Show repository status |
| `admin repo maintenance` | Run repository maintenance (cleanup/optimize) |
| `admin repo change-password` | Safely change repository password |
| `admin repo which-config` | Show active Kopia config file |
| `admin repo set-default` | Set as default Kopia config |
| `admin repo selftest` | Create ephemeral test repository |
| `admin repo init-path PATH` | Create repository at specific path |

### Admin Service Commands

| Command | Description |
|---------|-------------|
| `admin service daemon` | Run as systemd daemon |
| `admin service write-units` | Generate systemd unit files |

### Admin System Commands

| Command | Description |
|---------|-------------|
| `admin system install-deps` | Auto-install missing dependencies |
| `admin system show-deps` | Show manual installation guide |

### Admin Snapshot Commands

| Command | Description |
|---------|-------------|
| `admin snapshot list` | Show backup units (containers/stacks) |
| `admin snapshot list --snapshots` | Show all snapshots in repo |
| `admin snapshot estimate-size` | Calculate backup size |

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

## Migration from v3.3 to v3.4

Most old commands still work but are now under `admin`:

| Old Command (v3.3) | New Command (v3.4) |
|--------------------|-------------------|
| `new-config` | `admin config new` |
| `show-config` | `admin config show` |
| `edit-config` | `admin config edit` |
| `reset-config` | `admin config reset` |
| `change-password` | `admin repo change-password` |
| `init` | `admin repo init` |
| `repo-status` | `admin repo status` |
| `repo-maintenance` | `admin repo maintenance` |
| `check` | `doctor` |
| `status` | `doctor` (combined) |
| `install-deps` | `admin system install-deps` |
| `show-deps` | `admin system show-deps` |
| `list` | `admin snapshot list` |
| `estimate-size` | `admin snapshot estimate-size` |
| `daemon` | `admin service daemon` |
| `write-units` | `admin service write-units` |

**Top-level commands unchanged:**
- `setup`
- `backup`
- `restore`
- `disaster-recovery`
- `dry-run`
- `version`

---

[← Back to README](../README.md)
