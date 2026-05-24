# Changelog

All notable changes to Kopi-Docka will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.3.8] - 2026-05-24

### 🐛 Fixed — critical: silent second-config creation under permission failure

A live-system run uncovered a real **data-loss footgun**. Sequence:

1. User has a working `/etc/kopi-docka.json` (root-owned, mode 0600,
   typical multi-user install with a `password_file` pointing at
   another root-only file).
2. User runs e.g. `kopi-docka advanced snapshot retention set --latest 5`
   *without* `sudo` by accident.
3. `_find_config_file()` walks the default search order, hits
   `/etc/kopi-docka.json`, sees it exists, `os.access(..., R_OK)`
   returns False, **logs a warning and falls through**.
4. The fall-through branch creates a brand-new
   `~/.config/kopi-docka/config.json` from `config_template.json` —
   with the default password `"kopia-docka"` and the default repo
   path `"filesystem --path /backup/kopia-repository"`.
5. From now on `kopi-docka` finds the user-scoped config first
   (search order is user → root) and **never touches the /etc one
   again until the user notices**. Backups quietly run against a
   nonexistent repo, the password is wrong, the disaster-recovery
   bundle exports against the wrong config, and the user has two
   configs whose drift goes undetected.

Fix: `_find_config_file()` now collects unreadable existing paths
across the search pass and **raises `PermissionError`** if any were
found, instead of silently creating a second config. The error
message lists the unreadable path(s) and — when one of them is under
`/etc/` — explicitly suggests running with `sudo`.

```
$ kopi-docka advanced snapshot retention set --latest 5
Configuration file exists but is not readable: /etc/kopi-docka.json.

It's almost certainly a missing sudo: an /etc-scoped config is normally
root-owned. Re-run the command with `sudo`.

If you really want to start with a fresh user-scoped config instead of
using the existing one, point --config at a new path explicitly …
```

The only way to get a second config is now to ask for it explicitly
via `--config`. New tests in `tests/unit/test_helpers/test_config.py`
pin the "raise instead of silent fallback" + the sudo hint.

---

## [7.3.7] - 2026-05-24

### 🐛 Fixed — `advanced snapshot retention set`

Two UX problems surfaced on a live rclone+GDrive production system where
`kopia policy set --global` takes ~5 minutes (!) for a single round-trip:

- **Empty `retention set` invocations now ask for confirmation.** The
  command's six retention flags used to default to fixed numbers
  (`--latest 10 --daily 7 …`) at the Typer layer, which meant
  `kopi-docka advanced snapshot retention set` typed by accident would
  silently overwrite a custom config (say `monthly=6`) with the Typer
  defaults — and then spend a 30-90 s metadata round-trip doing it.
  Each flag is now `Optional[int]` defaulting to `None`. With no flags
  the command prints a yellow "Nothing to change" panel and exits;
  `--force` overrides for scripts that intend a no-op rewrite.
- **Partial invocations preserve the other values.** Previously
  `retention set --daily 14` would also clobber `latest`/`hourly`/etc.
  with Typer defaults. Now an omitted flag means "keep what the config
  has"; the new effective tuple is built by merging explicit args over
  the current config.
- **Spinner during the Kopia call.** The 30-90 s (up to 5 min on slow
  remote backends) `kopia policy set --global` round-trip used to run
  with no terminal feedback at all — looked like the CLI was hung. Now
  a Rich spinner runs, with a one-line "this typically takes 30-90 s on
  rclone backends" hint above it.

### Tests

Four new tests in `tests/unit/test_cores/test_snapshot_manager.py`
covering: explicit args still update, Kopia failure doesn't write
config, partial args merge with current config, no-args without
`--force` aborts cleanly, no-args with `--force` applies the current
config values. CLI-layer tests in
`tests/unit/test_commands/test_snapshot_commands_new.py` updated for
the new `Optional[int]` signature plus a new `--force` test.

---

## [7.3.6] - 2026-05-24

### 📝 Convention

