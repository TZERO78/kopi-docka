# Features

[← Back to README](../README.md)

## Unique Features

Kopi-Docka combines four unique features that no other Docker backup tool offers:

### 1. Compose-Stack-Awareness

**Recognition and backup of Docker Compose stacks as logical units**

#### What is Stack-Awareness?

Traditional Docker backup tools back up containers individually, without context. Kopi-Docka automatically recognizes Compose stacks and treats them as logical units.

**Traditional Backup (Container-based):**
```
- wordpress_web_1 → Backup
- wordpress_db_1 → Backup
- wordpress_redis_1 → Backup

Problem: Context is lost
- Which containers belong together?
- Version compatibility?
- What was the docker-compose.yml?
```

**Kopi-Docka (Stack-based):**
```
Stack: wordpress
├── Containers: web, db, redis
├── Volumes: wordpress_data, mysql_data
├── docker-compose.yml backed up
└── Common backup_id (atomic unit)

Result: Complete stack restorable
```

#### How Recognition Works

Kopi-Docka uses Docker labels for stack recognition:

```yaml
# docker-compose.yml
services:
  web:
    image: wordpress
    labels:
      com.docker.compose.project: wordpress
      com.docker.compose.service: web
```

**Discovery Process:**
1. Scans all running containers
2. Groups by `com.docker.compose.project`
3. Finds docker-compose.yml via `com.docker.compose.project.working_dir` label
4. Recognizes all associated volumes

#### What Gets Backed Up

**Per Stack:**

1. **Recipe (Configuration)**
   - docker-compose.yml (if present)
   - `docker inspect` output for each container
   - ENV variables (secrets redacted: `PASS`, `SECRET`, `KEY`, `TOKEN`, `API`, `AUTH`)
   - Labels and metadata
   - Network configuration

2. **Volumes (Data)**
   - All volumes of the stack
   - With owners and permissions
   - Extended attributes (xattrs)
   - ACLs if present

3. **Tags (Kopia)**
   ```json
   {
     "type": "recipe",  // or "volume"
     "unit": "wordpress",
     "backup_id": "2025-01-31T23-59-59Z",
     "timestamp": "2025-01-31T23:59:59Z",
     "volume": "wordpress_data"  // volumes only
   }
   ```

#### Backup Flow (Stack)

```bash
sudo kopi-docka backup --unit wordpress

# 1. Generate backup_id
backup_id = "2025-01-31T23-59-59Z"

# 2. Stop ALL containers in stack
docker stop wordpress_web_1
docker stop wordpress_db_1
docker stop wordpress_redis_1

# 3. Backup recipe
kopia snapshot create \
  --tags unit=wordpress \
  --tags type=recipe \
  --tags backup_id=2025-01-31T23-59-59Z

# 4. Backup volumes in parallel
for each volume:
  tar cvf - /var/lib/docker/volumes/wordpress_data \
    | kopia snapshot create --stdin \
      --tags unit=wordpress \
      --tags type=volume \
      --tags volume=wordpress_data \
      --tags backup_id=2025-01-31T23-59-59Z

# 5. Start containers
docker start wordpress_web_1
docker start wordpress_db_1
docker start wordpress_redis_1

# 6. Wait for healthcheck (if defined)
```

#### Restore Flow (Stack)

```bash
sudo kopi-docka restore

# Wizard shows stacks:
Available Restore Points:
  - wordpress (2025-01-31T23:59:59Z)
  - nextcloud (2025-01-30T23:59:59Z)
  - gitlab (2025-01-29T23:59:59Z)

# Select: wordpress

# Wizard restores:
# 1. docker-compose.yml → /tmp/kopia-restore-abc/recipes/wordpress/
# 2. All volumes → /tmp/kopia-restore-abc/volumes/wordpress/
# 3. Generate volume restore scripts

# You start:
cd /tmp/kopia-restore-abc/recipes/wordpress/
docker compose up -d
```

#### Benefits

**Atomic Backups:**
- All containers in a stack have the same `backup_id`
- Consistent state guaranteed
- No version inconsistencies between services

**Easy Restoration:**
- One command for complete stack
- docker-compose.yml included
- All volumes together

**Clarity:**
```bash
kopi-docka admin snapshot list

Backup Units:
  - wordpress (Stack, 3 containers, 2 volumes)
  - nextcloud (Stack, 5 containers, 3 volumes)
  - gitlab (Stack, 4 containers, 4 volumes)
  - redis (Standalone, 1 volume)
```

