# CLAUDE.md — Kopi-Docka Project Guide

## What is this project?

Kopi-Docka is a Python CLI tool that wraps **Kopia** for encrypted, deduplicated cold backups of Docker environments. It discovers Docker stacks/containers/volumes and backs them up via Kopia to various storage backends.

**Important**: This project will always be a Kopia wrapper. No second backup engine planned.

- **Version**: 7.6.1
- **Python**: 3.10, 3.11, 3.12
- **License**: MIT
- **Author**: Markus F. (TZERO78)
- **PyPI**: `pip install kopi-docka`

## Quick Commands

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=kopi_docka --cov-report=term-missing

# Coverage threshold (CI enforces 40%, target is higher)
pytest --cov-fail-under=40

# Lint
ruff check kopi_docka/

# Dead code detection
vulture kopi_docka/ --min-confidence 80

# Build
python -m build

# Run the CLI
kopi-docka --help
```

## Architecture Overview

```
CLI (typer) → Commands → Cores → KopiaRepository → subprocess → kopia
                                → Docker CLI
                                → OS tools (rsync, cp)
```

### Package Structure

| Package | Purpose | Lines |
|---|---|---|
| `commands/` | Typer CLI handlers, no business logic | ~6,600 |
| `cores/` | Business logic (backup, restore, DR, policies, snapshot mgmt) | ~9,000 |
| `helpers/` | Config, logging, UI, system utils | ~4,000 |
| `backends/` | Storage backend implementations (8 backends) | ~2,500 |
| `types.py` | Dataclasses (ContainerInfo, VolumeInfo, BackupUnit) | shared |

### Key Files

| File | What it does |
|---|---|
| `cores/repository_manager.py` | **KopiaRepository** — central Kopia CLI wrapper (834 lines) |
| `cores/backup_manager.py` | Backup orchestration |
| `cores/restore_manager.py` | Interactive restore wizard (2,279 lines, largest) |
| `cores/snapshot_manager.py` | **SnapshotManager** — interactive snapshot lifecycle (delete, pin, retention, maintenance) |
| `cores/disaster_recovery_manager.py` | DR bundle export (encrypted ZIP) |
| `helpers/config.py` | Config loading, validation, password handling (936 lines) |
| `__main__.py` | Typer app, command registration |

### KopiaRepository — Single Point of Contact

All Kopia CLI calls should go through `KopiaRepository` in `cores/repository_manager.py`. Key methods:

- `_run(args)` — internal subprocess wrapper, all kopia calls should use this
- `_get_env()` — builds env dict with KOPIA_PASSWORD etc.
- `connect()` / `disconnect()` / `is_connected()` / `status()`
- `create_snapshot()` / `list_snapshots()` / `restore_snapshot()`
- `delete_snapshot()` / `verify_snapshot()`
- `pin_snapshot()` / `unpin_snapshot()` / `expire_snapshots()`
- `maintenance_run()` / `set_repo_password()`

**Known bypass points** (direct subprocess→kopia calls outside `_run()`):
- `helpers/repo_helper.py`: 2× `kopia repository connect/disconnect` — intentional pre-init bypass (no `KopiaRepository` instance available yet)
- `repository_manager.py`: `create_snapshot_from_stdin()` — stdin piping requires direct `subprocess.run()` (Kopia has no stdin API via `_run()`)

### Command Structure (Typer)

Top-level commands ("The Big 6"): `setup`, `backup`, `restore`, `disaster-recovery`, `dry-run`, `doctor`, `version`

Admin/advanced subcommands: `config`, `repo`, `snapshot`, `service`, `system`, `notification`, `policy`

`advanced config` subcommands: `show`, `new`, `edit`, `reset`, `status`, `change-password`, `repair-kopia-params` (v7.5.0 — rebuilds SFTP `kopia_params` from `[credentials]` after the v7.0–v7.3.13 Tailscale wizard bug)

`advanced snapshot` subcommands: `list`, `estimate-size`, `manage`, `maintenance [--full]`, `prune-empty [--dry-run]`, `delete <id> [--force]`, `pin <id>`, `unpin <id>`, `retention show`, `retention set [options]`

`advanced policy` subcommands: `prune [--dry-run] [--force]`

Note: `advanced repo maintenance` was moved to `advanced snapshot maintenance` in v7.0.0.

## Conventions

### Code Style
- Python 3.10+ (no walrus operator abuse, keep it readable)
- Typer for CLI, Rich for output
- Pydantic v2 for config validation
- `ruff` for linting (F401 enforced)
- No type: ignore without comment

### Test Conventions
- Tests in `tests/unit/` and `tests/integration/`
- `__new__` pattern for manager instantiation (bypasses `__init__`, isolated tests)
- `monkeypatch` for env vars/attributes, `@patch` for external calls
- Coverage: CI enforces 40%, actual ~44%
- Integration tests guarded with `@pytest.mark` (Docker/Root required)

### Git & Releases
- Branch naming: `feature/XXXX-description`, `fix/description`, `release/vX.Y.Z`
- Conventional-ish commits: `feat:`, `fix:`, `chore:`, `docs:`
- CI: GitHub Actions (test matrix 3.10-3.12, publish to PyPI on tag)
- CHANGELOG.md maintained manually
- **Branch protection**: `main` is protected — all changes require a Pull Request (no direct push)

### Release Checklist (Version Bump)
When releasing a new version, follow this **exact** workflow:

**Step 1 — Version bump (on a release branch, NOT main):**
```bash
git checkout -b release/vX.Y.Z main
```
Update version in **all** of these files:
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `kopi_docka/helpers/constants.py` → `VERSION = "X.Y.Z"`
3. `kopi_docka/templates/config_template.json` → `"version": "X.Y.Z"` (since v7.3.6 the shipped config template tracks the release, so a freshly generated `kopi-docka.json` records which kopi-docka version wrote it)
4. `CLAUDE.md` → Version field in header
5. `CHANGELOG.md` → Set release date (replace "Unreleased")

**Step 2 — Commit & PR:**
```bash
git commit -m "release: vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "release: vX.Y.Z"
```
Wait for CI checks to pass, then merge the PR.

**Step 3 — Tag (triggers PyPI publish):**
```bash
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```
The tag triggers the GitHub Actions workflow that publishes to PyPI.

### Plan System
- Plans in `plan/active/`, archived to `plan/archive/vX.x/`
- Naming: `plan_XXXX_kebab-case-name.md`
- Standard frontmatter with status, target_release
- Plans are local-only, never pushed to GitHub (`plan/` is in `.gitignore`)

## Current State (Mai 2026)

### Active Plans
- **Plan 0028**: Global-Policy-Only + Interface-Vorbereitung für Multi-Path — committed on `refactor/global-policy-only` (target v7.3.0), end-to-end test in testlab pending

### Completed Plans
- **Plan 0020**: Bypass Cleanup — done, merged (v6.2.3)
- **Plan 0021**: Backup History Command — done, merged (v6.3.0)
- **Retention Policy Fix**: Path mismatch + doctor check — done (v6.4.0)
- **Plan 0023**: Security Hardening & Docs Overhaul — done, merged (v6.5.0)
- **Plan 0024**: Snapshot Management Wizard — done, merged (v7.0.0)
- **Plan 0025**: Alerting Overhaul (pre-flight check, verbose failures, missed-backup detection) — done, merged (v7.1.0)
- **Plan 0027**: Orphaned Policy Cleanup (`advanced policy prune`) — done, merged (v7.1.2)
- **Plan 0026**: Policy Overhaul — Staging cleanup, Smart-Skip, Auto-prune, Single Pre-flight, plus configurable rclone startup timeout with self-healing migration — done (v7.2.0)

### Known Technical Debt
- Test coverage at ~52 % (target: higher)
- `tests/README.md` is outdated (copy of v2.0 project README)
- Commands and backends have very low test coverage (~18 % and ~20 %)
- `engine/` directory exists but is empty (reserved, may not be needed)
- TAR-mode volume backup keeps its own per-volume path through `volume_handler.backup_volume_tar` instead of going through `create_snapshots()` — stdin streams don't fit the BackupSource shape. Low priority; TAR mode is legacy and not the default.

### Intentional Exceptions (not debt)
The two bypass points listed in the **KopiaRepository** section above (pre-init `kopia repository connect/disconnect` in `repo_helper.py`, and stdin-piping `create_snapshot_from_stdin()`) are documented architectural exceptions, not items for cleanup. Each has a structural reason (chicken-and-egg before `__init__`; no stdin-stream mode in `_run()`), each has an inline comment, both have been stable since v6.2.3. Only refactor if a new feature actively requires it.

## Documentation

All docs in `docs/`:
- ARCHITECTURE.md, FEATURES.md, CONFIGURATION.md
- USAGE.md, INSTALLATION.md, TROUBLESHOOTING.md
- DISASTER_RECOVERY.md, NOTIFICATIONS.md, HOOKS.md, DEVELOPMENT.md
