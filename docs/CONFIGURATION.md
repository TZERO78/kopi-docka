[← Back to README](../README.md)

# Configuration

## The Wizards

Kopi-Docka has **two interactive wizards**:

### 1. Master Setup Wizard (`setup`)
**For:** Complete initial setup

```bash
sudo kopi-docka setup
```

**What it does:**
1. Check/install dependencies (optional)
2. Start config wizard (see below)
3. Initialize repository
4. Test everything

**When to use:** First-time installation

---

### 2. Config Wizard (`admin config new`)
**For:** Create/recreate config only

```bash
sudo kopi-docka admin config new
```

**What it does:**
1. **Backend Selection** - Interactive menu:
   ```
   1. Local Filesystem  - Local disk/NAS
   2. AWS S3           - S3-compatible (Wasabi, MinIO)
   3. Backblaze B2     - Affordable, recommended!
   4. Azure Blob       - Microsoft Azure
   5. Google Cloud     - GCS
   6. SFTP             - Remote via SSH
   7. Tailscale        - Peer-to-peer over private network
   ```

2. **Backend Configuration** - Queries backend-specific values:
   - Local: Repository path
   - S3: Bucket, region, endpoint (optional)
   - B2: Bucket, prefix
   - Azure: Container, storage account
   - GCS: Bucket, prefix
   - SFTP: Host, user, path
   - Tailscale: Peer selection (automatically detected)

3. **Password Setup:**
   ```
   1. Secure random password (recommended)
   2. Enter custom password
   ```

4. **Save Config** as JSON:
   - Root: `/etc/kopi-docka.json`
   - User: `~/.config/kopi-docka/config.json`

**When to use:**
- Create new config
- Switch backend
- After manual config reset

**Example (B2 Backend):**
```bash
sudo kopi-docka admin config new

# Wizard asks:
Where should backups be stored?
→ 3 (Backblaze B2)

Bucket name: my-backup-bucket
Path prefix: kopia

Password setup:
→ 1 (Auto-generate secure password)

✓ Configuration created: /etc/kopi-docka.json
  kopia_params: b2 --bucket my-backup-bucket --prefix kopia

⚠️ Set environment variables:
  export B2_APPLICATION_KEY_ID='...'
  export B2_APPLICATION_KEY='...'
```

**Wizard Relationship:**
```
Option A (Recommended):
└─ kopi-docka setup
   ├─ 1. Dependency check
   ├─ 2. Config wizard (admin config new internally)
   │      ├─ Select backend
   │      ├─ Configure backend
   │      └─ Password setup
   ├─ 3. Repository init
   └─ 4. Connection test

Option B (Manual):
├─ kopi-docka doctor            # Check system health
├─ kopi-docka admin config new  # Create configuration
│      ├─ Select backend
│      ├─ Configure backend
│      └─ Password setup
├─ kopi-docka admin config edit # (optional)
└─ kopi-docka admin repo init   # Initialize repository
```

---

## Configuration

### Create Config File

**Recommended:** Use the interactive config wizard:
```bash
sudo kopi-docka admin config new
# Or as part of complete setup:
sudo kopi-docka setup
```

The wizard guides you through:
- ✅ Backend selection (interactive menu)
- ✅ Backend-specific settings
- ✅ Password setup (secure)
- ✅ Automatic config generation

---

### Config File Locations

Kopi-Docka v3.0+ uses **JSON format**:

**Standard paths** (in order):
1. `/etc/kopi-docka.json` (system-wide, recommended for servers)
2. `~/.config/kopi-docka/config.json` (user-specific)

**Custom path:**
```bash
kopi-docka --config /path/to/config.json <command>
```

### Config Example

```json
{
  "version": "3.0",
  "kopia": {
    "kopia_params": "filesystem --path /backup/kopia-repository",
    "password": "your-secure-password",
    "password_file": null,
    "compression": "zstd",
    "encryption": "AES256-GCM-HMAC-SHA256",
    "cache_directory": "/var/cache/kopi-docka"
  },
  "backup": {
    "base_path": "/backup/kopi-docka",
    "parallel_workers": "auto",
    "stop_timeout": 30,
    "start_timeout": 60,
    "task_timeout": 0,
    "update_recovery_bundle": false,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3,
    "exclude_patterns": [],
    "hooks": {
      "pre_backup": "/opt/hooks/pre-backup.sh",
      "post_backup": "/opt/hooks/post-backup.sh",
      "pre_restore": "/opt/hooks/pre-restore.sh",
      "post_restore": "/opt/hooks/post-restore.sh"
    }
  },
  "docker": {
    "socket": "/var/run/docker.sock",
    "compose_timeout": 300
  },
  "retention": {
    "latest": 10,
    "hourly": 0,
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
    "annual": 3
  },
  "logging": {
    "level": "INFO",
    "file": "/var/log/kopi-docka.log",
    "max_size_mb": 100,
    "backup_count": 5
  },
  "notifications": {
    "enabled": false,
    "service": null,
    "url": null,
    "secret": null,
    "secret_file": null,
    "on_success": true,
    "on_failure": true
  }
}
```