#### Fallback: Standalone Containers

Containers without Compose labels are treated as standalone units:

```
Standalone: redis
├── Container: redis
├── Volumes: redis_data
└── docker inspect backed up
```

---

### 2. Disaster Recovery Bundles

**Encrypted emergency packages for fast recovery**

#### What is a DR Bundle?

A Disaster Recovery Bundle is an encrypted, self-contained package containing everything needed to connect to your backup repository on a completely new server:

- Repository connection data (backend config, endpoint, etc.)
- Kopia password (encrypted)
- SSH keys (for SFTP/Tailscale)
- Network configuration (for Tailscale)
- Auto-reconnect script (`recover.sh`)

#### Why Are DR Bundles Important?

**Without DR Bundle (Traditional):**
```
Server dies → Data gone
You need:
  - Repository URL (where to find?)
  - Password (which one was it?)
  - Backend config (cloud keys? SFTP host?)
  - Kopia configuration (which encryption?)

Time to recovery: Hours to days
```

**With DR Bundle:**
```
Server dies → Get bundle
  1. Set up new server
  2. Decrypt bundle
  3. Run ./recover.sh
  4. kopi-docka restore

Time to recovery: 15-30 minutes
```

#### How It Works

**Create Bundle**

```bash
# Manual
sudo kopi-docka disaster-recovery
# Creates: /backup/recovery/kopi-docka-recovery-2025-01-31T23-59-59Z.tar.gz.enc

# Automatically with every backup
# In config.json:
{
  "backup": {
    "update_recovery_bundle": true,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3
  }
}
```

**Bundle Contents (encrypted)**

```
kopi-docka-recovery-*/
├── kopi-docka.json          # Complete config
├── repository.config        # Kopia repository config
├── credentials/             # Backend-specific credentials
│   ├── ssh-keys/           # SSH keys (SFTP/Tailscale)
│   └── env-vars.txt        # Cloud credentials (S3/B2/Azure)
├── recover.sh              # Auto-reconnect script
└── README.txt              # Decryption instructions
```

**Use Bundle in Emergency**

**Scenario:** Your production server completely failed, new hardware needed.

**Step 1: Set up new server**
```bash
# Any Linux distribution
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Kopi-Docka from PyPI
pipx install kopi-docka
```

**Step 2: Get and decrypt bundle**
```bash
# Get bundle from USB/cloud/safe
# Decrypt with DR password
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in kopi-docka-recovery-*.tar.gz.enc \
  -out bundle.tar.gz

# Extract
tar -xzf bundle.tar.gz
cd kopi-docka-recovery-*/
```

**Step 3: Auto-reconnect**
```bash
# Script automatically connects to repository
sudo ./recover.sh

# Script does:
#   - Restores Kopia config
#   - Copies SSH keys (if SFTP/Tailscale)
#   - Sets environment variables (if cloud)
#   - Connects to repository
#   - Verifies access
```

**Step 4: Restore services**
```bash
# Interactive restore wizard
sudo kopi-docka restore

# Select:
#   - Which stack/container
#   - Which backup point in time
#   - Where to restore

# Wizard restores:
#   - docker-compose.yml
#   - All volumes
#   - Configs and secrets
```

**Step 5: Start services**
```bash
cd /tmp/kopia-restore-*/recipes/nextcloud/
docker compose up -d

# Done! Services are running again.
```

#### Best Practices

**Storage Locations for DR Bundles:**
- USB stick (offline, physical)
- Second cloud account (different from backup backend)
- Encrypted cloud storage (Tresorit, Cryptomator)
- With family/friends (USB/paper backup)
- Company safe (physical)

**Important:**
- ❌ Don't store only on backup server
- ❌ Don't store in same cloud account as backups
- ✅ At least 2 copies in different locations
- ✅ DR password separate (not in bundle!)
- ✅ Test regularly (every 6 months)

#### Technical Details

- **Encryption:** AES-256-CBC with PBKDF2
- **Password:** Randomly generated (48 characters, alphanumeric)
- **Format:** .tar.gz.enc (compressed + encrypted)
- **Size:** ~10-50 KB (without logs)
- **Retention:** Automatic rotation (configurable)

---

### 3. Tailscale Integration

**Automatic peer discovery for P2P backups over private network**

Kopi-Docka integrates Tailscale discovery directly into the setup process and automates complete SSH configuration.

#### How It Works

