# Changelog

All notable changes to Kopi-Docka will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

- **New Command: `kopi-docka admin repo prune-empty-sessions`** 🧹
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
- 💡 **Optional**: Run `kopi-docka admin repo prune-empty-sessions` to clean up old ghost sessions

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
