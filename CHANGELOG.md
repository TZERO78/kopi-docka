# Changelog

All notable changes to Kopi-Docka will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
