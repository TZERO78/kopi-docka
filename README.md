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

**[See detailed features →](docs/FEATURES.md)**

---

## Quick Start

### Installation

```bash
# Recommended: pipx (isolated environment)
pipx install kopi-docka

# Or: pip (system-wide)
pip install kopi-docka
```

**[Full installation guide →](docs/INSTALLATION.md)**

### Setup

```bash
# Interactive setup wizard
sudo kopi-docka setup
```

The wizard guides you through:
1. ✅ Dependency check (Kopia, Docker)
2. ✅ Repository storage selection (Local, S3, B2, Azure, GCS, SFTP, Tailscale, Rclone)
3. ✅ Repository initialization
4. ✅ Connection test

**[Configuration guide →](docs/CONFIGURATION.md)**

### First Backup

```bash
# System health check
sudo kopi-docka doctor

# List backup units (containers/stacks)
sudo kopi-docka admin snapshot list

# Test run (no changes)
sudo kopi-docka dry-run

# Full backup
sudo kopi-docka backup

# Create disaster recovery bundle
sudo kopi-docka disaster-recovery
# → Store bundle off-site: USB/cloud/safe
```

**[Usage guide →](docs/USAGE.md)**

### Automatic Backups

```bash
# Generate systemd units
sudo kopi-docka admin service write-units

# Enable daily backups (02:00 default)
sudo systemctl enable --now kopi-docka.timer

# Check status
sudo systemctl status kopi-docka.timer

# Or use the interactive management wizard
sudo kopi-docka admin service manage
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

Encrypted packages containing repository connection data and auto-reconnect scripts:

```bash
# Create bundle
sudo kopi-docka disaster-recovery

# In emergency (on new server):
1. Decrypt bundle
2. Run ./recover.sh
3. kopi-docka restore
4. docker compose up -d
```

### 3. Tailscale Integration

Automatic peer discovery for P2P backups over WireGuard mesh network:

```bash
sudo kopi-docka admin config new
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

## Documentation

📚 **Guides:**

- **[Installation](docs/INSTALLATION.md)** - System requirements, installation options
- **[Configuration](docs/CONFIGURATION.md)** - Wizards, config files, storage backends
- **[Usage](docs/USAGE.md)** - CLI commands, workflows, how it works
- **[Features](docs/FEATURES.md)** - Detailed feature documentation
- **[Hooks](docs/HOOKS.md)** - Pre/post backup hooks, examples
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues, FAQ
- **[Development](docs/DEVELOPMENT.md)** - Project structure, contributing

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
sudo kopi-docka disaster-recovery  # Create DR bundle
sudo kopi-docka dry-run            # Simulate backup (preview)
sudo kopi-docka doctor             # System health check
kopi-docka version                 # Show version
```

### Admin Commands
```bash
# Configuration
sudo kopi-docka admin config show      # Show config
sudo kopi-docka admin config new       # Create new config
sudo kopi-docka admin config edit      # Edit config

# Repository
sudo kopi-docka admin repo init        # Initialize repository
sudo kopi-docka admin repo status      # Repository info
sudo kopi-docka admin repo maintenance # Run maintenance

# Snapshots & Units
sudo kopi-docka admin snapshot list          # List backup units
sudo kopi-docka admin snapshot list --snapshots  # List all snapshots
sudo kopi-docka admin snapshot estimate-size # Estimate backup size

# System & Service
sudo kopi-docka admin system install-deps    # Install dependencies
sudo kopi-docka admin service write-units    # Generate systemd units
sudo kopi-docka admin service daemon         # Run as daemon
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
8. **Rclone** - Universal adapter (OneDrive, Dropbox, Google Drive, 70+ services)

**[Storage configuration →](docs/CONFIGURATION.md#storage-backends)**

---

## System Requirements

- **OS:** Linux (Debian, Ubuntu, Arch, Fedora, RHEL/CentOS)
- **Python:** 3.10 or newer
- **Docker:** Docker Engine 20.10+
- **Kopia:** 0.10+ (automatically checked)

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

## Credits & Acknowledgments

**Author:** Markus F. (TZERO78)

**Links:**
- PyPI: [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- GitHub: [github.com/TZERO78/kopi-docka](https://github.com/TZERO78/kopi-docka)

### Uses Kopia

Kopi-Docka uses [Kopia](https://kopia.io) as its backup engine. Kopia provides:
- 🔐 End-to-end encryption (AES-256-GCM)
- 🗜️ Deduplication & compression
- ☁️ Multi-cloud support
- 📦 Incremental snapshots

**Links:**
- Kopia: https://kopia.io
- Kopia GitHub: https://github.com/kopia/kopia

### Other Dependencies

- **[Docker](https://www.docker.com/)** - Container lifecycle management
- **[Rclone](https://rclone.org/)** - Universal cloud storage adapter
- **[Tailscale](https://tailscale.com/)** - WireGuard-based mesh networking (optional, for P2P backups)
- **[Typer](https://typer.tiangolo.com/)** - CLI framework
- **[psutil](https://github.com/giampaolo/psutil)** - System resource monitoring

> **Note:** Kopi-Docka is an independent project with no official affiliation to Docker Inc., the Kopia project, or Rclone.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2025 Markus F. (TZERO78)

---

## Support & Community

- 📦 **PyPI:** [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- 📚 **Documentation:** [Complete docs](docs/)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)
