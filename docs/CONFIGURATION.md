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

### 2. Config Wizard (`advanced config new`)
**For:** Create/recreate config only

```bash
sudo kopi-docka advanced config new
```

**What it does:**
1. **Backup Scope Selection** - Choose what to backup:
   ```
   1. minimal  - Volumes only (fastest, smallest)
               ⚠️  Cannot restore containers, only data!
   2. standard - Volumes + Recipes + Networks [RECOMMENDED]
               ✅ Full container restore capability
   3. full     - Everything + Docker daemon config (DR-ready)
               ✅ Complete disaster recovery capability
   ```

2. **Backend Selection** - Interactive menu:
   ```
   1. Local Filesystem  - Local disk/NAS
   2. AWS S3           - S3-compatible (Wasabi, MinIO)
   3. Backblaze B2     - Affordable, recommended!
   4. Azure Blob       - Microsoft Azure
   5. Google Cloud     - GCS
   6. SFTP             - Remote via SSH
   7. Tailscale        - Peer-to-peer over private network
   8. Rclone           - Universal (70+ cloud providers)
   ```

3. **Backend Configuration** - Queries backend-specific values:
   - Local: Repository path
   - S3: Bucket, region, endpoint (optional)
   - B2: Bucket, prefix
   - Azure: Container, storage account
   - GCS: Bucket, prefix
   - SFTP: Host, user, path
   - Tailscale: Peer selection (automatically detected)
   - Rclone: Remote name and path

4. **Existing Repository Detection:**
   - If a repository already exists at the configured location:
     ```
     ⚠️  Existing Repository Detected
     
     Options:
       1 - Enter existing password (connect to repository)
       2 - Delete repository and start fresh
     ```
   - Option 1: Enter existing password (validated with 3 attempts)
   - Option 2: Delete repository after confirmation

5. **Password Setup** (for new repositories only):
   ```
   1. Secure random password (recommended)
   2. Enter custom password
   ```

6. **Save Config** as CONF:
   - Root: `/etc/kopi-docka.conf` + `/etc/.kopi-docka.password`
   - User: `~/.config/kopi-docka/config.conf` + `~/.config/kopi-docka/.config.password`

**When to use:**
- Create new config
- Switch backend
- After manual config reset

**Example (B2 Backend with new repository):**
```bash
sudo kopi-docka advanced config new

# Step 1: Backup Scope
Select backup scope [2]:
→ 2 (standard - recommended)

# Step 2: Backend Selection
Where should backups be stored?
→ 3 (Backblaze B2)

# Step 3: Backend Configuration
Bucket name: my-backup-bucket
Path prefix: kopia

# Step 4: No existing repository detected

# Step 5: Password setup
Generate secure random password?
→ Yes

✓ Configuration created: /etc/kopi-docka.conf
  Backup scope: standard
  kopia_params: b2 --bucket my-backup-bucket --prefix kopia
  Password file: /etc/.kopi-docka.password

⚠️ Set environment variables:
  export B2_APPLICATION_KEY_ID='...'
  export B2_APPLICATION_KEY='...'

Next Steps:
  1. Initialize repository: sudo kopi-docka advanced repo init
  2. Test backup: sudo kopi-docka dry-run
```

**Example (Existing Repository):**
```bash
sudo kopi-docka advanced config new

# Step 1-3: Scope and backend configuration...

# Step 4: Existing repository detected!
⚠️  Existing Kopia repository detected!
Location: /backup/kopia-repository

Options:
  1 - Enter existing password (connect to repository)
  2 - Delete repository and start fresh

Select option [1]: 1

# Validate existing password
Enter existing repository password: ****
Validating password...
✓ Password correct! Successfully connected.

✓ Configuration created: /etc/kopi-docka.conf
  Connected to existing repository

Next Steps:
  1. List Docker containers: sudo kopi-docka advanced snapshot list
  2. Test backup: sudo kopi-docka dry-run
```

