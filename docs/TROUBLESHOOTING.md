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
sudo kopi-docka admin config edit
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
sudo kopi-docka show-config

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
