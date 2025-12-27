# Changelog

All notable changes to Kopi-Docka will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
