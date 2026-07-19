# CLAUDE.md — Kopi-Docka Project Guide

## What is this project?

Kopi-Docka is a Python CLI tool that wraps **Kopia** for encrypted, deduplicated cold backups of Docker environments. It discovers Docker stacks/containers/volumes and backs them up via Kopia to various storage backends.

**Important**: This project will always be a Kopia wrapper. No second backup engine planned.

- **Version**: 7.9.0
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

## Project Commands (`.claude/commands/`)

Projektspezifische Slash-Commands, die wiederkehrende Workflows automatisieren und Architekturregeln erzwingen. Liegen in `.claude/commands/`, jede `*.md`-Datei ist ein Command.

| Command | Wofür |
|---|---|
| `/release-bump X.Y.Z` | Bumpt die Version an **allen 5 Stellen** der Releasecheckliste in einem Schritt (`pyproject.toml`, `helpers/constants.py`, `templates/config_template.json`, `CLAUDE.md`-Header, `CHANGELOG.md`-Datum). Erstellt Release-Branch, kein Tag (Tag passt erst nach Merge). |
| `/changelog-entry [text]` | Erzeugt einen `CHANGELOG.md`-Eintrag im Hausstil (`### Emoji Titel` → **Why / Changes / Upgrade notes**) aus aktuellem Diff oder Freitext. Schreibt in `## [Unreleased]`. |
| `/plan-new <slug>` | Legt `plan/active/plan_NNNN_<slug>.md` mit Standard-Frontmatter an. Vergibt nächste freie Nummer (sucht in `plan/active/` **und** `plan/archive/**`, recycelt keine Lücken). |
| `/claudemd-sync [--fix]` | Erkennt Drift zwischen `CLAUDE.md` und Realität: Versionsnummer, "Active Plans" vs. `plan/active/`, "Completed Plans" vs. Archiv, Zeilenzahlen in "Key Files", stale Technical-Debt-Punkte. Mit `--fix` Patches nach Bestätigung. |
| `/kopia-bypass-check [--diff]` | Findet direkte `subprocess`→`kopia`-Aufrufe außerhalb von `KopiaRepository._run()`. Whitelistet die zwei dokumentierten Bypässe in `repo_helper.py` und `create_snapshot_from_stdin()`. Architekturregel aus Plan 0020 maschinell statt nur in Doku. |
| `/docs <query>` | Dokulookup für Kopia, Docker, rclone, Backends. |

Allgemeine Skills aus dem Harness (`/code-review`, `/simplify`, `/verify`, `/loop`, `/schedule`, ...) sind weiterhin verfügbar.

## Architecture Overview

```
CLI (typer) → Commands → Cores → KopiaRepository → subprocess → kopia
                                → Docker CLI
                                → OS tools (rsync, cp)
```

### Package Structure

| Package | Purpose | Lines |
|---|---|---|
| `commands/` | Typer CLI handlers, no business logic | ~6,700 |
| `cores/` | Business logic (backup, restore, DR, policies, snapshot mgmt) | ~7,300 |
| `helpers/` | Config, logging, UI, system utils | ~3,800 |
| `backends/` | Storage backend implementations (8 backends) | ~2,800 |
| `types.py` | Dataclasses (ContainerInfo, VolumeInfo, BackupUnit) | shared |

### Key Files

| File | What it does |
|---|---|
| `cores/repository_manager.py` | **KopiaRepository** — central Kopia CLI wrapper (1,182 lines) |
| `cores/backup_manager.py` | Backup orchestration |
| `cores/restore_manager.py` | Interactive restore wizard (2,294 lines, largest) |
| `cores/snapshot_manager.py` | **SnapshotManager** — interactive snapshot lifecycle (delete, pin, retention, maintenance) |
| `cores/disaster_recovery_manager.py` | DR bundle export (encrypted ZIP) |
| `helpers/config.py` | Config loading, validation, password handling (1,034 lines) |
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
- Coverage: CI enforces 40%, actual ~52%
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

## Current State (Mai 2026, Stand v7.6.4)

> Diese Sektion driftet erfahrungsgemäß. Mit `/claudemd-sync` gegen Realität abgleichen.

### Active Plans (`plan/active/`)
- **Plan 0031**: Adaptive Health Timeout
- **Plan 0032**: Code Hygiene Modernization
- **Plan 0033**: Restore-Manager Decomposition — 2.294 Zeilen, 211 `console.print()`, 23 `input()`; Refactor-First-Argument vor jeder UI-Anbindung
- **Plan 0034**: Repository-Manager Decomposition — 1.182 Zeilen, 36 Methoden, 6 Themen in einer Klasse
- **Plan 0036**: ui-utils KVP
- **Plan 0038**: SFTP Canonical Params

### Recently Completed (archiviert in `plan/archive/v7.x/`)
- **Plan 0024** Snapshot Management Wizard (v7.0.0)
- **Plan 0025** Alerting Overhaul (v7.1.0)
- **Plan 0027** Orphaned Policy Cleanup (v7.1.2)
- **Plan 0026** Policy Overhaul / Smart-Skip / Auto-prune (v7.2.0)
- **Plan 0028** Global-Policy-Only + Multi-Path-Vorbereitung
- **Plan 0029** Tailscale-SFTP Correctness
- **Plan 0030** DR-Bundle SSH-Key Hygiene
- **Plan 0037** Sudo-Helper Extraction
- **Plan 0039** Docs Pass (v7.6.2)

Plan 0023 (Security Hardening) liegt in `plan/archive/v6.x/`; ältere Pläne (0020–0022) sind nur über `CHANGELOG.md` referenzierbar.

### Known Technical Debt
- Test coverage at ~52 % (target: higher)
- `tests/README.md` is at v6.4.0 stand and should be refreshed to v7.x
- Commands and backends have very low test coverage (~18 % and ~20 %)
- TAR-mode volume backup keeps its own per-volume path through `volume_handler.backup_volume_tar` instead of going through `create_snapshots()` — stdin streams don't fit the BackupSource shape. Low priority; TAR mode is legacy and not the default.
- **Restore-Manager-Größe** (2.294 Zeilen, niedrigste Coverage im Projekt) — siehe Plan 0033.
- **Repository-Manager-Größe** (1.182 Zeilen, 36 Methoden) — siehe Plan 0034.

### Intentional Exceptions (not debt)
The two bypass points listed in the **KopiaRepository** section above (pre-init `kopia repository connect/disconnect` in `repo_helper.py`, and stdin-piping `create_snapshot_from_stdin()`) are documented architectural exceptions, not items for cleanup. Each has a structural reason (chicken-and-egg before `__init__`; no stdin-stream mode in `_run()`), each has an inline comment, both have been stable since v6.2.3. Only refactor if a new feature actively requires it.

## Documentation

All docs in `docs/`:
- ARCHITECTURE.md, FEATURES.md, CONFIGURATION.md
- USAGE.md, INSTALLATION.md, TROUBLESHOOTING.md
- DISASTER_RECOVERY.md, NOTIFICATIONS.md, HOOKS.md, DEVELOPMENT.md
