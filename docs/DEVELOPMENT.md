[← Back to README](../README.md)

# Development

## Project Structure

```
kopi-docka/
├── kopi_docka/
│   ├── __init__.py              # Main exports
│   ├── __main__.py              # CLI entry point (Typer)
│   ├── types.py                 # Dataclasses (BackupUnit, etc.)
│   │
│   ├── backends/                # Storage backend implementations
│   │   ├── base.py              # BackendBase (abstract)
│   │   ├── local.py             # Local filesystem
│   │   ├── s3.py                # AWS S3 / Wasabi / MinIO
│   │   ├── b2.py                # Backblaze B2
│   │   ├── azure.py             # Azure Blob
│   │   ├── gcs.py               # Google Cloud Storage
│   │   ├── sftp.py              # SFTP/SSH
│   │   └── tailscale.py         # Tailscale P2P
│   │
│   ├── helpers/                 # Utilities
│   │   ├── config.py            # Config handling (JSON)
│   │   ├── constants.py         # Global constants
│   │   ├── logging.py           # Structured logging
│   │   └── system_utils.py      # System checks (RAM/CPU/disk)
│   │
│   ├── cores/                   # Business logic
│   │   ├── backup_manager.py    # Backup orchestration
│   │   ├── restore_manager.py   # Restore wizard
│   │   ├── docker_discovery.py  # Container detection
│   │   ├── repository_manager.py # Kopia wrapper
│   │   ├── dependency_manager.py # System deps check
│   │   ├── dry_run_manager.py   # Simulation mode
│   │   ├── disaster_recovery_manager.py # DR bundle creation
│   │   ├── kopia_policy_manager.py # Retention policies
│   │   └── service_manager.py   # Systemd integration
│   │
│   ├── commands/                # CLI command handlers
│   │   ├── backup_commands.py   # list, backup, restore
│   │   ├── config_commands.py   # Config management
│   │   ├── dependency_commands.py # Deps check/install
│   │   ├── repository_commands.py # Repo operations
│   │   ├── service_commands.py  # Systemd setup
│   │   ├── setup_commands.py    # Setup wizard
│   │   └── dry_run_commands.py  # Simulation commands
│   │
│   └── templates/               # Config templates
│       └── config_template.json # v3.0 JSON config
│
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── pytest.ini               # Test configuration
│   ├── unit/                    # Fast unit tests
│   └── integration/             # Slow integration tests
│
├── .github/
│   └── workflows/
│       └── publish.yml          # PyPI auto-publish on tags
│
├── pyproject.toml               # Package configuration (PEP 517/518)
├── requirements.txt             # Dependencies
├── Makefile                     # Dev tasks
├── README.md                    # This file
└── LICENSE                      # MIT License
```

---

## Development

### Setup Dev Environment

```bash
git clone https://github.com/TZERO78/kopi-docka.git
cd kopi-docka

# Install with dev dependencies
pip install -e ".[dev]"

# Format code
make format

# Check style
make check-style

# Run tests
make test

# Coverage
make test-coverage
```

### Code Style

- **Formatter:** Black (line-length: 100)
- **Linter:** flake8
- **Type Hints:** Recommended (not enforced yet)
- **Docstrings:** Google style

### Tests

```bash
# Fast unit tests
make test-unit

# All tests
make test

# With coverage
make test-coverage
# Opens htmlcov/index.html
```

---

## Status & Development

### Current Version: v5.5.1

Version 5.5.1 brings **enhanced backup scope tracking and Docker config backup**:
- ✅ **Backup Scope Tracking** - All snapshots include backup_scope tag (minimal/standard/full)
- ✅ **Docker Config Backup** - FULL scope backs up Docker daemon configuration
- ✅ **Restore Scope Detection** - Automatic warnings for minimal scope backups
- ✅ **Enhanced Setup Wizard** - Interactive scope selection with clear descriptions
- ✅ **Manual Docker Config Restore** - New `show-docker-config` command for safe daemon.json restoration
- ✅ **Hard/Soft Gate Dependencies** - Simplified dependency system (v5.5.0)
- ✅ **Think Simple Philosophy** - User-managed dependencies, no auto-install
- ✅ Modular structure (helpers, cores, commands)
- ✅ JSON config with hooks support
- ✅ Production-ready systemd integration
- ✅ Comprehensive journald logging

**The project lives from testing and feedback!** Current priorities:
1. **Testing** - Thoroughly test new v5.5.1 features (scope tracking, docker config backup)
2. **Bug-Fixing** - Fix known issues
3. **Stability** - Improve robustness
4. **Documentation** - User guides and best practices

### Planned Features

These features are **ideas for future releases**:

**Extended Exclude Patterns**
- More granular control over excluded files
- Per-unit excludes
- Status: ⏳ Planned

**Backup Verification**
- Automatic snapshot verification
- Restore tests
- Status: ⏳ Idea

**Multi-Repository Support**
- Parallel backups to multiple repos
- 3-2-1 strategy
- Status: ⏳ Idea

### How You Can Help

**Testing:**
```bash
# Test different scenarios
kopi-docka check
kopi-docka dry-run
kopi-docka backup
kopi-docka restore
```

**Report Bugs:**
- [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)
- Please attach complete error logs
- Describe your setup (OS, Docker version, etc.)

**Give Feedback:**
- What works well?
- What's unclear?
- Which features are you missing?
- [GitHub Discussions](https://github.com/TZERO78/kopi-docka/discussions)

**The project evolves through your feedback!**

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests if applicable
5. Format code: `make format`
6. Run tests: `make test`
7. Commit: `git commit -m "Add amazing feature"`
8. Push: `git push origin feature/amazing-feature`
9. Open pull request

**Report issues:** [GitHub Issues](https://github.com/TZERO78/kopi-docka/issues)

---

[← Back to README](../README.md)
