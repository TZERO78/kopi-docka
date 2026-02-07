[← Back to README](../README.md)

# Disaster Recovery

Kopi-Docka creates encrypted, self-contained recovery bundles that allow you to reconnect to your Kopia backup repository on a completely new server — typically within 15–30 minutes.

---

## Overview

A Disaster Recovery (DR) bundle is a single file containing everything needed to restore access to your backups:

| Content | Description |
|---------|-------------|
| `recovery-info.json` | Repository type, connection data, versions, paths |
| `kopia-repository.json` | Raw Kopia repository status |
| `kopia-password.txt` | Repository encryption password |
| `kopi-docka.conf` | Your Kopi-Docka configuration |
| `rclone.conf` | Rclone configuration (if using Rclone backend) |
| `recover.sh` | Guided auto-reconnect script |
| `RECOVERY-INSTRUCTIONS.txt` | Human-readable recovery steps |
| `backup-status.json` | Recent snapshot information |

> **Without a DR bundle**, recovering from a total server loss requires manually finding your repository URL, password, backend credentials, and Kopia configuration — a process that can take hours or even days. **With a DR bundle**, recovery takes minutes.

---

## Bundle Formats

### Encrypted ZIP (Recommended) — `disaster-recovery export`

*Available since v6.2.0*

The new default format produces a **single AES-256 encrypted ZIP file**. It requires no external tools (tar, openssl) on the server — only native Python libraries are used.

**Advantages:**
- Single file — easy to store and transfer
- AES-256 encryption (WinZip-compatible AES)
- No `tar` or `openssl` dependencies on the server
- Cross-platform extraction: 7-Zip, WinZip, `unzip`, macOS Archive Utility
- SSH stream mode for zero-disk-footprint exports
- Automatic file ownership (set to `SUDO_USER` when running via sudo)
- Interactive passphrase generation with confirmation

### Legacy 3-File Bundle (Deprecated) — `disaster-recovery`

The original format creates three files:

| File | Purpose |
|------|---------|
| `*.tar.gz.enc` | Encrypted tar archive (AES-256-CBC via OpenSSL) |
| `*.tar.gz.enc.PASSWORD` | Random 48-character decryption password |
| `*.tar.gz.enc.README` | Decryption instructions and metadata |

> ⚠️ **Deprecated since v6.2.0.** Running `disaster-recovery` without the `export` subcommand triggers a deprecation warning. This format will be removed in a future release. Migrate to `disaster-recovery export`.

---

## Quick Start

### Create a DR Bundle (Interactive)

```bash
sudo kopi-docka disaster-recovery export ~/recovery.zip
```

Kopi-Docka will:
1. Generate a memorable passphrase (e.g. `Crown-Falcon-Meadow-Prism-River`)
2. Display the passphrase and ask you to re-enter it for confirmation
3. Create the encrypted ZIP

**Output:**
```
🔑 Passphrase
╭──────────────────────────────────────╮
│ Generated Passphrase:                │
│                                      │
│   Crown-Falcon-Meadow-Prism-River   │
│                                      │
│ Write this down in a secure location!│
╰──────────────────────────────────────╯

Re-enter passphrase to confirm: Crown-Falcon-Meadow-Prism-River

 Creating encrypted ZIP bundle...

╭─── Bundle Created ───╮
│ ✓ Recovery bundle created!           │
│                                      │
│ File:   /home/user/recovery.zip      │
│ Size:   0.1 MB                       │
│ Format: AES-256 encrypted ZIP        │
╰──────────────────────────────────────╯
```

### Create with Custom Passphrase

```bash
sudo kopi-docka disaster-recovery export ~/recovery.zip --passphrase "my-secret-passphrase"
```

### Create with Random Passphrase

```bash
sudo kopi-docka disaster-recovery export ~/recovery.zip --passphrase-type random
```

This generates a 24-character alphanumeric passphrase instead of the default word-based format.

---

## SSH Stream Mode

For servers where you don't want the DR bundle to touch the disk at all, use `--stream` to pipe the ZIP directly to your local machine via SSH:

```bash
ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'My-Secret-Pass'" > recovery.zip
```

**How it works:**
- The encrypted ZIP is written to `stdout` on the server
- All informational output (progress, status) is sent to `stderr`
- Your SSH client redirects `stdout` to a local file
- **Zero disk footprint** on the remote server

> ⚠️ `--stream` requires `--passphrase` because there is no interactive TTY for passphrase generation.

