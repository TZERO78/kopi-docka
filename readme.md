# Kopi‑Docka

**Robust cold backups for Docker environments using Kopia**

[![Build](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml/badge.svg)](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-lightgrey)
![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)
![License](https://img.shields.io/badge/license-MIT-green)

Kopi‑Docka performs **consistent, cold backups** of Docker stacks ("backup units"). It briefly stops containers, snapshots **recipes** (Compose + `docker inspect`, with secret redaction) and **volumes** into a Kopia repository, then restarts your services.

**🛡️ True Disaster Recovery:** Server crashed? DR bundle + new server + 15 minutes = everything running again. No manual config hunting, no 8-hour restore marathons.

> **Note:** Kopi‑Docka intentionally **does not** create separate database dumps anymore. Volumes are the **single source of truth**.

---

## Why Kopi‑Docka?

**From server crash to running services in 15 minutes - on a completely different server!**

Kopi‑Docka focuses on **true disaster recovery** for Docker environments. Not just backups, but complete, encrypted stack restoration with one command.

### The Problem
Server crashed at 3 AM. Your docker-compose files? Gone. Kopia password? Where was that? S3 bucket name? Configuration? 8 hours of manual work to get everything running again.

### The Solution
Kopi‑Docka creates **Disaster Recovery Bundles** containing everything you need:
* Repository connection info
* Encrypted passwords
* Complete configuration
* Automatic reconnect script
* Backup inventory

**Result:** New server + DR Bundle + 15 minutes = Everything running again! 🚀

### Use it when you want:

* **True disaster recovery:** Restore complete stacks on ANY server (even different provider/datacenter)
* **Consistency first:** Cold backups (Stop → Snapshot → Start) guarantee data integrity
* **Stack awareness:** Back up complete Compose stacks as one **backup unit**
* **Encrypted cloud storage:** AES-256 client-side encryption via Kopia (S3, B2, Azure, GCS†)
* **Zero manual work:** Restore wizard handles everything - no config hunting, no guesswork
* **Complete autonomy:** No vendor lock-in, no subscription services, full control

† subject to Kopia support and your configuration.

**Perfect for:** Self-hosted services, homelab servers, small business Docker hosts where downtime is costly and manual restoration is painful.

If you need enterprise‑grade orchestration, consider Kubernetes backup tools like Velero. Kopi‑Docka shines on single Docker hosts and small fleets where simplicity and reliability matter most.

---

## Key Features

* 🛡️ **Disaster Recovery Bundles** - encrypted emergency kit with repo info, passwords, and auto-reconnect script
* 🔄 **Restore anywhere** - works on completely different servers (new hardware, provider, datacenter)
* 🔒 **Cold, consistent backups** - short downtime per unit, guaranteed data integrity
* 🧩 **Backup Units** - Compose stacks or standalone containers, backed up as one logical unit
* 🧾 **Complete recipes** - `docker-compose.yml` (if present) + `docker inspect` with secret redaction
* 📦 **Volume snapshots** - tar stream with owners/ACLs/xattrs, dedupe‑friendly ordering & mtimes
* 🏷️ **Mandatory `backup_id`** - every run tags snapshots with `{ unit, backup_id, type, timestamp }`
* 🧰 **Per‑unit Kopia policies** - retention set on `recipes/UNIT` and `volumes/UNIT`
* 🔐 **Client-side encryption** - AES-256 via Kopia, cloud provider sees only encrypted blobs
* ☁️ **Multi-cloud support** - S3, B2, Azure, GCS, or local filesystem
* 🧪 **Dry‑run mode** - full simulation, no changes, test before real backup
* 🐧 **systemd‑friendly** - daemon with sd_notify/watchdog/locking + sample service/timer units
* ⚙️ **Parallel workers = auto** - tuned by RAM/CPU; no artificial `task_timeout`
* ⏱️ **Fast recovery** - from server crash to running services in ~15 minutes

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

* Works on **completely different servers** (new hardware, different provider, blank Ubuntu install)
* Lists restore points grouped strictly by **(unit, backup_id)**
* Restores recipe files (`docker-compose.yml` + configs) to working directory
* Generates **safe volume restore scripts** (stop containers → safety backup → stream restore → restart)
* Uses modern **`docker compose up -d`** (no legacy fallback needed)
* Warns about redacted secrets in `*_inspect.json` (restore manually if needed)

**From crashed server to running stack: ~15 minutes!**

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
- ✅ Decrypt with your DR password: `openssl enc -aes-256-cbc -d -in bundle.tar.gz.enc -out bundle.tar.gz`

**3:10 AM - Deploy new server:**
- ✅ Spin up fresh Ubuntu/Debian instance (any provider!)
- ✅ Install Kopi-Docka: `pipx install git+https://github.com/TZERO78/kopi-docka.git`

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
# 5. Executes restoration
```

**3:30 AM - Back online:**
```bash
cd restored-stack/
docker compose up -d
# Services starting...
# Health checks passing...
# ✅ Production restored!
```

**Total downtime: 30 minutes instead of 8+ hours of manual work!**

### Creating & Managing DR Bundles

**Manual creation:**
```bash
kopi-docka disaster-recovery
# Creates encrypted bundle in configured location
```

**Automatic updates (recommended):**
```ini
[backup]
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
```

Then every backup run updates the bundle automatically!

**Storage recommendations:**
- 📱 **Phone/Tablet** - encrypted, always with you
- 💾 **USB stick** - in physical safe/vault
- ☁️ **Different cloud** - not the same as your backup repo!
- 🏠 **Off-site location** - friend's house, office, etc.

**Never store DR bundle on the same server as your backups!**

### Security Model

**Encryption layers:**
1. **Kopia repository** - AES-256-GCM encrypted at rest
2. **DR Bundle** - AES-256-CBC encrypted with PBKDF2
3. **Cloud storage** - provider's encryption (bonus layer)

**Access required:**
- DR Bundle password (only you know it)
- Cloud provider credentials (in bundle, encrypted)

**Even if attacker gets:**
- ❌ Your cloud bucket - everything encrypted
- ❌ Your DR bundle - needs password to decrypt
- ❌ Both - still needs bundle password

**You're protected!** 🛡️

---

## Requirements

- Linux (Debian/Ubuntu recommended)
- Docker Engine & CLI
- Kopia CLI
- Python 3.10+
- `tar` (usually pre-installed)

**Quick check:**
```bash
docker --version
kopia --version
python3 --version
```

---

## Installation

### Option 1: pipx (recommended)
```bash
pipx install git+https://github.com/TZERO78/kopi-docka.git
```

### Option 2: From source
```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e .
```

### Verify installation
```bash
kopi-docka --version
kopi-docka check
```

If dependencies are missing:
```bash
sudo kopi-docka install-deps
```

---

## Quickstart

```bash
# 1. Check system
kopi-docka check

# 2. Create config (opens editor)
kopi-docka new-config

# 3. Edit at least these settings:
#    - repository_path: where to store backups
#    - password: CHANGE from default 'kopi-docka'!

# 4. Initialize repository
kopi-docka init

# 5. Change default password immediately!
kopi-docka change-password

# 6. Check connection
kopi-docka repo-status

# 7. Discover your Docker containers
kopi-docka list --units

# 8. Test run (no changes made)
kopi-docka dry-run

# 9. Real backup
kopi-docka backup

# 10. Create Disaster Recovery Bundle (IMPORTANT!)
kopi-docka disaster-recovery
# Store the bundle somewhere SAFE (USB, phone, vault)
# This is your insurance policy!

# 11. Enable automatic backups (optional)
sudo kopi-docka write-units
sudo systemctl enable --now kopi-docka.timer

# 12. Test restore (dry run)
kopi-docka restore
```

**⚠️ Critical: Store your DR bundle off-site!** Without it, you'd need to manually remember all connection details in an emergency.

---

## Configuration

Config file locations (first found wins):
- `/etc/kopi-docka.conf` (system-wide)
- `~/.config/kopi-docka/config.conf` (user)

**Minimal example:**
```ini
[kopia]
repository_path = /backup/kopia-repository
password = your-secure-password-here
profile = kopi-docka
compression = zstd

[backup]
parallel_workers = auto
stop_timeout = 30
start_timeout = 60

[retention]
daily = 7
weekly = 4
monthly = 12
yearly = 5
```

**Important settings:**

| Setting | Description | Default |
|---------|-------------|---------|
| `repository_path` | Where backups are stored | `/backup/kopia-repository` |
| `password` | Repository password | `kopi-docka` ⚠️ |
| `parallel_workers` | Backup threads | `auto` (based on RAM/CPU) |
| `stop_timeout` | Seconds to wait for graceful stop | `30` |
| `retention.daily` | Keep N daily backups | `7` |

---

## Password Management

### Default Setup (Simple)
Password stored directly in config file:
```ini
[kopia]
password = my-secure-password
```

### External File (More Secure)
```bash
# Create password file
echo "my-secure-password" | sudo tee /etc/.kopia-password
sudo chmod 600 /etc/.kopia-password

# Update config
[kopia]
password_file = /etc/.kopia-password
password =
```

### Change Password Safely
```bash
kopi-docka change-password
```
This updates **both** the Kopia repository and your config.

⚠️ **IMPORTANT:** After first `kopi-docka init`, change the default password immediately!
```bash
kopi-docka change-password
```

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

### Disaster Recovery Workflows

**Create DR Bundle (Manual)**
```bash
# Create bundle now
kopi-docka disaster-recovery

# Bundle created at configured location
# Copy to safe storage!
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
kopi-docka backup --update-recovery
```

**Use DR Bundle in Emergency**
```bash
# On NEW server (blank install):

# 1. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in kopi-docka-recovery-*.tar.gz.enc \
  -out recovered.tar.gz

# 2. Extract
tar -xzf recovered.tar.gz
cd kopi-docka-recovery-*/

# 3. Auto-reconnect to repository
sudo ./recover.sh
# Guides you through reconnection

# 4. Restore your stacks
kopi-docka restore
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

**Example output:**
```
📋 Available restore points:

1. 📦 webapp  (2025-01-31 23:59:59)  💾 Volumes: 3
2. 📦 database  (2025-01-31 23:59:59)  💾 Volumes: 2

🎯 Select restore point: 1

✅ Selected: webapp from 2025-01-31 23:59:59
📂 Restore directory: /tmp/kopia-docka-restore-webapp-xyz/

1️⃣ Restoring recipes...
   ✅ Recipe files restored to: /tmp/.../recipes/
   
2️⃣ Volume restoration:
   Generated scripts for safe restore:
   /tmp/.../restore-volume-data.sh
   /tmp/.../restore-volume-config.sh

3️⃣ Service restart:
   cd /tmp/.../recipes/
   docker compose up -d

✅ Restoration guide complete!
```

### Advanced Scenarios

**Backup with Bundle Update**
```bash
kopi-docka backup --update-recovery
```

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
| `install-deps` | Auto-install missing system dependencies |
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
| `estimate-size` | Calculate estimated backup size for all units |
| `backup` | Run full cold backup for all units |
| `backup --unit NAME` | Backup specific unit(s) only |
| `backup --update-recovery` | Create/update disaster recovery bundle |
| `restore` | Interactive restore wizard |

### Service & Automation
| Command | Description |
|---------|-------------|
| `daemon` | Run systemd-friendly daemon (for manual testing) |
| `write-units` | Generate systemd service/timer unit files |

---

## Troubleshooting

### 🚨 Lost everything? (Server died, configs gone)

**You have a DR Bundle? You're saved!**

```bash
# 1. Get DR bundle from safe storage (USB/phone/vault)
# 2. Deploy new server (any Linux)
# 3. Install Kopi-Docka
pipx install git+https://github.com/TZERO78/kopi-docka.git

# 4. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in your-bundle.tar.gz.enc \
  -out recovered.tar.gz

# 5. Extract and reconnect
tar -xzf recovered.tar.gz
cd kopi-docka-recovery-*/
sudo ./recover.sh

# 6. Restore
kopi-docka restore

# Done! 🎉
```

**No DR Bundle?** You'll need to manually:
- Remember repository location (S3 bucket, path, etc.)
- Find repository password
- Reconnect manually with `kopi-docka init`

**Prevention:** Always create and store DR bundles!

---

### ❌ "invalid repository password" during init

**Cause:** Repository already exists with different password.

**Solution A: Use existing repository (RECOMMENDED)**
```bash
# 1. Find old password (check backup of config)
# 2. Update config with correct password
# 3. Run init again
kopi-docka init
```

**Solution B: Start fresh (⚠️ DELETES EXISTING BACKUPS!)**
```bash
# Backup old repo first!
sudo mv /backup/kopia-repository /backup/kopia-repository.OLD

# Create new repo
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
# Then logout and login again

# Or run with sudo
sudo kopi-docka list --units
```

### 🔍 "Not connected" vs. "Connected: ✓"

**Check your profile config:**
```bash
kopi-docka repo-which-config
```

Different users have different Kopia profiles!
- Root: `/root/.config/kopia/...`
- User: `/home/user/.config/kopia/...`

### 📁 Permission Issues

Ensure backup paths are writable:
```bash
sudo mkdir -p /backup/kopia-repository
sudo chown $USER:$USER /backup/kopia-repository
```

---

## Systemd Integration

### Setup Timer (Daily at 02:00)
```bash
# Write example units
sudo kopi-docka write-units

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable --now kopi-docka.timer

# Check status
systemctl status kopi-docka.timer
systemctl status kopi-docka.service

# View logs
journalctl -u kopi-docka -f
```

### Custom Schedule
Edit `/etc/systemd/system/kopi-docka.timer`:
```ini
[Timer]
OnCalendar=*-*-* 03:00:00  # Daily at 03:00
Persistent=true
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart kopi-docka.timer
```

---

## Storage Backends

Kopi-Docka supports all Kopia backends:

### Local Filesystem
```ini
repository_path = /backup/kopia-repository
```

### AWS S3
```ini
repository_path = s3://my-bucket/kopia
```
Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in environment.

### Backblaze B2
```ini
repository_path = b2://my-bucket/kopia
```

### Azure Blob
```ini
repository_path = azure://container/kopia
```

### Google Cloud Storage
```ini
repository_path = gs://my-bucket/kopia
```

---

## Development

### Setup Dev Environment
```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e ".[dev]"
```

### Code Style
```bash
# Format code
make format

# Check style
make check-style

# Run tests
make test
```

### Project Structure
```
kopi_docka/
├── helpers/        # Config, logging, system utils
├── cores/          # Core business logic
├── commands/       # CLI command modules
└── templates/      # Config templates
```

---

## Credits & Acknowledgments

**Author:** Markus F. (TZERO78)

### Dependencies

**Core Components:**
- **[Docker](https://www.docker.com/)** - Container lifecycle management (external, unmodified)
- **[Kopia](https://kopia.io/)** - Backup backend with encryption, deduplication & multi-cloud support (external, unmodified)

**Python Libraries:**
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [psutil](https://github.com/giampaolo/psutil) - System resource monitoring

> **Note:** Kopi-Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

### Inspiration

- [docker-volume-backup](https://github.com/offen/docker-volume-backup)
- Various Kopia integration projects
- Real-world disaster recovery requirements

### Contributors

Thanks to contributors, testers, and early adopters.

---

**Contribute:**
- Report bugs and suggest features
- Improve documentation
- Submit pull requests

---

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

**Report issues:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Markus F. (TZERO78)

---

## Support

- 📚 [Documentation](https://github.com/TZERO78/kopi-docka#readme)
- 🐛 [Bug Reports](https://github.com/TZERO78/kopi-docka/issues)
- 💬 [Discussions](https://github.com/TZERO78/kopi-docka/discussions)

**Love Kopi-Docka?** Give us a ⭐ on GitHub!
