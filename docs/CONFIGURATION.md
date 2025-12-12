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
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
    "yearly": 5
  },
  "logging": {
    "level": "INFO",
    "file": "/var/log/kopi-docka.log",
    "max_size_mb": 100,
    "backup_count": 5
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
| `retention.daily` | Daily backups to keep | `7` |
| `retention.weekly` | Weekly backups | `4` |
| `retention.monthly` | Monthly backups | `12` |
| `retention.yearly` | Yearly backups | `5` |

---

## Storage Backends

Kopi-Docka supports 7 different backends. The **config wizard** (`admin config new`) interactively guides you through backend selection and configuration!

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
┌──────────┬─────────────────┬────────────────┬─────────────┬──────────┐
│ Status   │ Hostname        │ IP             │ Disk Free   │ Latency  │
├──────────┼─────────────────┼────────────────┼─────────────┼──────────┤
│ 🟢 Online│ cloud-vps      │ 100.64.0.5     │ 450.2GB     │ 23ms     │
│ 🟢 Online│ home-nas       │ 100.64.0.12    │ 2.8TB       │ 45ms     │
│ 🔴 Offline│ raspberry-pi   │ 100.64.0.8     │ 28.5GB      │ -        │
└──────────┴─────────────────┴────────────────┴─────────────┴──────────┘

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

[← Back to README](../README.md)
