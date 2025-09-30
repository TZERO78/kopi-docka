# Kopi‑Docka

**Robust cold backups for Docker environments using Kopia**

Kopi‑Docka performs **consistent, cold backups** of Docker stacks ("backup units"). It briefly stops containers, snapshots **recipes** (Compose + `docker inspect`, with secret redaction) and **volumes** into a Kopia repository, then restarts your services.

> **Note:** Kopi‑Docka intentionally **does not** create separate database dumps anymore. Volumes are the **single source of truth**.

---

## Why Kopi‑Docka?

Kopi‑Docka focuses on a single, reliable workflow: **1:1 restoration of Docker services** without mixing hot DB tooling. Use it when you want:

- **Consistency first:** Cold backups (Stop → Snapshot → Start).
- **Stack awareness:** Back up complete Compose stacks as one **backup unit**.
- **Exact restores:** Bring back the same config, volumes, and layout.
- **Cloud‑ready repos:** Use Kopia repositories on filesystem or cloud (S3, B2, Azure, GCS†).
- **Simple ops:** Clear CLI, dry‑run, restore wizard, and systemd integration.
- **Deterministic archives:** Optimized tar streams for dedupe (`--numeric-owner --xattrs --acls --mtime=@0 --sort=name`).

† subject to Kopia support and your configuration.

If you need enterprise‑grade orchestration, consider Kubernetes backup tools like Velero, or general purpose solutions (Restic + scripting, Duplicati, commercial tools). Kopi‑Docka shines on single Docker hosts and small fleets.

---

## Key Features

- 🔒 **Cold, consistent backups** (short downtime per unit)
- 🧩 **Backup Units** (Compose stacks or standalone containers)
- 🧾 **Recipes**: `docker-compose.yml` (if present) + `docker inspect` with secret redaction
- 📦 **Volumes**: tar stream with owners/ACLs/xattrs, dedupe‑friendly ordering & mtimes
- 🏷️ **Mandatory `backup_id`**: every run tags snapshots with `{ unit, backup_id, type, timestamp }`
- 🧰 **Per‑unit Kopia policies**: retention set on `recipes/UNIT` and `volumes/UNIT`
- 🧪 **Dry‑run mode**: full simulation, no changes
- 🛟 **Disaster Recovery Bundle**: encrypted package with repo info, password, script, status
- 🐧 **systemd‑friendly**: daemon with sd_notify/watchdog/locking + sample service/timer/oneshot units
- ⚙️ **Parallel workers = auto**: tuned by RAM/CPU; no artificial `task_timeout`

---

## How it Works

1) **Discovery**  
   Finds running containers & volumes, groups them into **backup units**  
   (Compose stacks preferred; otherwise standalone). Recipes include Compose path (if labeled) and `docker inspect` (ENV secrets redacted: `PASS|SECRET|KEY|TOKEN|API|AUTH`).

2) **Backup Pipeline (Cold)**  
   - Create **`backup_id`** (e.g., `2025-01-31T23-59-59Z`) – required and used for grouping.  
   - **Stop** unit containers (graceful `docker stop -t <timeout>`).  
   - **Snapshot recipes** → Kopia tags: `{type: recipe, unit, backup_id, timestamp}`.  
   - **Snapshot volumes** (parallel, up to `parallel_workers`) via tar stream → Kopia `--stdin`  
     Tags: `{type: volume, unit, volume, backup_id, timestamp, size_bytes?}`.  
   - **Start** containers; if a healthcheck exists, wait until `healthy`.  
   - **Apply retention** policies per unit (daily/weekly/monthly/yearly).  
   - (Optional) **Create DR bundle** and rotate.

3) **Restore (Wizard)**  
   - Lists restore points grouped strictly by **(unit, backup_id)**.  
   - Restores recipe files to a working directory.  
   - Generates **safe volume restore scripts** (stop users, safety tar of current volume, stream restore, restart).  
   - Documents **modern `docker compose up -d`** only (no legacy fallback).  
   - Warns about redacted secrets in `*_inspect.json`.

---

## Requirements

- Linux (systemd recommended)
- Docker (Engine & CLI)
- Kopia (CLI)
- `tar`
- **Python 3.10+**

Quick checks:

```bash
which docker && docker --version
which kopia && kopia --version
which tar
python3 --version
```

---

## Installation

### From source (pipx recommended)

```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka
pipx install .
# or:
pip install -e .
```

The CLI is installed as `kopi-docka` (verify with `which kopi-docka`).

---

## Configuration

Default search order (first wins):

- `/etc/kopi-docka.conf`
- `~/.config/kopi-docker/config.conf`

### Example `kopi-docka.conf`