### Important Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `kopia_params` | Kopia repository parameters | `filesystem --path /backup/...` |
| `password` | Repository password | `CHANGE_ME_...` |
| `compression` | Compression | `zstd` |
| `parallel_workers` | Backup threads | `auto` (based on RAM/CPU) |
| `stop_timeout` | Container stop timeout (sec) | `30` |
| `start_timeout` | Container start timeout (sec) | `60` |
| `task_timeout` | Volume backup timeout (0=unlimited) | `0` |
| `exclude_patterns` | Tar exclude patterns (array) | `[]` |
| `update_recovery_bundle` | DR bundle with every backup | `false` |
| `recovery_bundle_retention` | DR bundles to keep | `3` |
| `retention.latest` | Latest snapshots to keep | `10` |
| `retention.hourly` | Hourly backups to keep | `0` |
| `retention.daily` | Daily backups to keep | `7` |
| `retention.weekly` | Weekly backups | `4` |
| `retention.monthly` | Monthly backups | `12` |
| `retention.annual` | Annual backups to keep | `3` |

---

## Retention Policies

### How Retention Policies Work

Retention policies control **how many snapshots to keep** for each backup target. Kopia automatically deletes older snapshots based on your retention settings.

**Example configuration:**
```json
"retention": {
  "latest": 3,     // Keep last 3 snapshots regardless of age
  "daily": 7,      // Keep 1 snapshot per day for last 7 days
  "weekly": 4,     // Keep 1 snapshot per week for last 4 weeks
  "monthly": 12,   // Keep 1 snapshot per month for last 12 months
  "annual": 3      // Keep 1 snapshot per year for last 3 years
}
```

### Path Matching Behavior

**IMPORTANT:** Retention policies are **path-based** in Kopia. The snapshot's source path must match exactly for retention to work.

#### Direct Mode (Default since v5.0)

**Volume backups:**
- Snapshots are created from actual Docker volume mountpoints
- Example path: `/var/lib/docker/volumes/myproject_data/_data`
- Retention policies are automatically applied to these **actual mountpoints**

**Recipe and network backups:**
- Use stable staging directories (since v5.3.0)
- Recipe path: `/var/cache/kopi-docka/staging/recipes/<unit-name>/`
- Network path: `/var/cache/kopi-docka/staging/networks/<unit-name>/`

**Example:**
```bash
# Backup creates snapshots with these paths:
/var/lib/docker/volumes/webapp_data/_data         # Volume
/var/lib/docker/volumes/webapp_db/_data           # Volume
/var/cache/kopi-docka/staging/recipes/webapp/     # Recipe
/var/cache/kopi-docka/staging/networks/webapp/    # Network

# Retention policy "latest: 3" is applied to EACH path independently
# After 4 backups, each path keeps only its 3 newest snapshots
```

#### TAR Mode (Legacy)

**Volume backups:**
- Snapshots created via tar streams
- Uses virtual paths like `volumes/myproject`
- Retention policies are applied to these **virtual paths**

**Recipe and network backups:**
- Same as Direct Mode (stable staging paths)

### Critical Fix in v5.3.0

Prior to v5.3.0, there was a critical bug where:
- ❌ Direct Mode: Retention policies were applied to virtual paths (`volumes/myproject`)
- ❌ But snapshots were created with actual mountpoints (`/var/lib/docker/volumes/...`)
- ❌ Result: **Path mismatch** → retention never triggered → repositories grew unbounded

**Fixed in v5.3.0:**
- ✅ Direct Mode retention policies now correctly applied to actual mountpoints
- ✅ Recipe/network metadata uses stable staging paths (no more random temp dirs)
- ✅ Retention policies work correctly in both modes
- ✅ Old snapshots are automatically deleted per your settings

### No Action Required

**If you're using v5.3.0 or later:**
- ✅ Retention policies work automatically
- ✅ No configuration changes needed
- ✅ Works correctly for both Direct Mode and TAR Mode
- ✅ Mixed repositories (old TAR + new Direct backups) are handled correctly

**Path matching happens automatically** based on your backup format setting. Just configure your desired retention values in the config file.

