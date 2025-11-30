[← Back to README](../README.md)

# Installation

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

[← Back to README](../README.md)