---

## Automatic DR Bundles with Every Backup

Configure Kopi-Docka to automatically create or update a DR bundle after each backup:

```json
{
  "backup": {
    "update_recovery_bundle": true,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3
  }
}
```

```bash
sudo kopi-docka backup
# → Backup runs
# → DR bundle is automatically created/updated afterward
```

> **Note:** The automatic bundle currently uses the legacy format. Manual `disaster-recovery export` is recommended for the new ZIP format.

---

## Full Recovery Walkthrough

**Scenario:** Your production server has completely failed. You have a new server and the DR bundle file (`recovery.zip`).

### Step 1: Prepare the New Server

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Kopia (https://kopia.io/docs/installation/)
curl -s https://kopia.io/signing-key | gpg --dearmor -o /etc/apt/keyrings/kopia-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kopia-keyring.gpg] http://packages.kopia.io/apt/ stable main" \
  > /etc/apt/sources.list.d/kopia.list
apt update && apt install -y kopia

# Install Kopi-Docka
pipx install kopi-docka
sudo ln -s ~/.local/bin/kopi-docka /usr/local/bin/kopi-docka
```

### Step 2: Extract the DR Bundle

**With 7-Zip (recommended):**
```bash
7z x recovery.zip
# → Enter passphrase when prompted
```

**With unzip:**
```bash
unzip recovery.zip
# → Enter passphrase when prompted
```

**On macOS / Windows:** Double-click and enter the passphrase.

### Step 3: Run the Recovery Script

```bash
cd kopi-docka-recovery-*/   # or wherever extracted
sudo ./recover.sh
```

The script will:
1. Verify that Docker and Kopia are installed
2. Restore `kopi-docka.conf` to its original path (with interactive backup if file exists)
3. Restore `rclone.conf` (if using Rclone backend)
4. Restore the Kopia password file (if configured)
5. Connect to the Kopia repository
6. Verify the connection

For cloud backends (S3, B2, Azure, GCS), the script will interactively ask for access keys.

### Step 4: Restore Services

```bash
# Interactive restore wizard
sudo kopi-docka restore

# The wizard shows available stacks and restore points:
#   - wordpress (2025-01-31T23:59:59Z)
#   - nextcloud (2025-01-30T23:59:59Z)
#   - gitlab (2025-01-29T23:59:59Z)
```

### Step 5: Start Containers

```bash
# For Compose stacks:
cd /tmp/kopia-restore-*/recipes/wordpress/
docker compose up -d

# For standalone containers:
# The restore wizard automatically reconstructs docker run commands
```

### Step 6: Re-enable Automated Backups

```bash
sudo kopi-docka advanced service write-units
sudo systemctl enable --now kopi-docka.timer

# Verify
systemctl list-timers | grep kopi-docka
```

---

## CLI Reference

### `disaster-recovery export` (Recommended)

```
sudo kopi-docka disaster-recovery export [OUTPUT] [OPTIONS]
```

| Argument / Option | Description |
|-------------------|-------------|
| `OUTPUT` | Path for the ZIP file (e.g. `/home/user/recovery.zip`). Required unless `--stream`. |
| `--stream` | Stream ZIP to stdout instead of writing to disk. Requires `--passphrase`. |
| `--passphrase TEXT` | Encryption passphrase. If omitted, one is generated interactively. |
| `--passphrase-type TEXT` | Passphrase style: `words` (default, memorable) or `random` (24-char alphanumeric). |

**Examples:**

```bash
# Interactive — generates and confirms passphrase
sudo kopi-docka disaster-recovery export /home/user/recovery.zip

# Custom passphrase
sudo kopi-docka disaster-recovery export /home/user/recovery.zip --passphrase "my-secret"

# Random passphrase style
sudo kopi-docka disaster-recovery export /home/user/recovery.zip --passphrase-type random

# SSH stream (zero disk footprint on server)
ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip
```

### `disaster-recovery` (Legacy, Deprecated)

```
sudo kopi-docka disaster-recovery [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output directory (default: configured `recovery_bundle_path`). |
| `--no-password-file` | Don't write password sidecar file. |
| `--skip-dependency-check` | Skip tar/openssl availability check. |

**Legacy decryption:**
```bash
openssl enc -aes-256-cbc -salt -pbkdf2 -d \
  -in kopi-docka-recovery-*.tar.gz.enc \
  -out bundle.tar.gz \
  -pass pass:'<PASSWORD_FROM_SIDECAR>'

tar -xzf bundle.tar.gz
cd kopi-docka-recovery-*/
sudo ./recover.sh
```

---

## Passphrase Security

### Word-Based Passphrases (Default)

Generated from a curated 200-word English wordlist. Five words are selected at random, Title-Cased, and joined with hyphens:

```
Crown-Falcon-Meadow-Prism-River
```

- **Entropy:** ~38 bits (200⁵ ≈ 3.2 × 10¹¹ combinations)
- **Easy to write down** and type
- **Hard to brute-force** against AES-256 encrypted ZIP

### Random Passphrases

24-character alphanumeric string:

```
kR7mN2xLpQ9wF4vB3jT6sY1a
```

- **Entropy:** ~143 bits
- **Best for automated/scripted workflows** where human readability is not needed

### Best Practices

- ✅ Store the passphrase **separately** from the bundle
- ✅ Use a password manager (1Password, Bitwarden, KeePass)
- ✅ Write it on paper and keep in a physical safe
- ❌ Don't store passphrase and bundle in the same location
- ❌ Don't send passphrase and bundle via the same channel

---

## Storage Best Practices

Store your DR bundle in **at least two** locations, separate from your backup repository:

| Location | Example | Notes |
|----------|---------|-------|
| 🔌 USB drive | Office safe, home safe | Offline, tamper-proof |
| ☁️ Cloud storage | Tresorit, Cryptomator + cloud | Different account than backup backend |
| 📱 Phone | Encrypted file manager | Quick access in emergencies |
| 👥 Trusted person | Family member, business partner | With separate passphrase delivery |
| 🏢 Company safe | Physical storage | For business environments |

**Rules:**
- ❌ **Never** store only on the backup server itself
- ❌ **Never** store in the same cloud account as backups
- ✅ At least **2 copies** in different physical locations
- ✅ **Test recovery** every 6 months

---

## Format Comparison

| | ZIP Export (v6.2.0+) | Legacy 3-File (deprecated) |
|---|---|---|
| **Files** | 1 file (`.zip`) | 3 files (`.tar.gz.enc` + `.PASSWORD` + `.README`) |
| **Encryption** | AES-256 (WinZip AES, pyzipper) | AES-256-CBC (OpenSSL PBKDF2) |
| **External tools needed** | None (pure Python) | `tar`, `openssl` |
| **Extract with** | 7-Zip, WinZip, unzip, macOS Archive Utility | `openssl` + `tar` (Linux only) |
| **SSH streaming** | ✅ `--stream` | ❌ |
| **Interactive passphrase** | ✅ Generated + confirmed | ❌ Random, written to sidecar file |
| **File ownership** | ✅ Automatic (SUDO_USER) | ❌ Owned by root |
| **Bundle size** | ~10–50 KB | ~10–50 KB |
| **Password storage** | User responsibility (not on disk) | Sidecar `.PASSWORD` file |

---

## Troubleshooting

### "kopia is required" Error

DR bundles require Kopia to read repository status. Install Kopia first:

```bash
# Check
kopia version

# Install: https://kopia.io/docs/installation/
```

### "Output directory is not writable"

Ensure the target directory exists and is writable by the current user (or use `sudo`).

### SSH Stream Produces Empty File

Make sure `--passphrase` is provided — `--stream` mode cannot interactively prompt for a passphrase:

```bash
# Wrong (no passphrase)
ssh server "sudo kopi-docka disaster-recovery export --stream" > recovery.zip

# Correct
ssh server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip
```

### Cannot Extract ZIP

- Make sure you are using the correct passphrase (case-sensitive)
- Use a tool that supports AES-256 encrypted ZIP: **7-Zip** (recommended), WinZip, or `unzip` on Linux
- The standard macOS Archive Utility may not support AES-encrypted ZIPs — use [Keka](https://www.keka.io/) or `7z` via Homebrew

### Legacy Bundle: "openssl: command not found"

The legacy format requires `openssl` and `tar`. Install them or migrate to the new ZIP format:

```bash
# Migrate to new format
sudo kopi-docka disaster-recovery export ~/recovery.zip
```

---

## Related Documentation

- **[Features](FEATURES.md)** — All Kopi-Docka features overview
- **[Usage](USAGE.md)** — Complete CLI reference
- **[Configuration](CONFIGURATION.md)** — Config file options including DR settings
- **[Troubleshooting](TROUBLESHOOTING.md)** — General troubleshooting guide
