# Kopi-Docka Test Suite

Komplette Test-Suite für alle 23 Commands und Core-Module von Kopi-Docka.

## Struktur

```
tests/
├── conftest.py              # Shared fixtures (tmp_config, mock_root, etc.)
├── pytest.ini               # Pytest configuration
├── README.md               # This file
│
├── unit/                    # Fast tests with mocks (~100ms)
│   ├── test_main.py                 # ✅ 10 tests (version, root-check)
│   ├── test_config_commands.py      # TODO: 5 commands
│   ├── test_dependency_commands.py  # TODO: 3 commands
│   ├── test_repository_commands.py  # TODO: 7 commands
│   ├── test_backup_commands.py      # TODO: 3 commands
│   ├── test_service_commands.py     # TODO: 2 commands
│   ├── test_dry_run_commands.py     # TODO: 2 commands
│   ├── test_cores/                  # Core module tests
│   │   ├── test_backup_manager.py
│   │   ├── test_repository_manager.py
│   │   ├── test_service_manager.py
│   │   ├── test_disaster_recovery.py
│   │   └── test_docker_discovery.py
│   └── test_helpers/                # Helper module tests
│       ├── test_config.py
│       ├── test_system_utils.py
│       └── test_logging.py
│
└── integration/             # Slow tests with real interactions (>1s)
    ├── test_backup_flow.py          # End-to-end backup workflow
    ├── test_disaster_recovery_flow.py
    └── test_config_workflow.py
```

## Running Tests

### All Tests
```bash
make test
# or
python3 -m pytest tests/
```

### Unit Tests Only (Fast)
```bash
make test-unit
# or
python3 -m pytest tests/unit/ -v
```

### Integration Tests Only
```bash
make test-integration
# or
python3 -m pytest tests/integration/ -v
```

### With Coverage
```bash
make test-coverage
# Generates HTML report in htmlcov/
```

### Fast Development Workflow
```bash
make test-fast
# Runs unit tests, stops on first failure
```

### Specific Test File
```bash
make test-file FILE=tests/unit/test_main.py
```

### By Marker
```bash
# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration

# Skip tests requiring Docker
pytest -m "not requires_docker"

# Skip tests requiring root
pytest -m "not requires_root"
```

## Test Markers

Tests are categorized with markers:

- `@pytest.mark.unit` - Fast tests with mocks
- `@pytest.mark.integration` - Slow tests with real interactions
- `@pytest.mark.requires_docker` - Needs Docker daemon
- `@pytest.mark.requires_root` - Needs sudo/root
- `@pytest.mark.slow` - Takes >1 second

## Fixtures

Common fixtures available in `conftest.py`:

### Configuration
- `tmp_config(tmp_path)` - Temporary config file
- `cli_runner()` - Typer CLI runner

### Mocking
- `mock_root()` - Mock os.geteuid() = 0
- `mock_non_root()` - Mock os.geteuid() = 1000
- `mock_subprocess()` - Mock subprocess.run
- `mock_docker_client()` - Mock Docker API
- `mock_kopia_connected()` - Mock Kopia connection

### Test Data
- `mock_backup_unit()` - Sample BackupUnit
- `mock_docker_inspect()` - Sample Docker inspect
- `sample_snapshots()` - Sample Kopia snapshots

## Writing Tests

### Example: Testing a Command

```python
import pytest
from typer.testing import CliRunner
from kopi_docka.__main__ import app

@pytest.mark.unit
def test_my_command(cli_runner, mock_root, tmp_config):
    """Test my command with mocks."""
    result = cli_runner.invoke(
        app, 
        ["my-command", "--config", str(tmp_config)]
    )
    
    assert result.exit_code == 0
    assert "Success" in result.stdout
```

### Example: Testing a Core Module

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_backup_manager_init(tmp_config):
    """Test BackupManager initialization."""
    from kopi_docka.helpers.config import Config
    from kopi_docka.cores.backup_manager import BackupManager
    
    config = Config(tmp_config)
    manager = BackupManager(config)
    
    assert manager.config == config
```

## Coverage Goals

Target: 80% overall coverage

Current status:
- Main CLI: ✅ 100% (10/10 tests)
- Config Commands: ⏳ 0% (TODO)
- Dependency Commands: ⏳ 0% (TODO)
- Repository Commands: ⏳ 0% (TODO)
- Backup Commands: ⏳ 0% (TODO)
- Service Commands: ⏳ 0% (TODO)
- Dry-Run Commands: ⏳ 0% (TODO)

## CI/CD Integration

Tests run automatically on:
- Every push to main
- Every pull request
- Nightly builds

GitHub Actions workflow: `.github/workflows/test.yml`

## Development Workflow

1. Write test first (TDD)
2. Run fast tests: `make test-fast`
3. Implement feature
4. Run full tests: `make test`
5. Check coverage: `make test-coverage`
6. Commit when green ✅

## Dependencies

Installed via `setup.py[dev]`:
- pytest >= 7.0.0
- pytest-cov >= 3.0.0
- black >= 22.0.0
- flake8 >= 4.0.0

Install with:
```bash
pip install -e ".[dev]"
```

## Troubleshooting

### Tests fail with "No module named 'kopi_docka'"
```bash
# Install in development mode
pip install -e .
```

### Coverage report empty
```bash
# Ensure kopi_docka is installed
pip install -e .
```

### Permission errors in tests
```bash
# Tests should mock root access, not require it
# Check if mock_root fixture is used
```

## Contributing

When adding new commands or features:
1. Add unit tests in `tests/unit/`
2. Add integration tests if needed in `tests/integration/`
3. Update this README
4. Ensure `make test` passes
5. Aim for >80% coverage

## Status

✅ **Test Infrastructure:** Complete  
✅ **Fixtures & Mocks:** Complete  
✅ **Main CLI Tests:** 10/10 passing  
⏳ **Command Tests:** 0/23 (next phase)  
⏳ **Core Tests:** 0/9 (next phase)  
⏳ **Integration Tests:** 0/3 (next phase)

**Total Progress:** 10 tests implemented, ~100+ tests planned
