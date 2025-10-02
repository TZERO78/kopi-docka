# Kopi‑Docka

**Robust cold backups for Docker environments using Kopia**

[![Build](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml/badge.svg)](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml)
![Version](https://img.shields.io/badge/version-2.0.0-blue)
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
* **Encrypted cloud storage:** AES-256 client-side encryption via Kopia (S3, B2, Azure, GCS)
* **Zero manual work:** Restore wizard handles everything - no config hunting, no guesswork
* **Complete autonomy:** No vendor lock-in, no subscription services, full control

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

1. Get DR bundle from safe storage (USB/phone/cloud)
2. Deploy new server (any Linux distro)
3. Install Kopi-Docka: `pipx install git+https://github.com/TZERO78/kopi-docka.git`
4. Decrypt bundle & run `./recover.sh` - auto-reconnects to your repository
5. `kopi-docka restore` - interactive wizard restores everything
6. `docker compose up -d` in restored directory - services online!

**Total time: ~15 minutes from bare metal to production!**

---

## Requirements

- **Linux** (Debian/Ubuntu recommended, also works on Arch/Fedora)
- **Docker Engine & CLI** (20.10+)
- **Kopia CLI** (0.10+)
- **Python 3.10+**
- **tar** (usually pre-installed)

**Quick check:**
```bash
docker --version
kopia --version
python3 --version
```

---

## Installation

### Option 1: pipx (Recommended)
```bash
# Install pipx if not present
sudo apt install pipx
pipx ensurepath

# Install Kopi-Docka
pipx install git+https://github.com/TZERO78/kopi-docka.git
```

### Option 2: pip (System-wide)
```bash
pip install git+https://github.com/TZERO78/kopi-docka.git
```

### Option 3: Development (From Source)
```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e ".[dev]"
```

### Verify Installation
```bash
kopi-docka --version
# Output: Kopi-Docka version 2.0.0

kopi-docka check
# Shows dependency status
```

### Install Missing Dependencies
```bash
sudo kopi-docka install-deps
```

---

## Quickstart (5 Minutes to First Backup)

```bash
# 1. Check system
kopi-docka check

# 2. Create config (opens in editor)
kopi-docka new-config
# Edit these settings:
#   - repository_path: where backups go (local or cloud)
#   - password: CHANGE from default 'kopi-docka'!

# 3. Initialize repository
kopi-docka init

# 4. Change default password IMMEDIATELY
kopi-docka change-password

# 5. Verify connection
kopi-docka repo-status

# 6. Discover your containers
kopi-docka list --units

# 7. Test run (simulates backup, no changes)
kopi-docka dry-run

# 8. Real backup
kopi-docka backup

# 9. Create DR bundle (CRITICAL - your insurance!)
kopi-docka disaster-recovery
# Store bundle OFF-SITE: USB, phone, vault, friend's house

# 10. (Optional) Enable automatic backups
sudo kopi-docka write-units
sudo systemctl enable --now kopi-docka.timer
```

**⚠️ CRITICAL:** Store your DR bundle somewhere safe! Without it, disaster recovery requires manual reconnection.

---

## Configuration

Config file locations (first found wins):
- `/etc/kopi-docka.conf` (system-wide, recommended for servers)
- `~/.config/kopi-docka/config.conf` (user-specific)

### Minimal Example

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

### Cloud Storage Examples

```ini
# AWS S3
repository_path = s3://my-backup-bucket/kopia

# Backblaze B2
repository_path = b2://my-b2-bucket/kopia

# Azure Blob
repository_path = azure://container/kopia

# Google Cloud Storage
repository_path = gs://my-gcs-bucket/kopia
```

Set cloud credentials via environment variables (see Kopia docs).

### Important Settings

| Setting | Description | Default | Notes |
|---------|-------------|---------|-------|
| `repository_path` | Where backups are stored | `/backup/kopia-repository` | Local or cloud URL |
| `password` | Repository password | `kopi-docka` | ⚠️ CHANGE IMMEDIATELY |
| `parallel_workers` | Backup threads | `auto` | Based on RAM/CPU |
| `stop_timeout` | Graceful stop wait (seconds) | `30` | Per container |
| `start_timeout` | Startup wait (seconds) | `60` | Per container |
| `exclude_patterns` | tar exclude patterns | _(empty)_ | Comma-separated |
| `retention.daily` | Keep N daily backups | `7` | Kopia policy |
| `retention.weekly` | Keep N weekly backups | `4` | Kopia policy |
| `retention.monthly` | Keep N monthly backups | `12` | Kopia policy |
| `retention.yearly` | Keep N yearly backups | `5` | Kopia policy |

### Password Management

**Option 1: In config file (simple)**
```ini
[kopia]
password = my-secure-password
```

**Option 2: External file (more secure)**
```bash
# Create password file
echo "my-secure-password" | sudo tee /etc/.kopia-password
sudo chmod 600 /etc/.kopia-password

# Update config
[kopia]
password_file = /etc/.kopia-password
password =
```

**Change password safely:**
```bash
kopi-docka change-password
# Updates BOTH repository and config
```

---

## CLI Commands Reference

### Configuration Management
```bash
kopi-docka show-config           # Display current config (secrets masked)
kopi-docka new-config            # Create new config from template
kopi-docka edit-config           # Open config in $EDITOR
kopi-docka reset-config          # ⚠️ Reset config (generates new password)
kopi-docka change-password       # Safely change repo password
```

### System & Dependencies
```bash
kopi-docka check                 # Verify dependencies
kopi-docka check --verbose       # Show detailed system info
kopi-docka install-deps          # Auto-install missing deps (needs sudo)
kopi-docka show-deps             # Show manual installation guide
kopi-docka version               # Show version
```

### Repository Management
```bash
kopi-docka init                  # Initialize/connect to repository
kopi-docka repo-status           # Show repository status
kopi-docka repo-which-config     # Show active Kopia config file
kopi-docka repo-set-default      # Set as default Kopia profile
kopi-docka repo-init-path PATH   # Create repo at specific path
kopi-docka repo-maintenance      # Run cleanup/optimization
kopi-docka repo-selftest         # Create test repository
```

### Backup & Restore
```bash
kopi-docka list --units          # Show discovered backup units
kopi-docka list --snapshots      # Show all snapshots in repo

kopi-docka dry-run               # Simulate backup (no changes)
kopi-docka dry-run --unit NAME   # Simulate specific unit
kopi-docka dry-run-units         # Show detailed unit analysis
kopi-docka estimate-size         # Calculate backup size estimate

kopi-docka backup                # Backup all units
kopi-docka backup --unit NAME    # Backup specific unit(s)
kopi-docka backup --dry-run      # Test mode
kopi-docka backup --update-recovery  # Update DR bundle

kopi-docka restore               # Interactive restore wizard
kopi-docka disaster-recovery     # Create DR bundle manually
```

### Service & Automation
```bash
kopi-docka daemon                # Run as systemd service
kopi-docka write-units           # Generate systemd files
```

---

## Usage Examples

### Basic Workflow

```bash
# List what will be backed up
kopi-docka list --units

# Test backup (no changes)
kopi-docka dry-run

# Real backup
kopi-docka backup

# Check what's in repository
kopi-docka list --snapshots

# Restore interactively
kopi-docka restore
```

### Selective Backups

```bash
# Backup only specific units
kopi-docka backup --unit webapp --unit database

# Dry-run one unit
kopi-docka dry-run --unit nextcloud
```

### Disaster Recovery Bundle

**Create manually:**
```bash
kopi-docka disaster-recovery
# Bundle saved to configured path
# Copy to USB/phone/vault NOW!
```

**Enable automatic updates:**
```ini
# In kopi-docka.conf:
[backup]
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
```

```bash
# Every backup now updates bundle
kopi-docka backup
```

**Use in emergency (on NEW server):**
```bash
# 1. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in kopi-docka-recovery-*.tar.gz.enc \
  -out recovered.tar.gz

# 2. Extract
tar -xzf recovered.tar.gz
cd kopi-docka-recovery-*/

# 3. Auto-reconnect
sudo ./recover.sh

# 4. Restore everything
kopi-docka restore
```

### Systemd Integration

```bash
# Generate service files
sudo kopi-docka write-units

# Reload systemd
sudo systemctl daemon-reload

# Enable daily backups at 02:00
sudo systemctl enable --now kopi-docka.timer

# Check status
systemctl status kopi-docka.timer
systemctl status kopi-docka.service

# View logs
journalctl -u kopi-docka -f
```

**Custom schedule (edit timer):**
```bash
sudo systemctl edit kopi-docka.timer
```

```ini
[Timer]
OnCalendar=*-*-* 03:00:00  # Daily at 3 AM
Persistent=true
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

**Prevention:** Always create DR bundles!

### ❌ "invalid repository password"

**Cause:** Repository exists with different password.

**Solution A (recommended):**
```bash
# Find old password
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
# Check Docker
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

### 📁 Permission Issues

```bash
# Ensure backup path is writable
sudo mkdir -p /backup/kopia-repository
sudo chown $USER:$USER /backup/kopia-repository
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
│   │   ├── disaster_recovery.py # DR bundle creation
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

### Test Status

**Current Coverage:**
- ✅ **Main CLI:** 10/10 tests passing
- ✅ **Test Infrastructure:** Complete (fixtures, mocks)
- ⏳ **Command Tests:** 6/37 tests (in progress)
- ⏳ **Core Module Tests:** 0/9 modules
- ⏳ **Integration Tests:** 0/3 workflows

**Run tests:**
```bash
# Fast unit tests only
make test-unit

# Full test suite
make test

# With coverage report
make test-coverage
# Opens htmlcov/index.html
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

### Core Dependencies

- **[Docker](https://www.docker.com/)** - Container lifecycle management
- **[Kopia](https://kopia.io/)** - Backup engine with encryption & deduplication
- **[Typer](https://typer.tiangolo.com/)** - CLI framework
- **[psutil](https://github.com/giampaolo/psutil)** - System resource monitoring

> **Note:** Kopi‑Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

### Inspiration

- [docker-volume-backup](https://github.com/offen/docker-volume-backup)
- Various Kopia integration projects
- Real-world disaster recovery requirements

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Markus F. (TZERO78)

---

## Support & Community

- 📚 **Documentation:** [GitHub README](https://github.com/TZERO78/kopi-docka#readme)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)

**Love Kopi‑Docka?** Give us a ⭐ on GitHub!

---

## Für deutsche Nutzer

### Schnellstart auf Deutsch

```bash
# 1. System prüfen
kopi-docka check

# 2. Konfiguration erstellen
kopi-docka new-config
# Wichtig: repository_path und password ändern!

# 3. Repository initialisieren
kopi-docka init

# 4. Passwort SOFORT ändern
kopi-docka change-password

# 5. Container anzeigen
kopi-docka list --units

# 6. Testlauf (keine Änderungen)
kopi-docka dry-run

# 7. Echtes Backup
kopi-docka backup

# 8. Notfall-Bundle erstellen (WICHTIG!)
kopi-docka disaster-recovery
# Speichere das Bundle EXTERN: USB-Stick, Handy, Safe!
```

### Wichtige Konzepte

**Backup Unit:** Eine logische Einheit zum Sichern
- Docker Compose Stack = 1 Unit (z.B. "nextcloud")
- Einzelner Container = 1 Unit (z.B. "nginx")

**Cold Backup:** Container werden kurz gestoppt
- ✅ Garantiert konsistente Daten
- ⏱️ Kurze Ausfallzeit pro Unit
- 🔄 Automatischer Neustart nach Backup

**DR Bundle (Disaster Recovery):** Notfall-Paket
- 🔐 Verschlüsselt mit AES-256
- 📋 Enthält alle Repository-Infos
- 🚀 Ermöglicht schnelle Wiederherstellung (15 Min)
- ⚠️ Unbedingt EXTERN speichern!

### Häufige Fragen

**F: Werden Datenbanken automatisch gesichert?**  
A: Ja! Volumes enthalten die DB-Daten. Cold Backup = konsistent.

**F: Wie lange dauert ein Backup?**  
A: Abhängig von Datenmenge. Beispiel: 10GB = ~2-5 Minuten.

**F: Kann ich auf anderem Server wiederherstellen?**  
A: Ja! Das ist der Hauptvorteil. DR Bundle + neuer Server = funktioniert.

**F: Was kostet Cloud-Speicher?**  
A: Beispiel Backblaze B2: ~0.005€/GB/Monat. 100GB = ~0.50€/Monat.

**F: Sind die Backups verschlüsselt?**  
A: Ja, AES-256 bereits vor dem Upload. Cloud-Anbieter sieht nur verschlüsselte Daten.

### Support auf Deutsch

Bei Fragen gerne:
- 🐛 **Issues auf GitHub** (English bevorzugt, Deutsch okay)
- 💬 **Discussions** für allgemeine Fragen

---

**Version:** 2.0.0  
**Last Updated:** Octotber 2025