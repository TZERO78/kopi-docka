# Tests — Kopi-Docka

Test suite for kopi-docka v6.4.0+. Tests live in `tests/unit/` and `tests/integration/`.

## Running tests

```bash
# All tests
python -m pytest

# With coverage report
python -m pytest --cov=kopi_docka --cov-report=term-missing

# Enforce coverage threshold (CI uses 40%)
python -m pytest --cov-fail-under=40

# A single file
python -m pytest tests/unit/test_config_helpers.py -v
```

## Structure

```
tests/
├── unit/                         # Fast, isolated unit tests (no Docker, no root)
│   ├── backends/                 # Storage backend tests (rclone, s3, tailscale, …)
│   ├── test_commands/            # CLI command handler tests
│   ├── test_cores/               # Business logic tests (backup, restore, DR, …)
│   ├── test_helpers/             # Config, logging, UI utils tests
│   ├── test_backup_commands.py   # Backup command coverage
│   ├── test_config_helpers.py    # Config loading/validation
│   ├── test_process_lock.py      # ProcessLock (fcntl-based)
│   ├── test_repository_commands.py
│   └── test_main.py              # Entry point / CLI registration
└── integration/                  # Slower tests that require Docker or root
    ├── test_backup_restore_cycle.py
    ├── test_hooks_integration.py
    ├── test_retention_direct_mode.py
    ├── test_safe_exit_abort_scenarios.py
    ├── test_service_templates.py
    └── test_stable_staging.py
```

## Conventions

### Instantiation pattern

Manager classes use `__new__` to bypass `__init__` in unit tests, giving you a bare instance you can configure with `monkeypatch`:

```python
mgr = BackupManager.__new__(BackupManager)
mgr.config = mock_config
mgr.repo = mock_repo
```

This avoids setting up a full `Config` + `KopiaRepository` just to test a single method.

### Mocking

- `monkeypatch` — env vars, object attributes, module-level constants
- `@patch` / `MagicMock` — external calls (subprocess, docker, kopia)
- Never mock the database (there isn't one); integration tests hit real Docker where needed

### Integration test guards

Tests that need Docker or root are guarded with `pytest.mark`:

```python
@pytest.mark.skipif(os.getuid() != 0, reason="Requires root for backup operations")
@pytest.mark.skipif(not shutil.which("docker"), reason="Requires Docker")
```

Run the full suite (including skipped) to see which guards apply:

```bash
python -m pytest -v 2>&1 | grep SKIP
```

### Coverage

- CI enforces **40%** minimum (`--cov-fail-under=40`)
- Actual coverage is ~44% (March 2026)
- `commands/` and `backends/` have the lowest coverage (~18–20%)
- New security-related tests added in v6.5.0 for hook validation and SUDO_USER input

## Linting

```bash
ruff check kopi_docka/
vulture kopi_docka/ --min-confidence 80
```