---

## Notifications

**NEW in v5.4.0** 🔔

Kopi-Docka can automatically send notifications about backup status to popular messaging platforms.

### Quick Setup

Use the interactive wizard:
```bash
sudo kopi-docka advanced notification setup
```

The wizard guides you through:
1. Service selection (Telegram, Discord, Email, Webhook, Custom)
2. Service configuration
3. Secret storage (secure file-based or config-based)
4. Test notification

### Management Commands

```bash
# Send test notification
sudo kopi-docka advanced notification test

# Check current status
sudo kopi-docka advanced notification status

# Enable/disable notifications
sudo kopi-docka advanced notification disable
sudo kopi-docka advanced notification enable
```

### Configuration

Add to your `config.json`:

```json
{
  "notifications": {
    "enabled": true,
    "service": "telegram",
    "url": "987654321",
    "secret": null,
    "secret_file": "/etc/kopi-docka-telegram-token",
    "on_success": true,
    "on_failure": true
  }
}
```

### Supported Services

| Service | Description | Use Case |
|---------|-------------|----------|
| `telegram` | Telegram Bot | Personal notifications, free |
| `discord` | Discord Webhook | Team notifications |
| `email` | SMTP Email | Enterprise, audit trails |
| `webhook` | Generic Webhook | Automation (n8n, Make, Zapier) |
| `custom` | Apprise URL | 100+ services (Slack, Matrix, etc.) |

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Enable/disable notifications |
| `service` | string | Service type (see table above) |
| `url` | string | Service URL/identifier (supports `${ENV_VAR}`) |
| `secret` | string | Token/password in config (less secure) |
| `secret_file` | string | Path to secret file (recommended) |
| `on_success` | boolean | Notify on backup success (default: true) |
| `on_failure` | boolean | Notify on backup failure (default: true) |

### Examples

**Telegram:**
```json
{
  "notifications": {
    "enabled": true,
    "service": "telegram",
    "url": "987654321",
    "secret_file": "/etc/kopi-docka-telegram-token"
  }
}
```

**Discord:**
```json
{
  "notifications": {
    "enabled": true,
    "service": "discord",
    "url": "https://discord.com/api/webhooks/123456/TOKEN"
  }
}
```

**Email:**
```json
{
  "notifications": {
    "enabled": true,
    "service": "email",
    "url": "mailto://user@smtp.gmail.com:587?to=admin@example.com&from=Kopi-Docka%20%3Cuser@gmail.com%3E",
    "secret_file": "/etc/kopi-docka-email-password"
  }
}
```

**Webhook:**
```json
{
  "notifications": {
    "enabled": true,
    "service": "webhook",
    "url": "https://your-automation.com/webhook/abc123"
  }
}
```

### Key Features

- **Fire-and-forget** - Notifications never block backups
- **10-second timeout** - Protection against slow services
- **3-way secret management** - File (secure) > Config > None
- **Environment variables** - Use `${VAR_NAME}` in URLs
- **Selective notifications** - Control success/failure separately

### Detailed Documentation

For complete setup guides, troubleshooting, and examples, see:
**[📖 Notifications Documentation](NOTIFICATIONS.md)**

---

## Storage Backends

Kopi-Docka supports 8 different backends. The **config wizard** (`admin config new`) interactively guides you through backend selection and configuration!

**Backend selection in wizard:**
```
Available backends:
  1. Local Filesystem  - Store on local disk/NAS mount
  2. AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)
  3. Backblaze B2     - Cost-effective cloud storage
  4. Azure Blob       - Microsoft Azure storage
  5. Google Cloud     - GCS storage
  6. SFTP             - Remote server via SSH
  7. Tailscale        - Peer-to-peer over private network
  8. Rclone           - 50+ cloud providers (Drive, OneDrive, Dropbox)
```

For each backend, the wizard queries necessary settings and generates the correct `kopia_params` config.

---

### Backend Overview

Here are manual `kopia_params` examples (if you edit config directly):

#### 1. Local Filesystem
```json
"kopia_params": "filesystem --path /backup/kopia-repository"
```

#### 2. AWS S3 (+ Wasabi, MinIO)
```json
"kopia_params": "s3 --bucket my-bucket --prefix kopia"
```
**Environment variables:**
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

#### 3. Backblaze B2
```json
"kopia_params": "b2 --bucket my-bucket --prefix kopia"
```
**Environment variables:**
```bash
export B2_APPLICATION_KEY_ID="..."
export B2_APPLICATION_KEY="..."
```

#### 4. Azure Blob
```json
"kopia_params": "azure --container my-container --prefix kopia"
```