- **Config template `version` field now tracks the kopi-docka release.**
  The shipped `kopi_docka/templates/config_template.json` carried
  `"version": "3.0"` since the v3.0 schema reshuffle and nobody had
  bumped it since. From v7.3.6 on, this field mirrors the kopi-docka
  release that wrote it (so a fresh `advanced config new` against
  v7.3.6 produces a file marked `"version": "7.3.6"`). This is purely
  a marker — Pydantic accepts any string — but it makes "which release
  generated this config file?" answerable by opening the file. Existing
  user configs are untouched; the migration helper does not rewrite the
  field (it's a user value, by the rule "don't overwrite what's already
  there").

- **Release checklist in CLAUDE.md** updated: the config template now
  joins `pyproject.toml`, `helpers/constants.py`, `CLAUDE.md` and
  `CHANGELOG.md` as a file to bump on every release.

---

## [7.3.5] - 2026-05-24

### 📝 Documentation / UX

- **All user-facing text now uses `advanced` instead of `admin`.** The
  CLI itself had been registering both names for a while —
  `advanced` as the documented top-level group and `admin` as a hidden
  Typer alias — but help texts, docstrings, error hints, disaster
  recovery scripts and the bundled systemd units were inconsistently
  mixing both. A `kopi-docka --help` showed `advanced` but a typical
  `kopi-docka advanced policy` user would still hit doc strings
  saying "use `kopi-docka admin config edit` instead", and the
  shipped `kopi-docka.service` template ran `kopi-docka admin service
  daemon`. 134 references across 23 files unified to `advanced`.

  **Back-compat**: the `admin` name remains as a `hidden=True` Typer
  alias on the same Typer app, so every existing user script, systemd
  unit, or cron entry that still says `admin` keeps working. The
  rename is a documentation / display fix, not a CLI break.

  Notably, the bundled systemd templates now use `advanced service
  daemon` and `advanced service write-units` — old installs running
  `admin service daemon` are unaffected, but freshly installed units
  match the documentation.

---

## [7.3.4] - 2026-05-24

### 🐛 Fixed

Round two of UX cleanup for `scripts/migrate-config.sh`, after a real
production config (with full notification setup, legacy hooks, and a
`retention.yearly` key from an old version) exposed several false
positives and a missing template field.

- **Stop flagging `template=null` vs scalar as a type mismatch.** A
  `null` value in the template marks a "not configured yet" slot —
  `kopia.password_file`, `notifications.service`, `notifications.url`
  and similar. On the first live-system run these produced page after
  page of `! kopia.password_file (template=null, user=string)` lines.
  Mismatch detection now suppresses null↔scalar in either direction;
  only genuine type clashes (e.g. `int` vs `bool`) surface.
- **Trailing empty `! ` entry in the type-mismatch block** removed.
  The block was concatenated with `$'\n'` between entries plus a
  terminating `$'\n'`, which produced one extra blank line at the
  end of the report. Switched to a proper bash array.
- **Template now ships `backup.database_backup`.** The Pydantic schema
  has had this field with default `"true"` since 5.x, but it was
  missing from `config_template.json` — so the migration helper would
  otherwise warn on every install that still had the key.

### 📝 Documentation

- **Known legacy renames table** in `docs/CONFIGURATION.md`. Several
  "Unknown keys" the script reports are not custom additions but old
  names: `retention.yearly` → `retention.annual`,
  `backup.pre_backup_hook` → `backup.hooks.pre_backup`,
  `backup.post_backup_hook` → `backup.hooks.post_backup`. The script
  doesn't auto-rename (it has no opinion about your data); the doc
  tells you which "Unknown" lines are safe to `--prune-unknown` once
  you've copied the value into the new key.

---

## [7.3.3] - 2026-05-24

### 🐛 Fixed

`scripts/migrate-config.sh` UX hardening after the first live-system run.

- **Template auto-locate is no longer `python3 -c 'import kopi_docka'` only.**
  When kopi-docka is installed under pipx or in a venv, the default
  `/usr/bin/python3` can't import the package — the script printed
  `tried: <empty>` with no further hint. New strategy chain:
    1. explicit `--template` flag
    2. default `python3 -c 'import kopi_docka'`
    3. python from `which kopi-docka`'s shebang (handles pipx / venv)
    4. GitHub raw fallback (no install needed)
  Each failed step now logs *why*; the final "could not locate" error
  lists all four strategies plus how to fix each one.
- **Documented the `chmod +x` step inline.** The `curl -o /usr/local/bin/...`
  command leaves the file without an execute bit; the docs now chain
  the `chmod` on the same line so the copy-paste path works first try.

### ✨ Added

- **`--config` is now optional.** When omitted, the script probes the
  same default locations kopi-docka itself uses
  (`$HOME/.config/kopi-docka/config.json` first, then
  `/etc/kopi-docka.json`). Honors `$SUDO_USER` so that
  `sudo migrate-config.sh` finds the invoking user's per-user config
  instead of root's.
- **kopi-docka version banner.** Every run prints the installed
  kopi-docka version and binary path up front, or says "not found on
  PATH — will use the GitHub-hosted template" if the binary is missing.
  Makes it obvious which release the migration is checking against.

---

## [7.3.2] - 2026-05-24

### ✨ Added

- **`scripts/migrate-config.sh`** — config migration helper that diffs an
  existing `kopi-docka.json` against the template shipped with the
  installed kopi-docka and fills in missing keys with the template
  defaults. The script does not hard-code any field names; every key
  it adds, warns about, or (optionally) prunes is derived live from
  the template, so a future release that adds new keys is handled
  automatically. Existing user values are never overwritten. A
  timestamped backup of the original file is written by default.
  Documented in `docs/CONFIGURATION.md` (Migrating an older config)
  and cross-linked from `docs/TROUBLESHOOTING.md`.

### 🐛 Fixed

- **Config template now ships with `kopia.profile`.** The Pydantic
  schema has had `kopia.profile` with default `"kopi-docka"` since
  early 5.x, but the on-disk `config_template.json` was missing the
  field — so `kopi-docka advanced config new` generated configs
  without a visible profile entry, and the migration helper above
  would otherwise flag every multi-profile install's `kopia.profile`
  as "unknown". Template now includes it.

---

## [7.3.1] - 2026-05-24

### 🐛 Fixed

Two pre-existing bugs uncovered by the post-v7.3.0 end-to-end testlab run.

- **`KopiaRepository.connect()` now re-applies the global retention policy on every call**, even when the underlying repository is already connected. Before this fix, the `is_connected()` short-circuit meant `apply_global_defaults()` only ran on a *fresh* `kopia repository connect` — long-lived connections never picked up retention changes from `kopi-docka.json`, so the config file and Kopia's actual global policy drifted indefinitely. Plan 0028's "idempotent on every connect" promise wasn't actually delivered on existing installs. The reapply is still idempotent at the Kopia layer (`kopia policy set --global` with identical values is a no-op), so the only cost on slow remote backends is one extra metadata round-trip per `connect()` call.
- **`advanced snapshot retention show` no longer reports "Kopia policy unavailable" on healthy repos**. `_display_retention` looked up Kopia's global policy under the `retentionPolicy` JSON key, but Kopia's `policy show --global --json` puts retention under the top-level `retention` key. The wrong key always resolved to `None`, hiding the actual Kopia values behind a misleading "not connected?" hint. Now reads `retention` first and falls back to `retentionPolicy` for defensive compatibility.

Both fixes verified end-to-end on the rclone+GDrive testlab — after upgrade, `kopia policy show --global` and `kopi-docka advanced snapshot retention show` agree on the same values from `kopi-docka.json`.

---

## [7.3.0] - 2026-05-24 — Plan 0028: Global-Policy-Only

Eliminates the entire per-path policy apparatus that v7.2.0 still relied on
for volume retention. With Plan 0028 there is exactly one place where Kopia
retention is written: the global policy at repository `connect()` /
`initialize()` time. No more hash-based smart-skip, no more auto-prune of
orphans, no more divergent timing on rclone backends. Three atomic commits on
`refactor/global-policy-only`.

### 🚀 Performance & Reliability

- **Backup hot path no longer writes per-path Kopia policies.** Plan 0026
  trimmed staging-path policies; Plan 0028 removes the remaining volume
  mountpoint writes too. On the rclone/Google-Drive backend that surfaced this
  bottleneck, a 5-unit backup run that previously paid 5+ `kopia policy set`
  round-trips now pays zero — global policy already covers every snapshot via
  Kopia's policy inheritance tree.
- **Global policy is applied on every `connect()`** (in addition to
  `initialize()`). Idempotent (Kopia treats identical `--global` writes as a
  no-op), so retention changes in `kopi-docka.json` reach Kopia on the next
  run without a manual step.

### 🗑️ Removed

- `BackupManager._ensure_policies`, `BackupManager._apply_target_policy`,
  `BackupManager.auto_prune_orphaned_policies` — the entire smart-skip +
  auto-prune apparatus introduced in Plan 0026.
- `BackupManager.policy_state` attribute and the `helpers/policy_state.py`
  module (PolicyStateManager + `compute_policy_hash`).
- `KopiaPolicyManager.set_retention_for_target` and
  `set_compression_for_target` — global-only retention has no consumer for
  these.
- The `auto_prune_orphaned_policies()` call from `commands/backup_commands.py`.

### 🐛 Fixed

- **`advanced policy prune` is now a true legacy-cleanup.** Pre-Plan-0028
  versions only deleted *orphaned* per-path policies — entries whose path
  no longer matched any snapshot. With per-path policies obsolete under
  Plan 0028, that left a confusing gap: doctor flagged any leftover
  per-path entry as "Legacy" and pointed at `policy prune`, but prune
  refused to touch it as long as a snapshot still lived at that path.
  `cmd_prune` now removes every per-path entry on this host/user under
  a kopi-docka-managed prefix (`/var/lib/docker/volumes/`,
  `/var/cache/kopi-docka/staging/`), regardless of snapshot state.
  Cross-host policies and unknown prefixes stay untouched as before
  (Plan 0024 safety). Verified end-to-end on the rclone+GDrive testlab:
  one leftover per-path policy detected by doctor, pruned in one batch
  call, doctor reports clean global-only state.

### 🧱 Refactor

- **Backup discovery decoupled from snapshot execution.** New
  ``BackupSource`` dataclass in ``kopi_docka/types.py`` carries the
  ``(path, kind, tags)`` triple a snapshot needs. New ``_collect_*_sources``
  helpers on ``BackupManager`` produce these — one per kind for
  recipes / networks / docker_config, one per volume for direct-mode
  volumes. The aggregate ``_collect_backup_sources()`` returns the full
  ordered list ``backup_unit()`` would snapshot.
- **Single sequential snapshot entry point.** New
  ``KopiaRepository.create_snapshots(sources)`` is the only call
  ``backup_unit()`` makes to produce snapshots. It iterates ``sources`` in
  order, returns one ID per source (empty string for failures so callers
  can map failures back to a kind/volume), and is intentionally sequential
  — see the docstring for the rationale and the Kopia upstream issue
  (``kopia/kopia#1725``) that would let the body be swapped for a
  multi-path call.
- **ThreadPoolExecutor removed from the volume loop.** Per-volume
  parallelism is gone (user preference: log determinism and predictable
  rclone behaviour beat throughput on VPS-class hardware). If a future
  user needs parallelism, ``kopia policy set --global --max-parallel-snapshots=N``
  is the right knob at the Kopia layer.
- **Discovery now runs before container stop.** Compose-file copy, docker
  inspect, network export and config staging happen with containers
  alive (docker inspect needs them); the snapshot loop runs after stop.
  This is also a friendlier failure mode — a discovery error aborts
  before anything is stopped.

### 🧹 Migration

- **`~/.config/kopi-docka/policy_state.json` is removed automatically.**
  v7.2.0's smart-skip hash cache is dead data after Plan 0028. On the
  first kopia call after upgrade, `KopiaRepository._maybe_cleanup_legacy_state_files()`
  unlinks the file once (idempotent, logged at INFO). No action required.
- **`backup.parallel_workers` and `backup.task_timeout` config fields are
  ignored.** Both are kept in the schema so existing `kopi-docka.json`
  files still validate, but the sequential snapshot loop reads neither.
  Fresh `config_template.json` no longer ships these keys.

### Upgrade Notes

- Existing repositories that still carry per-path policies from older
  kopi-docka versions are *not* automatically cleaned up by the backup
  run anymore (auto-prune is gone). Run **`kopi-docka advanced policy prune`**
  once after upgrading — under Plan 0028 it removes *every* per-path
  policy on this host (kopi-docka-managed prefixes only; cross-host
  policies stay untouched). Doctor flags any leftovers as "Legacy
  Per-Path Policies" with the same hint.
- The systemd templates still carve out write access to
  `/root/.config/kopi-docka` so the one-time `policy_state.json` cleanup
  on first run after upgrade can happen — after that the directory is
  no longer written to by kopi-docka.

## [7.1.2 – 7.2.1] - 2026-05-23 — Rclone/Policy convergence

Seven tightly-related point releases spanning Plan 0026 (the original
„policy overhead on rclone backends" rework) and the chain of follow-ups
that hardened it on real prod systems. They all converge on the same
story: per-path Kopia policies on slow remote backends were the dominant
runtime cost, and every regression fix added a layer of skip / prune /
timeout / systemd carve-out. **Plan 0028 (v7.3.0) makes most of this
obsolete by removing per-path policies entirely** — kept here for
historical context.

### ✨ Added (during the convergence)

- **`kopi-docka advanced policy prune`** (v7.1.2): clean up orphaned
  per-path Kopia retention policies. Compares `kopia policy list` against
  `kopia snapshot list --all`. Supports `--dry-run` and `--force`. Plan
  0028 still uses this for the post-upgrade legacy-cleanup workflow.
- **`KopiaPolicyManager.delete_policy()` / `delete_policies_batch()`**
  (v7.1.2 / v7.1.4): wrappers for `kopia policy delete`. Batch variant
  collapses N deletes into one rclone round-trip — critical when each
  round-trip costs ~120 s.
- **`kopia.rclone_startup_timeout` config option** (v7.2.0, default
  `120s`): Kopia's rclone backend default of 15 s is unreliable on cold
  Google Drive starts. Appended to `kopia repository create/connect` and
  persisted in the repo config. Self-healing migration patches existing
  configs (logs `"Migrated rclone startupTimeout 15s → 120s"`).
- **Hash-based smart-skip for volume policies** (v7.2.0,
  `helpers/policy_state.py`): fingerprinted `(target, retention)` per
  profile, persisted to `~/.config/kopi-docka/policy_state.json`. Removed
  in Plan 0028 (v7.3.0).
- **Auto-prune at backup start** (v7.2.0,
  `BackupManager.auto_prune_orphaned_policies()`): removed orphans before
  each backup run, guarded by `host == socket.gethostname()` /
  `user == getpass.getuser()` / known-prefix checks (cross-host restore
  safety, Plan 0024). Removed in Plan 0028.

### 🗑️ Removed (during the convergence)

- Per-path policies on staging dirs (v7.2.0): `_ensure_policies` stopped
  setting policies on `staging/recipes/<unit>` etc. — global covered them
  via Kopia's inheritance tree.
- Per-unit pre-flight check (v7.2.0): moved to a single check per backup
  run; a backend outage now aborts before any container is stopped.

### 🐛 Fixed (the chain of follow-ups)

- **`policy prune` delete syntax** (v7.1.3): `kopia policy delete` expects
  the target as `user@host:path`, not `--username`/`--host` flags. 41 of
  41 deletions were silently failing.
- **`policy prune` batch delete + timeout** (v7.1.4): batched into one
  call; `delete_policy()` timeout raised to 600 s for slow remotes.
- **`policy prune` & `doctor` orphan detection** (v7.1.5):
  `snap.get("source", {}).get("path")` returned an empty set because
  `list_snapshots()` already produces flat dicts. `doctor` over-reported
  orphans; `policy prune` would have deleted every per-path policy on
  certain repos. Fixed by reading `snap["path"]` directly; regression
  tests in `tests/unit/test_commands/test_policy_path_extraction.py`.
- **`Config.to_dict()`** (v7.1.1): missing method broke `doctor` section
  4 (Backend Dependencies) with `AttributeError`.
- **systemd service templates `ReadWritePaths`** (v7.2.1): the bundled
  templates set `ProtectHome=read-only`, blocking both Kopia's
  `repository connect` self-healing migration and kopi-docka's
  `policy_state.json` writes. Now carve out
  `-/root/.config/kopia -/root/.config/kopi-docka -/root/.cache/kopia`.
- **Kopia subprocess OS timeouts** (v7.2.1): the wrapping OS-level
  timeouts (`_REPO_OP_TIMEOUT`, `KopiaPolicyManager._run` default) were
  the same 120 s as the in-Kopia `--rclone-startup-timeout`, killing the
  actual operation before it could finish. Bumped to 300 s — gives
  rclone-startup its full 120 s budget plus ~3 min for the operation.
- **Actionable migration warning** (v7.2.1): `_maybe_patch_repo_config_for_rclone`
  now points at the systemd `ReadWritePaths` fix on EROFS instead of
  just printing errno.

### Upgrade Notes (v7.2.0 → v7.2.1)

Existing systemd-managed installs that hit the read-only error need a
one-time override:

```bash
sudo mkdir -p /root/.config/kopia /root/.config/kopi-docka
sudo systemctl edit kopi-docka-backup.service
```

```ini
[Service]
ReadWritePaths=-/root/.config/kopia -/root/.config/kopi-docka -/root/.cache/kopia
```

Then `sudo systemctl daemon-reload`. Fresh installs and `kopi-docka setup`
runs against 7.2.1+ get this automatically. (Note: with Plan 0028 / v7.3.0
the `kopi-docka` carve-out is only kept for legacy state files.)

---

## [7.1.1] - 2026-05-23

### 🐛 Fixed

- **`Config.to_dict()`**: Method was missing — `doctor` section 4 "Backend Dependencies" raised `AttributeError` when instantiating backends (rclone, S3, etc.). Fixed by delegating to the internal `_config` dict.

---

## [7.1.0] - 2026-05-23

### ✨ Added

- **Pre-flight backend connectivity check**: `backup_unit()` now verifies backend reachability via `is_connected(force_refresh=True)` before stopping any containers. If unreachable → `BACKUP ABORTED` notification is sent, containers stay running (zero downtime). Controlled by `notifications.preflight_check` (default `true`).
- **Structured Kopia error context**: `KopiaCommandError` replaces bare `RuntimeError` in `KopiaRepository._run()`. Carries `cmd`, `returncode`, `stderr_tail` (UTF-8 safe, max 1 KB). Structured context flows into `BackupErrorDetail` in metadata and verbose failure notifications.
- **Verbose failure notifications**: When `notifications.verbose = true` (default), failure payloads include phase, exit code, and stderr tail (fenced code block, Markdown-injection-safe).
- **Markdown notification format**: All Apprise sends now use `body_format=MARKDOWN`. Services without Markdown degrade gracefully to plaintext.
- **`BackendUnreachableError`**: New exception in `backends/base.py`, subclass of `ConnectionError`. Raised on pre-flight failure.
- **`BackupErrorDetail` dataclass** (`types.py`): Structured error context (phase, message, exit_code, stderr_tail). Persisted in metadata JSON (`error_details` field). `BackupMetadata.from_dict()` is backward-compatible.
- **`MissedBackupChecker`** (`cores/missed_backup_checker.py`): Time-based detection for overdue backups. Reads local metadata, compares last-success timestamp against `alerting.missed_backup.max_age_hours` (default 26h). Supports per-unit overrides.
- **Post-run missed-backup alerting**: After each `backup_unit()` run, `MissedBackupChecker` checks all units and sends a `BACKUP MISSED` notification for newly overdue units. Alert-suppression prevents repeat-spam; reset on successful backup.
- **Doctor "Backup Freshness" section**: Section 8 in `kopi-docka doctor` lists all units with last-success timestamp, age, and OVERDUE/OK status. Overdue units appear as warnings in the summary.
- **`NotificationManager.send_connectivity_alert()`** and **`send_missed_backup_alert()`**: New public send methods.
- **`is_connected(force_refresh=True)`**: New parameter on `KopiaRepository.is_connected()`. Bypasses the 60s cache for the initial pre-flight check; result (positive or negative) is written back to cache so subsequent unit checks stay fast.
- **Config keys** — `notifications.verbose` (bool, default `true`), `notifications.preflight_check` (bool, default `true`), `alerting.missed_backup.enabled` (bool, default `true`), `alerting.missed_backup.max_age_hours` (int, default `26`), `alerting.missed_backup.per_unit` (dict). All new keys have safe defaults; existing configs run unmodified.

## [7.0.3] - 2026-04-14

### 🐛 Fixed

- **`KopiaPolicyManager._run()`**: default timeout raised from 60s to 120s — `kopia policy set --global` against slow remote backends (rclone/GDrive) was timing out during `advanced repo init`, causing the global retention policy to not be applied
- **`KopiaRepository.initialize()` Step 3**: `_connected_cache` is now set to `True` after the post-connect status verification, so subsequent `is_connected()` calls in the same process are served from cache instead of hitting the backend again

---

## [7.0.2] - 2026-04-14

### ⚡ Performance

- **`KopiaRepository.is_connected()`**: result is now cached for 60 seconds within a single process run — remote backends (rclone/GDrive) can take 30s+ per `kopia repository status` call; repeated checks within the same command (e.g. `doctor`, `backup`) now return instantly from cache
- Cache is pre-warmed to `True` after successful `connect()` and `initialize()` calls, so the first post-connect check is also free

---

## [7.0.1] - 2026-04-14

### 🐛 Fixed

- **`KopiaRepository.initialize()`**: duplicate `_REPO_OP_TIMEOUT` class attribute removed (shadowed the correct definition at class top)
- **`KopiaRepository.is_connected()`**: bare `except Exception` now logs the suppressed exception via `logger.debug()` instead of silently returning `False`
- **`KopiaRepository.initialize()`**: all three `TimeoutExpired` handlers now bind the exception (`as e`) and chain it (`raise ... from e`) so the original traceback is preserved
- **`KopiaRepository._run()`**: docstring corrected — args include the `kopia` prefix, not a prefix-less list
- **`repository_manager`**: `import shlex` moved to module-level (was duplicated inside `connect()` and `initialize()`)

---

## [7.0.0] - 2026-04-12

### ✨ Added

- **SnapshotManager** (`cores/snapshot_manager.py`): new interactive snapshot management wizard (analogous to RestoreManager)
- **`advanced snapshot manage`**: menu-driven wizard for delete, pin/unpin, retention, prune, and maintenance
- **`advanced snapshot delete <id> [--force]`**: delete a specific snapshot (with confirmation)
- **`advanced snapshot pin <id>`**: pin a snapshot to protect it from retention cleanup
- **`advanced snapshot unpin <id>`**: remove pin from a snapshot
- **`advanced snapshot maintenance [--full]`**: run Kopia repository maintenance (moved from `advanced repo`)
- **`advanced snapshot prune-empty [--dry-run]`**: apply retention policy and expire old snapshots
- **`advanced snapshot retention show`**: display current retention policy from config and Kopia global policy
- **`advanced snapshot retention set [--latest N] [--hourly N] [--daily N] [--weekly N] [--monthly N] [--annual N]`**: update retention in both Kopia and config file
- **`KopiaRepository`**: added `pin_snapshot()`, `unpin_snapshot()`, `expire_snapshots()`
- **`KopiaPolicyManager`**: added `get_global_policy()`, `update_global_retention()`

### ⚠️ Breaking Changes

- **`advanced repo maintenance` removed** — use `advanced snapshot maintenance` instead

---

## [6.5.0] - 2026-04-11

### 🔒 Security

- **S1 Shell injection** (`restore_manager`): removed `shell=True` — replaced glob-based `rm` with `Path.iterdir()` + `shutil.rmtree()`, docker run command via list-based `shlex.split()`
- **S2 SUDO_USER validation** (`rclone`, `disaster_recovery_manager`): validate against `^[a-zA-Z0-9._-]+$` before path interpolation
- **S3 Plaintext password warning** (`config`): warn at setup time when password is stored inline; recommend `password_file` instead
- **S4 Hook security** (`hooks_manager`): refuse symlinks, world-writable scripts, and non-owner scripts to prevent hook hijacking
- **S5 rclone.conf permissions** (`rclone`): warn when `rclone.conf` has group/other read permissions
- **S6 fchmod race** (`config`): `fchmod(600)` on temp fd before write — closes chmod TOCTOU race
- **S7 Sensitive stderr filtering** (`ui_utils`): filter password/token/secret/key patterns from stderr before display
- **S8 mkdtemp** (`restore_manager`): replace hardcoded `/tmp` mount with `tempfile.mkdtemp()` for Docker safety backups
- **S9 Lock path** (`process_lock`): use `tempfile.gettempdir()` instead of hardcoded `/tmp`
- **S10 KOPIA_PASSWORD documentation** (`repository_manager`): document `/proc` exposure as known limitation

### 🛠 Fixed

- **R1 Subprocess leak** (`backup_volume_handler`): `try/finally` around `Popen` — kills tar process on snapshot exception
- **R2 JSON error handling** (`docker_discovery`, `restore_manager`): specific `json.JSONDecodeError` handlers with meaningful messages at three call sites
- **R3 Bounds checks** (`tailscale`, `docker_discovery`): validate `.split()` results before indexing
- **R4 Bare except** (`tailscale`, `repository_manager`): replace `except Exception` with specific types + warning/debug logging
- **R5 SIGTERM grace** (`ui_utils`): SIGTERM → 5s wait → SIGKILL on timeout (was direct SIGKILL)
- **R6 Docker start timeout** (`backup_manager`): use `self.start_timeout + 10` consistently (matches stop margin logic)
- **docker run shlex** (`restore_manager`): strip line-continuation formatting before `shlex.split()` to prevent stray `\n` argv entries

### 📝 Documentation

- **tests/README.md**: complete rewrite (was a copy of the v2.0 project README)
- **CONFIGURATION.md**: rewrite config examples from INI → JSON format; new Security Best Practices section
- **HOOKS.md**: new Security Requirements section (ownership, permissions, symlink enforcement)
- **DEVELOPMENT.md**: update version 5.5.1 → 6.4.0 with accurate feature list
- **CONFIGURATION.md / TROUBLESHOOTING.md / HOOKS.md**: replace stale `admin` and `show-config` command references with `advanced config show`
- **CLAUDE.md**: update bypass point list — remove 5 stale entries, document 2 remaining intentional bypasses

---

## [6.4.0] - 2026-03-24

### 🐛 Fixed

- **Retention policy path mismatch:** Policies for recipes, networks, and docker-config snapshots were applied to relative paths (`recipes/myunit`) but snapshots used absolute staging paths (`/var/cache/kopi-docka/staging/recipes/myunit`). Kopia never matched these — retention was silently broken for all non-volume snapshots since v5.3.0
- **Missing docker-config retention:** Docker-config snapshots had no retention policy at all — now included in `_ensure_policies()`

### ✨ Added

- **Doctor: Retention Policy Alignment check** (Section 7): `kopi-docka doctor` now verifies that Kopia retention policy targets match actual snapshot source paths, detecting orphaned policies and uncovered snapshots
- **`KopiaPolicyManager.list_policies()`**: New method to list all Kopia policies (JSON), used by the doctor check

### ⬆️ Upgrade Notes

- **No config changes required.** Existing configurations work as-is.
- On the first backup after upgrading, retention policies will be applied to the correct paths automatically. Old recipe/network/docker-config snapshots that accumulated due to the bug will be cleaned up according to your retention settings.
- You may notice increased storage reclamation after running `kopi-docka advanced repo maintenance` — this is expected as Kopia removes previously orphaned snapshot data.
- Run `kopi-docka doctor` to verify policy alignment on your installation (new Section 7).

---

## [6.3.0] - 2026-03-22

### ✨ Added

- **Backup History Command** (`kopi-docka history`): Browse past backups from stored metadata JSONs
  - Table view with color-coded status (green = success, red = failed)
  - Filter options: `--unit NAME`, `--failed`, `--last N`, `--since YYYY-MM-DD`
  - Detail view: `--detail` shows all fields per backup as Rich Panels
  - ID lookup: `--id BACKUP_ID` for a specific backup's details
  - Statistics: `--stats` shows avg/min/max duration per unit
  - JSON output: `--json` for machine-readable output (monitoring integration)
  - No root privileges required
- **MetadataReader** (`helpers/metadata_reader.py`): Reusable read-only loader for backup metadata JSON files
- **BackupMetadata.from_dict()**: Deserialization classmethod for backwards-compatible JSON loading

---

## [6.2.3] - 2026-03-22

### 🔧 Internal

- **Bypass Cleanup (Plan 0020):** All Kopia CLI calls now route through `KopiaRepository._run()` — single point of contact for Kopia changes
- Removed 3× direct `subprocess→kopia` bypass calls in `disaster_recovery_manager.py` (now uses `self.repo.status()`)
- Replaced `subprocess.run(["hostname"])` with `socket.gethostname()` in DR manager
- Routed `set_repo_password()`, `verify_password()`, `create_filesystem_repo_at_path()` through `_run()` with new `extra_env` and `config_file` parameters
- Documented `repo_helper.detect_existing_cloud_repo()` as intentional exception (runs before KopiaRepository init)

---

## [6.2.2] - 2026-03-22

### 🐛 Fixed
- **Issue #71:** Fixed TypeError in `advanced config show` command - removed invalid `show=True` argument from `cmd_config()` calls
- **Issue #70:** Fixed ImportError for `get_backend_class` - implemented missing function in `backends/__init__.py`
- **Issue #69:** Added `rsync` as SOFT dependency in dependency manager and documentation (fallback to `cp` remains functional)

---

## [6.2.1] - 2026-02-07

### 📚 Documentation
- **New dedicated Disaster Recovery guide:** Added `docs/DISASTER_RECOVERY.md` with comprehensive DR documentation (ZIP export, SSH streaming, recovery walkthrough, CLI reference, passphrase security, format comparison, storage best practices, troubleshooting)
- **README.md:** Updated DR section with new ZIP export examples, added Disaster Recovery link to documentation index
- **FEATURES.md:** Added v6.2.0 ZIP export info, updated CLI command listing and technical details
- **USAGE.md:** Added `disaster-recovery export` subcommand to CLI structure, updated emergency recovery steps for both ZIP and legacy formats

---

## [6.2.0] - 2026-02-07

### ✨ Added
- **Disaster Recovery: Single-file encrypted ZIP export (#58):** New `disaster-recovery export` subcommand replaces the legacy 3-file bundle format
  - Single AES-256 encrypted ZIP file instead of separate `.tar.gz.enc`, `.PASSWORD`, and `.README` files
  - No external dependencies: uses native Python `pyzipper` library instead of `tar` and `openssl`
  - Automatic passphrase generation with interactive confirmation (word-based or random)
  - SSH stream mode (`--stream`) for zero-disk-footprint exports via `ssh user@server "sudo kopi-docka disaster-recovery export --stream --passphrase 'xxx'" > recovery.zip`
  - Automatic file ownership (sets to SUDO_USER when running via sudo)
  - Cross-platform extraction with standard tools (7-Zip, WinZip, unzip)
  - `--passphrase-type words|random` for choosing passphrase style
  - New dependency: `pyzipper>=0.3.6`

### ⚠️ Deprecated
- **Legacy 3-file DR bundle format:** Running `disaster-recovery` without `export` subcommand now shows a deprecation warning. The legacy format (tar.gz.enc + PASSWORD + README using tar/openssl) will be removed in a future release.

---

## [6.1.0] - 2026-02-07

### ✨ Added
- **Automatic `docker run` reconstruction for standalone containers (#59):** Restore process now automatically rebuilds and optionally restarts standalone containers (without docker-compose.yml)
  - New `DockerRunBuilder` helper parses `*_inspect.json` files and reconstructs complete `docker run` commands
  - Interactive prompts to start containers immediately after restore
  - Supports all common Docker parameters: ports, volumes, env vars, networks, capabilities, resources
  - Handles both bind mounts and named volumes
  - Filters out Docker-injected environment variables
  - Shows clear, copyable commands for manual execution
  - Checks for existing containers before attempting start
  - Added 30+ unit tests for comprehensive coverage

### 🔧 Changed
- **Restore workflow for standalone containers:** `_display_restart_instructions()` now detects inspect files and offers full command reconstruction instead of generic "recreate containers" message

---

## [6.0.2] - 2026-01-31

### 🐛 Fixed
- **Prevent parallel backup execution (#61):** Added global process lock to prevent concurrent `kopi-docka backup` runs
  - New `ProcessLock` helper using `fcntl.flock()` for kernel-managed locking
  - Lock file at `/run/kopi-docka.lock` (fallback: `/tmp/kopi-docka.lock`)
  - Second backup attempt exits gracefully with "Backup already running (PID: X), skipping"
  - Auto-release on process termination (no stale locks)
  - Added 16 unit tests for lock functionality

- **Setup wizard Kopia installation crash:** Fixed `ImportError` when user selected "Install Kopia automatically"
  - Removed dead import of non-existent `cmd_install_deps` function
  - New interactive 3-option menu: run official installer, show manual instructions, or exit
  - Supports Ubuntu/Debian, Fedora/RHEL, Arch Linux, macOS via official Kopia installer
  - Re-checks Kopia availability after installation attempt

### ✨ Added
- **ProcessLock helper** (`kopi_docka/helpers/process_lock.py`)
  - Non-blocking file lock using `fcntl.flock()`
  - Context manager support
  - PID tracking for debugging
  - Cross-process safe

---

## [6.0.1] - 2026-01-05

### 🐛 Fixed
- **dry-run crash on fresh installation (#57):** Fixed `[Errno 2] No such file or directory` error when configured work directory doesn't exist yet
  - `_disk_probe_base()` now walks up directory tree to find nearest existing parent
  - Handles edge cases: non-existent nested paths, remote URLs, filesystem root
  - Added 17 unit tests for comprehensive coverage

### 📝 Documentation
- **pipx installation improvements (#56):** Added instructions for making `sudo kopi-docka` work after pipx installation
  - README.md: Added symlink command after pipx install
  - docs/INSTALLATION.md: Added troubleshooting section with 3 solution options
  - Explains why pipx's `~/.local/bin/` is not in root's PATH

---

## [6.0.0] - 2025-12-31

### 🎉 Major Release: Stability & Safety

Version 6.0.0 represents a mature, production-ready release with a focus on **operational safety** and **code quality**. This release stabilizes the v5.x feature set and introduces critical safety mechanisms for graceful shutdown handling.

### ⚠️ DEPRECATION NOTICE

**Deprecated Methods (will be removed in v7.0.0):**
- ⚠️ `create_snapshot_from_stdin()` - deprecated since v5.0.0, still functional but raises `DeprecationWarning`
- ⚠️ `from_stdin` parameter - deprecated, use directory paths for block-level deduplication
- ✅ **Recommended:** Use `create_snapshot()` with directory paths instead

### ✨ Added

**SafeExitManager - Graceful Shutdown Architecture:**
- New `SafeExitManager` singleton with two-layer architecture:
  - **Process Layer**: Automatic subprocess tracking (SIGTERM → 5s → SIGKILL)
  - **Strategy Layer**: Context-aware cleanup handlers with priorities
- Three handler types:
  - `ServiceContinuityHandler` (Priority 10): Restarts containers on backup abort (LIFO order)
  - `DataSafetyHandler` (Priority 20): Keeps containers stopped during restore abort
  - `CleanupHandler` (Priority 50): Generic cleanup for temp dirs, DR bundles
- Signal handlers for SIGINT/SIGTERM installed on startup
- Prevents: zombie processes, orphaned stopped containers, temp dir accumulation, held Kopia locks

**Pydantic Configuration Validation:**
- Config class now uses Pydantic v2 for schema validation
- Type-safe configuration loading with automatic validation
- Clear error messages for invalid configuration values
- Backward compatible with existing config files

**Improved Config Wizard UX:**
- New wizard flow with existing repository detection
- Support for `--reinit` flag to reconfigure existing repositories
- Kopia parameters displayed in change-password panel
- Better error handling and user guidance

**Repository Helper (`repo_helper.py`):**
- New helper for repository detection and validation
- Centralized logic for existing repo checks
- Used by config wizard and repository commands

### 🔧 Changed

**Core Manager Integration:**
- `BackupManager`: Integrated SafeExitManager for container restart on abort
- `RestoreManager`: Integrated SafeExitManager for data safety on abort
- `DisasterRecoveryManager`: Integrated SafeExitManager for bundle cleanup
- `HooksManager`: Integrated SafeExitManager for hook process cleanup

**run_command() Hardening:**
- All subprocesses automatically tracked by SafeExitManager
- Proper cleanup on application termination
- No more orphaned processes after Ctrl+C

**Dead Code Cleanup:**
- Removed unused imports across all modules
- Cleaned up commented-out code blocks
- Improved code consistency

### 🧪 Testing

**New Test Coverage:**
- 676 lines of unit tests for SafeExitManager
- 572 lines of integration tests for abort scenarios
- Manual testing guide: `tests/MANUAL_TESTING_SAFE_EXIT.md`
- Tests for: singleton pattern, process tracking, handler priorities, LIFO restart order, thread safety

**Test Scenarios:**
- Container restart on backup abort (LIFO order)
- Containers remain stopped on restore abort
- Temp directory cleanup on DR abort
- Subprocess termination (SIGTERM → SIGKILL escalation)
- Concurrent operation handling

### 📝 Documentation

**Updated Documentation:**
- ARCHITECTURE.md: Added SafeExitManager section with diagrams
- FEATURES.md: Updated for v6.0.0 capabilities
- DEVELOPMENT.md: Added safety testing guidelines
- USAGE.md: Updated CLI reference

### 🔗 Migration from v5.x

**For existing users:**
1. **Backup behavior unchanged** - same CLI, same results
2. **Graceful shutdown automatic** - no configuration needed
3. **Old configs work** - Pydantic validation is backward compatible
4. **Ctrl+C safe** - containers auto-restart after backup abort

**Breaking change migration:**
- If using `create_snapshot_from_stdin()`: Switch to `create_snapshot()` with directory path
- TAR-based workflows: Update to use direct Kopia snapshots (better deduplication)

---

## [5.5.1] - 2025-12-28

### ✨ Added

**Backup Scope Tracking:**
- All snapshots now include `backup_scope` tag (minimal/standard/full)
- Enables scope detection during restore operations
- Visible in `kopia snapshot list --tags` for debugging
- Automatic tracking eliminates guesswork about backup capabilities

**Docker Config Backup (FULL scope):**
- New `_backup_docker_config()` method backs up Docker daemon configuration
- Includes `/etc/docker/daemon.json` if present
- Includes `/etc/systemd/system/docker.service.d/` systemd overrides if present
- Only runs when using `--scope full` flag
- Non-fatal errors: logs warnings and continues backup
- Enables complete disaster recovery with daemon settings preserved

**Backup Scope Selection in Setup Wizard:**
- Interactive scope selection during `kopi-docka advanced config new`
- Three options with clear descriptions:
  - **minimal** - Volumes only (fastest, smallest backups)
  - **standard** - Volumes + Recipes + Networks [RECOMMENDED]
  - **full** - Everything + Docker daemon config (DR-ready)
- Warning confirmation for minimal scope selection
- Default is `standard` (best balance for most users)

**Restore Scope Detection and Warnings:**
- RestoreManager reads `backup_scope` tag from snapshots
- **MINIMAL scope backups** show prominent warning panel:
  - "This backup contains ONLY volume data"
  - "Container recipes (docker-compose files) are NOT included"
  - Lists restore limitations (manual container/network recreation required)
- Docker config snapshots displayed in restore list (manual restore only)
- Legacy snapshots without tag default to "standard" scope (backward compatible)

**Config Template Extension:**
- Added `backup_scope` field to `config_template.json`
- New `backup_scope` property in Config class with fallback to "standard"
- Explicit default replaces implicit code-based default
- Easier to understand and modify user preferences

**Docker Config Manual Restore Command:**
- New command: `kopi-docka show-docker-config <snapshot-id>`
- Extracts docker_config snapshots from FULL scope backups to temp directory
- Displays safety warnings about manual restore requirements
- Shows extracted files (daemon.json, systemd overrides) with sizes
- Displays daemon.json contents inline (if <10KB)
- Provides 6-step manual restore instructions with safety warnings
- Prevents accidental production breakage from automatic daemon.json restoration
- Example: `sudo kopi-docka show-docker-config k1a2b3c4d5e6f7g8`

### 🔧 Changed

**BackupManager Enhancements:**
- All snapshot methods (`_backup_volume`, `_backup_recipes`, `_backup_networks`) now accept `backup_scope` parameter
- `backup_unit()` passes scope to all backup methods
- Snapshot tags include `backup_scope` field for all snapshot types (volume, recipe, networks, docker_config)
- `backup_scope == BACKUP_SCOPE_FULL` triggers docker_config backup

**BackupMetadata Tracking:**
- Added `backup_scope: str` field to BackupMetadata dataclass
- Added `docker_config_backed_up: bool` field to track docker_config backup status
- Both fields included in `to_dict()` for JSON serialization
- Metadata JSON now contains scope for reference and debugging

**RestoreManager Improvements:**
- New `_get_backup_scope()` method reads scope from snapshot tags
- New `_show_scope_warnings()` displays scope-specific warnings
- Extended RestorePoint type with `docker_config_snapshots` field
- Updated snapshot grouping to recognize `type=docker_config` snapshots
- Integrated scope warnings into restore workflow

### 🧪 Testing

**New Test Coverage:**
- 7 unit tests for backup_scope tag presence in all snapshot types
- 7 unit tests for docker_config backup functionality
- 10 unit tests for restore scope detection and warnings
- All tests passing (88 backup_manager tests, all restore_manager tests)

**Test Scenarios:**
- backup_scope tag verification in volume/recipe/network snapshots
- docker_config backup with daemon.json and systemd overrides
- Permission error handling (non-fatal)
- Scope detection from snapshots
- Legacy snapshot handling (default to "standard")
- Minimal scope warning display
- docker_config snapshot recognition

### ⚠️ Important: Backup Scope Restore Matrix

**What can be restored with each scope:**

| Scope | Volumes | Container Configs | Networks | Docker Daemon Config |
|-------|---------|-------------------|----------|---------------------|
| **minimal** | ✅ Yes | ❌ No* | ❌ No | ❌ No |
| **standard** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| **full** | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Manual** |

**Notes:**
- \* **Minimal scope limitation:** Only volume data is backed up. After restore, you must manually recreate containers using your original docker-compose.yml files or container run commands. Networks must also be manually recreated.
- \*\* **Docker config restore:** Docker daemon configuration is backed up but **not automatically restored** for safety. Use manual restore to review and apply configuration changes.

**Scope Selection Guidance:**
- **Use minimal** when you only need data backups and always have your docker-compose files available
- **Use standard** (recommended) for complete container restore capability with recipes and networks
- **Use full** for complete disaster recovery scenarios requiring Docker daemon configuration preservation

### 📝 Migration

**For existing users:**
1. **No action required** - default scope is `standard` (same behavior as before)
2. **Old snapshots work** - snapshots without `backup_scope` tag default to "standard"
3. **New config field** - `backup_scope` added to config template, existing configs will use "standard" default
4. **To enable docker_config backup:** Use `--scope full` flag or set `backup_scope: "full"` in config

**Backward Compatibility:**
- All existing snapshots remain fully restorable
- Legacy snapshots without `backup_scope` tag are treated as "standard" scope
- No breaking changes to CLI or configuration format

### 🔗 Configuration Examples

**Set backup scope in config:**
```json
{
  "backup": {
    "backup_scope": "standard"
  }
}
```

**Override scope via CLI:**
```bash
sudo kopi-docka backup --scope minimal    # Volumes only (fastest)
sudo kopi-docka backup --scope standard   # Recommended default
sudo kopi-docka backup --scope full       # Include Docker daemon config
```

---

## [5.5.0] - 2025-12-28

### 🎯 Think Simple Strategy

This release represents a major philosophical shift: **Kopi-Docka expects a prepared system**. We've removed all automatic installation and distro detection logic in favor of user responsibility and system simplicity.

### ⚠️ BREAKING CHANGES

**Removed Features:**
- ❌ **`kopi-docka install-deps` command** - No longer exists
- ❌ **Automatic dependency installation** - All `install_dependencies()` methods removed
- ❌ **Distro detection logic** - No more `/etc/*-release` parsing
- ❌ **Package manager integration** - No apt, yum, pacman, apk support
- ❌ **`distro` library dependency** - Removed from requirements

**What this means for users:**
- You must manually install Docker and Kopia before using Kopi-Docka
- Or use [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten) for automated system setup
- `kopi-docka doctor` shows what's missing but won't install anything
- Backend dependencies (SSH, Tailscale, Rclone) must be installed manually

### ✨ Added

**Hard/Soft Gate Dependency System:**
- **Hard Gate (MUST_HAVE)**: Docker + Kopia - Non-skippable, always checked
  - Commands refuse to run if missing
  - Clear error messages with installation URLs
- **Soft Gate (SOFT)**: tar, openssl - Skippable with `--skip-dependency-check`
  - Checked before disaster recovery
  - Can bypass for advanced users

**New Infrastructure:**
- `DependencyHelper` utility class (`helpers/dependency_helper.py`)
  - Centralized CLI tool detection
  - Version parsing with edge case handling (v-prefix, suffixes, stderr, multiline)
  - Methods: `exists()`, `get_path()`, `get_version()`, `check()`, `check_all()`, `missing()`
- Dependency categories: `MUST_HAVE`, `SOFT`, `BACKEND`, `OPTIONAL`
- `check_hard_gate()` - Enforces docker + kopia (non-bypassable)
- `check_soft_gate(tools, skip=False)` - Enforces optional tools (bypassable)

**Backend Improvements:**
- All backends now have `REQUIRED_TOOLS` list
- Standardized `check_dependencies()` using DependencyHelper
- New `get_dependency_status()` returns detailed tool info
- OpenSSH dependency tracking (ssh, ssh-keygen) for Tailscale/SFTP
- Backends raise `DependencyError` before setup if tools missing

**Command Integration:**
- `backup` command: Hard gate check (docker + kopia)
- `restore` command: Hard gate check (docker + kopia)
- `disaster-recovery` command: Kopia check + soft gate (tar, openssl)
- `--skip-dependency-check` flag for disaster-recovery (affects only tar/openssl)

**Enhanced `doctor` Command:**
- Section 1: System Information (OS, Python, Kopi-Docka version)
- Section 2: Core Dependencies with categories (MUST_HAVE, SOFT, BACKEND, OPTIONAL)
- Section 3: Systemd Integration (systemctl, journalctl)
- Section 4: Backend Dependencies (per configured backend)
- Color-coded status indicators (green=installed, red=missing)
- Version display for all tools

**Server-Baukasten Integration:**
- All error messages include Server-Baukasten link
- Automated system preparation alternative
- Handles distro-specific quirks
- Recommended for users who want automated setup

### 🔧 Changed

**DependencyManager Simplification:**
- Removed 711 lines → 424 lines (40% reduction)
- No more distro detection (`_detect_distro` removed)
- No more package manager logic (`_get_package_manager` removed)
- No more install methods (`install_dependencies`, `install_missing`, `auto_install` removed)
- Simplified error messages: "Please install manually" + Server-Baukasten link

**Backend Refactoring:**
- `TailscaleBackend`: Added REQUIRED_TOOLS, removed install logic
- `RcloneBackend`: Added REQUIRED_TOOLS, removed install logic
- `SFTPBackend`: Replaced stub dependency check, added REQUIRED_TOOLS
- All backends have stub `install_dependencies()` that raises `NotImplementedError`

**Documentation:**
- Completely rewritten `docs/INSTALLATION.md`
  - Think Simple philosophy explained
  - Clear Hard/Soft Gate documentation
  - Server-Baukasten prominent
  - Migration guide from v5.4.x
- Error messages now actionable with installation URLs
- No more promises of automatic installation

### 🧪 Testing

**New Test Suites:**
- `test_dependency_helper.py`: 27 tests for DependencyHelper (edge cases, mocking)
- `test_dependency_manager.py`: 34 tests for Hard/Soft Gate system
- `test_tailscale_backend.py`: 14 tests for Tailscale dependency enforcement
- `test_sftp_backend.py`: 17 tests for SFTP dependency enforcement
- `test_rclone_backend.py`: 5 new dependency tests
- Total: 97 new/updated tests, all passing

**Test Coverage:**
- Hard gate non-bypassable behavior
- Soft gate skip flag functionality
- OpenSSH dual-tool checking (ssh + ssh-keygen)
- Distro detection removal verification
- Backend REQUIRED_TOOLS enforcement

### 📝 Migration Guide

**From v5.4.x to v5.5.0:**

1. **Before upgrading**, ensure Docker and Kopia are installed:
   ```bash
   docker --version
   kopia --version
   ```

2. **After upgrading**, verify dependencies:
   ```bash
   kopi-docka doctor
   ```

3. **If dependencies are missing:**
   - Manual installation: See [docs/INSTALLATION.md](docs/INSTALLATION.md)
   - Automated: Use [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten)

4. **If you used `install-deps`:**
   - This command no longer exists
   - Use Server-Baukasten for automation
   - Or install manually (one-time setup)

### 🎓 Philosophy

**Why "Think Simple"?**
- **Simpler codebase**: Less code, fewer bugs, easier maintenance
- **No sudo execution**: Kopi-Docka never runs privileged commands
- **User responsibility**: You control your system, we provide tools
- **Works everywhere**: No distro-specific logic to maintain
- **Clear separation**: System prep vs backup tool

**External automation:**
- [Server-Baukasten](https://github.com/TZERO78/Server-Baukasten) handles system setup
- Battle-tested, distro-aware
- Separate concern from backup operations

### 🔗 Links

- **Server-Baukasten**: https://github.com/TZERO78/Server-Baukasten
- **Docker Installation**: https://docs.docker.com/engine/install/
- **Kopia Installation**: https://kopia.io/docs/installation/
- **Installation Guide**: [docs/INSTALLATION.md](docs/INSTALLATION.md)

---

## [5.4.3] - 2025-12-27

### Fixed

- **ImportError in wizard integration**
  - Fixed `ImportError: cannot import name '_notification_setup_cmd'`
  - Extracted setup logic into importable `run_notification_setup()` function
  - Updated config_commands.py and setup_commands.py to use new function
  - Wizard integration now works correctly when called from setup/config commands

### Changed

- `notification_commands.py`:
  - Created `run_notification_setup(config)` - Importable function containing setup logic
  - Simplified `_notification_setup_cmd` to call the new function
  - Returns bool indicating success/skip
- `config_commands.py` and `setup_commands.py`:
  - Import `run_notification_setup` instead of `_notification_setup_cmd`
  - Removed unnecessary SimpleNamespace context creation
  - Direct function call with config object

## [5.4.2] - 2025-12-27

### Fixed

- **Email Notification Display Name - Proper URL Encoding**
  - Fixed URL encoding for email sender display name
  - Added `urllib.parse.quote()` to properly encode spaces and special characters
  - Format: `Display Name <email>` → `Display%20Name%20%3Cemail%3E`
  - Changed prompt text from "Display Name" to "Sender Display Name" for clarity
  - Example URL: `mailto://user@smtp.gmail.com:587?to=admin@example.com&from=Kopi-Docka%20%3Cuser@gmail.com%3E`
  - Updated documentation with URL-encoded examples and encoding reference

### Changed

- `notification_commands.py`:
  - Added `from urllib.parse import quote`
  - Properly URL-encode from-header: `quote(f"{display_name} <{username}>", safe='')`
  - Append encoded parameter: `&from={encoded_from}`
- `docs/NOTIFICATIONS.md`:
  - Updated manual configuration with URL-encoded example
  - Added URL encoding reference note (Space=%20, <=%3C, >=%3E)
- `docs/CONFIGURATION.md`:
  - Updated email example with properly encoded from parameter

## [5.4.1] - 2025-12-27

### Fixed

- **Email Notification Setup Enhancement** (⚠️ Incomplete - Fixed in v5.4.2)
  - Added "Display Name" prompt in email setup wizard
  - Email sender now shows custom display name instead of just email address
  - Example: "Kopi-Docka Backup <user@gmail.com>" instead of "user@gmail.com"
  - ⚠️ Note: Missing proper URL encoding - fixed in v5.4.2

### Changed

- Updated `notification_commands.py` - Email setup wizard now asks for display name
- Updated `docs/NOTIFICATIONS.md` - Added display name to setup instructions
- Updated `docs/CONFIGURATION.md` - Email example now includes from parameter

## [5.4.0] - 2025-12-27

### Added

- **Notification System** 🔔
  - Automatic notifications for backup success/failure via popular messaging platforms
  - **Supported Services:**
    - Telegram - Free messaging app with bot integration
    - Discord - Webhook-based notifications
    - Email - SMTP-based email alerts
    - Webhook - JSON POST to custom endpoints (n8n, Make, Zapier)
    - Custom - Any Apprise-compatible service (100+ services supported)
  - **Interactive Setup Wizard:**
    - `kopi-docka advanced notification setup` - Step-by-step configuration
    - Service-specific handlers for easy setup
    - Secure secret storage (file-based or config-based)
  - **Management Commands:**
    - `kopi-docka advanced notification test` - Send test notification
    - `kopi-docka advanced notification status` - Show current configuration
    - `kopi-docka advanced notification enable/disable` - Toggle notifications
  - **Key Features:**
    - Fire-and-forget pattern - notifications never block backups
    - 10-second timeout protection
    - 3-way secret management (file > config > none)
    - Environment variable substitution in URLs (`${VAR_NAME}`)
    - Separate control for success/failure notifications (`on_success`, `on_failure`)
    - Comprehensive error handling and logging
  - **Implementation:**
    - New `NotificationManager` core class
    - New `BackupStats` dataclass for structured notification data
    - Integration in `BackupManager` - sends notification at end of each backup unit
    - 40 unit tests with full coverage
    - Uses Apprise library for multi-service support
  - **Documentation:**
    - New `docs/NOTIFICATIONS.md` with complete setup guides
    - Service-specific examples (Telegram, Discord, Email, Webhook)
    - Troubleshooting section
    - Security best practices

### Technical

- Added `apprise>=1.6.0` dependency for notification support
- Extended config schema with `notifications` section
- Exported `NotificationManager` and `BackupStats` in `cores/__init__.py`
- Registered notification commands under `advanced notification` subgroup

## [5.3.2] - 2025-12-27

### Fixed

- **Wizard Command References**: Updated all interactive wizards to reference `advanced` instead of `admin`
  - Setup wizard: Post-setup next steps now show `kopi-docka advanced`
  - Doctor command: System check recommendations updated
  - Config wizard: Configuration hints now use correct command group
  - Backup/Restore wizards: Error messages show correct commands
  - Service wizard: Management hints updated
  - Affects 10 command files with 26 instances updated
  - Ensures consistency with v5.3.1 CLI UX changes

## [5.3.1] - 2025-12-27

### Changed

- **CLI UX Improvements:**
  - Dynamic version display in `--help` header (shows current version automatically)
  - Renamed `admin` command group to `advanced` for better clarity
  - Help text updated to "Advanced tools (Config, Repo, System)."
  - Hidden wrapper commands from help menu while preserving functionality:
    - Dependency commands: `check`, `install-deps`, `show-deps`
    - Repository commands: `init`, `repo-*`, `change-password`
    - Service command: `daemon`
  - Result: Cleaner `kopi-docka --help` output showing only primary commands and advanced group

### Technical

- Updated `kopi_docka/__main__.py` to import `__version__` dynamically
- Modified `dependency_commands.register()` to support `hidden=True` parameter
- Modified `repository_commands.register()` to support `hidden=True` parameter
- Backward compatibility: All hidden commands remain fully functional
- Legacy `admin` command alias preserved (hidden) for backward compatibility

## [5.3.0] - 2025-12-27

### Fixed

- **CRITICAL: Direct Mode Retention Policies Now Work** 🔥
  - **Issue**: Since v5.0, retention policies (e.g., `latest: 3`) failed to delete old volume backups in Direct Mode
  - **Root Cause**: Policies were applied to virtual paths (`volumes/myproject`) but snapshots used actual mountpoints (`/var/lib/docker/volumes/myproject_data/_data`)
  - **Impact**: Repositories grew unbounded, storage costs increased significantly
  - **Solution**: Retention policies now correctly applied to actual volume mountpoints in Direct Mode
  - **Details**: `BackupManager._ensure_policies()` now detects backup format and applies policies to appropriate paths
  - TAR Mode behavior unchanged (uses virtual paths as before)
  - Mixed repositories (old TAR + new Direct backups) handled correctly
  - **Migration**: No action required - retention will work automatically on next backup

- **Rclone Backend Improvements** (#29)
  - **Fixed**: Rclone config detection now distinguishes permission errors from missing config
  - **Fixed**: Better handling of sudo usage with rclone configuration
  - **Improved**: Clear error messages when config is found but not readable
  - **Impact**: Prevents confusing "config not found" errors when permission issues exist

- **CLI Config Handling**
  - Fixed configuration loading and related tests
  - Improved config file detection and validation

### Added

- **Stable Staging Paths for Recipe/Network Metadata** 🎯
  - Recipe backups now use `/var/cache/kopi-docka/staging/recipes/<unit-name>/`
  - Network backups now use `/var/cache/kopi-docka/staging/networks/<unit-name>/`
  - **Why**: Replaced random temp directories (`/tmp/tmpXYZ...`) with stable paths
  - **Benefit**: Enables Kopia retention policies to work correctly for metadata
  - **Impact**: Prevents "ghost sessions" (empty backup sessions with only metadata, no volumes)
  - **Implementation**: New `_prepare_staging_dir()` helper method for directory management
  - Staging directories are cleared and reused on each backup (idempotent)
  - Better debuggability (can inspect staging dir on errors)

- **New Command: `kopi-docka advanced repo prune-empty-sessions`** 🧹
  - Clean up legacy "ghost sessions" from repositories created before v5.3.0
  - Identifies backup sessions with only recipe/network snapshots (no volumes)
  - **Dry-run mode by default** - preview what would be deleted without making changes
  - Use `--no-dry-run` flag to perform actual deletion
  - Rich table display showing backup ID, recipe count, network count
  - Confirmation prompt before deletion (double safety)
  - Progress bar with spinner during deletion
  - **Use case**: Clean up repositories with accumulated empty sessions from pre-5.3.0 backups

- **MASSIVE Test Coverage Improvements** 🧪
  - **Integration Tests**:
    - Comprehensive hooks and cross-machine restore tests
    - Full backup→restore integration test suite
    - TAR format tests for legacy backup/restore compatibility
    - Stable staging directory functionality tests
    - Direct Mode retention policy verification
  - **Unit Tests**:
    - P1 edge case tests for backup manager
    - Comprehensive disaster recovery and restore operation tests
    - Critical backup/restore path coverage
    - Error handling tests for backup/restore operations
    - Staging directory management tests (8 new tests)
  - **Test Infrastructure**:
    - Improved pytest configuration with parallelization support (`pytest-xdist`)
    - Better test markers (unit, integration, slow, requires_docker, requires_root)
    - Enhanced test fixtures and utilities
  - **Coverage**: Significantly improved test coverage across critical paths

- **Documentation & Infrastructure** 📚
  - **CLAUDE.md**: Quick reference guide for Claude Code assistance
  - **Machine-Readable Architecture**: JSON format architecture documentation
  - **Mermaid CI Workflow**: Automatic SVG rendering of architecture diagrams on GitHub
  - **Code of Conduct**: Added community guidelines
  - **Architecture Organization**: Moved ARCHITECTURE.md into docs/ folder
  - **Rclone Backend Documentation**: Comprehensive guide for rclone backend and sudo behavior

### Changed

- **Code Quality Improvements** ✨
  - **Centralized Subprocess Handling**: Migrated to `run_command()` wrapper throughout codebase
    - Repository commands now use standardized subprocess calls
    - Service manager uses run_command for systemctl operations
    - Lock PID checks use run_command
    - Daemon backup invocations standardized
    - Improved error handling and logging consistency
  - **UI Design Coverage**: Added automated test for UI component coverage
  - **Pytest Configuration**: Better parallelization and test organization

- **Documentation Updates** 📖
  - **USAGE.md**: Added "Retention Policies (Direct Mode vs TAR Mode)" section explaining path matching behavior
  - **CONFIGURATION.md**: Added comprehensive "Retention Policies" section with path matching examples
  - **ARCHITECTURE.md**: Updated backup flow diagrams and method descriptions to reflect stable staging paths
  - All documentation now clearly explains v5.3.0 retention fixes and stable staging feature
  - Updated references from v5.2.1 to v5.3.0 throughout documentation

### Removed

- Obsolete files: `PR_DESCRIPTION.md`, `RELEASE_NOTES.md`, `requirements.txt`
- Planning documents: `PROBLEM_1_PLAN.md`, `PROBLEM_2_PLAN.md`

### Technical Details

- **Files Modified**:
  - `kopi_docka/cores/backup_manager.py` - Updated `_ensure_policies()`, `_backup_recipes()`, `_backup_networks()`, added `_prepare_staging_dir()`
  - `kopi_docka/helpers/constants.py` - Added `STAGING_BASE_DIR` constant and documentation
  - `kopi_docka/cores/repository_manager.py` - Added `delete_snapshot()` method
  - `kopi_docka/commands/repository_commands.py` - Added `prune_empty_sessions` command

- **Tests Added**:
  - 8 new unit tests for `_prepare_staging_dir()` method
  - 3 integration tests for stable staging functionality
  - 1 integration test for Direct Mode retention (proves old snapshots are deleted)
  - Fixed 2 existing tests to work with new staging implementation
  - **Total**: 74 unit tests passing, 4 new integration tests

### Migration Guide

**No action required!** This release is fully backward compatible:
- ✅ Existing repositories work without modification
- ✅ Old TAR-based backups remain fully restorable
- ✅ Old Direct Mode backups remain restorable
- ✅ Retention policies will start working automatically on next backup
- 💡 **Optional**: Run `kopi-docka advanced repo prune-empty-sessions` to clean up old ghost sessions

### Performance Impact

- **Storage**: Reduced repository growth (retention now works correctly)
- **Metadata**: Slightly fewer snapshots created (no more ghost sessions)
- **Debugging**: Easier to inspect staging directories (stable paths)
- **No negative performance impact** - changes are additive

---

## [5.2.1] - 2025-12-26

### Added

- **CLAUDE.md** - Quick reference guide for Claude Code assistance
- **Machine-Readable Architecture** - JSON format for architecture documentation
- **Mermaid CI Workflow** - Automatic SVG rendering of architecture diagrams

### Changed

- **Documentation Reorganization** - Moved `ARCHITECTURE.md` into `docs/` folder
- **Code of Conduct** - Added community guidelines and synced documentation
- **CI Pipeline** - Multiple improvements for Mermaid diagram rendering on GitHub runners

### Removed

- Obsolete files: `PR_DESCRIPTION.md`, `RELEASE_NOTES.md`, `requirements.txt`
- Planning documents: `PROBLEM_1_PLAN.md`, `PROBLEM_2_PLAN.md`

---

## [5.2.0] - 2025-12-24

### Added

- **Centralized `run_command()` Wrapper** - New subprocess helper in `ui_utils.py`
  - Standardized error handling for all subprocess calls
  - Consistent logging and output capture
  - Foundation for improved testability
- **UI Design Coverage Test** - Automated test for UI component coverage

### Changed

- **Subprocess Migration** - Migrated all subprocess calls to `run_command()`:
  - `backup_manager.py` - Backup execution calls
  - `restore_manager.py` - 21 subprocess calls migrated
  - `service_helper.py` - 14 subprocess calls migrated
  - `tailscale.py` - 9 subprocess calls migrated
  - `rclone.py` - 5 subprocess calls migrated
  - Repository commands, service manager, daemon backup invocations
- **Restore Network Handling** - Improved network recreation with better container handling

### Fixed

- **CLI Config Handling** - Fixed configuration loading and related tests
- **Advanced Restore Mode** - Fixed datetime comparison in advanced restore workflow

---

## [5.1.0] - 2025-12-23

### Added

- **Advanced Restore with Cross-Machine Support** (`--advanced`)
  - New `kopi-docka restore --advanced` for cross-machine restore
  - Machine discovery: shows all machines with backups in repository
  - Cross-machine warning with conflict detection hints
  - `MachineInfo` dataclass for machine metadata aggregation
  - `list_all_snapshots()` method with `--all` flag for full repository scan
  - `discover_machines()` method for machine enumeration
  - Use case: Restore from crashed server to new hardware

---

## [5.0.0] - 2025-12-23

### BREAKING CHANGES

- **Direct Kopia Snapshots** - Volume backups now use direct Kopia snapshots instead of TAR streams
  - **Impact**: Block-level deduplication now works correctly
  - **Impact**: Incremental backups are significantly smaller and faster
  - **Migration**: No action required - old TAR-based backups remain fully restorable
  - **Compatibility**: Kopi-Docka < 5.0 cannot restore backups created with v5.0+

### Added

- **Direct Backup Format** (`backup_format: direct`)
  - New `_backup_volume_direct()` method for direct Kopia snapshots
  - New `_execute_volume_restore_direct()` for restoring direct snapshots
  - Automatic format detection in restore workflow
  - `backup_format` tag added to all volume snapshots
  - `backup_format` field added to `BackupMetadata` dataclass
- **Exclude Patterns for Direct Mode** - `exclude_patterns` config now works with direct snapshots
- **Constants**: `BACKUP_FORMAT_TAR`, `BACKUP_FORMAT_DIRECT`, `BACKUP_FORMAT_DEFAULT`

### Changed

- **Default Backup Format** - Changed from TAR to direct Kopia snapshots
- **Restore Logic** - Now auto-detects backup format and uses appropriate restore method
- `create_snapshot()` now accepts optional `exclude_patterns` parameter

### Deprecated

- **`create_snapshot_from_stdin()`** - Deprecated in favor of `create_snapshot()`
  - Will be removed in v6.0.0
  - TAR-based backups prevent block-level deduplication

### Fixed

- **Storage Efficiency** - 100 GB volume with 1 GB changes now only backs up ~1 GB (was 100 GB)

---

## [4.2.5] - 2025-12-22

### Fixed
- **ProtectSystem Setting** - Changed from `strict` to `full` for proper filesystem access
  - Service can now write to all necessary Kopia directories without explicit paths
  - Fixed all "read-only file system" errors during backup execution
  - Removed `ReadWritePaths` lines (not needed with `ProtectSystem=full`)
  - `ProtectSystem=full` makes only `/usr`, `/boot`, `/efi` read-only

---

## [4.2.4] - 2025-12-22

### Fixed
- **Timer-Triggered Mode Restart Loop** - Timer now triggers oneshot backup service
  - Changed `kopi-docka.timer` to trigger `kopi-docka-backup.service` (Type=oneshot)
  - Prevents infinite restart loops when timer triggers the daemon service
  - Service now properly: starts → runs backup → exits cleanly
  - No more systemd timeouts or "restart counter is at 702" errors
  - Timer-triggered mode is now the recommended approach
- **Service Permission Errors** - Added missing ReadWritePaths for Kopia directories
  - Added `/root/.config/kopia` for Kopia repository configuration
  - Added `/root/.cache/kopia` for Kopia logs and cache
  - Added `/etc/kopi-docka.json` and `/etc/.kopi-docka.password` for app config
  - Added `/tmp` for temporary files during backup operations
  - Changed `PrivateTmp=no` to allow access to real `/tmp` directory
  - Fixes "read-only file system" and "no such file or directory" errors

### Changed
- **Clarified Service Architecture**:
  - `kopi-docka.timer` → triggers `kopi-docka-backup.service` (Type=oneshot)
  - `kopi-docka.service` → daemon mode with internal scheduling (Type=notify)
- Updated systemd template documentation to explain both modes
- Improved header comments in all three service unit templates

---

## [4.2.2] - 2025-12-22

### Fixed
- **Rclone Config: Single Source of Truth** - Use user's config path directly instead of copying
  - Follows industry best practice (same approach as Restic, rclone docs)
  - Uses `--config` parameter to reference user's config directly
  - Prevents config duplication and OAuth token staleness
  - Preserves `root_folder_id` and other user settings correctly
  - Eliminates confusion from having multiple config files

### Changed
- Removed config copying logic (`_copy_user_config_to_root()`)
- Simplified config detection to find and use path directly
- Improved user messaging during config detection

---

## [4.2.1] - 2025-12-22

### Fixed
- **Rclone Config Root Issue** - Copy user's rclone config to root when running with sudo
  - Detects when user has `root_folder_id` setting that root config lacks
  - Offers to copy user config to `/root/.config/rclone/rclone.conf`
  - Preserves all settings (root_folder_id, tokens, etc.)
  - Backs up existing root config before overwriting
  - Prevents folders being created in wrong location (Drive root vs user's folder)

---

## [4.2.0] - 2025-12-22

### Added
- **Auto-Create Remote Folders with Hostname Suffix** for Rclone backend
  - Default remote path now includes sanitized hostname (e.g., `kopia-backup_MYSERVER`)
  - Prevents Kopia repository conflicts when multiple machines use the same cloud storage
  - Automatic folder creation prompt when remote folder doesn't exist
  - `get_default_remote_path()` function for hostname-based path generation
  - `_check_remote_path_exists()` method to verify folder existence
  - `_rclone_mkdir()` method to create remote folders via rclone

### Changed
- **Rclone Backend Configuration** - Improved UX with folder detection and creation
  - Shows folder existence check during configuration
  - Offers to create missing folders with user confirmation
  - Handles edge cases: empty hostnames, special characters, mkdir failures

### Use Cases
- Multi-machine setups using the same cloud storage (e.g., Google Drive, OneDrive)
- VPS1 → `gdrive:kopia-backup_VPS1/`
- VPS2 → `gdrive:kopia-backup_VPS2/`
- Each machine gets its own Kopia repository automatically

---

## [4.1.1] - 2025-12-22

### Fixed
- **DependencyManager Import** - Fixed missing import in `setup_commands.py`

---

## [4.1.0] - 2025-12-22

### Added
- **Non-Interactive Restore Mode** - New `--yes` / `-y` flag for `restore` command
  - Enables fully automated restore operations for CI/CD pipelines
  - Automatic session selection (newest backup)
  - Automatic unit selection (first available)
  - Skips all confirmation prompts
  - Auto-recreates networks on conflict
  - Restores all volumes without prompting
  - Uses default directory for configs with auto-backup on conflict

### Use Cases
- CI/CD pipeline testing (`sudo kopi-docka restore --yes`)
- Automated disaster recovery drills
- Scheduled restore verification scripts

---

## [4.0.0] - 2025-12-22

### Added
- **rich-click Integration** - Beautiful styled `--help` output with syntax highlighting
- **11 New UI Components** in `ui_utils.py`:
  - `print_panel()` - Styled content panels
  - `print_menu()` - Menu display helper
  - `print_step()` - Progress step indicators
  - `print_divider()` - Section dividers
  - `print_success_panel()` - Green success boxes
  - `print_error_panel()` - Red error boxes
  - `print_warning_panel()` - Yellow warning boxes
  - `print_info_panel()` - Cyan info boxes
  - `print_next_steps()` - Next steps list
  - `get_menu_choice()` - Menu selection helper
  - `confirm_action()` - Confirmation prompt
  - `create_status_table()` - Status table builder
- **Unit tests** for new UI components (`tests/unit/test_helpers/test_ui_utils.py`)

### Changed
- **Complete UI Consistency Refactoring** - All 11 command files modernized with Rich
  - `setup_commands.py` - Wizard panels and step indicators
  - `config_commands.py` - Configuration menus and password displays
  - `backup_commands.py` - Backup progress and status
  - `dry_run_commands.py` - Simulation tables and estimates
  - `repository_commands.py` - Repository status and initialization
  - `dependency_commands.py` - Dependency checks
  - `advanced/snapshot_commands.py` - Snapshot listings
- **Consistent Color Scheme** across all commands:
  - Green: Success messages
  - Red: Error messages
  - Yellow: Warning messages
  - Cyan: Information messages
- Replaced all `typer.echo()` with Rich `console.print()`
- Rich Tables for data presentation (backup units, snapshots, size estimates)
- Rich Panels for structured information display

### Fixed
- **log_manager.configure() -> log_manager.setup()** - Corrected method name in `__main__.py`
- **ui_utils.py imports** - Added missing `Progress`, `SpinnerColumn`, `TextColumn` imports
- Added `Tuple` type hint and `box` import for table styling

### Dependencies
- Added `rich-click>=1.7.0`

### Breaking Changes
- **None** - This is a UI-only update. All command APIs remain unchanged.

---

## [3.9.1] - 2025-12-21

### Added
- **Stale Lock Removal** - New `remove_stale_lock()` method in ServiceHelper
- **Menu Option** - "Remove Stale Lock File" option in service wizard

### Changed
- **Lock Status Display** - Rich panels instead of simple text
- **Process Checking** - More portable using `os.kill(pid, 0)`

### Fixed
- Improved lock file diagnostics and stale lock detection
- Better error handling in ServiceHelper

---

## [3.9.0] - 2025-12-20

### Added
- **Interactive Service Management** - New wizard for systemd administration
- **Systemd Template System** - Unit files moved to templates
- **ServiceHelper Class** - High-level API for systemctl/journalctl
- **Input Validation** - Time format and OnCalendar syntax validation

### Changed
- Rich-based UI with color-coded status indicators
- Extensive documentation for systemd templates (400+ lines)

---

## [3.8.0] - 2025-12-15

### Changed
- **Architecture Refactoring** - Eliminated ~1000 lines of duplicate code
- Consistent "Repository Type" terminology

### Fixed
- **Doctor Command** - Correct repository type detection
- **Tailscale** - Fixed KeyError bug in `get_kopia_args()`

---

## [3.4.0] - 2025-12-01

### Added
- **Doctor Command** - Comprehensive system health check
- **Simplified CLI** - "The Big 6" top-level commands
- **Admin Subcommands** - Organized advanced operations

### Changed
- Cleaner command organization for better UX

---

## [3.3.0] - 2025-11-15

### Added
- **Backup Scopes** - minimal, standard, full
- **Docker Network Backup** - Automatic backup of custom networks
- **Pre/Post Hooks** - Custom scripts before/after backups

---

[5.3.0]: https://github.com/TZERO78/kopi-docka/compare/v5.2.1...v5.3.0
[5.2.1]: https://github.com/TZERO78/kopi-docka/compare/v5.2.0...v5.2.1
[5.2.0]: https://github.com/TZERO78/kopi-docka/compare/v5.1.0...v5.2.0
[5.1.0]: https://github.com/TZERO78/kopi-docka/compare/v5.0.0...v5.1.0
[5.0.0]: https://github.com/TZERO78/kopi-docka/compare/v4.2.5...v5.0.0
[4.2.5]: https://github.com/TZERO78/kopi-docka/compare/v4.2.4...v4.2.5
[4.2.4]: https://github.com/TZERO78/kopi-docka/compare/v4.2.3...v4.2.4
[4.2.3]: https://github.com/TZERO78/kopi-docka/compare/v4.2.2...v4.2.3
[4.2.2]: https://github.com/TZERO78/kopi-docka/compare/v4.2.1...v4.2.2
[4.2.1]: https://github.com/TZERO78/kopi-docka/compare/v4.2.0...v4.2.1
[4.2.0]: https://github.com/TZERO78/kopi-docka/compare/v4.1.1...v4.2.0
[4.1.1]: https://github.com/TZERO78/kopi-docka/compare/v4.1.0...v4.1.1
[4.1.0]: https://github.com/TZERO78/kopi-docka/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/TZERO78/kopi-docka/compare/v3.9.1...v4.0.0
[3.9.1]: https://github.com/TZERO78/kopi-docka/compare/v3.9.0...v3.9.1
[3.9.0]: https://github.com/TZERO78/kopi-docka/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/TZERO78/kopi-docka/compare/v3.4.0...v3.8.0
[3.4.0]: https://github.com/TZERO78/kopi-docka/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/TZERO78/kopi-docka/releases/tag/v3.3.0
