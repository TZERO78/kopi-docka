# Kopi‑Docka

**Robust cold backups for Docker environments using Kopia**

[![Build](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml/badge.svg)](https://github.com/TZERO78/kopi-docka/actions/workflows/python-app.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-lightgrey)
![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)
![License](https://img.shields.io/badge/license-MIT-green)

Kopi‑Docka performs **consistent, cold backups** of Docker stacks ("backup units"). It briefly stops containers, snapshots **recipes** (Compose + `docker inspect`, with secret redaction) and **volumes** into a Kopia repository, then restarts your services.

> **Note:** Kopi‑Docka intentionally **does not** create separate database dumps anymore. Volumes are the **single source of truth**.

---

## Why Kopi‑Docka?

Kopi‑Docka focuses on a single, reliable workflow: **1:1 restoration of Docker services** without mixing hot DB tooling. Use it when you want:

* **Consistency first:** Cold backups (Stop → Snapshot → Start).
* **Stack awareness:** Back up complete Compose stacks as one **backup unit**.
* **Exact restores:** Bring back the same config, volumes, and layout.
* **Cloud‑ready repos:** Use Kopia repositories on filesystem or cloud (S3, B2, Azure, GCS†).
* **Simple ops:** Clear CLI, dry‑run, restore wizard, and systemd integration.
* **Deterministic archives:** Optimized tar streams for dedupe (`--numeric-owner --xattrs --acls --mtime=@0 --sort=name`).

† subject to Kopia support and your configuration.

If you need enterprise‑grade orchestration, consider Kubernetes backup tools like Velero, or general purpose solutions (Restic + scripting, Duplicati, commercial tools). Kopi‑Docka shines on single Docker hosts and small fleets.

---

## Key Features

* 🔒 **Cold, consistent backups** (short downtime per unit)
* 🧩 **Backup Units** (Compose stacks or standalone containers)
* 🧾 **Recipes**: `docker-compose.yml` (if present) + `docker inspect` with secret redaction
* 📦 **Volumes**: tar stream with owners/ACLs/xattrs, dedupe‑friendly ordering & mtimes
* 🏷️ **Mandatory `backup_id`**: every run tags snapshots with `{ unit, backup_id, type, timestamp }`
* 🧰 **Per‑unit Kopia policies**: retention set on `recipes/UNIT` and `volumes/UNIT`
* 🧪 **Dry‑run mode**: full simulation, no changes
* 🛟 **Disaster Recovery Bundle**: encrypted package with repo info, password, script, status
* 🐧 **systemd‑friendly**: daemon with sd_notify/watchdog/locking + sample service/timer/oneshot units
* ⚙️ **Parallel workers = auto**: tuned by RAM/CPU; no artificial `task_timeout`

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

### 3) Restore (Wizard)

* Lists restore points grouped strictly by **(unit, backup_id)**.
* Restores recipe files to a working directory.
* Generates **safe volume restore scripts** (stop users, safety tar of current volume, stream restore, restart).
* Documents **modern `docker compose up -d`** only (no legacy fallback).
* Warns about redacted secrets in `*_inspect.json`.

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

# 10. Restore if needed
kopi-docka restore
```

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

### List Backup Units
```bash
kopi-docka list --units
```

### Dry Run (Test Mode)
```bash
kopi-docka dry-run
kopi-docka dry-run --unit my-stack
```

### Backup Everything
```bash
kopi-docka backup
```

### Backup Specific Units
```bash
kopi-docka backup --unit webapp --unit database
```

### Backup with Recovery Bundle
```bash
kopi-docka backup --update-recovery
```

### Restore Wizard
```bash
kopi-docka restore
```
Guides you through:
1. Selecting a restore point
2. Restoring config files
3. Creating safe volume restore scripts
4. Restarting services

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

## Credits & Thanks

**Created by:** Markus F. (TZERO78)

**Built with:**
- [Kopia](https://kopia.io/) – Fast, secure backup/restore
- [Docker](https://www.docker.com/) – Container platform
- [Typer](https://typer.tiangolo.com/) – CLI framework
- [psutil](https://github.com/giampaolo/psutil) – System utilities

**Special thanks to:**
- The Kopia team for building an amazing backup tool
- The Docker community
- All contributors and testers
- AI assistants for code reviews and documentation

**Inspired by:**
- [docker-volume-backup](https://github.com/offen/docker-volume-backup)
- Various Kopia integration projects
- The need for simpler Docker backup solutions

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