# CLAUDE.md — Kopi-Docka Project Guide

## What is this project?

Kopi-Docka is a Python CLI tool that wraps **Kopia** for encrypted, deduplicated cold backups of Docker environments. It discovers Docker stacks/containers/volumes and backs them up via Kopia to various storage backends.

**Important**: This project will always be a Kopia wrapper. No second backup engine planned.

- **Version**: 6.3.0
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
| `cores/` | Business logic (backup, restore, DR, policies) | ~8,500 |
| `helpers/` | Config, logging, UI, system utils | ~4,000 |
| `backends/` | Storage backend implementations (8 backends) | ~2,500 |
| `types.py` | Dataclasses (ContainerInfo, VolumeInfo, BackupUnit) | shared |

### Key Files

| File | What it does |
|---|---|
| `cores/repository_manager.py` | **KopiaRepository** — central Kopia CLI wrapper (834 lines) |
| `cores/backup_manager.py` | Backup orchestration |
| `cores/restore_manager.py` | Interactive restore wizard (2,279 lines, largest) |
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
- `maintenance_run()` / `set_repo_password()`

**Known bypass points** (direct subprocess→kopia calls outside `_run()`):
- `disaster_recovery_manager.py`: 3× `kopia repository status --json`
- `helpers/repo_helper.py`: 2× `kopia repository connect/disconnect`
- `repository_manager.py` internal: `set_repo_password()`, `verify_password()`, `create_filesystem_repo_at_path()` (4× bypasses)

### Command Structure (Typer)

Top-level commands ("The Big 6"): `setup`, `backup`, `restore`, `disaster-recovery`, `dry-run`, `doctor`, `version`

Admin/advanced subcommands: `config`, `repo`, `snapshot`, `service`, `system`, `notification`

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

### Release Checklist (Version Bump)
When releasing a new version, **all** of these must be updated:
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `kopi_docka/helpers/constants.py` → `VERSION = "X.Y.Z"`
3. `CLAUDE.md` → Version field in header
4. `CHANGELOG.md` → Set release date (replace "Unreleased")
5. Commit: `release: vX.Y.Z`
6. Tag: `git tag vX.Y.Z` + `git push origin vX.Y.Z` (triggers PyPI publish)

### Plan System
- Plans in `plan/active/`, archived to `plan/archive/vX.x/`
- Naming: `plan_XXXX_kebab-case-name.md`
- Standard frontmatter with status, target_release
- Plans are local-only, never committed to GitHub (use `/plan` skill)

## Current State (March 2026)

### Active Plans
- **Plan 0021**: Backup History Command (v6.3.0) — **done**, merged
- **Plan 0022**: Missed Backup Alerting (v6.4.0, depends on 0021) — draft

### Known Technical Debt
- Bypass points (see above) — Plan 0020 addresses this
- Test coverage at ~44% (target: higher)
- `tests/README.md` is outdated (copy of v2.0 project README)
- Commands and backends have very low test coverage (~18% and ~20%)
- `engine/` directory exists but is empty (reserved, may not be needed)

## Documentation

All docs in `docs/`:
- ARCHITECTURE.md, FEATURES.md, CONFIGURATION.md
- USAGE.md, INSTALLATION.md, TROUBLESHOOTING.md
- DISASTER_RECOVERY.md, NOTIFICATIONS.md, HOOKS.md, DEVELOPMENT.md
