# Kopi-Docka

[![PyPI version](https://badge.fury.io/py/kopi-docka.svg)](https://pypi.org/project/kopi-docka/)
[![Python](https://img.shields.io/pypi/pyversions/kopi-docka.svg)](https://pypi.org/project/kopi-docka/)
[![License](https://img.shields.io/github/license/TZERO78/kopi-docka.svg)](https://github.com/TZERO78/kopi-docka/blob/main/LICENSE)
[![Build](https://github.com/TZERO78/kopi-docka/actions/workflows/publish.yml/badge.svg)](https://github.com/TZERO78/kopi-docka/actions)

Cold backup solution for Docker environments using Kopia.

Kopi-Docka performs consistent backups of Docker containers by stopping them, creating snapshots of docker-compose files and volumes, then restarting services. Backups are encrypted and stored in Kopia repositories with configurable retention policies.

---

## Restore Process

### Interactive Restore Wizard

Start the restore wizard:

```bash
kopi-docka restore
```

The wizard guides you through these steps:

**1. Select Backup Session**

Lists available backup sessions grouped by time (5-minute tolerance):

```
📅 Available Backup Sessions:

1. 2025-01-15 02:00:45
   Units: mysql-stack, nginx-stack (2 units, 8 volumes)

2. 2025-01-14 02:00:12
   Units: mysql-stack, nginx-stack, redis (3 units, 10 volumes)

Select session (number or 'q' to quit): _
```

**2. Select Backup Unit**

If multiple units in session, choose which to restore:

```
📦 Units in this backup session:

1. mysql-stack (3 volumes) - 02:00:45
2. nginx-stack (2 volumes) - 02:00:48

Select unit to restore (number or 'q' to quit): _
```

**3. Confirm Restore**

Review what will be restored:

```
✅ Selected: mysql-stack from 2025-01-15 02:00:45

📝 This will guide you through restoring:
  - Recipe/configuration files
  - 3 volumes

Proceed with restore? (yes/no/q): _
```

**4. Recipe Restoration**

Automatically restores to temporary directory:

```
📂 Restoring recipes...
   ✓ docker-compose.yml
   ✓ mysql-db_inspect.json
   ✓ mysql-web_inspect.json

📁 Restored to: /tmp/kopia-restore-20250115-020045/recipes/mysql-stack/
```

**5. Volume Restoration**

For each volume, choose immediate or manual restore:

```
📦 Volume Restoration:

📁 Volume: mysql-data
📸 Snapshot: a3f5d892...

⚠️  Restore 'mysql-data' NOW? (yes/no/q):
```

**If you choose 'yes':**
- Stops affected containers
- Creates safety backup in `/tmp`
- Restores volume directly
- Restarts containers

**If you choose 'no':**
- Shows manual restore instructions
- Continues to next volume

**6. Service Restart**

After restore completes, start services:

```
cd /tmp/kopia-restore-20250115-020045/recipes/mysql-stack/
docker compose up -d
```

### Restore Options

**Restore specific snapshot:**

```bash
# List all snapshots
kopi-docka list --snapshots

# Restore uses interactive wizard
kopi-docka restore
```

**Restore to different server:**

```bash
# 1. Install Kopi-Docka on new server
pipx install kopi-docka

# 2. Connect to existing repository
kopi-docka init
# Configure same repository_path and password

# 3. Restore
kopi-docka restore
```

**Manual volume restore:**

If you declined automatic restore or need to restore later:

```bash
# Stop containers using the volume
docker ps -q --filter 'volume=mysql-data' | xargs docker stop

# Create safety backup
docker run --rm -v mysql-data:/source -v /tmp:/backup \
  alpine tar czf /backup/mysql-data-backup.tar.gz -C /source .

# Restore from Kopia
kopia snapshot restore SNAPSHOT_ID /target/path

# Or use tar stream
kopia snapshot restore SNAPSHOT_ID --mode tar | \
  docker run --rm -i -v mysql-data:/target alpine \
  sh -c "rm -rf /target/* /target/.[!.]* 2>/dev/null || true; \
  tar -xpf - --numeric-owner --xattrs --acls -C /target"

# Restart containers
docker start CONTAINER_ID
```

### Restore Safety Features

- **Automatic safety backups** - Creates `/tmp/volume-backup-*.tar.gz` before overwriting
- **Quit anytime** - Press 'q' at any prompt to cancel
- **Manual instructions** - Shows exact commands if you decline automatic restore
- **Secret redaction warnings** - Alerts if restored files contain `***REDACTED***`
- **Container management** - Stops/starts containers automatically during volume restore

---

## Features

- Cold backups for data consistency
- Docker Compose stack awareness
- AES-256 encryption via Kopia
- Multiple storage backends (S3, B2, Azure, GCS, SFTP, local)
- Disaster recovery bundles
- Systemd timer integration with journald logging
- Configurable retention policies
- Interactive restore wizard
- Automatic dependency installation
- Full Kopia CLI compatibility (use Kopia directly with Kopi-Docka's repository)

---

## Installation

```bash
pipx install kopi-docka

# Install system dependencies (Docker, Kopia, tar, openssl)
sudo kopi-docka install-deps
```

Alternative with pip:

```bash
pip install kopi-docka
sudo kopi-docka install-deps
```

### Verify Installation

```bash
kopi-docka --version
kopi-docka check
```

---

## Requirements

- Linux (Debian/Ubuntu recommended, also Arch/Fedora)
- Docker Engine 20.10+
- Kopia CLI 0.10+ (tested with 0.10-0.18)
- Python 3.10+
- tar, openssl (usually pre-installed)

Verify versions:

```bash
docker --version
kopia --version
python3 --version
```

### Automatic Dependency Installation

```bash
kopi-docka check                    # Show missing dependencies
sudo kopi-docka install-deps        # Install automatically
sudo kopi-docka install-deps --dry-run  # Preview changes
```

Supported distributions: Debian/Ubuntu (apt), RHEL/CentOS/Fedora (yum/dnf), Arch Linux (pacman + AUR).

---

## Quick Start

```bash
# 1. Install and verify
pipx install kopi-docka
sudo kopi-docka install-deps

# 2. Create configuration
kopi-docka new-config
# Edit ~/.config/kopi-docka/config.conf:
#   - repository_path: backup destination
#   - password: change default password

# 3. Initialize repository
kopi-docka init
kopi-docka change-password

# 4. Verify setup
kopi-docka list --units
kopi-docka dry-run

# 5. Create backup
kopi-docka backup

# 6. Create disaster recovery bundle
kopi-docka disaster-recovery
```

---

## Configuration

Config file locations (by precedence):
- `/etc/kopi-docka.conf` (system-wide)
- `~/.config/kopi-docka/config.conf` (user-specific)

Kopi-Docka uses a dedicated Kopia profile (`~/.config/kopia/repository-kopi-docka.config`) and does not interfere with existing Kopia configurations.

Example configuration:

```ini
[kopia]
repository_path = b2://bucket-name/kopia
password = secure-password
compression = zstd
encryption = AES256-GCM-HMAC-SHA256

[backup]
parallel_workers = 4
stop_timeout = 30

[retention]
daily = 7
weekly = 4
monthly = 12
yearly = 5

[logging]
level = INFO              # DEBUG, INFO, WARNING, ERROR
file = /var/log/kopi-docka.log  # Optional file logging
max_size_mb = 100        # Log rotation size
backup_count = 5         # Keep 5 rotated logs
```

### Storage Backends

**Backblaze B2:**
```bash
export B2_APPLICATION_KEY_ID="key-id"
export B2_APPLICATION_KEY="key-secret"
```
```ini
repository_path = b2://bucket-name/kopia
```

**AWS S3:**
```bash
export AWS_ACCESS_KEY_ID="key-id"
export AWS_SECRET_ACCESS_KEY="key-secret"
```
```ini
repository_path = s3://bucket-name/kopia
```

**Local filesystem:**
```ini
repository_path = /backup/kopia-repository
```

Additional backends: Azure Blob Storage, Google Cloud Storage, SFTP.

---

## Automated Backups

### Systemd Timer Setup

```bash
sudo kopi-docka write-units
sudo systemctl daemon-reload
sudo systemctl enable --now kopi-docka.timer
```

### Check Status

```bash
systemctl list-timers kopi-docka.timer
systemctl status kopi-docka.timer
journalctl -u kopi-docka -f
```

### Journald Integration

When running under systemd, Kopi-Docka automatically outputs structured logs to the systemd journal with searchable fields:

```bash
# View all Kopi-Docka logs
journalctl -u kopi-docka

# Follow logs in real-time
journalctl -u kopi-docka -f

# Filter by specific backup unit
journalctl -u kopi-docka UNIT=my-stack

# Show only errors
journalctl -u kopi-docka -p err

# Show logs from last backup run
journalctl -u kopi-docka --since "1 hour ago"

# Filter by operation
journalctl -u kopi-docka OPERATION=backup

# Show with metadata
journalctl -u kopi-docka -o json-pretty
```

**Structured fields available:**
- `UNIT` - Backup unit name
- `OPERATION` - backup, restore, etc.
- `DURATION` - Operation duration in seconds
- `STATUS` - SUCCESS, FAILED, PARTIAL
- `MODULE` - Python module name
- `LEVEL` - Log level

Enhanced journald support with `python3-systemd`:

```bash
sudo apt install python3-systemd  # Debian/Ubuntu
# or
sudo kopi-docka install-deps  # Installs automatically
```

### Custom Schedule

```bash
sudo systemctl edit kopi-docka.timer
```

```ini
[Timer]
OnCalendar=*-*-* 03:00:00  # Daily at 03:00
Persistent=true
```

---

## Disaster Recovery

Disaster recovery bundles contain repository connection info, encrypted credentials, configuration, and restore scripts.

### Create Bundle

```bash
kopi-docka disaster-recovery
```

Automatic bundle updates after each backup:

```ini
[backup]
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3
```

### Restore from Bundle

On a new server:

```bash
# 1. Install Kopi-Docka
pipx install kopi-docka

# 2. Decrypt bundle
openssl enc -aes-256-cbc -d -pbkdf2 \
  -in bundle.tar.gz.enc -out bundle.tar.gz

# 3. Extract and reconnect
tar -xzf bundle.tar.gz
cd kopi-docka-recovery-*/
sudo ./recover.sh

# 4. Restore data
kopi-docka restore

# 5. Start services
cd /tmp/kopia-restore-*/recipes/
docker compose up -d
```

---

## CLI Commands

### Backup & Restore
| Command | Description |
|---------|-------------|
| `list --units` | Show discovered backup units |
| `list --snapshots` | Show all backups in repository |
| `backup` | Create cold backup of selected units |
| `restore` | Interactive restore wizard (step-by-step) |
| `dry-run` | Simulate backup without changes |

### Repository
| Command | Description |
|---------|-------------|
| `init` | Initialize Kopia repository |
| `repo-status` | Check repository connection |
| `repo-maintenance` | Run Kopia maintenance |
| `change-password` | Change repository password |

### Configuration
| Command | Description |
|---------|-------------|
| `new-config` | Create config template |
| `show-config` | Display config (secrets masked) |
| `edit-config` | Open config in editor |
| `check` | Verify system dependencies |
| `install-deps` | Install missing dependencies |

### Disaster Recovery
| Command | Description |
|---------|-------------|
| `disaster-recovery` | Create encrypted DR bundle |

### Service
| Command | Description |
|---------|-------------|
| `write-units` | Generate systemd files |
| `daemon` | Run as systemd service |

---

## Kopia Profile Isolation

Kopi-Docka uses a separate Kopia profile and does not interfere with existing Kopia installations:

```bash
# Existing Kopia backups (default profile)
~/.config/kopia/repository.config
kopia snapshot create /home/user/documents

# Kopi-Docka (separate profile)
~/.config/kopia/repository-kopi-docka.config
kopi-docka backup
```

Both configurations operate independently with separate repositories, schedules, and retention policies.

---

## Direct Kopia Usage

Kopi-Docka is a wrapper around Kopia. You can use Kopia CLI directly with Kopi-Docka's repository by specifying the config file:

### Kopia Config File Location

```bash
# Kopi-Docka uses this config:
~/.config/kopia/repository-kopi-docka.config

# Your personal Kopia config (if any):
~/.config/kopia/repository.config
```

### Using Kopia with Kopi-Docka Repository

**Always specify the config file:**

```bash
# Set as alias for convenience
alias kopia-docka="kopia --config-file ~/.config/kopia/repository-kopi-docka.config"

# Or use full command
kopia --config-file ~/.config/kopia/repository-kopi-docka.config COMMAND
```

### Common Kopia Operations

**List snapshots:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config snapshot list
kopia --config-file ~/.config/kopia/repository-kopi-docka.config snapshot list --all
```

**Show snapshot details:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config snapshot show SNAPSHOT_ID
```

**Restore snapshot manually:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  snapshot restore SNAPSHOT_ID /restore/target/path
```

**Repository maintenance:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  maintenance run --full
```

**Check repository status:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config repository status
```

**Search snapshots by tag:**
```bash
# Find all backups for specific unit
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  snapshot list --tags=unit:mysql-stack

# Find all volume snapshots
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  snapshot list --tags=type:volume
```

**Mount repository as filesystem:**
```bash
mkdir /tmp/kopia-mount
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  mount all /tmp/kopia-mount
# Browse backups, then unmount:
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  unmount /tmp/kopia-mount
```

**Export snapshot to tar:**
```bash
kopia --config-file ~/.config/kopia/repository-kopi-docka.config \
  snapshot restore SNAPSHOT_ID --mode tar > backup.tar
```

### Important Notes

- **Always use `--config-file`** when working with Kopi-Docka's repository
- Without `--config-file`, Kopia uses your default config (different repository!)
- Kopi-Docka tags snapshots with: `unit`, `type` (recipe/volume), `backup_id`, `timestamp`
- You can create custom snapshots in the same repository if needed
- Kopia policies are set per-unit (e.g., `recipes/mysql-stack`)

---

## Troubleshooting

### Missing Dependencies

```bash
kopi-docka check
sudo kopi-docka install-deps
sudo kopi-docka install-deps --dry-run  # Preview only
```

After installation, logout and login for docker group membership to take effect.

### No Backup Units Found

Check Docker status and socket access:

```bash
docker ps
sudo usermod -aG docker $USER  # Logout/login required
```

### Invalid Repository Password

Repository exists with different password:

```bash
# Update config with correct password, then:
kopi-docka init
```

To reinitialize (deletes existing backups):

```bash
sudo mv /backup/kopia-repository /backup/kopia-repository.backup
kopi-docka init
```

### Permission Issues

```bash
sudo mkdir -p /backup/kopia-repository
sudo chown $USER:$USER /backup/kopia-repository
```

### Restore Issues

**No restore points found:**

```bash
# Verify repository connection
kopi-docka repo-status

# List snapshots manually
kopi-docka list --snapshots
```

**Volume restore fails:**

```bash
# Check Docker is running
docker ps

# Ensure volume exists
docker volume ls | grep VOLUME_NAME

# Check available disk space
df -h
```

**Redacted secrets in restored files:**

Files containing `***REDACTED***` need manual intervention. Check `*_inspect.json` files in restored recipes and update environment variables manually before starting containers.

---

## Development

### Setup

```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pip install -e ".[dev]"
```

### Tasks

```bash
make format       # Format code (Black)
make check-style  # Lint (flake8)
make test         # Run tests
make test-unit    # Unit tests only
make test-coverage # Coverage report
```

### Code Style

- Formatter: Black
- Linter: flake8
- Type hints: Encouraged
- Docstrings: Google style

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Run `make format` and `make test`
5. Submit a pull request

Report issues: [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)

---

## License

MIT License - see [LICENSE](LICENSE)

Copyright (c) 2025 Markus F. (TZERO78)

---

## Credits

- [Kopia](https://kopia.io/) - Backup engine with encryption and deduplication
- [Docker](https://www.docker.com/) - Container platform
- [Typer](https://typer.tiangolo.com/) - CLI framework

Kopi-Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

---

## Links

- [PyPI Package](https://pypi.org/project/kopi-docka/)
- [GitHub Repository](https://github.com/TZERO78/kopi-docka)
- [Issue Tracker](https://github.com/TZERO78/kopi-docka/issues)
- [Discussions](https://github.com/TZERO78/kopi-docka/discussions)