**Wizard Relationship:**
```
Option A (Recommended):
└─ kopi-docka setup
   ├─ 1. Dependency check
   ├─ 2. Config wizard (advanced config new internally)
   │      ├─ Backup scope selection (minimal/standard/full)
   │      ├─ Select backend (filesystem/S3/B2/...)
   │      ├─ Configure backend (paths, buckets, etc.)
   │      ├─ Detect existing repository
   │      └─ Password setup (new or existing)
   ├─ 3. Repository init (if needed)
   └─ 4. Connection test

Option B (Manual):
├─ kopi-docka doctor            # Check system health
├─ kopi-docka advanced config new  # Create configuration
│      ├─ Backup scope selection
│      ├─ Select backend
│      ├─ Configure backend
│      ├─ Detect existing repository
│      └─ Password setup (validated if existing)
├─ kopi-docka advanced config edit # (optional)
└─ kopi-docka advanced repo init   # Initialize repository (if new)
```

---

## Configuration

### Create Config File

**Recommended:** Use the interactive config wizard:
```bash
sudo kopi-docka advanced config new
# Or as part of complete setup:
sudo kopi-docka setup
```

The wizard guides you through:
- ✅ Backup scope selection (what to backup)
- ✅ Backend selection (where to store backups)
- ✅ Backend-specific settings (paths, buckets, etc.)
- ✅ Existing repository detection (automatic)
- ✅ Password setup (validated for existing repos)
- ✅ Automatic config generation (.conf + .password file)

---

### Config File Locations

Kopi-Docka uses **INI/CONF format** with separate password file:

**Standard paths** (in order):
1. `/etc/kopi-docka.conf` (system-wide, recommended for servers)
   - Password: `/etc/.kopi-docka.password` (chmod 600)
2. `~/.config/kopi-docka/config.conf` (user-specific)
   - Password: `~/.config/kopi-docka/.config.password` (chmod 600)

**Custom path:**
```bash
kopi-docka --config /path/to/config.conf <command>
```

**Password storage:**
- By default, passwords are stored in a separate file (`.kopi-docka.password`)
- Password file is automatically created with chmod 600 (owner read/write only)
- Alternatively, password can be stored inline in the config (not recommended)

### Config Example

```json
{
  "kopia": {
    "kopia_params": "filesystem --path /backup/kopia-repository",
    "password_file": "/etc/.kopi-docka.password",
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
    "backup_scope": "standard",
    "update_recovery_bundle": false,
    "recovery_bundle_path": "/backup/recovery",
    "recovery_bundle_retention": 3,
    "exclude_patterns": ["*.tmp", "*.log", "cache/*"]
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
    "on_success": true,
    "on_failure": true
  }
}
```

**Password file example** (`/etc/.kopi-docka.password`):
```
your-secure-generated-password-here
```

**Hooks configuration** (optional, add to config):
```json
{
  "hooks": {
    "pre_backup": "/opt/hooks/pre-backup.sh",
    "post_backup": "/opt/hooks/post-backup.sh",
    "pre_restore": "/opt/hooks/pre-restore.sh",
    "post_restore": "/opt/hooks/post-restore.sh"
  }
}
```

### Migrating an older config

When a new kopi-docka release adds keys to the config schema, an existing
`kopi-docka.json` keeps working — missing keys fall back to the schema's
default, and removed keys (e.g. `backup.parallel_workers` after v7.3.0)
are silently ignored. But if you want your file to match the current
template, there's a helper script that ships in the source tree and is
also published as a single file on GitHub:

```bash
# Download (one-time). The chmod is on the same line because `curl -o`
# does NOT set the execute bit.
sudo curl -fsSL -o /usr/local/bin/kopi-docka-migrate-config \
  https://raw.githubusercontent.com/TZERO78/kopi-docka/main/scripts/migrate-config.sh \
  && sudo chmod +x /usr/local/bin/kopi-docka-migrate-config

# Or run it directly from GitHub (no install needed):
curl -fsSL https://raw.githubusercontent.com/TZERO78/kopi-docka/main/scripts/migrate-config.sh \
  | sudo bash -s -- [--config /etc/kopi-docka.json] [OPTIONS]

# Or — if you've cloned the repo — from the source tree:
scripts/migrate-config.sh [--config /etc/kopi-docka.json] [OPTIONS]
```

**`--config` is optional.** If omitted, the script probes the same
defaults kopi-docka itself uses, in this order:

1. `$HOME/.config/kopi-docka/config.json` (honors `$SUDO_USER` under
   sudo, so you get the invoking user's config, not root's)
2. `/etc/kopi-docka.json`

**Version banner.** Every run prints the installed kopi-docka version
and binary path up front so you can confirm which release the
migration is checking against:

```
kopi-docka installed: 7.3.3  (/usr/local/bin/kopi-docka)
```

If kopi-docka isn't on `PATH`, the banner says so and the GitHub raw
template fallback takes over. In that mode the template reflects
whatever is on the `main` branch — usually fine, but pass
`--template` if you need to pin to a specific release.

**Template auto-location.** Strategies tried, in order: an explicit
`--template` flag, the default `python3 -c 'import kopi_docka'`, the
python from `kopi-docka`'s own shebang (handles pipx and venv installs
where `/usr/bin/python3` can't import the package), and a GitHub raw
fallback. Each failed step explains why so you know what to fix.

**What it does**

It reads two files: your config and the `config_template.json` that
ships with the installed kopi-docka. It compares the **key paths**
present in each (it does not look at values, so your password and
`kopia_params` are never touched), and reports three categories:

| Category | Meaning | Default action |
|---|---|---|
| Missing | Path in the template, not in your file. | Added with the template default. |
| Unknown | Path in your file, not in the template (deprecated keys *or* your own additions). | Kept. Add `--prune-unknown` to remove. |
| Type mismatch | Same path, different JSON type. *Exception:* `null` in the template against a scalar in your config is **not** flagged — `null` in the template marks a "not configured yet" slot (e.g. `kopia.password_file`, `notifications.url`). | Left alone, flagged in the report — review manually. |

**Known legacy renames worth knowing**

A few "Unknown" entries you may see are not custom additions but old
names that kopi-docka renamed. The script doesn't rename them
automatically (it has no opinions about your data), but you can
`--prune-unknown` once you've copied the value into the new key:

| Legacy key (in your config) | New name | Since |
|---|---|---|
| `retention.yearly`           | `retention.annual`         | very early — value semantics identical |
| `backup.pre_backup_hook`     | `backup.hooks.pre_backup`  | 5.x |
| `backup.post_backup_hook`    | `backup.hooks.post_backup` | 5.x |
| `backup.parallel_workers`    | *(removed)*                | v7.3.0 / Plan 0028 — sequential loop |
| `backup.task_timeout`        | *(removed)*                | v7.3.0 / Plan 0028 — sequential loop |

**Important properties**

- **Nothing you wrote is overwritten.** The merge is `template * user`
  in jq terms — user values always win.
- **A timestamped backup is written.** Default location is the same
  directory as the input (`kopi-docka.json.backup-YYYYMMDD-HHMMSS`).
  Disable with `--no-backup` (not recommended).
- **The template is read from the installed package**, not hard-coded.
  Upgrade kopi-docka, then re-run the script and the new release's
  keys show up automatically.

**Common flags** (substitute `kopi-docka-migrate-config` /
`scripts/migrate-config.sh` / `curl …| sudo bash -s --` for the
invocation style you prefer):

```bash
# 1) Show the diff without writing anything
kopi-docka-migrate-config --config /etc/kopi-docka.json --dry-run

# 2) Apply (recommended first run)
sudo kopi-docka-migrate-config --config /etc/kopi-docka.json

# 3) Also drop keys the template no longer has
sudo kopi-docka-migrate-config --config /etc/kopi-docka.json --prune-unknown

# 4) Override template location (e.g. when running against a
#    user-local install)
kopi-docka-migrate-config \
    --config /home/me/kopi-docka.json \
    --template /opt/kopi-docka-venv/lib/python3.12/site-packages/kopi_docka/templates/config_template.json
```

**Pre-flight check**

After the migration, run a sanity check:

```bash
sudo kopi-docka --config /etc/kopi-docka.json doctor
```

If anything looks off, the original file is one `cp` away.

---

### Configuration Validation

**Since v5.6.0:** Kopi-Docka uses **Pydantic** for automatic configuration validation.