```bash
sudo kopi-docka admin config new
# → Select backend: Tailscale
# → Automatic peer discovery
# → Displays disk space, latency, online status
# → Automatic SSH key setup (passwordless)
```

The wizard shows all available devices in your Tailnet:

```
Available Backup Targets
┌──────────┬─────────────────┬────────────────┐
│ Status   │ Hostname        │ IP             │
├──────────┼─────────────────┼────────────────┤
│ 🟢 Online│ cloud-vps      │ 100.64.0.5      │
│ 🟢 Online│ home-nas       │ 100.64.0.12     │
│ 🔴 Offline│ raspberry-pi   │ 100.64.0.8     │
└──────────┴─────────────────┴────────────────┘
```

#### Comparison: Traditional vs. Tailscale

**Traditional Offsite Backups:**
- Cloud storage (S3/B2/Azure) - ongoing costs
- Upload limits and provider-dependent speed
- Firewall/VPN configuration needed
- Port forwarding or public IPs required

**With Kopi-Docka + Tailscale:**
- Use your own hardware - no ongoing costs
- Direct P2P connection via WireGuard
- End-to-end encrypted (Tailscale + Kopia)
- No firewall configuration needed
- Automatic peer discovery and SSH setup

#### Typical Scenarios

**Homelab → Cloud VPS**
```
Home Server (Homelab)         Cloud VPS (Hetzner/DigitalOcean)
┌─────────────────────┐       ┌─────────────────────┐
│ Docker Services     │ Tail  │ Kopia Repository    │
│ (Nextcloud, etc.)   │ scale │ (backups only)      │
└─────────────────────┘       └─────────────────────┘
```
**Cost:** ~$5/month VPS vs. typically $50+/month cloud storage

**VPS → Homelab**
```
Production VPS                Home NAS/Server
┌─────────────────────┐       ┌─────────────────────┐
│ Live Services       │ Tail  │ 4TB Storage         │
│ (Websites, APIs)    │ scale │ Kopia Repo          │
└─────────────────────┘       └─────────────────────┘
```
Physical access to backup data possible

**3-2-1 Backup Strategy**
```
Production Server      Backup VPS            Homelab
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Live Data    │──1──>│ Offsite Copy │──2──>│ Local Copy   │
└──────────────┘      └──────────────┘      └──────────────┘

3 copies / 2 different locations / 1 offsite
```

#### Setup

```bash
# 1. Install Tailscale (if not already installed)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. Configure Kopi-Docka with Tailscale
sudo kopi-docka setup
# Backend: Tailscale
# Select peer (e.g., your VPS)
# SSH key is automatically set up

# 3. First backup
sudo kopi-docka backup
```

#### Technical Details

- **Protocol:** SFTP over Tailscale (Kopia SFTP backend)
- **Encryption:** Double - Tailscale (WireGuard) + Kopia (AES-256-GCM)
- **Authentication:** ED25519 SSH key (automatically generated)
- **Network:** Direct P2P via WireGuard, no relay
- **Discovery:** Automatic via `tailscale status --json`
- **Performance:** Peer selection based on latency

#### Requirements

- Tailscale installed on both servers
- Both in the same Tailnet
- SSH access to backup server (one-time for key setup)

