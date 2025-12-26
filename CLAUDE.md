# CLAUDE.md

Quick reference for Claude Code when working with Kopi-Docka.

## 🎯 Quick Facts

- **What:** Python CLI for Docker cold backups via Kopia
- **Version:** 5.2.0 (Beta, Stabilization Phase)
- **Platform:** Linux only, Python 3.10+
- **Key Rule:** Always work on `dev` branch, always use venv

## 🚀 Start Here

```bash
# 1. Activate venv (create if missing)
source venv/bin/activate
# No venv? → python -m venv venv && source venv/bin/activate

# 2. Checkout dev branch
git checkout dev && git pull origin dev

# 3. Install dev dependencies
pip install -e ".[dev]"

# 4. Ready to code!
```

## 📚 Where to Find What

**Need to understand architecture?**  
→ Read `docs/ARCHITECTURE.md` (authoritative source)

**Need to know development workflow?**  
→ Read `docs/DEVELOPMENT.md` (setup, testing, contributing)

**Need to understand features?**  
→ Read `docs/FEATURES.md`, `docs/USAGE.md`, `docs/CONFIGURATION.md`

**Need hook system details?**  
→ Read `docs/HOOKS.md`

## ✅ Do's

- ✅ Always activate venv first: `source venv/bin/activate`
- ✅ Always work on `dev` branch (PRs to `dev`, NOT `main`)
- ✅ Run `make format` before committing (Black, line-length: 100)
- ✅ Run `make test` before pushing
- ✅ Use `ui_utils.run_command()` for subprocess calls (centralized error handling)
- ✅ Add tests for new features (see `tests/conftest.py` for fixtures)
- ✅ Use Google-style docstrings
- ✅ Check `docs/ARCHITECTURE.md` before modifying core managers

## ❌ Don'ts

- ❌ Never work directly on `main` branch
- ❌ Never commit without `make format`
- ❌ Never use direct `subprocess.run()` (use `ui_utils.run_command()`)
- ❌ Never hardcode paths (use config system)
- ❌ Never skip tests for core functionality changes
- ❌ Never merge PRs to `main` (only to `dev`)
- ❌ Don't use browser storage APIs (localStorage/sessionStorage)

## 🔧 Common Tasks

### Run Tests
```bash
source venv/bin/activate
make test              # All tests
make test-unit         # Fast unit tests only
make test-coverage     # With HTML report
pytest -k "test_name"  # Single test
```

### Code Formatting
```bash
source venv/bin/activate
make format            # Auto-format with Black
make check-style       # Check with flake8
```

### Test CLI Commands
```bash
source venv/bin/activate

# Info commands (no sudo)
python -m kopi_docka --help
python -m kopi_docka version

# Real operations (needs sudo)
sudo venv/bin/python -m kopi_docka backup
sudo venv/bin/python -m kopi_docka dry-run
```

**Note:** Claude Code can't run sudo commands directly - it will suggest them for you to execute manually.

### Add New Backend
1. Create `kopi_docka/backends/newbackend.py`
2. Inherit from `BackendBase` (see `backends/base.py`)
3. Implement abstract methods: `get_kopia_args()`, `validate_config()`, etc.
4. See existing backends (`s3.py`, `b2.py`) for patterns
5. Add tests in `tests/unit/backends/`

### Modify Backup Flow
→ See `kopi_docka/cores/backup_manager.py`  
→ Flow: Discovery → Pre-Hooks → Stop → Backup → Start → Post-Hooks → Metadata

### Change CLI Structure
→ Entry: `kopi_docka/__main__.py`  
→ Commands: `kopi_docka/commands/`  
→ Uses Typer framework

## 🏗️ Project Structure (Brief)

```
kopi_docka/
├── __main__.py              # CLI entry point (Typer)
├── types.py                 # Data models (BackupUnit, etc.)
├── backends/                # 8 storage backends
│   └── base.py              # Abstract BackendBase
├── cores/                   # Business logic managers
│   ├── backup_manager.py    # Orchestrates backups
│   ├── restore_manager.py   # Restore wizard
│   ├── repository_manager.py # Kopia wrapper (25 methods)
│   └── docker_discovery.py  # Container/volume discovery
├── commands/                # CLI command handlers
└── helpers/                 # Utilities (config, logging, ui_utils)

tests/
├── unit/                    # Fast tests with mocks
└── integration/             # Slow tests with real Docker/Kopia
```

**Full details:** → `docs/ARCHITECTURE.md`

## ⚠️ Common Pitfalls

1. **Forgetting venv activation** → Always `source venv/bin/activate` first
2. **Working on main branch** → Always use `dev` branch
3. **Using direct subprocess calls** → Use `ui_utils.run_command()` instead
4. **Not checking ARCHITECTURE.md** → Core managers are documented there
5. **Assuming sudo works in Claude Code** → It doesn't, only suggests commands
6. **Breaking snapshot tagging** → Critical for restore, check `repository_manager.py`

## 🎨 Code Style

- **Formatter:** Black (line-length: 100)
- **Linter:** Flake8 (max-line-length: 88, extend-ignore: E203)
- **Docstrings:** Google style
- **Type hints:** Recommended (gradual adoption)

## 🌳 Git Workflow

```bash
# 1. Start from dev
source venv/bin/activate
git checkout dev && git pull origin dev

# 2. Create feature branch
git checkout -b feature/my-feature

# 3. Make changes, test, format
# ... code changes ...
make format
make test

# 4. Commit and push
git add .
git commit -m "feat: description"
git push origin feature/my-feature

# 5. Create PR to dev (NOT main!)
```

## 🔍 Decision Tree

**Need to understand a component?**  
→ Check `docs/ARCHITECTURE.md` first

**Need to modify backup flow?**  
→ See `cores/backup_manager.py` + check tests

**Need to add CLI command?**  
→ Add to `commands/` + register in `__main__.py`

**Need to add backend?**  
→ Inherit `BackendBase` + implement abstract methods

**Need to fix bug?**  
→ Write failing test first + fix + verify test passes

**Need to add feature?**  
→ Check `docs/DEVELOPMENT.md` roadmap first (no scope creep in stabilization phase)

## 📝 Key Implementation Details

**Snapshot Tagging (Critical!):**
```json
{
  "type": "recipe|volume|networks",
  "unit": "stack_name",
  "backup_id": "uuid",
  "timestamp": "iso"
}
```
All snapshots from one backup share same `backup_id` for session reconstruction.

**Config Priority:**
1. `--config` CLI flag
2. `KOPI_DOCKA_CONFIG` env var
3. `/etc/kopi-docka.json`
4. `~/.config/kopi-docka/config.json`

**Root Requirements:**
- Tests, formatting, Git → No sudo (run in venv)
- Backup/restore operations → `sudo venv/bin/python -m kopi_docka`

## 🆘 When Stuck

1. Check `docs/ARCHITECTURE.md` for component details
2. Check existing similar code for patterns
3. Check `tests/` for how it's tested
4. Check `docs/DEVELOPMENT.md` for guidelines
5. Search codebase for similar functionality

---

**Remember:**  
📖 This is a **quick reference** - detailed docs are in `docs/`  
🔄 Always work on `dev` branch  
🧪 Always test before pushing  
✨ Always format before committing