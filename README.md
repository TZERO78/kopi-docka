# Kopi-Docka

> **Robust Cold Backup for Docker Environments using Kopia**

Kopi-Docka is a Python-based backup tool for Docker containers and their volumes. Features controlled downtime windows, encrypted snapshots, and automatic disaster recovery bundles.

[![PyPI](https://img.shields.io/pypi/v/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![Python Version](https://img.shields.io/pypi/pyversions/kopi-docka)](https://pypi.org/project/kopi-docka/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/kopi-docka)](https://pypi.org/project/kopi-docka/)

---

## What is Kopi-Docka?

**Kopi-Docka = Kopia + Docker + Backup**

A wrapper around [Kopia](https://kopia.io), specifically designed for Docker environments:

- **📦 Stack-Aware** - Backs up entire Docker Compose stacks as logical units
- **🔐 Encrypted** - End-to-end encryption via Kopia (AES-256-GCM)
- **🌐 Multi-Backend** - Local, S3, B2, Azure, GCS, SFTP, Tailscale
- **💾 Disaster Recovery** - Encrypted emergency bundles with auto-reconnect
- **🔧 Pre/Post Hooks** - Custom scripts for maintenance mode
- **📊 Systemd-Native** - Production-ready daemon with sd_notify & watchdog
- **🚀 Restore Anywhere** - Recovery on completely new hardware

**[See all features →](docs/FEATURES.md)**

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
2. ✅ Backend selection (Local, S3, B2, Azure, GCS, SFTP, Tailscale)
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

# Create disaster recovery bundle (IMPORTANT!)
sudo kopi-docka disaster-recovery
# → Copy bundle to safe location: USB/cloud/safe!
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
```

**[Systemd integration →](docs/FEATURES.md#4-systemd-integration)**

---

## Unique Features

### 1. Compose-Stack-Awareness

Automatically recognizes Docker Compose stacks and backs them up as atomic units with docker-compose.yml included.

```bash
kopi-docka admin snapshot list

Backup Units:
  - wordpress (Stack, 3 containers, 2 volumes)
  - nextcloud (Stack, 5 containers, 3 volumes)
  - gitlab (Stack, 4 containers, 4 volumes)
```

### 2. Disaster Recovery Bundles

Encrypted packages containing everything needed to reconnect to your repository on a new server. Time to recovery: 15-30 minutes instead of hours.

### 3. Tailscale Integration

Automatic peer discovery for P2P backups over your private network. Use your own hardware instead of cloud storage.

```
Available Backup Targets
┌─────────────┬─────────────────┐
│ Status      │ Hostname        │
├─────────────┼─────────────────┤
│ 🟢 Online  │ cloud-vps       │
│ 🟢 Online  │ home-nas        │
└────────────┴──────────────────┘
```

### 4. Systemd Integration

Production-ready daemon with sd_notify, watchdog monitoring, PID locking, and security hardening.

**[Read detailed feature documentation →](docs/FEATURES.md)**

---

## What's New in v3.6.0

- **🎯 Smart Restore** - Recovery script uses dynamic paths from bundle metadata
- **🛡️ Safe Restore** - Interactive file restoration with automatic backups
- **💾 Complete Recovery** - Password files are now restored to their original locations
- **📋 Systemd Reminder** - Clear instructions to re-enable automated backups
- **🔄 Idempotent Recovery** - Run recover.sh multiple times without conflicts

**Previous (v3.5.0):**
- Rclone Backend Improvements (PermissionError fix)
- Enhanced DR Bundles (rclone.conf included)
- Kopia Flag Fix (--rclone-args)

**Previous (v3.4.0):**
- Simplified CLI with "The Big 6" commands
- Doctor Command for system health checks
- Organized admin subcommands

**Previous (v3.3.0):**
- Backup Scope Selection (minimal/standard/full)
- Docker Network Backup
- Pre/Post Backup Hooks
- Conflict Detection

**[See what's new →](docs/FEATURES.md#whats-new-in-v340)**

---

## Documentation

📚 **Complete Documentation:**

- **[Features](docs/FEATURES.md)** - Unique features, what's new, why Kopi-Docka?
- **[Installation](docs/INSTALLATION.md)** - System requirements, installation options
- **[Configuration](docs/CONFIGURATION.md)** - Wizards, config files, storage backends
- **[Usage](docs/USAGE.md)** - CLI commands, workflows, how it works
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

Kopi-Docka v3.4+ features a simplified CLI with **"The Big 6"** top-level commands and an `admin` subcommand for advanced operations.

### Top-Level Commands ("The Big 6")
```bash
sudo kopi-docka setup              # Complete setup wizard
sudo kopi-docka backup             # Full backup (standard scope)
sudo kopi-docka restore            # Interactive restore wizard
sudo kopi-docka disaster-recovery  # Create DR bundle
sudo kopi-docka dry-run            # Simulate backup (preview)
sudo kopi-docka doctor             # System health check
kopi-docka version                 # Show version
```

### Admin Commands (Advanced)
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

## Storage Backends

Kopi-Docka supports 7 different backends:

1. **Local Filesystem** - Local disk or NAS mount
2. **AWS S3** - Amazon S3 or compatible (Wasabi, MinIO)
3. **Backblaze B2** - Affordable cloud storage (~$5/TB/month)
4. **Azure Blob** - Microsoft Azure storage
5. **Google Cloud Storage** - GCS
6. **SFTP** - Remote server via SSH
7. **Tailscale** - P2P over private network (no cloud costs!)

**[Backend configuration →](docs/CONFIGURATION.md#storage-backends)**

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
| **Compose-Stack-Aware** | ✅ | ❌ | ❌ | ❌ |
| **Network Backup** | ✅ | ❌ | ❌ | ❌ |
| **DR Bundles** | ✅ | ❌ | ❌ | ❌ |
| **Tailscale Integration** | ✅ | ❌ | ❌ | ❌ |
| **systemd-native** | ✅ | ❌ | ❌ | ❌ |
| **Pre/Post Hooks** | ✅ | ⚠️ | ❌ | ❌ |
| **Multi-Cloud** | ✅ | ✅ | ✅ | ✅ |

**[Full comparison →](docs/FEATURES.md#why-kopi-docka)**

---

## Who Is It For?

- **Homelab Operators** - Multiple Docker hosts with offsite backups
- **Self-Hosters** - Docker services with professional backup strategy
- **Small Businesses** - Disaster recovery without enterprise costs
- **Power Users** - Full control over backup and restore processes

---

## Credits & Acknowledgments

**Author:** Markus F. (TZERO78)

**Links:**
- PyPI: [pypi.org/project/kopi-docka](https://pypi.org/project/kopi-docka/)
- GitHub: [github.com/TZERO78/kopi-docka](https://github.com/TZERO78/kopi-docka)

### Powered by Kopia

**Kopi-Docka wouldn't exist without [Kopia](https://kopia.io)!**

Kopi-Docka is a wrapper that uses Kopia's powerful backup engine. Kopia provides:
- 🔐 End-to-end encryption (AES-256-GCM)
- 🗜️ Deduplication & compression
- ☁️ Multi-cloud support
- 📦 Incremental snapshots
- 🚀 High performance

**Links:**
- Kopia: https://kopia.io
- Kopia GitHub: https://github.com/kopia/kopia

### Other Dependencies

- **[Docker](https://www.docker.com/)** - Container lifecycle management
- **[Typer](https://typer.tiangolo.com/)** - CLI framework
- **[psutil](https://github.com/giampaolo/psutil)** - System resource monitoring

> **Note:** Kopi-Docka is an independent project with no official affiliation to Docker Inc. or the Kopia project.

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

**Love Kopi-Docka?** Give us a ⭐ on GitHub!

---

**Current Version:** v3.6.0

**[View changelog](docs/FEATURES.md#whats-new-in-v360)** | **[Contributing](docs/DEVELOPMENT.md#contributing)** | **[Troubleshooting](docs/TROUBLESHOOTING.md)**