**Benefits:**
- ✅ **Early error detection** - Invalid configs fail at startup, not during backup
- ✅ **Clear error messages** - Shows exactly what's wrong and where
- ✅ **Type safety** - Ensures values have correct types (string, int, bool)
- ✅ **Range validation** - Checks values are within sensible limits

**Example error message:**
```
Configuration validation failed:
  • backup -> parallel_workers: Value error, parallel_workers must be 'auto' or 1-32
  • kopia -> kopia_params: Invalid repository type 'xyz'. Must be one of: filesystem, rclone, s3, ...

Fix the errors in: /etc/kopi-docka.conf
```

**Validated fields include:**
- Repository type must be valid (filesystem, rclone, s3, b2, azure, gcs, sftp, webdav)
- Backup scope must be: minimal, standard, or full
- Parallel workers: "auto" or 1-32
- Timeouts: 1-600 seconds
- Retention values: within sensible limits
- Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL

---

### Important Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `kopia_params` | Kopia repository parameters | `filesystem --path /backup/...` |
| `password` | Repository password | `CHANGE_ME_...` |
| `compression` | Compression | `zstd` |
| `rclone_startup_timeout` | Timeout for `rclone serve` subprocess spawn (rclone backend only). Kopia's 15s default is unreliable on cold starts against GDrive. Go duration string. | `120s` |
| `parallel_workers` | Backup threads | `auto` (based on RAM/CPU) |
| `stop_timeout` | Container stop timeout (sec) | `30` |
| `start_timeout` | Container start timeout (sec) | `60` |
| `task_timeout` | Volume backup timeout (0=unlimited) | `0` |
| `exclude_patterns` | Tar exclude patterns (array) | `[]` |
| `backup_scope` | What to backup: `minimal` (volumes only), `standard` (volumes+recipes+networks), `full` (everything+docker_config) | `standard` |
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

### Historical: Path-Mismatch Fix (v5.3.0)

A pre-v5.3.0 bug applied retention to virtual paths (`volumes/myproject`)
while snapshots used actual mountpoints (`/var/lib/docker/volumes/...`),
so retention never triggered and repositories grew unbounded. v5.3.0
realigned both. Plan 0028 (v7.3.0) makes the path issue moot entirely:
retention is global, so the per-path matching question never comes up.

---

### Global Retention Policy (since v7.3.0 / Plan 0028)

Kopi-Docka writes **one** Kopia retention policy: the global one, applied at
`kopia repository initialize()` and at every `kopia repository connect()`
(idempotent — Kopia treats identical `--global` writes as a no-op). Every
snapshot inherits that global policy via Kopia's policy tree
(`--global` → `@host` → `user@host` → `user@host:/path`), so no per-path
overrides are needed.

**Why this matters on rclone/GDrive backends**: `kopia policy set` is a
metadata round-trip that costs 15–40 s on a cold rclone start. Pre-v7.3.0
kopi-docka wrote one per volume on every backup, which dominated runtime
on multi-unit setups. v7.3.0 collapses all that to a single
`apply_global_defaults()` call on connect.

**Changing retention**: edit the values in your `kopi-docka.json` config
under `retention:` and re-run any kopi-docka command that opens the repo
(e.g. `kopi-docka doctor`). The new values land on the next connect.

**Manual overrides**: `kopia policy set <path> ...` from the CLI keeps
working — Kopia merges per-path on top of global. kopi-docka itself no
longer writes per-path entries, so anything you set manually is yours.

**Legacy cleanup**: upgrading from a pre-v7.3.0 install? Run
`kopi-docka advanced policy prune` once. `kopi-docka doctor` flags any
leftover per-path entries as "Legacy Per-Path Policies" with the same
hint.

---

### rclone Backend Tuning (since v7.2.0)

Kopia's `rclone` backend (`[Not maintained]` per Kopia upstream) spawns `rclone serve` as a subprocess for each kopia invocation. The default `startupTimeout` is 15s, which is unreliable on cold starts against Google Drive — the rclone-serve startup plus OAuth refresh plus first API call routinely exceeds 15s and produces:

```
unable to start rclone: timed out waiting for rclone to start
```