#### 5. Google Cloud Storage
```json
"kopia_params": "gcs --bucket my-bucket --prefix kopia"
```

#### 6. SFTP
```json
"kopia_params": "sftp --path user@server:/path/to/repo"
```

#### 7. Tailscale
**P2P backups over your private network**

```json
"kopia_params": "sftp --path sftp://root@backup-server.tailnet:/backup/kopia"
```

**What the wizard does:**
1. Checks Tailscale connection
2. **Shows all peers** with:
   - Online status (🟢/🔴)
   - Free disk space
   - Latency/ping
3. **Automatically sets up SSH key**:
   - Generates ED25519 key
   - Copies to target server
   - Passwordless SSH
4. Tests connection

**Example output:**
```bash
sudo kopi-docka admin config new

Available Backup Targets
┌──────────┬─────────────────┬────────────────┐
│ Status   │ Hostname        │ IP             │
├──────────┼─────────────────┼────────────────┤
│ 🟢 Online│ cloud-vps      │ 100.64.0.5     │
│ 🟢 Online│ home-nas       │ 100.64.0.12    │
│ 🔴 Offline│ raspberrypi   │ 100.64.0.8     │
└──────────┴─────────────────┴────────────────┘

Select peer: home-nas

Backup path on remote [/backup/kopi-docka]: /mnt/nas/backups

Setup SSH key for passwordless access? Yes
✓ SSH key generated
✓ SSH key copied to home-nas
✓ Connection successful

✓ Configuration saved!
```

**Features:**
- No cloud costs
- No port forwarding needed
- End-to-end encrypted (WireGuard + Kopia)
- Direct P2P connection
- Automatic configuration

**Requirements:**
- Tailscale on both servers: `curl -fsSL https://tailscale.com/install.sh | sh`
- Both in the same Tailnet
- SSH access to backup server (one-time for key setup)

**More details:** See README.md - Tailscale Integration section

---

#### 8. Rclone (Cloud Storage)
**Support for 50+ cloud providers via Rclone**

```json
"kopia_params": "rclone --remote-path=gdrive:kopia-backup"
```

**What it supports:**
- Google Drive, OneDrive, Dropbox
- Box, pCloud, Mega
- 50+ other cloud providers supported by Rclone

**Prerequisites:**
```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure rclone (as your regular user, not root!)
rclone config
```

---

##### Using Rclone with Sudo (Important!)

When running `sudo kopi-docka admin config new`, the application needs to access your rclone configuration. Due to permission restrictions, you may encounter warnings if the config is only readable by your user.

**Config Detection Priority:**
1. `/home/YOUR_USER/.config/rclone/rclone.conf` (when using sudo)
2. `/root/.config/rclone/rclone.conf` (when running as root)

**⚠️ Permission Issues:**

If you see this warning:
```
WARNING: Rclone configuration found but not readable!
  Found: /home/username/.config/rclone/rclone.conf
  Status: Permission denied (running as root via sudo)
```

**Solution - Choose one workaround:**

1. **Preserve environment (Recommended):**
   ```bash
   sudo -E kopi-docka admin config new
   ```
   The `-E` flag preserves your user environment, allowing access to your rclone config.

2. **Make config readable by root:**
   ```bash
   chmod 644 ~/.config/rclone/rclone.conf
   sudo kopi-docka admin config new
   ```
   This allows root to read your config file.

3. **Copy config to root's home:**
   ```bash
   sudo cp ~/.config/rclone/rclone.conf /root/.config/rclone/
   sudo kopi-docka admin config new
   ```
   Creates a separate config for root (requires manual updates if you change rclone settings).

**Best Practice:**
- Run `rclone config` as your **regular user** (not with sudo)
- Use `sudo -E` when running kopi-docka commands
- Keep OAuth tokens fresh by using the original config (option 1 or 2)

**Example workflow:**
```bash
# 1. Configure rclone as regular user
rclone config
# Follow prompts to set up Google Drive, OneDrive, etc.

# 2. Test rclone connection
rclone lsd gdrive:

# 3. Run kopi-docka with -E flag
sudo -E kopi-docka admin config new
# Select Rclone backend
# Enter remote path: gdrive:kopia-backup

# 4. Verify connection
sudo -E kopi-docka admin repo status
```

**Why preserve user config?**
- **OAuth tokens**: Cloud providers like Google Drive use OAuth tokens that expire. Using the original config keeps tokens fresh.
- **Settings preserved**: Custom settings (like `root_folder_id` for Google Drive) remain intact.
- **Single source of truth**: No duplicate configs to maintain.

---

[← Back to README](../README.md)
