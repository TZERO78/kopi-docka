# Kopi-Docka

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub release](https://img.shields.io/github/v/release/TZERO78/kopi-docka)](https://github.com/TZERO78/kopi-docka/releases)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-lightgrey)](https://github.com/TZERO78/kopi-docka)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> 🐳 **Docker Backup & Disaster Recovery using Kopia**  
> Automated backups of Docker Compose stacks with encryption, deduplication & cloud storage.  
> **Production back online in 15 minutes!**

Kopi-Docka performs **consistent, cold backups** of Docker stacks ("backup units"). It briefly stops containers, snapshots **recipes** (Compose + `docker inspect`, with secret redaction) and **volumes** into a Kopia repository, then restarts your services.

**🛡️ True Disaster Recovery:** Server crashed? DR bundle + new server + 15 minutes = everything running again. No manual config hunting, no 8-hour restore marathons.

> **Note:** Kopi-Docka intentionally **does not** create separate database dumps anymore. Volumes are the **single source of truth**.

---

## Why Kopi-Docka?

**From server crash to running services in 15 minutes - on a completely different server!**

Kopi-Docka focuses on **true disaster recovery** for Docker environments. Not just backups, but complete, encrypted stack restoration with one command.

### The Problem
Server crashed at 3 AM. Your docker-compose files? Gone. Kopia password? Where was that? S3 bucket name? Configuration? 8 hours of manual work to get everything running again.

### The Solution
Kopi-Docka creates **Disaster Recovery Bundles** containing everything you need:
* Repository connection info
* Encrypted passwords
* Complete configuration
* Automatic reconnect script
* Backup inventory

**Result:** New server + DR Bundle + 15 minutes = Everything running again! 🚀

### Use Cases

#### 🏠 Homelab
*"I run 15 Docker stacks on my NAS. Manual backups are a nightmare."*  
→ Automate everything with systemd timers

#### 🖥️ VPS Self-Hosting
*"Hetzner VPS with Nextcloud, Traefik, etc. Need offsite backups."*  
→ Direct backup to Backblaze B2 (cheap and reliable!)

#### 🚀 Production Servers
*"Disaster recovery must be fast and reliable."*  
→ Recovery bundles restore everything in 15 minutes

#### 🧪 Testing/Staging
*"Need snapshots before updates."*  
→ Quick snapshots, easy rollback

**Perfect for:** Self-hosted services, homelab servers, small business Docker hosts where downtime is costly and manual restoration is painful.

If you need enterprise-grade orchestration, consider Kubernetes backup tools like Velero. Kopi-Docka shines on single Docker hosts and small fleets where simplicity and reliability matter most.

### Already using Kopia?

**No problem!** Kopi-Docka uses its own separate profile (`~/.config/kopia/repository-kopi-docka.config`), so your existing Kopia backups continue to work unchanged. You can run both side-by-side:

```bash
# Your personal backups (unchanged)
kopia snapshot create /home/user/documents

# Docker backups (separate profile)
kopi-docka backup
```

**Zero conflicts. Both can even run simultaneously.**

---

## Key Features

* 🛡️ **Disaster Recovery Bundles** - encrypted emergency kit with repo info, passwords, and auto-reconnect script
* 🔄 **Restore anywhere** - works on completely different servers (new hardware, provider, datacenter)
* 🔒 **Cold, consistent backups** - short downtime per unit, guaranteed data integrity
* 🧩 **Backup Units** - Compose stacks or standalone containers, backed up as one logical unit
* 🧾 **Complete recipes** - `docker-compose.yml` (if present) + `docker inspect` with secret redaction
* 📦 **Volume snapshots** - tar stream with owners/ACLs/xattrs, dedupe-friendly ordering & mtimes
* 🏷️ **Mandatory `backup_id`** - every run tags snapshots with `{ unit, backup_id, type, timestamp }`
* 🧰 **Per-unit Kopia policies** - retention set on `recipes/UNIT` and `volumes/UNIT`
* 🔐 **Client-side encryption** - AES-256 via Kopia, cloud provider sees only encrypted blobs
* ☁️ **Multi-cloud support** - S3, Backblaze B2, Azure, Google Cloud, SFTP, or local filesystem
* 🧪 **Dry-run mode** - full simulation, no changes, test before real backup
* 🐧 **systemd-friendly** - daemon with sd_notify/watchdog/locking + sample service/timer units
* ⚙️ **Parallel workers = auto** - tuned by RAM/CPU; no artificial `task_timeout`
* ⏱️ **Fast recovery** - from server crash to running services in ~15 minutes
* 🔧 **Separate Kopia profile** - uses its own config, doesn't interfere with your existing Kopia backups

---

## Works with Your Existing Kopia Setup

**Kopi-Docka uses a separate Kopia profile - zero conflicts!**

If you already use Kopia for other backups (like `/home`, documents, photos), Kopi-Docka **will not interfere**:

```bash
# Your existing Kopia backups
~/.config/kopia/repository.config           # Your default profile
kopia snapshot create /home/user/documents  # Works as always

# Kopi-Docka uses its own profile
~/.config/kopia/repository-kopi-docka.config  # Separate profile
kopi-docka backup                            # Uses separate config

# Both run independently - no conflicts!
```

**What this means:**
- ✅ You can keep using Kopia for your personal backups
- ✅ Kopi-Docka handles Docker backups separately
- ✅ Different repositories, different schedules, different retention policies
- ✅ Both can run at the same time
- ✅ Kopia remains completely unmodified - we're just a wrapper

**Example setup:**
```bash
# Morning: Your personal backup (to USB drive)
kopia snapshot create /home/user

# Night: Docker backup (to cloud)
kopi-docka backup

# Both backups are completely independent!
```

---

## How it Works

### 1) Discovery

Finds running containers & volumes, groups them into **backup units** (Compose stacks preferred; otherwise standalone). Recipes include Compose path (if labeled) and `docker inspect` (ENV secrets redacted: `PASS|SECRET|KEY|TOKEN|API|AUTH`).

### 2) Backup Pipeline (Cold)

1. Create **`backup_id`** (e.g., `2025-01-31T23-59-59Z`) – required and used for grouping.
2. **Stop** unit containers (graceful `docker stop -t <timeout>`).
3. **Snapshot recipes** → Kopia tags: `{type: recipe, unit, backup_id, timestamp}`.
4. **Snapshot volumes** (parallel, up to `parallel_workers`) via tar stream → Kopia `--stdin`  
   Tags: `{type: volume, unit, volume, backup_id, timestamp, size_bytes?}`.
5. **Start** containers; if a healthcheck exists, wait until `healthy`.
6. **Apply retention** policies per unit (daily/weekly/monthly/yearly).
7. (Optional) **Create DR bundle** and rotate.

### 3) Restore (On ANY Server!)

**Disaster scenario? No problem!**

1. Get DR bundle from safe storage (USB/phone/cloud)
2. Deploy new server (any Linux distro)
3. Install Kopi-Docka
4. Decrypt bundle & run `./recover.sh` - auto-reconnects to your repository
5. `kopi-docka restore` - interactive wizard restores everything
6. `docker compose up -d` in restored directory - services online!

**Total time: ~15 minutes from bare metal to production!**

---

## Installation

### Requirements

- **OS:** Linux (Debian, Ubuntu, or similar)
- **Python:** 3.10 or newer
- **Docker:** Docker Engine + Docker Compose
- **Kopia:** Will be checked/installed by dependency manager

### Install from Source

```bash
# Clone repository
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka

# Install
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"

# Verify installation
kopi-docka --version
```

### Alternative: Install directly from GitHub

```bash
# Install latest version
pip install git+https://github.com/TZERO78/kopi-docka.git

# Or specific version
pip install git+https://github.com/TZERO78/kopi-docka.git@v2.0.0
```

---

## Quick Start

### First-Time Setup

```bash
# 1. Check system dependencies
kopi-docka check

# 2. Create configuration file
kopi-docka new-config
# Edit ~/.config/kopi-docka/config.conf:
#   - Set repository_path (local or cloud)
#   - Set password (change this!)

# 3. Initialize Kopia repository
kopi-docka init

# 4. IMPORTANT: Change default password!
kopi-docka change-password

# 5. See what would be backed up
kopi-docka list --units

# 6. Test run (no changes)
kopi-docka dry-run

# 7. Create first backup
sudo kopi-docka backup

# 8. Create disaster recovery bundle (IMPORTANT!)
sudo kopi-docka disaster-recovery
# Copy bundle to safe storage (USB/phone/cloud vault)!
```

### Configuration

Configuration file locations (in order of precedence):
- **Root:** `/etc/kopi-docka.conf`
- **User:** `~/.config/kopi-docka/config.conf`

**Kopia Profile:** Kopi-Docka uses its own Kopia config file at `~/.config/kopia/repository-kopi-docka.config`. This ensures your existing Kopia backups (if any) are not affected.

Example configuration:
```ini
[kopia]
repository_path = b2://my-backup-bucket/kopia
password = your-secure-password-here
profile = kopi-docka
compression = zstd
encryption = AES256-GCM-HMAC-SHA256
cache_directory = /var/cache/kopia

[backup]
base_path = /backup/kopi-docka
parallel_workers = 4
stop_timeout = 30
start_timeout = 60
task_timeout = 0
update_recovery_bundle = false
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
exclude_patterns = 
pre_backup_hook = 
post_backup_hook = 

[retention]
daily = 7
weekly = 4
monthly = 12
yearly = 5

[docker]
socket = /var/run/docker.sock
compose_timeout = 300
prune_stopped_containers = false

[logging]
level = INFO
file = /var/log/kopi-docka.log
max_size_mb = 100
backup_count = 5
```

---

## CLI Commands Reference

### Configuration Management
| Command | Description |
|---------|-------------|
| `show-config` | Display current configuration (with secrets masked) |
| `new-config` | Create new config file with template |
| `edit-config` | Open config in editor ($EDITOR or nano) |
| `reset-config` | ⚠️ Reset config completely (creates new password!) |
| `change-password` | Safely change Kopia repository password |

### System & Dependencies
| Command | Description |
|---------|-------------|
| `check` | Verify all dependencies and show status |
| `check --verbose` | Show detailed system information |
| `install-deps` | Auto-install missing system dependencies |
| `install-deps --dry-run` | Show what would be installed |
| `show-deps` | Show manual installation guide for dependencies |
| `version` | Show Kopi-Docka version |

### Repository Management
| Command | Description |
|---------|-------------|
| `init` | Initialize or connect to Kopia repository |
| `repo-status` | Show detailed repository status with native Kopia info |
| `repo-which-config` | Display which Kopia config file is being used |
| `repo-set-default` | Make current profile the default Kopia config |
| `repo-init-path PATH` | Create new filesystem repository at specific path |
| `repo-maintenance` | Run Kopia repository maintenance (cleanup, optimize) |
| `repo-selftest` | Create temporary test repository for validation |

### Backup & Restore Operations
| Command | Description |
|---------|-------------|
| `list --units` | Show all discovered backup units (containers/stacks) |
| `list --snapshots` | Show all Kopia snapshots in repository |
| `dry-run` | Simulate backup without making any changes |
| `dry-run --unit NAME` | Simulate backup for specific unit only |
| `dry-run-units` | Show detailed unit analysis |
| `estimate-size` | Calculate estimated backup size for all units |
| `backup` | Run full cold backup for all units |
| `backup --unit NAME` | Backup specific unit(s) only |
| `backup --dry-run` | Test mode - no actual changes |
| `backup --update-recovery` | Create/update disaster recovery bundle after backup |
| `restore` | Interactive restore wizard |
| `disaster-recovery` | Create disaster recovery bundle manually |

### Service & Automation
| Command | Description |
|---------|-------------|
| `daemon` | Run systemd-friendly daemon (for manual testing) |
| `write-units` | Generate systemd service/timer unit files |

---

## Usage Examples

### Basic Operations

**List Backup Units**
```bash
kopi-docka list --units
```

**Dry Run (Test Mode)**
```bash
kopi-docka dry-run
kopi-docka dry-run --unit my-stack
```

**Backup Everything**
```bash
kopi-docka backup
```

**Backup Specific Units**
```bash
kopi-docka backup --unit webapp --unit database
```

**Check Repository Status**
```bash
kopi-docka repo-status
```

**List All Snapshots**
```bash
kopi-docka list --snapshots
```

### Disaster Recovery Workflows

**Create DR Bundle (Manual)**
```bash
# Create bundle now
kopi-docka disaster-recovery

# Bundle created at configured location
# Copy to safe storage (USB/phone/vault)!
```

**Enable Automatic DR Updates**
```ini
# In kopi-docka.conf:
[backup]
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
```

```bash
# Now every backup updates the bundle
kopi-docka backup
```

**Use DR Bundle in Emergency (on NEW server)**
```bash
# 1. Install Kopi-Docka on new server
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e .

# 2. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in kopi-docka-recovery-*.tar.gz.enc \
  -out recovered.tar.gz

# 3. Extract
tar -xzf recovered.tar.gz
cd kopi-docka-recovery-*/

# 4. Auto-reconnect to repository
sudo ./recover.sh
# Guides you through reconnection

# 5. Restore your stacks
kopi-docka restore

# 6. Start services
cd /tmp/kopia-restore-*/recipes/
docker compose up -d
```

### Full Restore Workflow

**Interactive Restore Wizard**
```bash
kopi-docka restore
```

**What the wizard does:**
1. Shows available restore points (grouped by unit + backup_id)
2. Lets you select which stack to restore
3. Restores docker-compose.yml and configs
4. Creates safe volume restore scripts
5. Provides commands to restart services

**Restore on Different Server**
```bash
# Server A died, restoring on Server B:
# 1. Install Kopi-Docka on Server B
# 2. Use DR bundle to reconnect
# 3. Restore as normal
kopi-docka restore
# Volumes restore to new server
# Docker Compose brings up services
```

**Verify Backups**
```bash
# List all snapshots
kopi-docka list --snapshots

# Check repository
kopi-docka repo-status

# Run maintenance
kopi-docka repo-maintenance
```

---

## Cloud Storage Backends

Kopi-Docka supports all Kopia backends. Set up credentials and configure `repository_path`:

### Local Filesystem
```ini
[kopia]
repository_path = /backup/kopia-repository
```

### AWS S3 / Wasabi / MinIO
```bash
# Set environment variables
export AWS_ACCESS_KEY_ID="your-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"  # optional
```

```ini
[kopia]
repository_path = s3://my-bucket/kopia
# Optional: specify endpoint for Wasabi/MinIO
# Add to [kopia] section: s3_endpoint = s3.wasabisys.com
```

### Backblaze B2 (Recommended - Cheap!)
```bash
# Set environment variables
export B2_APPLICATION_KEY_ID="your-key-id"
export B2_APPLICATION_KEY="your-key"
```

```ini
[kopia]
repository_path = b2://my-bucket/kopia
```

### Azure Blob Storage
```bash
# Set environment variable
export AZURE_STORAGE_ACCOUNT="youraccount"
export AZURE_STORAGE_KEY="your-key"
```

```ini
[kopia]
repository_path = azure://container/kopia
```

### Google Cloud Storage
```bash
# Authenticate with gcloud
gcloud auth application-default login

# Or set service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

```ini
[kopia]
repository_path = gs://my-bucket/kopia
```

### SFTP
```ini
[kopia]
repository_path = sftp://user@server/path/to/kopia
# Configure SSH key authentication separately
```

---

## Disaster Recovery

**Your "Break Glass" emergency plan for total server loss.**

### What is the Disaster Recovery Bundle?

An encrypted package containing **everything** you need to reconnect to your backups and restore services - even if your entire infrastructure is gone.

**Bundle contents:**
```
kopi-docka-recovery-TIMESTAMP.tar.gz.enc  (encrypted with AES-256-CBC)
├── kopia-repository.json       # Repository connection info
├── kopia-password.txt          # Encrypted repository password
├── kopi-docka.conf            # Your complete configuration
├── recover.sh                 # Automatic reconnect script
├── backup-status.json         # Inventory of all backups
└── RECOVERY-INSTRUCTIONS.txt  # Human-readable steps
```

### Disaster Scenario Walkthrough

**3:00 AM - Everything is gone:**
- ❌ Production server crashed (hardware failure)
- ❌ All configs lost
- ❌ Can't remember Kopia password
- ❌ Which S3 bucket was it again?
- ❌ Team is panicking

**3:05 AM - Get the DR Bundle:**
- ✅ Retrieve from safe storage (USB stick / phone / vault)
- ✅ Decrypt with your DR password:
```bash
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in bundle.tar.gz.enc \
  -out bundle.tar.gz
```

**3:10 AM - Deploy new server:**
- ✅ Spin up fresh Ubuntu/Debian instance (any provider!)
- ✅ Install Kopi-Docka:
```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e .
```

**3:15 AM - Auto-reconnect:**
```bash
cd recovered-bundle/
sudo ./recover.sh
# Script automatically:
# - Connects to your cloud repository (S3/B2/Azure/GCS)
# - Authenticates with stored credentials
# - Verifies backup integrity
# - Shows available restore points
```

**3:20 AM - Restore services:**
```bash
kopi-docka restore
# Interactive wizard:
# 1. Select stack/unit
# 2. Choose backup_id (timestamp)
# 3. Restores docker-compose.yml
# 4. Generates safe volume restore scripts
# 5. Provides startup commands
```

**3:30 AM - Services online:**
```bash
cd /tmp/kopia-restore-*/recipes/
docker compose up -d
```

**Total time: 30 minutes from total loss to running production!**

### Creating DR Bundles

**Manual creation:**
```bash
kopi-docka disaster-recovery
```

**Automatic updates after every backup:**
```ini
# kopi-docka.conf
[backup]
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
```

**Best practices:**
- ✅ Store bundle in **multiple** safe locations (USB, phone, password manager, trusted person)
- ✅ Test decryption regularly
- ✅ Update after major config changes
- ✅ Keep bundle password separate from repository password
- ✅ Document bundle location in team runbook

---

## Systemd Integration

### Setup Automated Backups

```bash
# Generate systemd service and timer files
sudo kopi-docka write-units

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timer (daily backups at 02:00)
sudo systemctl enable --now kopi-docka.timer

# Check timer status
systemctl status kopi-docka.timer

# Check service status
systemctl status kopi-docka.service

# View logs (real-time)
journalctl -u kopi-docka -f

# View recent logs
journalctl -u kopi-docka -n 50
```

### Custom Schedule

Edit timer configuration:
```bash
sudo systemctl edit kopi-docka.timer
```

```ini
[Timer]
OnCalendar=*-*-* 03:00:00  # Daily at 03:00
Persistent=true
RandomizedDelaySec=300      # Add 0-5 min random delay
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart kopi-docka.timer
```

**Calendar syntax examples:**
```ini
OnCalendar=daily             # Daily at midnight
OnCalendar=weekly            # Weekly on Mondays
OnCalendar=Mon *-*-* 02:00:00  # Every Monday at 02:00
OnCalendar=*-*-1 03:00:00    # First of month at 03:00
OnCalendar=*-*-* 02,14:00:00 # Twice daily (02:00 and 14:00)
```

### Monitoring

```bash
# Check if timer is active
systemctl list-timers kopi-docka.timer

# View service logs
journalctl -u kopi-docka -f

# Check last backup status
sudo kopi-docka repo-status
```

---

## Troubleshooting

### 🚨 Lost Everything? (Server Crashed)

**You have DR Bundle?**
1. ✅ Install Kopi-Docka on new server
2. ✅ Decrypt & extract bundle
3. ✅ Run `./recover.sh` (auto-reconnects)
4. ✅ `kopi-docka restore` (restores everything)
5. ✅ `docker compose up -d` (services online)

**Total time: ~15 minutes!**

**No DR Bundle?**
- ❌ Manually remember repo location
- ❌ Find repo password somewhere
- ❌ Manually configure everything
- ❌ Hours of work

**Prevention:** Always create DR bundles and store them safely!

### ❌ "invalid repository password"

**Cause:** Repository already exists with different password.

**Solution A (recommended):**
```bash
# Find old password (check backup of config)
# Update config with correct password
kopi-docka init
```

**Solution B (⚠️ DELETES BACKUPS):**
```bash
# Backup old repo first!
sudo mv /backup/kopia-repository /backup/kopia-repository.OLD
kopi-docka init
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

### 🔍 "Not connected" vs "Connected"

Different users = different Kopia profiles!

```bash
# Check which config is used
kopi-docka repo-which-config

# Root vs User have separate configs:
# - Root: /root/.config/kopia/...
# - User: /home/user/.config/kopia/...
```

**Note:** Kopi-Docka always uses its own profile (`repository-kopi-docka.config`), so it won't interfere with your default Kopia setup.

### 🤔 Can I use Kopia for other backups too?

**Yes, absolutely!** Kopi-Docka uses a separate Kopia profile, so you can continue using Kopia for:
- Personal file backups (`kopia snapshot create /home/user`)
- Server configuration backups
- Database dumps
- Anything else!

**Your Kopia backups and Kopi-Docka backups are completely independent:**

```bash
# Check your default Kopia profile
kopia repository status

# Check Kopi-Docka's profile
kopi-docka repo-status

# Both work independently!
```

### 📁 Permission Issues

```bash
# Ensure backup path is writable
sudo mkdir -p /backup/kopia-repository
sudo chown $USER:$USER /backup/kopia-repository

# Check Docker socket permissions
ls -la /var/run/docker.sock
sudo chmod 666 /var/run/docker.sock  # temporary fix
# Better: add user to docker group (see above)
```

### 🐛 Debugging

```bash
# Verbose logging
kopi-docka --log-level DEBUG check

# Check config
kopi-docka show-config

# Verify dependencies
kopi-docka check --verbose

# Test repository connection
kopi-docka repo-status

# Dry run to see what would happen
kopi-docka dry-run --verbose
```

---

## Project Structure

```
kopi-docka/
├── kopi_docka/
│   ├── __init__.py              # Main exports
│   ├── __main__.py              # CLI entry point (Typer)
│   ├── types.py                 # Dataclasses (BackupUnit, etc.)
│   │
│   ├── helpers/                 # Utility modules
│   │   ├── __init__.py
│   │   ├── config.py            # Config file handling
│   │   ├── constants.py         # Global constants
│   │   ├── logging.py           # Structured logging
│   │   └── system_utils.py      # System checks (RAM/CPU/disk)
│   │
│   ├── cores/                   # Business logic
│   │   ├── __init__.py
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
│   │   ├── __init__.py
│   │   ├── backup_commands.py   # list, backup, restore
│   │   ├── config_commands.py   # Config management
│   │   ├── dependency_commands.py # Deps check/install
│   │   ├── repository_commands.py # Repo operations
│   │   ├── service_commands.py  # Systemd setup
│   │   └── dry_run_commands.py  # Simulation commands
│   │
│   └── templates/               # Config templates
│       └── config_template.conf
│
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── pytest.ini               # Test configuration
│   ├── unit/                    # Fast unit tests
│   │   ├── test_main.py         # ✅ 10/10 passing
│   │   ├── test_backup_commands.py
│   │   ├── test_dependency_commands.py
│   │   └── test_repository_commands.py
│   └── integration/             # Slow integration tests
│       └── test_backup_flow.py
│
├── .github/
│   └── workflows/
│       └── python-app.yml       # CI/CD pipeline
│
├── setup.py                     # Package configuration
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
```

### Development Tasks

```bash
# Format code (Black)
make format

# Check style (flake8)
make check-style

# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run tests with coverage
make test-coverage

# Run specific test file
make test-file FILE=tests/unit/test_main.py
```

### Code Style

- **Formatter:** Black
- **Linter:** flake8
- **Type Hints:** Encouraged (not enforced yet)
- **Docstrings:** Google style

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests if applicable
5. Format code: `make format`
6. Run tests: `make test`
7. Commit: `git commit -m "Add amazing feature"`
8. Push: `git push origin feature/amazing-feature`
9. Open a Pull Request

**Report issues:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)

---

## Credits & Acknowledgments

**Author:** Markus F. (TZERO78)

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
- **[psutil](https://github.com/giampaolo/psutil)** - System resource monitoring

> **Note:** Kopi-Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Markus F. (TZERO78)

**Third-Party Notices:**
- Kopia: Apache License 2.0
- Docker: Proprietary
- Python dependencies: See LICENSE file for full details

---

## Contact

**Project Maintainer:** Markus F. (TZERO78)

- **GitHub:** [@TZERO78](https://github.com/TZERO78)
- **Issues:** [Report bugs](https://github.com/TZERO78/kopi-docka/issues)
- **Discussions:** [Ask questions](https://github.com/TZERO78/kopi-docka/discussions)

---

**Hinweis:** Kopi-Docka ist ein privates Open-Source-Projekt ohne kommerzielle Absichten.
Es wird kein Gewerbe betrieben und es werden keine Einnahmen generiert.

---

**Love Kopi-Docka?** Give us a ⭐ on GitHub!