**Fix**: kopi-docka now defaults to `120s` and persists this into the Kopia repo config (`storage.config.startupTimeout`) so subsequent kopia calls use it too. Existing installs are migrated automatically on first run after upgrade — look for `Migrated rclone startupTimeout 15s → 120s` in the log.

**Override**:
```json
"kopia": {
  "rclone_startup_timeout": "300s"
}
```

Go duration string (`"60s"`, `"2m"`, `"5m"`, etc.).

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

Kopi-Docka supports 8 different backends. The **config wizard**
(`advanced config new`) interactively guides you through backend
selection and configuration!

> **Performance reality check.** Not all backends are equal under the
> hood. Kopia's own CLI docs mark the **rclone** backend as
> `[Not maintained]`, and on a Google Drive repository it's measurably
> ~30–60× slower than SFTP (e.g. via Tailscale) for the same workload —
> see [TROUBLESHOOTING.md → "Backups against rclone+Google Drive feel
> very slow"](TROUBLESHOOTING.md#-backups-against-rclonegoogle-drive-feel-very-slow)
> for numbers and forum links. If you have any choice in the matter,
> prefer **Tailscale → SFTP**, **Backblaze B2**, **S3-compatible**, or
> **native SFTP/WebDAV** over rclone. rclone stays as a fallback for
> providers Kopia doesn't natively support.

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
sudo kopi-docka advanced config new

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

When running `sudo kopi-docka advanced config new`, the application needs to access your rclone configuration. Due to permission restrictions, you may encounter warnings if the config is only readable by your user.

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
   sudo -E kopi-docka advanced config new
   ```
   The `-E` flag preserves your user environment, allowing access to your rclone config.

2. **Make config readable by root:**
   ```bash
   chmod 644 ~/.config/rclone/rclone.conf
   sudo kopi-docka advanced config new
   ```
   This allows root to read your config file.

3. **Copy config to root's home:**
   ```bash
   sudo cp ~/.config/rclone/rclone.conf /root/.config/rclone/
   sudo kopi-docka advanced config new
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
sudo -E kopi-docka advanced config new
# Select Rclone backend
# Enter remote path: gdrive:kopia-backup

# 4. Verify connection
sudo -E kopi-docka advanced repo status
```

**Why preserve user config?**
- **OAuth tokens**: Cloud providers like Google Drive use OAuth tokens that expire. Using the original config keeps tokens fresh.
- **Settings preserved**: Custom settings (like `root_folder_id` for Google Drive) remain intact.
- **Single source of truth**: No duplicate configs to maintain.

---

## Security Best Practices

### Use a password file — not inline passwords

Storing the repository password directly in the config exposes it to anyone who can read the file. Use `password_file` instead:

```json
{
  "kopia": {
    "password_file": "/etc/.kopi-docka.password"
  }
}
```

```bash
# Create the password file with strict permissions
echo "your-secure-password" | sudo tee /etc/.kopi-docka.password
sudo chmod 600 /etc/.kopi-docka.password
sudo chown root:root /etc/.kopi-docka.password
```

The config wizard (`advanced config new`) creates this file automatically with the correct permissions.

### Protect your config file

The config file should only be readable by root:

```bash
sudo chmod 600 /etc/kopi-docka/kopi-docka.conf
sudo chown root:root /etc/kopi-docka/kopi-docka.conf
```

The `doctor` command checks config file permissions and will warn you if they are too open.

### Protect your rclone config

If you use the rclone backend, the rclone config often contains cloud credentials:

```bash
chmod 600 ~/.config/rclone/rclone.conf
```

Kopi-Docka warns on startup if the rclone config is readable by group or others.

### Hook script security

Hook scripts must be owned by root (or the running user) and must not be world-writable or symlinks. Kopi-Docka refuses to execute hooks that do not meet these requirements:

- Owner must be `root` or the current process UID
- File must not be world-writable (`chmod o-w`)
- File must not be a symlink

See [HOOKS.md](HOOKS.md) for full guidance.

### Run as root only where needed

Most read-only commands (`advanced repo status`, `advanced config show`, `doctor`) can be run as a regular user if the config file is readable. Only backup, restore, and setup require root (for Docker socket access and volume mounts).

---

[← Back to README](../README.md)
