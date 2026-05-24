[← Back to README](../README.md)

# Troubleshooting

## 🔧 Troubleshooting

### ❌ "Unknown flag" or Parameter Errors

**Problem:** Kopia throws "unknown long flag" or "unknown flag" errors after updates.

**Example:**
```
Error: unknown flag: --rclone-config
```

**Why:** Kopia sometimes changes its command-line interface between versions. For example:
- `--rclone-config` was replaced with `--rclone-args='--config=...'`

**Solution:** Kopi-Docka is designed to be flexible. You don't need to wait for a software update.

You can manually edit the raw configuration:
```bash
sudo kopi-docka advanced config edit
```

Find the `kopia_params` field and adjust flags according to Kopia's current syntax. Refer to Kopia's documentation for current flag syntax:
```bash
kopia repository create --help
# or
kopia repository connect --help
```

**Example fix for rclone:**
```json
{
  "kopia": {
    "kopia_params": "rclone --remote-path=myremote:backup --rclone-args='--config=/root/.config/rclone/rclone.conf'"
  }
}
```

**Permanent Fix:** Update Kopi-Docka when a new version is available:
```bash
pipx upgrade kopi-docka
# or
pip install --upgrade kopi-docka
```

---

### ❌ "No configuration found"

**Solution:**
```bash
sudo kopi-docka new-config
# or
sudo kopi-docka setup
```

### 🛠️ Existing config out of sync with a new release

After a kopi-docka upgrade your `kopi-docka.json` may be missing keys
that the new version's template added (e.g. `alerting.missed_backup`
landed in v7.1.0, `notifications.preflight_check` followed). Existing
values keep working — kopi-docka falls back to the schema default — but
running with an outdated file can mask new features.

There's a helper for that. It compares your file against the template
shipped with the installed kopi-docka, prints a clean diff, and (by
default) only **adds** missing keys; nothing existing is overwritten or
removed.

**One-shot from GitHub** (no clone needed; downloads + runs):

```bash
# Dry-run — show the diff, don't write anything
curl -fsSL https://raw.githubusercontent.com/TZERO78/kopi-docka/main/scripts/migrate-config.sh \
  | sudo bash -s -- --config /etc/kopi-docka.json --dry-run

# Apply — adds missing keys, writes a timestamped backup
curl -fsSL https://raw.githubusercontent.com/TZERO78/kopi-docka/main/scripts/migrate-config.sh \
  | sudo bash -s -- --config /etc/kopi-docka.json
```

**Or download it once and keep it on disk** (useful if you'd rather
review the script before running it). The `chmod` is on the same line
on purpose — `curl -o` leaves the file without the execute bit:

```bash
sudo curl -fsSL -o /usr/local/bin/kopi-docka-migrate-config \
  https://raw.githubusercontent.com/TZERO78/kopi-docka/main/scripts/migrate-config.sh \
  && sudo chmod +x /usr/local/bin/kopi-docka-migrate-config

# Then:
sudo kopi-docka-migrate-config --config /etc/kopi-docka.json --dry-run
sudo kopi-docka-migrate-config --config /etc/kopi-docka.json
```

> **Note**: The script auto-locates the `config_template.json` that
> ships with the installed kopi-docka. If kopi-docka was installed via
> `pipx` or into a venv that the default `python3` can't import from,
> the script will fall back to reading the python interpreter out of
> `kopi-docka`'s own shebang. If that also fails, it downloads the
> template directly from GitHub. You can always force a specific path
> with `--template /path/to/config_template.json`.

**From a source checkout** (if you cloned the repo):

```bash
scripts/migrate-config.sh --config /etc/kopi-docka.json --dry-run
sudo scripts/migrate-config.sh --config /etc/kopi-docka.json
```

The script's output groups changes into three buckets:

- **Missing** — added from template defaults.
- **Unknown** — present in your config but no longer in the template
  (`backup.parallel_workers`, `backup.task_timeout` after Plan 0028 /
  v7.3.0 are the common ones). **Kept by default** to avoid deleting
  your own custom keys. Add `--prune-unknown` to remove them.
- **Type mismatch** — same path, different JSON type. Never touched
  automatically; review and fix manually.

The script does not modify the password, `kopia_params`, or any other
value you already set — it only fills in defaults for keys you don't
have yet. If anything looks wrong, restore the `.backup-YYYYMMDD-HHMMSS`
file the script printed.

See [CONFIGURATION.md → "Migrating an older config"](CONFIGURATION.md#migrating-an-older-config) for the full reference.

### 🐌 "Backups against rclone+Google Drive feel very slow"

This is a **known upstream issue** with the Kopia ↔ rclone ↔ Google Drive
combination, not a kopi-docka bug. The Kopia project itself marks the
rclone backend as `[Not maintained]` in its CLI docs, and other users
on the Kopia forum report identical symptoms.

**Typical numbers** (from forum reports plus our own measurements):

| Operation                              | rclone+GDrive | SFTP (e.g. via Tailscale) |
|----------------------------------------|---------------|---------------------------|
| First `kopia repository status` (cold) | 60–120 s      | < 1 s                     |
| Single `kopia policy set --global`     | 30–300 s      | ~ 0.5 s                   |
| Maintenance ops on a 100 GB repo       | 40+ minutes   | seconds                   |
| Per-snapshot fixed overhead            | 1–5 minutes   | sub-second                |

**Why it's slow**: Kopia spawns a fresh `rclone serve` subprocess for
each invocation, and rclone has to re-auth against Google Drive every
time (OAuth refresh + first API call routinely take ≥60 s). On top of
that, GDrive's per-file write overhead is high — Kopia's manifest
commits, which are many small writes, hit it on every snapshot. The
sum is what you feel as "kopi-docka hangs".

**What kopi-docka v7.3.10 already does to soften it**:

- Single `is_connected()` per backup run (no `force_refresh` double-check).
- Rich spinner during the unavoidable cold-start with a
  "rclone cold-start can take 60-120 s on Google Drive" hint.
- `kopia policy set --global` is read-before-write (v7.3.9) — no write
  when nothing actually changed.
- `kopi-docka backup --dry-run` skips the repo status check entirely.

But the per-snapshot ~1–5 minutes of rclone overhead is **physical** —
we can't fix it from kopi-docka's side. Three realistic alternatives:

| Backend                       | Setup effort | Speed                       | Notes                                                                                                                                  |
|-------------------------------|--------------|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| **Tailscale → SFTP** (recommended) | small        | LAN-speed mesh              | If you already have a second machine (NAS, home server, second VPS) on Tailscale, this is the fastest path. Kopia uses SFTP natively, no rclone in sight. See [Tailscale Backend in CONFIGURATION.md](CONFIGURATION.md#storage-backends). |
| **Backblaze B2**              | small        | normal cloud bandwidth      | $6.95/TB/month, Kopia has native B2 support (no rclone). The cheapest "just works" cloud option for kopia.                                |
| **Native Kopia `gdrive`**     | medium       | ~5–10× faster than rclone    | Kopia has an experimental, non-rclone Google Drive backend. **Major caveat**: service-account auth only, and Google service accounts have a **30 GB Drive quota** — fine for small data, useless for larger repos. |

Sources (forum + upstream tracker):

- [Kopia Forum — "Very slow commands on rclone Google Drive repository"](https://kopia.discourse.group/t/very-slow-commands-on-rclone-google-drive-repository/2597)
- [GitHub kopia/kopia#2344 — "Slow backup process on GDrive"](https://github.com/kopia/kopia/issues/2344)
- [Kopia docs — repository connect rclone (\"[Not maintained]\")](https://kopia.io/docs/reference/command-line/common/repository-connect-rclone/)

### ❌ "invalid repository password"

**Cause:** Repository already exists with different password.

**Solution A (recommended):**
```bash
# Find old password (check config backup)
# Update config with correct password
sudo kopi-docka init
```

**Solution B (⚠️ DELETES BACKUPS):**
```bash
# Backup old repo first!
sudo mv /backup/kopia-repository /backup/kopia-repository.OLD
sudo kopi-docka init
```

### ⚠️ "No backup units found"

**Causes:**
- No Docker containers running
- Docker socket not accessible

**Solutions:**
```bash
# Check Docker access
docker ps

# Add user to docker group
sudo usermod -aG docker $USER
# Logout/login required

# Or run with sudo
sudo kopi-docka list --units
```

### Troubleshooting Tailscale

#### ❌ Tailscale-SFTP `kopia_params` migration (v7.0.0–v7.3.13 → v7.5.0+)

**Symptom:** Backups hang on connect, or `kopia` errors out with
`required flag(s) '--username' not provided` / `repository not
initialized` — even though the wizard ran "successfully".

**Cause:** The Tailscale wizard in v7.0.0–v7.3.13 emitted a broken
`kopia_params` shape — `--path=HOST:PATH --host=HOST` without
`--username` or `--keyfile`. Kopia accepts the form at
`repository connect` and only blows up on the first snapshot. Fixed in
v7.4.0; v7.5.0 ships a one-command repair path.

**Fix — one command:**

```bash
sudo kopi-docka advanced config repair-kopia-params
```

The command reads your existing `[credentials]` section (peer FQDN,
SSH user, key path, known_hosts) and rebuilds `kopia_params` in the
canonical shape. It shows a diff and asks for confirmation before
writing; pass `--dry-run` to preview only, `--yes` to skip the prompt.
The Kopia repository itself is untouched — only the local config string
changes.

Then reconnect to the existing repository (no data loss):

```bash
sudo kopi-docka advanced repo init
sudo kopi-docka doctor   # confirms Section 5.1 is all green
```

**Verify the new form by hand:** the four required flags Kopia's SFTP
backend wants are `--path` (path **only**, no host prefix), `--host`,
`--username`, and one of `--keyfile`/`--key-data`/`--sftp-password`. For
unattended runs (systemd/cron) also add `--known-hosts=PATH` so Kopia
doesn't hang on the host-key prompt.

---

#### ℹ️ Unraid 6.12+ persistent SSH key handling

On modern Unraid (6.12 and later) `/root/.ssh` is symlinked or
bind-mounted onto `/boot/config/ssh/root/` — writes to
`~/.ssh/authorized_keys` are *already* persistent. The wizard detects
this layout by comparing inodes (`stat -c '%d:%i'`) and **skips the
mirror step**.

If `kopi-docka doctor` or the wizard logs `Detected USB-boot/tmpfs-style
remote (e.g. Unraid). Also writing authorized_keys to …`, your Unraid is
the older layout where `/boot/config/ssh/root` is a single file
containing the authorized keys; that path still works and is mirrored on
your behalf. Either way the public key survives a reboot — only the
mechanism differs.

---

#### ❌ "No peers found in Tailnet"

**Cause:** No other devices in Tailnet or not logged in.

**Solution:**
```bash
# Check Tailscale status
tailscale status

# Log in if needed
sudo tailscale up

# Add other devices to Tailnet
# → tailscale.com → Settings → Machines
```

#### ❌ "Peer offline"

**Cause:** Backup server is offline or not in Tailnet.

**Solution:**
```bash
# On backup server:
sudo tailscale up

# Test from main server:
tailscale ping backup-server
```

#### ❌ "SSH key setup failed"

**Cause:** Root login not allowed or password auth disabled.

**Solution:**
```bash
# On backup server: /etc/ssh/sshd_config
PermitRootLogin yes  # Or 'prohibit-password'
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd

# Manually copy key:
ssh-copy-id -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet
```

#### 🔍 Test Connection

```bash
# Tailscale connection
tailscale status
tailscale ping backup-server

# SSH connection
ssh -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet

# SFTP connection (as Kopia uses it)
echo "ls" | sftp -i ~/.ssh/kopi-docka_ed25519 root@backup-server.tailnet
```

### 🔍 Debugging

```bash
# Verbose logging
sudo kopi-docka --log-level DEBUG check

# Check config
sudo kopi-docka advanced config show

# Verify dependencies
sudo kopi-docka check --verbose

# Test repository connection
sudo kopi-docka repo-status

# Dry run to see what would happen
sudo kopi-docka dry-run
```

---

## FAQ

### When should I use which backend?

**Local Filesystem**
- For local backups on NAS or external drive
- Fast, but no offsite protection
- Suitable for additional local copy

**Backblaze B2**
- Affordable cloud backups (~$5/TB/month)
- No own hardware needed
- Reliable and simple

**Tailscale**
- Own hardware at different location available (VPS/NAS/Pi)
- No ongoing costs
- Full control over data

**AWS S3**
- Existing AWS infrastructure
- Enterprise requirements

**SFTP**
- Existing SFTP server available
- Without Tailscale setup

### Can I combine multiple backends?

Yes! Use e.g. Tailscale as primary backup + B2 as additional offsite:

```bash
# Primary: Tailscale (daily)
sudo kopi-docka backup

# Secondary: B2 (weekly, different config)
sudo kopi-docka --config /etc/kopi-docka-b2.json backup
```

### How fast are Tailscale backups?

Speed depends on connection:

**Direct P2P (both in same LAN):** 100-500 MB/s
**P2P over Internet:** 10-50 MB/s
**Via DERP relay (if P2P not possible):** 5-20 MB/s

**Comparison other backends:**
- Cloud upload (S3/B2): Depends on upload speed (5-20 MB/s typical)
- Local NAS: 100-1000 MB/s (network dependent)

### Is Tailscale secure enough for backups?

Tailscale backups use double encryption:

1. **Tailscale (WireGuard)** - End-to-end encryption at network level
2. **Kopia (AES-256-GCM)** - Client-side encryption of backup data

Network traffic is encrypted by Tailscale, backup data itself is additionally encrypted by Kopia. Even with compromised network layer, data remains protected.

### Can I use Tailscale for multiple servers?

Yes, each server can have its own backup target:
- Multiple production servers → One backup server
- Server A ⇄ Server B (mutual backups)
- Different backup targets per server

Each server needs its own Kopi-Docka config with respective target peer.

### Should I use systemd Timer or Cron?

**systemd Timer (Recommended):**
- Native status communication (sd_notify)
- Watchdog monitoring
- Automatic restart on error
- Structured logs in journal
- PID locking
- Security hardening
- Persistent (catch up on failure)

**Cron (Alternative):**
- Simpler for existing setups
- Fewer features
- Manual error handling needed

**Use systemd Timer for production, Cron only if systemd not available.**

### How do I monitor backup status?

**Via systemd:**
```bash
# Timer status
systemctl list-timers | grep kopi-docka

# Service status
systemctl status kopi-docka.service

# Logs
journalctl -u kopi-docka.service --since "24 hours ago"

# Errors
journalctl -u kopi-docka.service -p err
```

**Monitoring integration:**
- Prometheus: node_exporter systemd module
- Zabbix: systemd monitoring template
- Nagios/Icinga: check_systemd_unit
- Email on error: OnFailure=status-email@%n.service

### Can I trigger backups manually while timer is running?

Yes, thanks to PID locking it's safe:
```bash
# Timer already running
sudo systemctl is-active kopi-docka.timer
# → active

# Manual backup
sudo kopi-docka backup
# → Runs if no other backup active
# → Waits or aborts otherwise
```

The lock prevents parallel backups.

---

[← Back to README](../README.md)