```ini
[kopia]
repository_path = /backup/kopia-repo
password = CHANGE_ME_TO_A_SECURE_PASSWORD
compression = zstd-fastest
encryption = aes256
cache_directory = /var/cache/kopia

[backup]
backup_base_path = /backup/kopi-docka
parallel_workers = auto
stop_timeout = 30
start_timeout = 60
exclude_patterns = ["*.tmp", "*.cache", "lost+found"]
update_recovery_bundle = false
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3

[retention]
daily   = 7
weekly  = 4
monthly = 12
yearly  = 2

[logging]
level = INFO
```

Notes:

- `parallel_workers = auto` uses a RAM/CPU heuristic (capped at CPU cores).
- `exclude_patterns` are passed to `tar --exclude`.
- **No `task_timeout`** anymore (removed). If you still have `task_timeout=0` it is interpreted as “no timeout”.

---

## Usage

### Initialize & Inspect

```bash
# Initialize or connect repository, check deps
kopi-docka init
kopi-docka check
```

### List Units

```bash
kopi-docka list --units
```

### Backup

```bash
# Dry run (no changes)
kopi-docka backup --dry-run

# Full backup (all units)
kopi-docka backup

# Specific unit
kopi-docka backup --unit my-stack

# Also generate/update DR bundle
kopi-docka backup --update-recovery
```

### Restore

```bash
# Interactive restore wizard
kopi-docka restore
```

Flow:

1. Pick **unit** and **backup_id**.
2. Wizard restores recipes to a working directory.
3. For each volume, it writes a **restore script** (stops containers, safety backup, stream restore, restart).
4. Use **`docker compose up -d`** when ready.  
   If you need manual recreation (no Compose), use the `*_inspect.json` hints.

---

## Disaster Recovery Bundle

Create/rotate an encrypted bundle with **repo info**, **Kopia password**, **config**, **recovery script**, and **status**:

```bash
kopi-docka disaster-recovery
```

Configure automatic updates in `[backup]`:

```ini
update_recovery_bundle      = true
recovery_bundle_path        = /backup/recovery
recovery_bundle_retention   = 3
```

You’ll get:
- `kopia-repository.json`
- `kopia-password.txt` (keep secure!)
- `kopi-docka.conf`
- `recover.sh` (automated bootstrap + repo connect)
- `backup-status.json`
- `<bundle>.README` (password & steps), `<bundle>.PASSWORD` (0600)

---

## Scheduling & Service

### systemd (recommended)

Write example units, reload, enable:

```bash
sudo kopi-docka write-units
sudo systemctl daemon-reload

# Timer: daily at 02:00 with jitter
sudo systemctl enable --now kopi-docka.timer
systemctl status kopi-docka.timer
```

### Optional daemon (internal interval)

```bash
kopi-docka daemon --interval-minutes 1440
```

The daemon is sd_notify/watchdog aware and uses a PID lock to avoid overlaps.  
Prefer the **timer** for production; the daemon can run alongside as needed.

Logs:

```bash
journalctl -u kopi-docka --no-pager -n 200
```

---

## Performance Tips

- Tune `parallel_workers` (auto is usually fine; lower if RAM is tight).
- Add `exclude_patterns` to reduce noise and speed up backups.
- Put `KOPIA_CACHE_DIRECTORY` on fast storage.
- Set sensible retention; policies are applied per unit automatically.

---

## Troubleshooting

**Doctor & versions**

```bash
kopi-docka doctor
docker --version
kopia --version
```

**Repository & snapshots**

```bash
kopia repository status
kopia snapshot list --json | jq '.'
```

**Disk space**

```bash
df -h
```

**Permissions**

- Ensure access to `/var/run/docker.sock` (root or user in `docker` group).
- Ensure write access to `repository_path` and `backup_base_path`.

**Healthchecks**

- On startup, Kopi‑Docka waits for `healthy` if a healthcheck is defined.

---

## Security

- `*_inspect.json` redact env variables matching `PASS|SECRET|KEY|TOKEN|API|AUTH`.
- DR bundle is OpenSSL‑encrypted (`aes-256-cbc` with `pbkdf2`). Store the password safely.
- Docker socket access ≈ root. Restrict to trusted administrators.

---

## FAQ

**Why remove live DB dumps?**  
Cold backups are simpler and fully consistent for containerized apps. The volume is the truth; fewer moving parts.

**Can I restore a single file?**  
Yes. Use Kopia to restore or mount a snapshot and copy files out. The wizard’s scripts show streaming examples.

**How do I pick an older backup?**  
Choose by **`backup_id`** in the restore wizard. Snapshots are grouped by `(unit, backup_id)`.

---

## License & Contributing

- License: MIT
- Issues/PRs welcome ✨

---