Tailscale is free for up to 100 devices: [tailscale.com](https://tailscale.com)

---

### 4. Systemd Integration

**Production-ready daemon with sd_notify, Watchdog, and Security Hardening**

Kopi-Docka is designed from the ground up for production use as a systemd service.

#### How It Works

**Systemd Daemon Mode:**
```bash
sudo kopi-docka admin service daemon
```

The daemon uses systemd-specific features:
- **sd_notify:** Reports status to systemd (READY, STOPPING, WATCHDOG)
- **Watchdog:** Heartbeat monitoring (systemd restarts on failure)
- **Locking:** PID lock prevents parallel instances
- **Signal Handling:** Clean shutdown on SIGTERM/SIGINT

#### Automatic Backups with systemd Timer

**Generate unit files:**
```bash
# Creates service + timer in /etc/systemd/system/
sudo kopi-docka admin service write-units

# Generates:
# - kopi-docka.service (daemon)
# - kopi-docka.timer (scheduling)
# - kopi-docka-backup.service (one-shot)
```

**Enable timer:**
```bash
# Enable and start timer
sudo systemctl enable --now kopi-docka.timer

# Check status
sudo systemctl status kopi-docka.timer
sudo systemctl list-timers | grep kopi-docka

# Next run
systemctl list-timers kopi-docka.timer
```

#### Timer Configuration

**Default (daily at 02:00):**
```ini
[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=15m
```

**Custom Schedules:**
```bash
# Edit /etc/systemd/system/kopi-docka.timer
sudo systemctl edit kopi-docka.timer

# Examples:
OnCalendar=*-*-* 02:00:00        # Daily 2 AM
OnCalendar=Mon *-*-* 03:00:00    # Mondays 3 AM
OnCalendar=*-*-* 00/6:00:00      # Every 6 hours
OnCalendar=Sun 04:00:00          # Sundays 4 AM

# Reload after changes
sudo systemctl daemon-reload
```

#### Service Features

**1. sd_notify - Status Communication**
```
Daemon starts  → READY=1
Backup running → STATUS=Running backup
Backup done    → STATUS=Last backup: 2025-01-31 23:59:59
Shutdown       → STOPPING=1
```

Systemd always knows what the service is doing.

**2. Watchdog - Monitoring**
```ini
[Service]
WatchdogSec=300
```

Daemon sends heartbeat every 150 seconds (half of WatchdogSec).
If heartbeat stops → systemd restarts service.

**3. Locking - Prevent Parallel Runs**
```
/run/kopi-docka/kopi-docka.lock
```

Prevents multiple backups from running simultaneously:
- Via systemd timer
- Via manual `kopi-docka backup`
- Via cron job (if someone uses both)

**4. Security Hardening**

Generated unit files contain extensive security settings:

```ini
[Service]
# Privilege minimization
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only

# Only necessary paths writable
ReadWritePaths=/backup /var/lib/docker /var/run/docker.sock /var/log

# Runtime directory (auto-cleanup)
RuntimeDirectory=kopi-docka
RuntimeDirectoryMode=0755

# Process isolation
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes

# Network restriction
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

# System call filtering
SystemCallFilter=@system-service
```

These settings:
- Minimize attack surface
- Isolate the process
- Follow security best practices
- Still allow full Docker access

#### Logging & Monitoring

**Structured logs in systemd journal:**
```bash
# All logs
sudo journalctl -u kopi-docka.service

# Live logs
sudo journalctl -u kopi-docka.service -f

# Errors only
sudo journalctl -u kopi-docka.service -p err

# Last hour
sudo journalctl -u kopi-docka.service --since "1 hour ago"

# Last backup run
sudo journalctl -u kopi-docka.service --since "last boot"

# With metadata
sudo journalctl -u kopi-docka.service -o json-pretty
```

**Searchable fields:**
```bash
# Filter by unit
sudo journalctl -u kopi-docka.service UNIT=wordpress

# Filter by operation
sudo journalctl -u kopi-docka.service OPERATION=backup

# Combined
sudo journalctl -u kopi-docka.service UNIT=nextcloud OPERATION=restore
```

#### Operation Modes

**Mode 1: Timer (Recommended for Production)**
```bash
# Daemon waits for timer events
sudo systemctl enable --now kopi-docka.timer

# Timer triggers kopi-docka backup
# Daemon stays idle
```

**Mode 2: Internal Interval (Simple, less flexible)**
```bash
# Daemon runs and backs up every N minutes
sudo kopi-docka admin service daemon --interval-minutes 1440  # Daily

# In systemd unit:
[Service]
ExecStart=/usr/bin/env kopi-docka admin service daemon --interval-minutes 1440
```

**Mode 3: One-Shot (For cron or manual triggers)**
```bash
# No daemon, one-time backup
sudo systemctl start kopi-docka-backup.service

# Or via cron
0 2 * * * /usr/bin/env kopi-docka backup
```

#### Comparison: systemd vs. Cron

| Feature | systemd Timer | Cron |
|---------|---------------|------|
| **Status Tracking** | ✅ Native (sd_notify) | ❌ None |
| **Watchdog** | ✅ Yes | ❌ No |
| **Logging** | ✅ systemd Journal | ⚠️ Syslog/File |
| **Restart on Error** | ✅ Automatic | ❌ Manual |
| **Locking** | ✅ PID lock | ⚠️ Build yourself |
| **Scheduling** | ✅ Flexible | ✅ Flexible |
| **Persistent** | ✅ Yes (catch up) | ❌ No |
| **RandomDelay** | ✅ Yes | ❌ No |
| **Security** | ✅ Hardening | ❌ Root context |
| **Dependencies** | ✅ After/Requires | ❌ None |

**Recommendation:** systemd Timer for production environments.

#### Interactive Service Management

**Easy service administration without systemctl knowledge**

Kopi-Docka v3.9.0 introduces an interactive service management wizard that makes systemd service administration accessible to users without systemctl expertise:

```bash
sudo kopi-docka admin service manage
```

The wizard provides a user-friendly menu for all service management tasks:

**Features:**
- **Status Dashboard:** View service/timer status, next backup time, last backup result
- **Timer Configuration:** Change backup schedule with presets or custom times
- **Log Viewer:** View logs with filters (last N lines, errors only, today, etc.)
- **Service Control:** Start/stop/restart services, enable/disable timer
- **Auto-Setup:** Automatically creates systemd units if missing

**Example Workflow:**
```bash
sudo kopi-docka admin service manage

# Menu shows:
# [1] Show Status
# [2] Configure Timer
# [3] View Logs
# [4] Control Service
# [0] Exit

# Select [2] to configure timer:
# [1] 02:00 (Default)
# [2] 03:00
# [3] 04:00
# [4] 23:00
# [5] Custom Time (HH:MM)
# [6] Advanced (OnCalendar)

# Changes are applied immediately
# Next run time is displayed
```

**Benefits:**
- No systemctl knowledge required
- Clear, intuitive menus
- Confirmation dialogs for destructive actions
- Immediate feedback on changes
- Root privilege checking
- Validates time formats before applying

#### Technical Details

- **Type:** `notify` (sd_notify support)
- **Restart:** `on-failure` with 30s delay
- **WatchdogSec:** 300s (5 minutes)
- **StandardOutput/Error:** `journal` (structured logs)
- **RuntimeDirectory:** `/run/kopi-docka` (auto-cleanup)
- **Security:** Minimal privileges, process isolation
- **Locking:** fcntl-based PID lock

---

## What's New in v3.9.1

### 🔒 Enhanced Lock File Management
**Improved diagnostics and stale lock detection**

Kopi-Docka v3.9.1 enhances lock file handling with better diagnostics and automatic detection of stale locks from dead processes.

**New Features:**

1. **Improved Lock Status Display**
   - Lock status now shown in informative Rich panels instead of simple text
   - Clear distinction between active locks (running process) and stale locks (dead process)
   - Helpful explanations and next steps for users

2. **Stale Lock Removal**
   - New `remove_stale_lock()` method in ServiceHelper
   - New menu option **[6] Remove Stale Lock File** in service wizard
   - Prevents removal of locks from running processes
   - Safe cleanup of locks from dead processes (crashes, reboots)

3. **Enhanced Logging**
   - DEBUG-level logging for lock operations:
     - "No lock file found"
     - "Lock file found with PID: X"
     - "Process X is running"
     - "Process X is not running (stale lock)"
   - Better error messages and warnings

4. **More Portable Process Checking**
   - Changed from `subprocess.run(["kill", "-0"])` to `os.kill(pid, 0)`
   - Handles `ProcessLookupError` and `PermissionError` properly
   - More efficient and portable

**Example Usage:**
```bash
sudo kopi-docka admin service manage
# → [1] Show Status (shows lock status if present)
# → [4] Control Service
#    → [6] Remove Stale Lock File (if needed)
```

**Technical Details:**
- Lock files are ONLY created by the daemon service (`kopi-docka admin service daemon`)
- The wizard's `get_lock_status()` method is read-only and never creates locks
- Comprehensive investigation documented in `INVESTIGATION_LOCK_FILE_CREATION.md`

---

## What's New in v3.9.0

### 🎛️ Interactive Service Management
**Easy systemd service administration without systemctl knowledge**

Kopi-Docka v3.9.0 introduces a comprehensive interactive service management wizard that makes systemd administration accessible to users without systemctl expertise.

**New Command:**
```bash
sudo kopi-docka admin service manage
```

**Features:**
- **Status Dashboard** - View service/timer status, next backup time, last backup result at a glance
- **Timer Configuration** - Change backup schedule with presets (02:00, 03:00, 04:00, 23:00) or custom time (HH:MM)
- **Advanced Scheduling** - Full OnCalendar syntax support for complex schedules (weekly, hourly, etc.)
- **Log Viewer** - View logs with filters: last N lines, last hour, errors only, today
- **Service Control** - Start/stop/restart service, enable/disable timer with confirmation dialogs
- **Auto-Setup** - Automatically creates systemd units if missing (with user confirmation)
- **Input Validation** - Validates time formats and OnCalendar syntax before applying changes
- **Root Checking** - Exits with code 13 if not running as root

**User Experience:**
- Rich-based UI with color-coded status indicators
- Clear, intuitive menus
- Immediate feedback on all changes
- Confirmation dialogs for destructive actions
- Syntax highlighting in log viewer
- No systemctl knowledge required

**Example Workflow:**
```bash
sudo kopi-docka admin service manage

# Menu:
# [1] Show Status        → Service/Timer status dashboard
# [2] Configure Timer    → Change backup schedule
# [3] View Logs          → View filtered logs
# [4] Control Service    → Control services
# [0] Exit               → Exit

# Select [2] to configure timer:
#   [1] 02:00 (Default)
#   [2] 03:00
#   [3] 04:00
#   [4] 23:00
#   [5] Custom Time (HH:MM)
#   [6] Advanced (OnCalendar)

# Enter custom time: 14:30
# ✓ Timer successfully updated
# ✓ Next run: Sat 2025-12-21 14:30:00
```

### 📄 Systemd Template System
**Unit files moved to templates with extensive documentation**

All systemd unit files are now generated from well-documented templates instead of hardcoded strings:

**Templates:**
- `kopi-docka.service.template` - Main daemon service with extensive security hardening comments (150+ lines)
- `kopi-docka.timer.template` - Timer unit with OnCalendar examples and usage guide (100+ lines)
- `kopi-docka-backup.service.template` - One-shot service for manual/cron usage (80+ lines)
- `templates/systemd/README.md` - Comprehensive user guide (400+ lines)

**Benefits:**
- **Self-Documenting** - Every setting explained with comments
- **OnCalendar Examples** - Extensive scheduling syntax examples in timer template
- **Security Documentation** - Each security setting documented with rationale
- **Customization Guide** - README explains how to customize units without editing source
- **Installation Instructions** - Step-by-step setup guide included
- **Troubleshooting** - Common issues and solutions documented

**Example from timer template:**
```ini
# ONCALENDAR SYNTAX EXAMPLES
#
# DAILY BACKUPS:
#   OnCalendar=*-*-* 02:00:00          # Every day at 02:00 AM
#   OnCalendar=*-*-* 23:00:00          # Every day at 11 PM
#
# WEEKLY BACKUPS:
#   OnCalendar=Mon *-*-* 03:00:00      # Every Monday at 03:00
#   OnCalendar=Sun *-*-* 02:00:00      # Every Sunday at 02:00
#
# MULTIPLE TIMES PER DAY:
#   OnCalendar=*-*-* 02:00,14:00:00    # 02:00 and 14:00 daily
```

### 🛠️ ServiceHelper Class
**High-level abstraction for systemctl/journalctl operations**

New `ServiceHelper` class provides a clean API for service management:

**Methods:**
- `get_service_status()` - Check service active/enabled/failed state
- `get_timer_status()` - Check timer status and next run time
- `get_current_schedule()` - Read OnCalendar from timer file
- `get_logs(mode, lines)` - View logs with filters (last, errors, hour, today)
- `get_last_backup_info()` - Parse logs for last backup timestamp and status
- `control_service(action, unit)` - Execute systemctl actions (start/stop/restart/enable/disable)
- `edit_timer_schedule(new_schedule)` - Update OnCalendar with validation
- `validate_time_format(time_str)` - Validate HH:MM format
- `validate_oncalendar(calendar_str)` - Test OnCalendar syntax via systemd-analyze
- `get_lock_status()` - Check lock file status and process state
- `units_exist()` - Check if systemd units are installed
- `reload_daemon()` - Reload systemd daemon configuration

**Data Classes:**
- `ServiceStatus` - Service state (active, enabled, failed)
- `TimerStatus` - Timer state (active, enabled, next_run, time_left)
- `BackupInfo` - Last backup info (timestamp, status, duration)

### 📦 Package Updates
- Added `rich>=13.0.0` to core dependencies
- Updated package_data to include systemd templates
- Full test coverage for new functionality (80%+)

### 📚 Documentation Updates
- Updated FEATURES.md with Interactive Service Management section
- Updated README.md with `manage` command example
- Comprehensive systemd template README with examples and troubleshooting

---

## What's New in v3.8.0

### 🔧 Architecture Refactoring
**Eliminated ~1000 lines of duplicate code**

The `commands/advanced/` modules were previously full copies of the legacy `commands/` modules. This caused:
- Code duplication (~1500 lines)
- Divergent bug fixes
- Maintenance burden

**Solution:** Converted all advanced modules to thin wrappers that delegate to legacy modules (Single Source of Truth):

| Module | Before | After | Savings |
|--------|--------|-------|---------|
| `advanced/config_commands.py` | 449 lines | 102 lines | -347 |
| `advanced/service_commands.py` | 103 lines | 75 lines | -28 |
| `advanced/repo_commands.py` | 703 lines | 121 lines | -582 |
| `advanced/system_commands.py` | 101 lines | 65 lines | -36 |

### 🩺 Doctor Command Fix
**Correct repository type detection**

The `doctor` command was incorrectly reading repository type from a non-existent config section, always showing "filesystem" even for rclone/S3/etc. repositories.

**Fix:** Now parses the first word of `kopia_params` to detect the actual repository type.

### 🏷️ Terminology Consistency
**"Repository Type" instead of "Backend Type"**

- All user-facing output now uses consistent "Repository Type" terminology
- Internal code standardized to use `repository_type` where appropriate
- Backend modules updated with consistent status output

### 🐛 Bug Fixes
- **Tailscale:** Fixed KeyError in `get_kopia_args()` when parsing repository path
- **Backends:** Removed dead code from `__init__.py` (unused registry pattern)
- **Config:** Removed dead code reading non-existent config sections

---

## What's New in v3.4.0

### 🎯 Simplified CLI Structure ("The Big 6")
**Cleaner command organization for better user experience**

Kopi-Docka v3.4.0 introduces a simplified CLI with **"The Big 6"** top-level commands and an `admin` subcommand for advanced operations.

**Top-Level Commands:**
```bash
kopi-docka setup              # Complete setup wizard
kopi-docka backup             # Run backup
kopi-docka restore            # Interactive restore wizard
kopi-docka disaster-recovery  # Create DR bundle
kopi-docka dry-run            # Simulate backup (preview)
kopi-docka doctor             # NEW: System health check
kopi-docka version            # Show version
```

**Admin Subcommands (Advanced):**
```bash
kopi-docka admin config show|new|edit|reset
kopi-docka admin repo init|status|maintenance|change-password
kopi-docka admin service daemon|write-units
kopi-docka admin system install-deps|show-deps
kopi-docka admin snapshot list|estimate-size
```

**Why This Change?**
- Reduced cognitive load for new users
- Most common operations are top-level
- Advanced operations organized in logical groups
- Cleaner `--help` output

---

### 🩺 New Doctor Command
**Comprehensive system health check**

The new `doctor` command merges `check`, `status`, and `repo-status` into a single health check:

```bash
sudo kopi-docka doctor

# Checks:
# 1. System Dependencies (Kopia, Docker)
# 2. Configuration Status
# 3. Repository Status (connection is the single source of truth)
```

Output includes:
- Dependency status (installed/missing)
- Config file location and validity
- Password configuration status
- Repository type and connection status
- Snapshot and backup unit count

---

### 📁 Admin Subcommand Groups
**Organized advanced commands**

| Group | Commands | Purpose |
|-------|----------|---------|
| `admin config` | show, new, edit, reset | Configuration management |
| `admin repo` | init, status, maintenance, change-password, etc. | Repository management |
| `admin service` | daemon, write-units | Systemd integration |
| `admin system` | install-deps, show-deps | Dependency management |
| `admin snapshot` | list, estimate-size | Snapshot & unit management |

---

### 📋 Migration from v3.3

Most commands still work, just moved under `admin`:

| Old (v3.3) | New (v3.4) |
|------------|------------|
| `new-config` | `admin config new` |
| `show-config` | `admin config show` |
| `init` | `admin repo init` |
| `repo-status` | `admin repo status` |
| `check` | `doctor` |
| `list` | `admin snapshot list` |
| `write-units` | `admin service write-units` |

**Unchanged top-level commands:** `setup`, `backup`, `restore`, `disaster-recovery`, `dry-run`, `version`

---

## What's New in v3.3.0

### 🎯 Backup Scope Selection
**Choose what to backup - from minimal to complete system backup**

Kopi-Docka v3.3.0 introduces three backup scopes:

```bash
# Minimal - Only container data (volumes)
sudo kopi-docka backup --scope minimal

# Standard - Volumes + Recipes + Networks (Recommended, Default)
sudo kopi-docka backup --scope standard

# Full - Everything including Docker daemon config (Complete)
sudo kopi-docka backup --scope full
```

**Scope Overview:**

| Scope | Volumes | docker-compose.yml | Networks | Docker Config | Use Case |
|-------|---------|-------------------|----------|---------------|----------|
| **minimal** | ✅ | ❌ | ❌ | ❌ | Fast data backup only |
| **standard** | ✅ | ✅ | ✅ | ❌ | **Recommended** - Complete stack backup |
| **full** | ✅ | ✅ | ✅ | ✅ | Disaster recovery - Complete system |

**Why Scopes?**
- **Minimal:** Fast daily backups when config rarely changes
- **Standard:** Best balance - complete stack recovery (default)
- **Full:** Complete disaster recovery including Docker daemon settings

---

### 🌐 Docker Network Backup & Restore
**Automatic backup of custom Docker networks with IPAM configuration**

Kopi-Docka now backs up your custom Docker networks including:
- Network driver configuration
- IPAM settings (subnets, gateways, IP ranges)
- Labels and options
- Custom network names

**What gets backed up:**
```bash
# Your custom networks
docker network ls
# → nextcloud_network (subnet: 172.20.0.0/16)
# → traefik_proxy (gateway: 172.21.0.1)
# → app_backend

# Kopi-Docka automatically backs up:
# - Network configuration (driver, IPAM, labels)
# - Subnet and gateway settings
# - Custom options
# Skips: bridge, host, none (default networks)
```

**Restore with conflict detection:**
```bash
sudo kopi-docka restore

# Interactive wizard shows:
# → 2️⃣ Restoring networks...
#    ⚠️ Network 'nextcloud_network' already exists
#       Recreate network 'nextcloud_network'? (yes/no/q):
```

**Features:**
- ✅ Automatic detection of custom networks
- ✅ Export of complete IPAM configuration
- ✅ Interactive conflict resolution during restore
- ✅ Preserves network topology

---

### 🔧 Pre/Post Backup Hooks
**Run custom scripts before and after backups - perfect for maintenance mode**

See detailed guide: [Hooks Documentation](HOOKS.md)

**Example: Nextcloud Maintenance Mode**

```bash
# /opt/hooks/nextcloud-pre-backup.sh
#!/bin/bash
docker exec nextcloud php occ maintenance:mode --on

# config.json
{
  "backup": {
    "hooks": {
      "pre_backup": "/opt/hooks/nextcloud-pre-backup.sh",
      "post_backup": "/opt/hooks/nextcloud-post-backup.sh"
    }
  }
}
```

**Use Cases:**
- Enable/disable application maintenance mode
- Custom database dumps before backup
- Send notifications (Telegram, email, Slack)
- Stop/start related services
- Custom pre-flight checks
- Cleanup tasks after backup

---

## Why Kopi-Docka?

### Feature Comparison

| Feature | Kopi-Docka | docker-volume-backup | Duplicati | Restic |
|---------|------------|----------------------|-----------|--------|
| **Docker-native** | ✅ | ✅ | ❌ | ❌ |
| **Cold Backups** | ✅ | ✅ | ❌ | ❌ |
| **Compose-Stack-Aware** | ✅ | ❌ | ❌ | ❌ |
| **Network Backup** | ✅ | ❌ | ❌ | ❌ |
| **Backup Scopes** | ✅ | ❌ | ❌ | ❌ |
| **Pre/Post Hooks** | ✅ | ⚠️ | ❌ | ❌ |
| **DR Bundles** | ✅ | ❌ | ❌ | ❌ |
| **Tailscale Integration** | ✅ | ❌ | ❌ | ❌ |
| **systemd-native** | ✅ | ❌ | ❌ | ❌ |
| **sd_notify + Watchdog** | ✅ | ❌ | ❌ | ❌ |
| **Security Hardening** | ✅ | ⚠️ | ⚠️ | ❌ |
| **Auto Peer Discovery** | ✅ | ❌ | ❌ | ❌ |
| **Multi-Cloud** | ✅ | ✅ | ✅ | ✅ |
| **Deduplication** | ✅ (Kopia) | ❌ | ✅ | ✅ |

Kopi-Docka combines four unique features: Stack-Awareness, DR-Bundles, Tailscale-Integration, and production-ready systemd integration.

### Who Is It For?

- **Homelab Operators** - Multiple Docker hosts with offsite backups
- **Self-Hosters** - Docker services with professional backup strategy
- **Small Businesses** - Disaster recovery without enterprise costs
- **Power Users** - Full control over backup and restore processes

[← Back to README](../README.md)
