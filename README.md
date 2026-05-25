# Kopi-Docka

> **Cold Backup Tool for Docker Environments using Kopia**

Kopi-Docka is a Python-based backup wrapper for Docker containers and volumes. It uses Kopia for encryption and deduplication, with specific focus on Docker Compose stack awareness.

[![PyPI](https://img.shields.io/pypi/v/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![Python Version](https://img.shields.io/pypi/pyversions/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/kopi-docka)](https://pypi.org/project/kopi-docka/)

---

## What is Kopi-Docka?

**Kopi-Docka = Kopia + Docker + Backup**

A wrapper around [Kopia](https://kopia.io), designed for Docker environments:

- **📦 Stack-Aware** - Recognizes Docker Compose stacks and backs them up as logical units
- **🔐 Encrypted** - End-to-end encryption via Kopia (AES-256-GCM)
- **🌐 Multiple Storage Options** - Local, S3, B2, Azure, GCS, SFTP, Tailscale, Rclone
- **💾 Disaster Recovery** - Encrypted bundles with auto-reconnect scripts
- **🔧 Pre/Post Hooks** - Custom scripts (maintenance mode, notifications, etc.)
- **📊 Systemd Integration** - Daemon with sd_notify and watchdog support
- **🚀 Restore on New Hardware** - Recovery without original system
- **🛡️ Graceful Shutdown** - SafeExitManager ensures containers restart after Ctrl+C
- **🔔 Notifications** - Telegram, Discord, Email alerts via Apprise

**[See detailed features →](docs/FEATURES.md)**

---

## Quick Start

### Prerequisites

**Kopi-Docka expects a prepared system.** You need to install dependencies **before** installing Kopi-Docka:

**Required:**
- [Docker](https://docs.docker.com/engine/install/) (20.10+)
- [Kopia](https://kopia.io/docs/installation/) (0.13+)

**Quick check:**
```bash
docker --version
kopia --version
```

**Need automated setup?** Use [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten) for automated system preparation.

### Installation

```bash
# Recommended: pipx (isolated environment)
pipx install kopi-docka

# Make available for sudo (pipx installs to ~/.local/bin)
sudo ln -s ~/.local/bin/kopi-docka /usr/local/bin/kopi-docka

# Or: pip (system-wide)
pip install kopi-docka

# Verify all dependencies
kopi-docka doctor
```

**[Full installation guide →](docs/INSTALLATION.md)**

### Setup

```bash
# Interactive setup wizard
sudo kopi-docka setup
```

The wizard guides you through:
1. ✅ Dependency verification (Docker, Kopia)
2. ✅ Repository storage selection (Local, S3, B2, Azure, GCS, SFTP, Tailscale, Rclone)
3. ✅ Repository initialization
4. ✅ Connection test

**[Configuration guide →](docs/CONFIGURATION.md)**

### First Backup

```bash
# System health check
sudo kopi-docka doctor

# List backup units (containers/stacks)
sudo kopi-docka advanced snapshot list

# Test run (no changes)
sudo kopi-docka dry-run

# Full backup
sudo kopi-docka backup

# Create disaster recovery bundle (encrypted ZIP)
sudo kopi-docka disaster-recovery export ~/recovery.zip
# → Store bundle + passphrase off-site: USB/cloud/safe
```

**[Usage guide →](docs/USAGE.md)**

### Automatic Backups

```bash
# Generate systemd units
sudo kopi-docka advanced service write-units

# Enable daily backups (02:00 default)
sudo systemctl enable --now kopi-docka.timer

# Check status
sudo systemctl status kopi-docka.timer

# Or use the interactive management wizard
sudo kopi-docka advanced service manage
```

**[Systemd integration →](docs/FEATURES.md#4-systemd-integration)**

---

## Key Features

### 1. Compose-Stack-Awareness

Recognizes Docker Compose stacks and backs them up as atomic units with docker-compose.yml included.

**Traditional vs. Kopi-Docka:**
```
Traditional:                    Kopi-Docka:
├── wordpress_web_1            Stack: wordpress
├── wordpress_db_1             ├── Containers: web, db, redis
└── wordpress_redis_1          ├── Volumes: wordpress_data, mysql_data
                               ├── docker-compose.yml
❌ Context lost                └── Common backup_id
                               ✅ Complete stack restorable
```

### 2. Disaster Recovery Bundles

Single encrypted ZIP files containing repository connection data, configuration, and auto-reconnect scripts:

```bash
# Create encrypted ZIP bundle (recommended, v6.2.0+)
sudo kopi-docka disaster-recovery export ~/recovery.zip

# Or stream via SSH (zero disk footprint on server)
ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip

# In emergency (on new server):
1. Extract ZIP (7-Zip, unzip, WinZip)
2. Run sudo ./recover.sh
3. kopi-docka restore
4. docker compose up -d
```

**[Disaster Recovery guide →](docs/DISASTER_RECOVERY.md)**

### 3. Tailscale Integration

Automatic peer discovery for P2P backups over WireGuard mesh network:

```bash
sudo kopi-docka advanced config new
# → Select Tailscale
# → Shows all devices in your Tailnet
# → Auto-configures SSH keys
# → Direct encrypted connection (no cloud costs)
```

### 4. Systemd Integration

Daemon implementation with:
- sd_notify status reporting
- Watchdog monitoring
- Security hardening (ProtectSystem, NoNewPrivileges, etc.)
- PID locking (prevents parallel runs)
- Structured logging to systemd journal

**[See detailed features →](docs/FEATURES.md)**

---

## Backup Scopes

Kopi-Docka supports three backup scopes to balance speed, size, and restore capabilities:

### Scope Comparison

| Scope | What's Backed Up | Restore Capability | Use Case |
|-------|------------------|-------------------|----------|
| **minimal** | ✅ Volumes only | ⚠️ Data only - containers must be manually recreated | Fastest backups when you always have docker-compose files available |
| **standard** | ✅ Volumes<br>✅ Recipes (docker-compose.yml)<br>✅ Networks (IPAM config) | ✅ Full container restore | **Recommended** - Complete restore capability |
| **full** | ✅ Volumes<br>✅ Recipes<br>✅ Networks<br>✅ Docker daemon config | ✅ Full restore + manual daemon config | Disaster recovery with Docker daemon settings |

### Detailed Restore Matrix

| Scope | Volumes | Container Configs | Networks | Docker Daemon Config |
|-------|---------|-------------------|----------|---------------------|
| **minimal** | ✅ Restored | ❌ Not backed up* | ❌ Not backed up | ❌ Not backed up |
| **standard** | ✅ Restored | ✅ Restored | ✅ Restored | ❌ Not backed up |
| **full** | ✅ Restored | ✅ Restored | ✅ Restored | ⚠️ Manual restore** |

**Notes:**
- \* **Minimal scope limitation:** Only volume data is backed up. After restore, you **must manually recreate containers** using your original `docker-compose.yml` files or `docker run` commands. Networks must also be manually recreated.
- \*\* **Docker config safety:** Docker daemon configuration (`/etc/docker/daemon.json`, systemd overrides) is backed up but **not automatically restored**. This prevents accidental production breakage. Review and manually apply configuration changes.

### Usage Examples

**Set default scope in config wizard:**
```bash
sudo kopi-docka advanced config new
# → Interactive menu will prompt for scope selection
# → Default: standard (recommended)
```

**Set scope in config file:**
```json
{
  "backup": {
    "backup_scope": "standard"
  }
}
```

**Override scope via CLI flag:**
```bash
# Minimal - Fastest, smallest backups (volumes only)
sudo kopi-docka backup --scope minimal

# Standard - Recommended (volumes + recipes + networks)
sudo kopi-docka backup --scope standard

# Full - Complete DR including Docker daemon config
sudo kopi-docka backup --scope full
```

### ⚠️ Minimal Scope Warning

If you restore from a **minimal scope** backup, Kopi-Docka will show a prominent warning:

```
⚠️  MINIMAL Scope Backup Detected

This backup contains ONLY volume data.
Container recipes (docker-compose files) are NOT included.

After restore:
• Volumes will be restored
• Containers must be recreated manually
• Networks must be recreated manually

Consider using --scope standard or --scope full for complete backups.
```

**Recovery steps for minimal scope backups:**
1. `sudo kopi-docka restore` → Restores volume data
2. Manually recreate containers: `docker compose up -d` (using your original docker-compose.yml)
3. Manually recreate networks if needed: `docker network create ...`

### 🔧 Docker Config Manual Restore

For **FULL scope** backups, Docker daemon configuration is backed up but requires manual restoration:

**Extract docker_config snapshot:**
```bash
# List docker_config snapshots
sudo kopi-docka list --snapshots | grep docker_config

# Extract configuration to temp directory
sudo kopi-docka show-docker-config <snapshot-id>
```

**What this command does:**
- Extracts docker_config snapshot to `/tmp/kopia-docker-config-XXXXX/`
- Displays safety warnings about manual restore
- Shows extracted files (`daemon.json`, systemd overrides)
- Displays `daemon.json` contents inline (if <10KB)
- Provides 6-step manual restore instructions

**Why manual restore?**
- Docker daemon configuration is extremely sensitive
- Incorrect config can break Docker entirely
- Must be reviewed before applying to production
- Prevents accidental system breakage

**Example output:**
```
✓ Extracted files:
   • daemon.json (2.3 KB)
   • docker.service.d/override.conf (0.5 KB)

📄 daemon.json contents:
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

🔧 Manual Restore Instructions
Step 1: Review extracted files
Step 2: Backup current config
Step 3: Apply configuration (CAREFULLY!)
Step 4: Systemd overrides (if present)
Step 5: Restart Docker daemon
Step 6: Verify Docker is working
```

### Scope Selection Guidance

**Choose minimal when:**
- You need fastest possible backups
- You always have access to original docker-compose files
- You're comfortable manually recreating containers after restore
- Storage space is extremely limited

**Choose standard when (RECOMMENDED):**
- You want complete restore capability
- You prefer automated container recreation
- You want network configurations preserved
- You need reliable disaster recovery

**Choose full when:**
- You need complete disaster recovery capability
- You have custom Docker daemon configuration
- You use systemd service overrides for Docker
- You want to preserve all Docker settings

**Default:** `standard` (best balance for most users)

---

## Documentation

📚 **Guides:**

- **[Installation](docs/INSTALLATION.md)** - System requirements, installation options
- **[Configuration](docs/CONFIGURATION.md)** - Wizards, config files, storage backends
- **[Usage](docs/USAGE.md)** - CLI commands, workflows, how it works
- **[Features](docs/FEATURES.md)** - Detailed feature documentation
- **[Disaster Recovery](docs/DISASTER_RECOVERY.md)** - DR bundles, recovery workflow, SSH streaming
- **[Hooks](docs/HOOKS.md)** - Pre/post backup hooks, examples
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues, FAQ
- **[Development](docs/DEVELOPMENT.md)** - Project structure, contributing
- **[Architecture](docs/ARCHITECTURE.md)** - Code-driven architecture overview (authoritative)


📁 **Examples:**

- **[examples/config.json](examples/config.json)** - Sample configuration
- **[examples/docker-compose.yml](examples/docker-compose.yml)** - Example stack
- **[examples/hooks/](examples/hooks/)** - Hook script examples
- **[examples/systemd/](examples/systemd/)** - Systemd setup guide

---

## CLI Commands

Kopi-Docka features a simplified CLI with top-level commands and an `admin` subcommand for advanced operations.

### Top-Level Commands
```bash
sudo kopi-docka setup              # Complete setup wizard
sudo kopi-docka backup             # Full backup (standard scope)
sudo kopi-docka restore            # Interactive restore wizard
sudo kopi-docka restore --yes      # Non-interactive restore (CI/CD)
sudo kopi-docka show-docker-config <snapshot-id>  # Extract docker_config for manual restore
sudo kopi-docka disaster-recovery export ~/recovery.zip  # Create DR bundle (ZIP)
sudo kopi-docka dry-run            # Simulate backup (preview)
sudo kopi-docka doctor             # System health check
kopi-docka version                 # Show version
```

### Admin Commands
```bash
# Configuration
sudo kopi-docka advanced config show      # Show config
sudo kopi-docka advanced config new       # Create new config
sudo kopi-docka advanced config edit      # Edit config

# Repository
sudo kopi-docka advanced repo init        # Initialize repository
sudo kopi-docka advanced repo status      # Repository info

# Snapshots & Units
sudo kopi-docka advanced snapshot list              # List backup units
sudo kopi-docka advanced snapshot list --snapshots  # List all snapshots
sudo kopi-docka advanced snapshot estimate-size     # Estimate backup size
sudo kopi-docka advanced snapshot manage            # Interactive management wizard
sudo kopi-docka advanced snapshot delete <id>       # Delete a snapshot
sudo kopi-docka advanced snapshot pin <id>          # Pin snapshot (protect from cleanup)
sudo kopi-docka advanced snapshot unpin <id>        # Unpin snapshot
sudo kopi-docka advanced snapshot maintenance       # Run maintenance
sudo kopi-docka advanced snapshot prune-empty       # Expire snapshots (apply retention)
sudo kopi-docka advanced snapshot retention show    # Show retention policy
sudo kopi-docka advanced snapshot retention set \
  --latest 10 --daily 7 --weekly 4 --monthly 12    # Update retention policy

# System & Service
sudo kopi-docka advanced system install-deps    # Install dependencies
sudo kopi-docka advanced service write-units    # Generate systemd units
sudo kopi-docka advanced service daemon         # Run as daemon
```

**[Complete CLI reference →](docs/USAGE.md#cli-commands-reference)**

---

## Storage Backend Options

Kopi-Docka supports 8 different storage backends:

1. **Local Filesystem** - Local disk or NAS mount
2. **AWS S3** - Amazon S3 or S3-compatible (Wasabi, MinIO)
3. **Backblaze B2** - ~$6/TB/month (includes egress)
4. **Azure Blob** - Microsoft Azure storage
5. **Google Cloud Storage** - GCS
6. **SFTP** - Remote server via SSH
7. **Tailscale** - P2P over WireGuard mesh network
8. **Rclone** - Universal adapter (OneDrive, Dropbox, Google Drive, 70+ services) — ⚠️ **slow on Google Drive, [see issue #111](https://github.com/TZERO78/kopi-docka/issues/111)**

### Tested Backends

End-to-end backup + restore tested by the author against real storage.
Other backends are wired up and unit-tested, but I haven't run a full
backup cycle against them myself — community reports welcome.

| Backend | Status | Notes |
|---|:---:|---|
| **Rclone** | ✅ tested | Live test lab. Google-Drive remote has known upstream perf limits — [#111](https://github.com/TZERO78/kopi-docka/issues/111) |
| **Tailscale** | ✅ tested | NAS-over-tailnet; Plan 0029 + 0038 reproductions |
| **SFTP** | ✅ tested | v7.6.1 E2E: wizard → `kopia repository create` → full `kopi-docka backup` → snapshot persistence |
| Local Filesystem | ❓ untested | Should work — same code path as the others, no external auth |
| AWS S3 | ❓ untested | — |
| Backblaze B2 | ❓ untested | — |
| Azure Blob | ❓ untested | — |
| Google Cloud Storage | ❓ untested | — |

> **⚠️ Performance note for rclone + Google Drive users**: a known
> upstream limitation makes individual snapshot operations take 60-300
> seconds each (Kopia marks the rclone backend as `[Not maintained]`,
> Google Drive has high small-file write overhead). If you're seeing
> 30+ minute backups for a small amount of data, see
> **[pinned issue #111](https://github.com/TZERO78/kopi-docka/issues/111)**
> for measurements and recommended alternatives (any of the other 7
> backends will be an order of magnitude faster).

**[Storage configuration →](docs/CONFIGURATION.md#storage-backends)**

---

## System Requirements

- **OS:** Linux (Debian, Ubuntu, Arch, Fedora, RHEL/CentOS)
- **Python:** 3.10 or newer
- **Docker:** Docker Engine 20.10+
- **Kopia:** >= 0.13 (recommended; required for sparse-file support) (automatically checked)

**[Detailed requirements →](docs/INSTALLATION.md#system-requirements)**

---

## Feature Comparison

| Feature | Kopi-Docka | docker-volume-backup | Duplicati | Restic |
|---------|------------|----------------------|-----------|--------|
| **Docker-native** | ✅ | ✅ | ❌ | ❌ |
| **Cold Backups** | ✅ | ✅ | ❌ | ❌ |
| **Compose-Stack-Aware** | ✅ | ❌ | ❌ | ❌ |
| **Network Backup*** | ✅ | ❌ | ❌ | ❌ |
| **DR Bundles** | ✅ | ❌ | ❌ | ❌ |
| **Tailscale Integration** | ✅ | ❌ | ❌ | ❌ |
| **Rclone Support** | ✅ | ❌ | ❌ | ❌ |
| **systemd Integration** | ✅ | ❌ | ❌ | ❌ |
| **Pre/Post Hooks** | ✅ | ⚠️ | ❌ | ❌ |
| **Storage Options** | 8 backends | Basic | Many | Many |
| **Deduplication** | ✅ (Kopia) | ❌ | ✅ | ✅ |

*Network Backup = Automatic backup of custom Docker networks with IPAM configuration (subnets, gateways)

**Kopi-Docka's focus:** Stack-awareness, disaster recovery bundles, Tailscale P2P, and systemd hardening

**[Full comparison →](docs/FEATURES.md#why-kopi-docka)**

---

## Project Status

**Status:** Feature-Complete, Stabilization Phase  
**Latest Release:** See badges above ↑

The current release includes all planned core features:
- ✅ Backup scope selection (minimal/standard/full)
- ✅ Docker network backup with IPAM
- ✅ Pre/Post backup hooks
- ✅ Disaster recovery bundles
- ✅ Systemd integration with hardening

**Current Focus:**
- Bug fixing and edge-case handling
- Test coverage expansion
- Documentation improvements

**Known Limitations:**
- Single repository only (no parallel multi-cloud backup)
- Hooks require careful configuration ([Safety Guide](docs/HOOKS.md#hook-safety-rules))
- Restore edge-cases still being hardened

**New major features:** Only after stable foundation

[View Changelog](CHANGELOG.md) | [Development Roadmap](docs/DEVELOPMENT.md#planned-features)

---

## Thanks & Acknowledgments

**Kopi-Docka** = **Kopi**a + **Docka**r – the name reflects what this project is: a bridge between two excellent tools.

Kopi-Docka would not exist without these excellent tools:

- **Kopia** – the rock-solid backup engine providing encryption, deduplication
  and snapshot management  
  https://kopia.io

- **Docker** – container runtime and ecosystem that makes reproducible
  environments possible  
  https://www.docker.com

- **Tailscale** – secure WireGuard-based networking that enables simple
  peer-to-peer offsite backups  
  https://tailscale.com

- **rclone** – universal storage adapter enabling access to many affordable
  cloud and remote storage providers  
  https://rclone.org

- **Typer** – clean and readable CLI framework for Python
  https://typer.tiangolo.com

- **Pydantic** – data validation and settings management using Python type annotations
  https://docs.pydantic.dev

- **Apprise** – universal notification library supporting 100+ services
  https://github.com/caronc/apprise

All of these tools remain under their respective licenses and are **not bundled**
with Kopi-Docka.

This project is built with deep respect for the open-source ecosystem.

**Author:** Markus F. (TZERO78)  
**Links:** [PyPI](https://pypi.org/project/kopi-docka/) | [GitHub](https://github.com/TZERO78/kopi-docka)

---

## License

MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2025 Markus F. (TZERO78)

---

## Feedback & Support

If you find Kopi-Docka useful, feel free to leave a ⭐ on GitHub.

I cannot test all storage backends and edge cases on my own, so feedback from
real-world setups is highly appreciated.

If something doesn't work as expected, please open an **Issue** and include
your environment details.

- 📦 **PyPI:** [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- 📚 **Documentation:** [Complete docs](docs/)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)
- 🧑‍🤝‍🧑 **Code of Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
