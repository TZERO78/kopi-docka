# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kopi-Docka is a Python CLI tool for cold backups of Docker environments using Kopia as the storage backend. It orchestrates stopping containers, backing up volumes/recipes/networks, and restarting containers atomically.

**Key Facts:**
- Python 3.10+ with Typer (CLI), Rich (UI)
- Linux only, requires root for most operations
- Version: 5.2.0 (Beta, Feature-Complete, Stabilization Phase)

## Common Commands

```bash
# Development setup
pip install -e ".[dev]"

# Code formatting and linting
make format          # Black (line-length: 100)
make check-style     # Flake8

# Testing
make test            # All tests
make test-unit       # Fast unit tests only
make test-coverage   # With HTML coverage report
pytest tests/unit/test_file.py -v  # Single test file
pytest -k "test_name" -v           # Single test by name

# Run the CLI
sudo kopi-docka --help
sudo kopi-docka backup
sudo kopi-docka dry-run  # Preview without changes
```

## Architecture

### Entry Point & CLI Structure

`kopi_docka/__main__.py` → Typer CLI with commands delegating to managers:
- **commands/**: CLI command handlers (backup, restore, setup, doctor, etc.)
- **commands/advanced/**: Admin subcommands (config, repo, snapshot, service, system)

### Core Managers (kopi_docka/cores/)

| Manager | Responsibility |
|---------|---------------|
| `backup_manager.py` | Orchestrates cold backup: stop → backup → start → hooks |
| `restore_manager.py` | Interactive restore wizard (28 methods) |
| `docker_discovery.py` | Container/volume discovery, groups into BackupUnits |
| `repository_manager.py` | Kopia CLI wrapper (25 methods) |
| `hooks_manager.py` | Pre/post backup/restore hook execution |
| `dependency_manager.py` | System dependency checks & installation |

### Storage Backends (kopi_docka/backends/)

All inherit from `BackendBase` abstract class:
- `local.py`, `s3.py`, `b2.py`, `azure.py`, `gcs.py`, `sftp.py`, `tailscale.py`, `rclone.py`

Adding a new backend: create `backends/newbackend.py`, inherit `BackendBase`, implement abstract methods.

### Data Models (kopi_docka/types.py)

- `BackupUnit`: Logical backup unit (stack or standalone container)
- `ContainerInfo`: Container metadata
- `VolumeInfo`: Volume metadata
- `BackupMetadata`: Backup run info (backup_id, snapshots, errors)
- `RestorePoint`: Restore session info

### Snapshot Tagging Strategy

Kopia snapshots are tagged for session reconstruction:
```json
{
  "type": "recipe|volume|networks",
  "unit": "unit_name",
  "backup_id": "unique_uuid",
  "timestamp": "iso_timestamp",
  "volume": "volume_name"  // volumes only
}
```

All snapshots from one backup run share the same `backup_id`.

### Helpers (kopi_docka/helpers/)

- `config.py`: Config loading, password handling (`get_password()`, `set_password()`)
- `constants.py`: VERSION, BACKUP_SCOPE_*, BACKUP_FORMAT_*, DATABASE_IMAGES
- `logging.py`: Structured logging with systemd journal support
- `ui_utils.py`: `run_command()` subprocess wrapper, Rich console helpers
- `system_utils.py`: CPU/RAM detection, worker auto-tuning

## Code Style

- **Formatter**: Black (line-length: 100)
- **Linter**: Flake8 (max-line-length: 88, extend-ignore: E203)
- **Docstrings**: Google style

## Testing

- Framework: pytest
- `tests/unit/`: Fast tests with mocks (marked `@pytest.mark.unit`)
- `tests/integration/`: Slow tests with real Docker/Kopia
- `tests/conftest.py`: Shared fixtures

Markers: `unit`, `integration`, `requires_docker`, `requires_root`, `slow`

## Configuration

Config file locations (priority order):
1. `--config` CLI flag
2. `KOPI_DOCKA_CONFIG` env var
3. `/etc/kopi-docka.json`
4. `~/.config/kopi-docka/config.json`

Passwords: Use `password_file` (chmod 600) over plaintext `password`.

## Key Workflows

**Cold Backup Flow:**
1. Discovery → groups containers into BackupUnits
2. Pre-hooks execution
3. Stop containers
4. Backup recipes (compose files + docker inspect)
5. Backup volumes (direct Kopia snapshot)
6. Backup networks
7. Start containers
8. Post-hooks execution
9. Save metadata JSON

**Restore Flow:**
1. Query Kopia snapshots by tags
2. Present interactive session selection
3. Restore recipes, networks, volumes
4. Execute post-restore hooks

## Important Constraints

- Root required for most operations (checked in `initialize_context()`)
- Docker labels (`com.docker.compose.project`) determine stack membership
- Secrets in env vars are redacted (PASS, SECRET, KEY, TOKEN, API, AUTH patterns)
- Parallel workers auto-tuned based on available RAM

## Documentation

Detailed docs in `docs/`:
- `ARCHITECTURE.md` - Comprehensive architecture reference
- `DEVELOPMENT.md` - Development guide
- `CONFIGURATION.md` - Config wizard & backends
- `USAGE.md` - CLI reference
- `HOOKS.md` - Pre/post hooks
