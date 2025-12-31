[← Back to README](../README.md)

# Installation

## Think Simple Philosophy

**Kopi-Docka expects a prepared system.** We believe in user responsibility and system simplicity:

- ✅ **You prepare your system** (manually or with automation tools)
- ✅ **We provide clear guidance** on what's needed
- ❌ **No automatic installations** - keeps the codebase simple and maintainable
- ❌ **No distro detection** - works everywhere without complexity

**Need automated setup?** Use [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten) for automated system preparation.

---

## System Requirements

### Required Dependencies (MUST-HAVE)

These are **non-negotiable** - Kopi-Docka cannot function without them:

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| **Docker** | Container runtime for Kopi-Docka | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| **Kopia** | Backup engine | [kopia.io/docs/installation](https://kopia.io/docs/installation/) |

**Quick check:**
```bash
docker --version
kopia --version
```

### Optional Dependencies (SOFT)

These are needed for specific features and can be skipped with `--skip-dependency-check`:

| Dependency | Needed For | Usually Pre-installed |
|------------|------------|----------------------|
| **tar** | Disaster recovery bundles | ✓ Most Linux distros |
| **openssl** | Encryption of recovery bundles | ✓ Most Linux distros |

### Backend-Specific Dependencies

Checked automatically when you configure a backend:

| Backend | Additional Tools Required |
|---------|---------------------------|
| **Tailscale** | tailscale, ssh, ssh-keygen, ssh-copy-id |
| **SFTP** | ssh, ssh-keygen |
| **Rclone** | rclone |

---

## Installation Methods

### Option 1: Automated Setup (Recommended)

Use **Server-Baukasten** for complete automated system preparation:

```bash
# Clone Server-Baukasten
git clone https://github.com/TZERO78/Server-Baukasten.git
cd Server-Baukasten

# Run setup (installs Docker, Kopia, SSH tools, etc.)
./setup.sh

# Then install Kopi-Docka
pipx install kopi-docka
```

**✓ Benefits:**
- Installs all required dependencies
- Configures system properly
- Handles distro-specific quirks
- Battle-tested automation

### Option 2: Manual Installation

#### Step 1: Install Docker

**Debian/Ubuntu:**
```bash
# Official Docker installation
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**Arch Linux:**
```bash
sudo pacman -S docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

**Fedora/RHEL:**
```bash
sudo dnf install docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

#### Step 2: Install Kopia

Visit [kopia.io/docs/installation](https://kopia.io/docs/installation/) for your platform.

**Example (Debian/Ubuntu):**
```bash
curl -s https://kopia.io/signing-key | sudo gpg --dearmor -o /usr/share/keyrings/kopia-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/kopia-keyring.gpg] https://packages.kopia.io/apt/ stable main" | sudo tee /etc/apt/sources.list.d/kopia.list
sudo apt update
sudo apt install kopia
```

#### Step 3: Install Optional Tools

**For disaster recovery:**
```bash
# Debian/Ubuntu
sudo apt install tar openssl

# Arch
sudo pacman -S tar openssl

# Fedora/RHEL
sudo dnf install tar openssl
```

**For SSH-based backends (Tailscale, SFTP):**
```bash
# Debian/Ubuntu
sudo apt install openssh-client

# Arch
sudo pacman -S openssh

# Fedora/RHEL
sudo dnf install openssh-clients
```

#### Step 4: Install Kopi-Docka

**With pipx (Recommended - Isolated Environment):**
```bash
# Install pipx if not present
sudo apt install pipx  # or: sudo pacman -S python-pipx
pipx ensurepath

# Install Kopi-Docka
pipx install kopi-docka

# Verify
kopi-docka version
```

**With pip (System-wide):**
```bash
pip install kopi-docka
# or
sudo pip install kopi-docka
```

**From Source (Development):**
```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka

# Development mode
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

---

## Verify Installation

Run the system diagnostics command to check all dependencies:

```bash
kopi-docka doctor
```

**Expected output:**
```
✓ System Information
  OS: Linux
  Python: 3.12.3
  Kopi-Docka: 6.0.0

✓ Core Dependencies
  docker       [MUST_HAVE]   ✓ Installed   20.10.23   /usr/bin/docker
  kopia        [MUST_HAVE]   ✓ Installed   0.16.1     /usr/bin/kopia
  tar          [SOFT]        ✓ Installed   1.34       /usr/bin/tar
  openssl      [SOFT]        ✓ Installed   3.0.2      /usr/bin/openssl
```

---

## Hard Gate vs Soft Gate

Kopi-Docka uses a two-tier dependency system:

### Hard Gate (Non-Skippable)

**Docker + Kopia** are **always required**. Commands will refuse to run without them:

```bash
$ kopi-docka backup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ Cannot proceed - required dependencies missing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Missing: docker

Kopi-Docka requires Docker and Kopia to function.

Installation:
  • Docker: https://docs.docker.com/engine/install/

Automated Setup:
  Use Server-Baukasten for automated system preparation:
  https://github.com/TZERO78/Server-Baukasten

Note: --skip-dependency-check does NOT apply to Docker/Kopia.
```

### Soft Gate (Skippable)

**tar, openssl** are checked before disaster recovery but can be skipped:

```bash
$ kopi-docka disaster-recovery

✗ Missing optional dependencies: tar

Please install manually.

Or run with --skip-dependency-check (not recommended):
  kopi-docka disaster-recovery --skip-dependency-check
```

**Using the skip flag:**
```bash
$ kopi-docka disaster-recovery --skip-dependency-check

⚠️ Skipping dependency check for: tar
   Some features may not work correctly.
```

---

## Updating Kopi-Docka

```bash
# pipx
pipx upgrade kopi-docka

# pip
pip install --upgrade kopi-docka

# Verify new version
kopi-docka version
```

---

## Migration from v5.4.x

### Breaking Changes in v5.5.0

**Removed features:**
- ❌ `kopi-docka install-deps` command (no longer exists)
- ❌ Automatic dependency installation
- ❌ Distro detection logic
- ❌ Package manager integration

**What you need to do:**
1. **Ensure Docker and Kopia are installed** before upgrading
2. Run `kopi-docka doctor` after upgrading to verify dependencies
3. Use [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten) for automated system setup

**If you relied on `install-deps`:**
- Switch to manual installation (see above)
- Or use Server-Baukasten for automation

---

## Troubleshooting

### "Cannot proceed - required dependencies missing"

**Problem:** Docker or Kopia is not installed.

**Solution:**
```bash
# Check what's missing
kopi-docka doctor

# Install missing dependencies
# See "Manual Installation" section above
```

### "Missing optional dependencies: tar, openssl"

**Problem:** tar or openssl is not available (rare on most Linux systems).

**Solutions:**
1. Install the missing tools (recommended)
2. Skip the check with `--skip-dependency-check` (not recommended)

### Backend dependency errors

**Problem:** "Missing required tools for Tailscale backend: ssh, ssh-keygen"

**Solution:**
```bash
# Install OpenSSH client
sudo apt install openssh-client  # Debian/Ubuntu
sudo pacman -S openssh           # Arch
sudo dnf install openssh-clients # Fedora/RHEL
```

---

## Next Steps

After installation:

1. **Verify installation:** `kopi-docka doctor`
2. **Configure storage:** `kopi-docka setup`
3. **Create first backup:** `kopi-docka backup --dry-run`
4. **Read usage guide:** [USAGE.md](USAGE.md)

---

[← Back to README](../README.md)
