# Kopi-Docka

> **Robust Cold Backups for Docker Environments using Kopia**

Kopi-Docka is a Python-based backup tool for Docker containers and their volumes. Features controlled downtime windows, encrypted snapshots, and automatic disaster recovery bundles.

[![PyPI](https://img.shields.io/pypi/v/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![Python Version](https://img.shields.io/pypi/pyversions/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/kopi-docka)](https://pypi.org/project/kopi-docka/)

---

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
kopi-docka list --units

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
sudo kopi-docka new-config
# → Select backend: Tailscale
# → Automatic peer discovery
# → Displays disk space, latency, online status
# → Automatic SSH key setup (passwordless)
```

The wizard shows all available devices in your Tailnet:

```
Available Backup Targets
┌──────────┬─────────────────┬────────────────┬─────────────┬──────────┐
│ Status   │ Hostname        │ IP             │ Disk Free   │ Latency  │
├──────────┼─────────────────┼────────────────┼─────────────┼──────────┤
│ 🟢 Online│ cloud-vps      │ 100.64.0.5     │ 450.2GB     │ 23ms     │
│ 🟢 Online│ home-nas       │ 100.64.0.12    │ 2.8TB       │ 45ms     │
│ 🔴 Offline│ raspberry-pi   │ 100.64.0.8     │ 28.5GB      │ -        │
└──────────┴─────────────────┴────────────────┴─────────────┴──────────┘
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

Kopi-Docka on PyPI: [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)

---

### 4. Systemd Integration

**Production-ready daemon with sd_notify, Watchdog, and Security Hardening**

Kopi-Docka is designed from the ground up for production use as a systemd service.

#### How It Works

**Systemd Daemon Mode:**
```bash
sudo kopi-docka daemon
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
sudo kopi-docka write-units

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
sudo kopi-docka daemon --interval-minutes 1440  # Daily

# In systemd unit:
[Service]
ExecStart=/usr/bin/env kopi-docka daemon --interval-minutes 1440
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

#### Technical Details

- **Type:** `notify` (sd_notify support)
- **Restart:** `on-failure` with 30s delay
- **WatchdogSec:** 300s (5 minutes)
- **StandardOutput/Error:** `journal` (structured logs)
- **RuntimeDirectory:** `/run/kopi-docka` (auto-cleanup)
- **Security:** Minimal privileges, process isolation
- **Locking:** fcntl-based PID lock

---

## Why Kopi-Docka?

### Feature Comparison

| Feature | Kopi-Docka | docker-volume-backup | Duplicati | Restic |
|---------|------------|----------------------|-----------|--------|
| **Docker-native** | ✅ | ✅ | ❌ | ❌ |
| **Cold Backups** | ✅ | ✅ | ❌ | ❌ |
| **Compose-Stack-Aware** | ✅ | ❌ | ❌ | ❌ |
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

---

## What is Kopi-Docka?

**Kopi-Docka = Kopia + Docker + Backup**

A wrapper around [Kopia](https://kopia.io), specifically for Docker environments:

- **Cold Backups** - Containers are briefly stopped for consistent data
- **Stack-Awareness** - Back up/restore Compose stacks as logical units
- **DR-Bundles** - Encrypted emergency packages with auto-reconnect script
- **Tailscale Integration** - P2P backups with automatic peer discovery
- **systemd-native** - Production-ready daemon with sd_notify, Watchdog, Security Hardening
- **Multi-Cloud** - Local paths, S3, B2, Azure, GCS, SFTP, Tailscale
- **Encrypted** - AES-256-GCM via Kopia, end-to-end
- **Restore Anywhere** - Recovery on completely new hardware

---

## The Wizards

Kopi-Docka has **two interactive wizards**:

### 1. Master Setup Wizard (`setup`)
**For:** Complete initial setup

```bash
sudo kopi-docka setup
```

**What it does:**
1. Check/install dependencies (optional)
2. Start config wizard (see below)
3. Initialize repository
4. Test everything

**When to use:** First-time installation

---

### 2. Config Wizard (`new-config`)
**For:** Create/recreate config only

```bash
sudo kopi-docka new-config
```

**What it does:**
1. **Backend Selection** - Interactive menu:
   ```
   1. Local Filesystem  - Local disk/NAS
   2. AWS S3           - S3-compatible (Wasabi, MinIO)
   3. Backblaze B2     - Affordable, recommended!
   4. Azure Blob       - Microsoft Azure
   5. Google Cloud     - GCS
   6. SFTP             - Remote via SSH
   7. Tailscale        - Peer-to-peer over private network
   ```

2. **Backend Configuration** - Queries backend-specific values:
   - Local: Repository path
   - S3: Bucket, region, endpoint (optional)
   - B2: Bucket, prefix
   - Azure: Container, storage account
   - GCS: Bucket, prefix
   - SFTP: Host, user, path
   - Tailscale: Peer selection (automatically detected)

3. **Password Setup:**
   ```
   1. Secure random password (recommended)
   2. Enter custom password
   ```

4. **Save Config** as JSON:
   - Root: `/etc/kopi-docka.json`
   - User: `~/.config/kopi-docka/config.json`

**When to use:** 
- Create new config
- Switch backend
- After manual config reset

**Example (B2 Backend):**
```bash
sudo kopi-docka new-config

# Wizard asks:
Where should backups be stored?
→ 3 (Backblaze B2)

Bucket name: my-backup-bucket
Path prefix: kopia

Password setup:
→ 1 (Auto-generate secure password)

✓ Configuration created: /etc/kopi-docka.json
  kopia_params: b2 --bucket my-backup-bucket --prefix kopia
  
⚠️ Set environment variables:
  export B2_APPLICATION_KEY_ID='...'
  export B2_APPLICATION_KEY='...'
```

**Wizard Relationship:**
```
Option A (Recommended):
└─ kopi-docka setup
   ├─ 1. Dependency check
   ├─ 2. Config wizard (new-config internally)
   │      ├─ Select backend
   │      ├─ Configure backend
   │      └─ Password setup
   ├─ 3. Repository init
   └─ 4. Connection test

Option B (Manual):
├─ kopi-docka check
├─ kopi-docka new-config (← Same wizard as in Option A!)
│      ├─ Select backend
│      ├─ Configure backend
│      └─ Password setup
├─ kopi-docka edit-config (optional)
└─ kopi-docka init
```

---

## Quick Start

### 🚀 Option A: Setup Wizard (Recommended)

**Master wizard - complete setup in one go!**

```bash
sudo kopi-docka setup
```

The master wizard automatically:
1. ✅ Dependency check (Kopia, Docker)
2. ✅ **Calls config wizard** (see above)
3. ✅ Initializes repository
4. ✅ Tests connection

**The integrated config wizard guides you through:**
- Backend selection (Local, S3, B2, Azure, GCS, SFTP, Tailscale)
- Interactive backend-specific settings
- Password setup (securely auto-generated or custom)
- Save config as JSON

**Then immediately ready:**
```bash
# Show containers
sudo kopi-docka list --units

# Test run
sudo kopi-docka dry-run

# First backup
sudo kopi-docka backup

# Create DR bundle (IMPORTANT!)
sudo kopi-docka disaster-recovery
```

---

### 🛠️ Option B: Manual Way (Advanced)

**Full control over each step:**

```bash
# 1. Check dependencies
sudo kopi-docka check

# 2. Install missing dependencies (optional)
sudo kopi-docka install-deps

# 3. Create config file (Interactive wizard!)
sudo kopi-docka new-config
# The config wizard guides you through:
#   → Backend selection (Local, S3, B2, Azure, GCS, SFTP, Tailscale)
#   → Backend-specific settings
#   → Password setup (auto-generate or custom)
#   → Config storage (JSON: /etc/kopi-docka.json)

# 4. Manually adjust config if needed (optional)
sudo kopi-docka edit-config

# 5. Initialize repository
sudo kopi-docka init

# 6. Check connection
sudo kopi-docka repo-status

# 7. Discover containers
sudo kopi-docka list --units

# 8. Test run (simulates backup)
sudo kopi-docka dry-run

# 9. First real backup
sudo kopi-docka backup

# 10. Create DR bundle (CRITICAL!)
sudo kopi-docka disaster-recovery
# Copy bundle to safe location: USB/phone/cloud/safe!
```

---

### 🎯 Which Option to Choose?

| Criteria | Setup Wizard | Manual |
|----------|--------------|---------|
| **Beginner-friendly** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Process** | One command | Multiple steps |
| **Control** | Standard | Full |
| **Recommended for** | First installation | Production, custom |
| **Config creation** | Automatic (wizard) | Config wizard + manual |
| **Password** | Wizard (auto/custom) | Wizard (auto/custom) |
| **Deps check** | Automatic | Manual |
| **Repo init** | Automatic | Manual |

**💡 Tip:** Both options use the **interactive config wizard** for backend configuration! The difference is just that `setup` does everything in one go.

---

## System Requirements

### Operating System
- **Linux** (Debian, Ubuntu, Arch, Fedora, RHEL/CentOS)
- Python 3.10 or newer
- Root privileges for Docker access

### Required Software
- **Docker Engine** (20.10+)
- **Docker CLI** 
- **Kopia CLI** (0.10+) - automatically checked
- **tar**, **openssl** (usually pre-installed)

**Quick check:**
```bash
sudo kopi-docka check
# Shows status of all dependencies
```

---

## Installation

### Requirements

- **OS:** Linux (Debian, Ubuntu, Arch, Fedora, RHEL/CentOS)
- **Python:** 3.10 or newer
- **Docker:** Docker Engine + Docker CLI
- **Kopia:** Automatically checked/installed

**Quick check:**
```bash
docker --version
python3 --version
```

---

### Option 1: pipx (Recommended - Isolated Environment)

```bash
# Install pipx if not present
sudo apt install pipx
pipx ensurepath

# Install Kopi-Docka from PyPI
pipx install kopi-docka

# Verify
kopi-docka version
```

### Option 2: pip (System-wide)

```bash
# Install from PyPI
pip install kopi-docka

# Or with sudo for system-wide installation
sudo pip install kopi-docka
```

### Option 3: From Source (Development)

```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka

# Development mode
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

### Install Dependencies

```bash
# Automatic (Debian/Ubuntu/Arch/Fedora)
sudo kopi-docka install-deps

# Show manual install guide
kopi-docka show-deps
```

### Update

```bash
# pipx
pipx upgrade kopi-docka

# pip
pip install --upgrade kopi-docka
```

---

## Configuration

### Create Config File

**Recommended:** Use the interactive config wizard:
```bash
sudo kopi-docka new-config
# Or as part of complete setup:
sudo kopi-docka setup
```

The wizard guides you through:
- ✅ Backend selection (interactive menu)
- ✅ Backend-specific settings
- ✅ Password setup (secure)
- ✅ Automatic config generation

---

### Config File Locations

Kopi-Docka v3.0+ uses **JSON format**:

**Standard paths** (in order):
1. `/etc/kopi-docka.json` (system-wide, recommended for servers)
2. `~/.config/kopi-docka/config.json` (user-specific)

**Custom path:**
```bash
kopi-docka --config /path/to/config.json <command>
```

### Config Example

```json
{
  "version": "3.0",
  "kopia": {
    "kopia_params": "filesystem --path /backup/kopia-repository",
    "password": "your-secure-password",
    "password_file": null,
    "compression": "zstd",
    "encryption": "AES256-GCM-HMAC-SHA256",
    "cache_directory": "/var/cache/kopi-docka"
  },
  "backup": {
    "base_path": "/backup/kopi-docka",
    "parallel_workers": "auto",
    "stop_timeout": 30,
    "start_timeout": 60,
    "task_timeout": 0,
    "update_recovery_bundle": false,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3,
    "exclude_patterns": []
  },
  "docker": {
    "socket": "/var/run/docker.sock",
    "compose_timeout": 300
  },
  "retention": {
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
    "yearly": 5
  },
  "logging": {
    "level": "INFO",
    "file": "/var/log/kopi-docka.log",
    "max_size_mb": 100,
    "backup_count": 5
  }
}
```

### Important Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `kopia_params` | Kopia repository parameters | `filesystem --path /backup/...` |
| `password` | Repository password | `CHANGE_ME_...` |
| `compression` | Compression | `zstd` |
| `parallel_workers` | Backup threads | `auto` (based on RAM/CPU) |
| `stop_timeout` | Container stop timeout (sec) | `30` |
| `start_timeout` | Container start timeout (sec) | `60` |
| `task_timeout` | Volume backup timeout (0=unlimited) | `0` |
| `exclude_patterns` | Tar exclude patterns (array) | `[]` |
| `update_recovery_bundle` | DR bundle with every backup | `false` |
| `recovery_bundle_retention` | DR bundles to keep | `3` |
| `retention.daily` | Daily backups to keep | `7` |
| `retention.weekly` | Weekly backups | `4` |
| `retention.monthly` | Monthly backups | `12` |
| `retention.yearly` | Yearly backups | `5` |

---

## Storage Backends

Kopi-Docka supports 7 different backends. The **config wizard** (`new-config`) interactively guides you through backend selection and configuration!

**Backend selection in wizard:**
```
Available backends:
  1. Local Filesystem  - Store on local disk/NAS mount
  2. AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)
  3. Backblaze B2     - Cost-effective cloud storage
  4. Azure Blob       - Microsoft Azure storage
  5. Google Cloud     - GCS storage
  6. SFTP             - Remote server via SSH
  7. Tailscale        - Peer-to-peer over private network
```

For each backend, the wizard queries necessary settings and generates the correct `kopia_params` config.

---

### Backend Overview

Here are manual `kopia_params` examples (if you edit config directly):

#### 1. Local Filesystem
```json
"kopia_params": "filesystem --path /backup/kopia-repository"
```

#### 2. AWS S3 (+ Wasabi, MinIO)
```json
"kopia_params": "s3 --bucket my-bucket --prefix kopia"
```
**Environment variables:**
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

#### 3. Backblaze B2
```json
"kopia_params": "b2 --bucket my-bucket --prefix kopia"
```
**Environment variables:**
```bash
export B2_APPLICATION_KEY_ID="..."
export B2_APPLICATION_KEY="..."
```

#### 4. Azure Blob
```json
"kopia_params": "azure --container my-container --prefix kopia"
```

#### 5. Google Cloud Storage
```json
"kopia_params": "gcs --bucket my-bucket --prefix kopia"
```

#### 6. SFTP
```json
"kopia_params": "sftp --path user@server:/path/to/repo"
```

#### 7. Tailscale
**P2P backups over your private network**

```json
"kopia_params": "sftp --path sftp://root@backup-server.tailnet:/backup/kopia"
```

**What the wizard does:**
1. Checks Tailscale connection
2. **Shows all peers** with:
   - Online status (🟢/🔴)
   - Free disk space
   - Latency/ping
3. **Automatically sets up SSH key**:
   - Generates ED25519 key
   - Copies to target server
   - Passwordless SSH
4. Tests connection

**Example output:**
```bash
sudo kopi-docka new-config

Available Backup Targets
┌──────────┬─────────────────┬────────────────┬─────────────┬──────────┐
│ Status   │ Hostname        │ IP             │ Disk Free   │ Latency  │
├──────────┼─────────────────┼────────────────┼─────────────┼──────────┤
│ 🟢 Online│ cloud-vps      │ 100.64.0.5     │ 450.2GB     │ 23ms     │
│ 🟢 Online│ home-nas       │ 100.64.0.12    │ 2.8TB       │ 45ms     │
│ 🔴 Offline│ raspberry-pi   │ 100.64.0.8     │ 28.5GB      │ -        │
└──────────┴─────────────────┴────────────────┴─────────────┴──────────┘

Select peer: home-nas

Backup path on remote [/backup/kopi-docka]: /mnt/nas/backups

Setup SSH key for passwordless access? Yes
✓ SSH key generated
✓ SSH key copied to home-nas
✓ Connection successful

✓ Configuration saved!
```

**Features:**
- No cloud costs
- No port forwarding needed
- End-to-end encrypted (WireGuard + Kopia)
- Direct P2P connection
- Automatic configuration

**Requirements:**
- Tailscale on both servers: `curl -fsSL https://tailscale.com/install.sh | sh`
- Both in the same Tailnet
- SSH access to backup server (one-time for key setup)

**More details:** [Tailscale Integration](#3-tailscale-integration)

---

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
| `backup` | **Full backup** (all units) |
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

**For detailed info see:** [Systemd Integration](#4-systemd-integration)

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

## Troubleshooting

### ❌ "No configuration found"

**Solution:**
```bash
sudo kopi-docka new-config
# or
sudo kopi-docka setup
```

### ❌ "invalid repository password"

**Cause:** Repository already exists with different password.

**Solution A (recommended):**
```bash
# Find old password (check config backup)
# Update config with correct password
sudo kopi-docka init
```

**Solution B (⚠️ DELETES BACKUPS):**
```bash
# Backup old repo first!
sudo mv /backup/kopia-repository /backup/kopia-repository.OLD
sudo kopi-docka init
```

### ⚠️ "No backup units found"

**Causes:**
- No Docker containers running
- Docker socket not accessible

**Solutions:**
```bash
# Check Docker access
docker ps

# Add user to docker group
sudo usermod -aG docker $USER
# Logout/login required

# Or run with sudo
sudo kopi-docka list --units
```

### Troubleshooting Tailscale

#### ❌ "No peers found in Tailnet"

**Cause:** No other devices in Tailnet or not logged in.

**Solution:**
```bash
# Check Tailscale status
tailscale status

# Log in if needed
sudo tailscale up

# Add other devices to Tailnet
# → tailscale.com → Settings → Machines
```

#### ❌ "Peer offline"

**Cause:** Backup server is offline or not in Tailnet.

**Solution:**
```bash
# On backup server:
sudo tailscale up

# Test from main server:
tailscale ping backup-server
```

#### ❌ "SSH key setup failed"

**Cause:** Root login not allowed or password auth disabled.

**Solution:**
```bash
# On backup server: /etc/ssh/sshd_config
PermitRootLogin yes  # Or 'prohibit-password'
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd

# Manually copy key:
ssh-copy-id -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet
```

#### 🔍 Test Connection

```bash
# Tailscale connection
tailscale status
tailscale ping backup-server

# SSH connection
ssh -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet

# SFTP connection (as Kopia uses it)
echo "ls" | sftp -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet
```

### 🔍 Debugging

```bash
# Verbose logging
sudo kopi-docka --log-level DEBUG check

# Check config
sudo kopi-docka show-config

# Verify dependencies
sudo kopi-docka check --verbose

# Test repository connection
sudo kopi-docka repo-status

# Dry run to see what would happen
sudo kopi-docka dry-run
```

---

## FAQ

### When should I use which backend?

**Local Filesystem**
- For local backups on NAS or external drive
- Fast, but no offsite protection
- Suitable for additional local copy

**Backblaze B2**
- Affordable cloud backups (~$5/TB/month)
- No own hardware needed
- Reliable and simple

**Tailscale**
- Own hardware at different location available (VPS/NAS/Pi)
- No ongoing costs
- Full control over data

**AWS S3**
- Existing AWS infrastructure
- Enterprise requirements

**SFTP**
- Existing SFTP server available
- Without Tailscale setup

### Can I combine multiple backends?

Yes! Use e.g. Tailscale as primary backup + B2 as additional offsite:

```bash
# Primary: Tailscale (daily)
sudo kopi-docka backup

# Secondary: B2 (weekly, different config)
sudo kopi-docka --config /etc/kopi-docka-b2.json backup
```

### How fast are Tailscale backups?

Speed depends on connection:

**Direct P2P (both in same LAN):** 100-500 MB/s
**P2P over Internet:** 10-50 MB/s
**Via DERP relay (if P2P not possible):** 5-20 MB/s

**Comparison other backends:**
- Cloud upload (S3/B2): Depends on upload speed (5-20 MB/s typical)
- Local NAS: 100-1000 MB/s (network dependent)

### Is Tailscale secure enough for backups?

Tailscale backups use double encryption:

1. **Tailscale (WireGuard)** - End-to-end encryption at network level
2. **Kopia (AES-256-GCM)** - Client-side encryption of backup data

Network traffic is encrypted by Tailscale, backup data itself is additionally encrypted by Kopia. Even with compromised network layer, data remains protected.

### Can I use Tailscale for multiple servers?

Yes, each server can have its own backup target:
- Multiple production servers → One backup server
- Server A ⇄ Server B (mutual backups)
- Different backup targets per server

Each server needs its own Kopi-Docka config with respective target peer.

### Should I use systemd Timer or Cron?

**systemd Timer (Recommended):**
- Native status communication (sd_notify)
- Watchdog monitoring
- Automatic restart on error
- Structured logs in journal
- PID locking
- Security hardening
- Persistent (catch up on failure)

**Cron (Alternative):**
- Simpler for existing setups
- Fewer features
- Manual error handling needed

**Use systemd Timer for production, Cron only if systemd not available.**

### How do I monitor backup status?

**Via systemd:**
```bash
# Timer status
systemctl list-timers | grep kopi-docka

# Service status
systemctl status kopi-docka.service

# Logs
journalctl -u kopi-docka.service --since "24 hours ago"

# Errors
journalctl -u kopi-docka.service -p err
```

**Monitoring integration:**
- Prometheus: node_exporter systemd module
- Zabbix: systemd monitoring template
- Nagios/Icinga: check_systemd_unit
- Email on error: OnFailure=status-email@%n.service

### Can I trigger backups manually while timer is running?

Yes, thanks to PID locking it's safe:
```bash
# Timer already running
sudo systemctl is-active kopi-docka.timer
# → active

# Manual backup
sudo kopi-docka backup
# → Runs if no other backup active
# → Waits or aborts otherwise
```

The lock prevents parallel backups.

---

## Project Structure

```
kopi-docka/
├── kopi_docka/
│   ├── __init__.py              # Main exports
│   ├── __main__.py              # CLI entry point (Typer)
│   ├── types.py                 # Dataclasses (BackupUnit, etc.)
│   │
│   ├── backends/                # Storage backend implementations
│   │   ├── base.py              # BackendBase (abstract)
│   │   ├── local.py             # Local filesystem
│   │   ├── s3.py                # AWS S3 / Wasabi / MinIO
│   │   ├── b2.py                # Backblaze B2
│   │   ├── azure.py             # Azure Blob
│   │   ├── gcs.py               # Google Cloud Storage
│   │   ├── sftp.py              # SFTP/SSH
│   │   └── tailscale.py         # Tailscale P2P
│   │
│   ├── helpers/                 # Utilities
│   │   ├── config.py            # Config handling (JSON)
│   │   ├── constants.py         # Global constants
│   │   ├── logging.py           # Structured logging
│   │   └── system_utils.py      # System checks (RAM/CPU/disk)
│   │
│   ├── cores/                   # Business logic
│   │   ├── backup_manager.py    # Backup orchestration
│   │   ├── restore_manager.py   # Restore wizard
│   │   ├── docker_discovery.py  # Container detection
│   │   ├── repository_manager.py # Kopia wrapper
│   │   ├── dependency_manager.py # System deps check
│   │   ├── dry_run_manager.py   # Simulation mode
│   │   ├── disaster_recovery_manager.py # DR bundle creation
│   │   ├── kopia_policy_manager.py # Retention policies
│   │   └── service_manager.py   # Systemd integration
│   │
│   ├── commands/                # CLI command handlers
│   │   ├── backup_commands.py   # list, backup, restore
│   │   ├── config_commands.py   # Config management
│   │   ├── dependency_commands.py # Deps check/install
│   │   ├── repository_commands.py # Repo operations
│   │   ├── service_commands.py  # Systemd setup
│   │   ├── setup_commands.py    # Setup wizard
│   │   └── dry_run_commands.py  # Simulation commands
│   │
│   └── templates/               # Config templates
│       └── config_template.json # v3.0 JSON config
│
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── pytest.ini               # Test configuration
│   ├── unit/                    # Fast unit tests
│   └── integration/             # Slow integration tests
│
├── .github/
│   └── workflows/
│       └── publish.yml          # PyPI auto-publish on tags
│
├── pyproject.toml               # Package configuration (PEP 517/518)
├── requirements.txt             # Dependencies
├── Makefile                     # Dev tasks
├── README.md                    # This file
└── LICENSE                      # MIT License
```

---

## Development

### Setup Dev Environment

```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka

# Install with dev dependencies
pip install -e ".[dev]"

# Format code
make format

# Check style
make check-style

# Run tests
make test

# Coverage
make test-coverage
```

### Code Style

- **Formatter:** Black (line-length: 100)
- **Linter:** flake8
- **Type Hints:** Recommended (not enforced yet)
- **Docstrings:** Google style

### Tests

```bash
# Fast unit tests
make test-unit

# All tests
make test

# With coverage
make test-coverage
# Opens htmlcov/index.html
```

---

## Status & Development

### Current Version: v3.0

Version 3.0 provides a **solid foundation** with stable architecture:
- ✅ Modular structure (helpers, cores, commands)
- ✅ JSON config instead of INI
- ✅ Clean type definitions
- ✅ Testable code structure
- ✅ Production-ready systemd integration
- ✅ Four unique core features

**The project lives from testing and feedback!** Current priorities:
1. **Testing** - Thoroughly test existing features
2. **Bug-Fixing** - Fix known issues
3. **Stability** - Improve robustness
4. **Documentation** - Close gaps

### Planned Features

These features are **prepared but not yet implemented**:

**Pre/Post-Backup Hooks**
- Config structure present (in older versions)
- Enables custom scripts before/after backups
- Use cases: Database dumps, notifications, custom checks
- Status: ⏳ Planned, no concrete timeline

**Extended Exclude Patterns**
- More granular control over excluded files
- Per-unit excludes
- Status: ⏳ Planned

**Backup Verification**
- Automatic snapshot verification
- Restore tests
- Status: ⏳ Idea

**Multi-Repository Support**
- Parallel backups to multiple repos
- 3-2-1 strategy
- Status: ⏳ Idea

### How You Can Help

**Testing:**
```bash
# Test different scenarios
kopi-docka check
kopi-docka dry-run
kopi-docka backup
kopi-docka restore
```

**Report Bugs:**
- [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- Please attach complete error logs
- Describe your setup (OS, Docker version, etc.)

**Give Feedback:**
- What works well?
- What's unclear?
- Which features are you missing?
- [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)

**The project evolves through your feedback!**

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests if applicable
5. Format code: `make format`
6. Run tests: `make test`
7. Commit: `git commit -m "Add amazing feature"`
8. Push: `git push origin feature/amazing-feature`
9. Open pull request

**Report issues:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)

---

## Credits & Acknowledgments

**Author:** Markus F. (TZERO78)

**Links:**
- PyPI: [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- GitHub: [github.com/TZERO78/kopi-docka](https://github.com/TZERO78/kopi-docka)

### Powered by Kopia

**Kopi-Docka wouldn't exist without [Kopia](https://kopia.io)!**

Kopi-Docka is a **wrapper** that uses Kopia's powerful backup engine. Kopia remains **completely unmodified** - we just orchestrate it for Docker workflows.

Huge thanks to [Jarek Kowalski](https://github.com/jkowalski) and all Kopia contributors for building an incredible backup tool. Kopia provides:
- 🔐 End-to-end encryption (AES-256-GCM)
- 🗜️ Deduplication & compression
- ☁️ Multi-cloud support (S3, B2, Azure, GCS, SFTP)
- 📦 Incremental backups with snapshots
- 🚀 High performance and reliability

**How Kopi-Docka uses Kopia:**
- ✅ Kopi-Docka uses a **separate Kopia profile** (`~/.config/kopia/repository-kopi-docka.config`)
- ✅ Your existing Kopia backups continue to work unchanged
- ✅ Kopia's code is **never modified** - it's an external dependency
- ✅ You get all of Kopia's features (encryption, deduplication, multi-cloud, etc.)
- ✅ Both Kopi-Docka and your personal Kopia backups can run simultaneously

**Links:**
- Kopia Website: https://kopia.io
- Kopia GitHub: https://github.com/kopia/kopia
- Kopia Docs: https://kopia.io/docs/

### Other Dependencies

- **[Docker](https://www.docker.com/)** - Container lifecycle management
- **[Typer](https://typer.tiangolo.com/)** - CLI framework
- **[Rich](https://rich.readthedocs.io/)** - Beautiful terminal output
- **[psutil](https://github.com/giampaolo/psutil)** - System resource monitoring

> **Note:** Kopi-Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2025 Markus F. (TZERO78)

**Third-Party Notices:**
- Kopia: Apache License 2.0
- Docker: Proprietary
- Python dependencies: See LICENSE file for full details

---

## Support & Community

- 📦 **PyPI:** [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- 📚 **Documentation:** [GitHub README](https://github.com/TZERO78/kopi-docka#readme)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)

**Like Kopi-Docka?** Give us a ⭐ on GitHub!

---

**Note:** Kopi-Docka is a private open-source project without commercial intentions.
No business is operated and no revenue is generated.
