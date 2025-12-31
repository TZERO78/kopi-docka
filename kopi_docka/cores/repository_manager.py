#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        repository_manager.py
# @module:      kopi_docka.cores.repository_manager
# @description: Kopia CLI wrapper with profile-specific config handling.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Changelog v2.0.0:
# - Simplified password handling (plaintext in config or password_file)
# - Added set_repo_password() and verify_password() methods
# - Removed systemd-creds complexity
################################################################################

"""
Kopia repository management with profile support.

- Uses a dedicated Kopia config file per profile (e.g. ~/.config/kopia/repository-kopi-docka.config)
- Ensures all Kopia calls include --config-file and proper environment
- Provides connect/create logic, status checks, snapshot (dir/stdin), list, restore, verify, maintenance
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, IO, List, Optional, Union

from ..helpers.config import Config
from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError

logger = get_logger(__name__)


class KopiaRepository:
    """
    Wraps Kopia CLI interactions for a given profile.

    A 'profile' here is just a dedicated Kopia config file name:
    ~/.config/kopia/repository-<profile>.config
    """

    # --------------- Construction ---------------

    def __init__(self, config: Config):
        self.config = config
        self.kopia_params = config.get("kopia", "kopia_params", fallback="")
        if not self.kopia_params:
            raise ValueError(
                "Config missing 'kopia_params'. "
                "Please create a new config with 'kopi-docka new-config'."
            )
        self.profile_name = config.kopia_profile

    # --------------- Low-level helpers ---------------

    def _get_config_file(self) -> str:
        """Return profile-specific Kopia config file path."""
        cfg_dir = Path.home() / ".config" / "kopia"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return str(cfg_dir / f"repository-{self.profile_name}.config")

    def _get_env(self) -> Dict[str, str]:
        """Build environment for Kopia CLI (password, cache dir)."""
        env = os.environ.copy()

        # Hole Passwort über Config.get_password() - ohne Fallback!
        # Wenn Passwort fehlt, wirft get_password() ValueError
        password = self.config.get_password()
        if password:
            env["KOPIA_PASSWORD"] = password

        cache_dir = self.config.kopia_cache_directory
        if cache_dir:
            env["KOPIA_CACHE_DIRECTORY"] = str(cache_dir)

        # Optional: also expose path via env (we *also* pass --config-file explicitly)
        env.setdefault("KOPIA_CONFIG_PATH", self._get_config_file())
        return env

    def _get_cache_params(self) -> List[str]:
        """
        Get Kopia cache size parameters to prevent unbounded cache growth.

        Returns CLI args like: ['--content-cache-size-mb', '500', '--metadata-cache-size-mb', '100']
        """
        cache_size = self.config.kopia_cache_size_mb
        if cache_size <= 0:
            return []  # User explicitly disabled cache limiting

        # Content cache is for actual data, metadata cache is for indexes
        # Metadata cache should be ~20% of content cache
        metadata_size = max(50, cache_size // 5)

        return [
            "--content-cache-size-mb",
            str(cache_size),
            "--metadata-cache-size-mb",
            str(metadata_size),
        ]

    def _run(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """
        Run Kopia command with our env and config.
        Uses run_command() for automatic subprocess tracking.
        Raises RuntimeError if check=True and rc!=0 (backward compatibility).
        """
        if "--config-file" not in args:
            args = [*args, "--config-file", self._get_config_file()]

        try:
            return run_command(
                args,
                description=f"Kopia: {' '.join(args[:3])}",
                check=check,
                show_output=False,
                env=self._get_env(),
            )
        except SubprocessError as e:
            # Backward compatibility: convert SubprocessError → RuntimeError
            raise RuntimeError(f"{' '.join(args)} failed: {e.stderr.strip() or e.stdout.strip()}")

    # --------------- Status / Connect / Create ---------------

    def status(self, json_output: bool = True, verbose: bool = False) -> Union[str, Dict[str, Any]]:
        """
        Call 'kopia repository status' for our profile.
        - json_output=True: parse JSON (if possible)
        - verbose=True: try '--json-verbose', fallback to '--json'
        Returns dict when json_output=True and JSON parses; otherwise plaintext.
        """
        base = ["kopia", "repository", "status"]
        if json_output:
            # prefer --json-verbose (newer Kopia), fallback to --json
            args = base + (["--json-verbose"] if verbose else ["--json"])
            proc = self._run(args, check=False)
            if proc.returncode != 0 and verbose:
                proc = self._run(base + ["--json"], check=False)
        else:
            proc = self._run(base, check=False)

        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"'kopia repository status' failed: {err}")

        out = proc.stdout.strip()
        if json_output:
            try:
                return json.loads(out) if out else {}
            except json.JSONDecodeError:
                return out
        return out

    def is_connected(self) -> bool:
        """True when 'kopia repository status' succeeds for our profile."""
        if not shutil.which("kopia"):
            return False
        proc = self._run(["kopia", "repository", "status", "--json"], check=False)
        return proc.returncode == 0

    def is_initialized(self) -> bool:
        """Alias to connection check: initialized & connected for this profile."""
        try:
            _ = self.status(json_output=True)
            return True
        except Exception:
            return False

    def connect(self) -> None:
        """
        Connect to existing repository (idempotent).
        If repository doesn't exist, raises error - use initialize() instead.
        """
        # Already connected?
        if self.is_connected():
            logger.debug("Already connected to repository")
            return

        import shlex

        params = shlex.split(self.kopia_params)
        # Include cache size limits to prevent unbounded cache growth
        cmd = ["kopia", "repository", "connect"] + params + self._get_cache_params()

        # Try connect
        proc = self._run(cmd, check=False)

        if proc.returncode == 0:
            logger.info("Connected to repository")
            return

        # Failed - check why
        err_msg = (proc.stderr or proc.stdout or "").lower()
        if "not found" in err_msg or "does not exist" in err_msg or "not initialized" in err_msg:
            raise RuntimeError(
                f"Repository not found ({self.kopia_params}). "
                f"Run 'kopi-docka init' to create it first."
            )

        # Other error (wrong password, permissions, etc.)
        raise RuntimeError(f"Failed to connect: {proc.stderr or proc.stdout}")

    def disconnect(self) -> None:
        """Disconnect from repository (kopia repository disconnect)."""
        try:
            self._run(["kopia", "repository", "disconnect"], check=False)
            logger.info("Disconnected from repository")
        except Exception as e:
            logger.debug(f"Disconnect failed (may not be connected): {e}")

    def initialize(self) -> None:
        """
        Create new repository and connect to it (idempotent).
        If repository already exists, just connects to it.
        Verifies connection with 'repository status' and applies default policies.
        """
        # Check if already connected to this repo
        if self.is_connected():
            logger.info("Already connected to repository")
            return

        import shlex

        params = shlex.split(self.kopia_params)

        # Für filesystem: Directory erstellen
        if len(params) >= 2 and params[0] == "filesystem" and params[1] == "--path":
            if len(params) >= 3:
                Path(params[2]).expanduser().mkdir(parents=True, exist_ok=True)

        cmd_create = (
            ["kopia", "repository", "create"]
            + params
            + ["--description", f"Kopi-Docka Backup Repository ({self.profile_name})"]
        )
        # Include cache size limits to prevent unbounded cache growth
        cmd_connect = ["kopia", "repository", "connect"] + params + self._get_cache_params()

        # Try to create (may fail if exists)
        proc = self._run(cmd_create, check=False)

        # If create failed, check if it's because repo exists
        if proc.returncode != 0:
            err_msg = (proc.stderr or proc.stdout or "").lower()
            if "already exists" in err_msg or "existing data" in err_msg:
                logger.info("Repository already exists, connecting...")
            else:
                # Real error, re-raise
                raise RuntimeError(f"Failed to create repository: {proc.stderr or proc.stdout}")

        # Connect (idempotent)
        try:
            self._run(cmd_connect, check=True)
        except Exception as e:
            logger.error(f"Failed to connect after create: {e}")
            raise

        # Verify connection
        try:
            _ = self.status(json_output=True, verbose=True)
        except Exception as e:
            raise RuntimeError(f"Repository not accessible after init: {e}")

        # Apply default policies (best-effort)
        try:
            from .kopia_policy_manager import KopiaPolicyManager

            KopiaPolicyManager(self).apply_global_defaults()
        except Exception as e:
            logger.debug("Skipping policy defaults (optional): %s", e)

        logger.info("Repository initialized successfully")

    def make_default_profile(self) -> None:
        """
        Make this profile the default Kopia config (~/.config/kopia/repository.config).
        Helpful when you want 'kopia ...' without --config-file to use this profile.
        """
        from shutil import copy2

        src = Path(self._get_config_file())
        dst = Path.home() / ".config" / "kopia" / "repository.config"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            dst.symlink_to(src)
            logger.info("Default kopia config now symlinked to %s", src)
        except Exception:
            copy2(src, dst)
            logger.info("Default kopia config copied to %s", dst)

    # --------------- Password Management ---------------

    def set_repo_password(self, new_password: str) -> None:
        """
        Change the Kopia repository password.

        This updates the password in the Kopia repository itself.
        You must also update the password in your config file separately
        using Config.set_password().

        Args:
            new_password: The new password to set

        Raises:
            RuntimeError: If password change fails

        Example:
            >>> repo = KopiaRepository(config)
            >>> repo.set_repo_password("new-secure-password")
            >>> config.set_password("new-secure-password", use_file=True)
        """
        if not self.is_connected():
            raise RuntimeError(
                "Not connected to repository. " "Cannot change password without active connection."
            )

        logger.info("Changing repository password...")

        # Build environment with NEW password
        env = self._get_env().copy()
        env["KOPIA_NEW_PASSWORD"] = new_password

        # Call kopia repository change-password
        cmd = ["kopia", "repository", "change-password", "--config-file", self._get_config_file()]

        proc = subprocess.run(cmd, env=env, text=True, capture_output=True)

        if proc.returncode != 0:
            err_msg = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Failed to change repository password: {err_msg}")

        logger.info("Repository password changed successfully")

    def verify_password(self, password: str) -> bool:
        """
        Verify if a password works with the repository.

        Args:
            password: Password to test

        Returns:
            True if password is correct, False otherwise
        """
        # Temporarily override password in env
        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = password

        cache_dir = self.config.kopia_cache_directory
        if cache_dir:
            env["KOPIA_CACHE_DIRECTORY"] = str(cache_dir)

        # Try a simple status check
        proc = subprocess.run(
            ["kopia", "repository", "status", "--json", "--config-file", self._get_config_file()],
            env=env,
            text=True,
            capture_output=True,
        )

        return proc.returncode == 0

    # --------------- Snapshots ---------------

    def create_snapshot(
        self,
        path: str,
        tags: Optional[Dict[str, str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> str:
        """
        Create a directory/file snapshot at 'path' with optional tags.

        Args:
            path: Directory or file path to snapshot
            tags: Optional dict of tags to add to the snapshot
            exclude_patterns: Optional list of glob patterns to exclude (e.g., ["*.log", "cache/*"])

        Returns:
            Snapshot ID
        """
        # Validate path is not empty
        if not path or path.strip() == "":
            raise ValueError("Snapshot path cannot be empty")

        args = ["kopia", "snapshot", "create", path, "--json"]
        if tags:
            for k, v in tags.items():
                args += ["--tags", f"{k}:{v}"]
        if exclude_patterns:
            for pattern in exclude_patterns:
                args += ["--ignore", pattern]

        # Debug: Log the actual command being executed
        logger.debug(
            f"Executing Kopia snapshot create",
            extra={
                "path": path,
                "tags": tags,
                "exclude_patterns": exclude_patterns,
                "full_command": " ".join(args[:10]) + ("..." if len(args) > 10 else ""),
            },
        )

        proc = self._run(args, check=True)
        snap = self._parse_single_json_line(proc.stdout)
        snap_id = snap.get("snapshotID") or snap.get("id") or ""

        # Debug: Log raw Kopia response
        logger.debug(
            f"Kopia snapshot created",
            extra={
                "snapshot_id": snap_id,
                "raw_response_preview": proc.stdout[:500] if proc.stdout else "empty",
            },
        )

        if not snap_id:
            raise RuntimeError(f"Could not determine snapshot ID from output: {proc.stdout[:200]}")
        return snap_id

    def create_snapshot_from_stdin(
        self,
        stdin: IO[bytes],
        dest_virtual_path: str,  # ← Parameter heißt "dest_virtual_path"
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create a snapshot from stdin (single virtual file).

        DEPRECATED (v5.0.0): This method creates TAR-based backups that prevent
        Kopia's block-level deduplication. Use create_snapshot() with a directory
        path instead for efficient incremental backups.

        Will be removed in v6.0.0.

        IMPORTANT: Use '--stdin-file <name>' **and** '-' as source to indicate stdin.
        """
        import warnings

        warnings.warn(
            "create_snapshot_from_stdin() is deprecated since v5.0.0. "
            "Use create_snapshot() with a directory path for block-level deduplication. "
            "This method will be removed in v6.0.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        args = ["kopia", "snapshot", "create", "--stdin-file", dest_virtual_path, "-", "--json"]
        if tags:
            for k, v in tags.items():
                args += ["--tags", f"{k}:{v}"]

        # Add config-file explicitly (can't use _run() because of stdin parameter)
        args.append("--config-file")
        args.append(self._get_config_file())

        proc = subprocess.run(
            args,
            env=self._get_env(),
            text=False,
            stdin=stdin,
            capture_output=True,
        )
        if proc.returncode != 0:
            err = (
                proc.stderr.decode("utf-8", "replace")
                if isinstance(proc.stderr, (bytes, bytearray))
                else proc.stderr
            )
            raise RuntimeError(f"stdin snapshot failed: {err.strip()}")

        out = (
            proc.stdout.decode("utf-8", "replace")
            if isinstance(proc.stdout, (bytes, bytearray))
            else proc.stdout
        )
        snap = self._parse_single_json_line(out)
        snap_id = snap.get("snapshotID") or snap.get("id") or ""
        if not snap_id:
            raise RuntimeError(f"Could not determine snapshot ID from output: {out[:200]}")
        return snap_id

    def list_snapshots(self, tag_filter: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        List snapshots. Kopia returns a JSON array.
        Returns simplified dicts: id, path, timestamp, tags, size.
        """
        proc = self._run(["kopia", "snapshot", "list", "--json"], check=True)

        # Parse as JSON array (not NDJSON!)
        try:
            raw_snaps = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse snapshot list: {e}")
            return []

        if not isinstance(raw_snaps, list):
            logger.warning("Unexpected snapshot list format (not an array)")
            return []

        snaps: List[Dict[str, Any]] = []
        for obj in raw_snaps:
            # Remove "tag:" prefix from tags
            tags_raw = obj.get("tags") or {}
            tags = {k.replace("tag:", ""): v for k, v in tags_raw.items()}

            # Apply tag filter if provided
            if tag_filter and any(tags.get(k) != v for k, v in tag_filter.items()):
                continue

            src = obj.get("source") or {}
            stats = obj.get("stats") or {}
            snaps.append(
                {
                    "id": obj.get("id", ""),
                    "path": src.get("path", ""),
                    "timestamp": obj.get("startTime") or obj.get("time") or "",
                    "tags": tags,  # Without "tag:" prefix!
                    "size": stats.get("totalSize") or 0,
                }
            )

        return snaps

    def list_all_snapshots(
        self, tag_filter: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List ALL snapshots from ALL machines in repository.

        Unlike list_snapshots(), this includes snapshots from other hosts.
        Used for cross-machine restore functionality.

        Args:
            tag_filter: Optional dict to filter by tags

        Returns:
            List of snapshot dicts with id, path, timestamp, tags, size, host
        """
        proc = self._run(["kopia", "snapshot", "list", "--all", "--json"], check=True)

        try:
            raw_snaps = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse snapshot list: {e}")
            return []

        if not isinstance(raw_snaps, list):
            logger.warning("Unexpected snapshot list format (not an array)")
            return []

        snaps: List[Dict[str, Any]] = []
        for obj in raw_snaps:
            # Remove "tag:" prefix from tags
            tags_raw = obj.get("tags") or {}
            tags = {k.replace("tag:", ""): v for k, v in tags_raw.items()}

            # Apply tag filter if provided
            if tag_filter and any(tags.get(k) != v for k, v in tag_filter.items()):
                continue

            src = obj.get("source") or {}
            stats = obj.get("stats") or {}
            snaps.append(
                {
                    "id": obj.get("id", ""),
                    "path": src.get("path", ""),
                    "host": src.get("host", "unknown"),  # Include hostname!
                    "userName": src.get("userName", ""),
                    "timestamp": obj.get("startTime") or obj.get("time") or "",
                    "tags": tags,
                    "size": stats.get("totalSize") or 0,
                }
            )

        return snaps

    def discover_machines(self) -> List["MachineInfo"]:
        """
        Discover all machines that have backups in the repository.

        Aggregates snapshot information by hostname to provide an overview
        of all backup sources.

        Returns:
            List of MachineInfo objects sorted by last backup (newest first)
        """
        from ..types import MachineInfo

        all_snapshots = self.list_all_snapshots()
        machines: Dict[str, MachineInfo] = {}

        for snap in all_snapshots:
            host = snap.get("host", "unknown")

            if host not in machines:
                machines[host] = MachineInfo(
                    hostname=host,
                    last_backup=datetime.min.replace(tzinfo=timezone.utc),
                    backup_count=0,
                    units=[],
                    total_size=0,
                )

            m = machines[host]
            m.backup_count += 1

            # Parse timestamp
            ts_str = snap.get("timestamp")
            if ts_str:
                try:
                    # Handle ISO format with timezone
                    ts_str_clean = ts_str.replace("Z", "+00:00")
                    ts = datetime.fromisoformat(ts_str_clean)
                    if ts > m.last_backup:
                        m.last_backup = ts
                except ValueError:
                    pass

            # Extract unit name from tags
            tags = snap.get("tags", {})
            unit = tags.get("unit")
            if unit and unit not in m.units:
                m.units.append(unit)

            # Aggregate size
            m.total_size += snap.get("size", 0)

        # Sort by last backup (newest first)
        result = sorted(machines.values(), key=lambda m: m.last_backup, reverse=True)

        logger.debug(
            f"Discovered {len(result)} machines in repository",
            extra={"machines": [m.hostname for m in result]},
        )

        return result

    # --------------- Restore / Verify / Maintenance ---------------

    def restore_snapshot(self, snapshot_id: str, target_path: str) -> None:
        """Restore snapshot to target directory."""
        self._run(["kopia", "snapshot", "restore", snapshot_id, target_path], check=True)
        logger.info("Restored snapshot %s to %s", snapshot_id, target_path)

    def verify_snapshot(self, snapshot_id: str, verify_percent: int = 10) -> bool:
        """Run snapshot verification (downloads a random % of files)."""
        proc = self._run(
            [
                "kopia",
                "snapshot",
                "verify",
                f"--verify-files-percent={verify_percent}",
                snapshot_id,
            ],
            check=False,
        )
        return proc.returncode == 0

    def delete_snapshot(self, snapshot_id: str, unsafe_ignore_source: bool = False) -> None:
        """
        Delete a snapshot from the repository.

        Args:
            snapshot_id: The snapshot ID to delete
            unsafe_ignore_source: If True, ignore source mismatch warnings
                                  (needed for snapshots from different machines)
        """
        cmd = ["kopia", "snapshot", "delete", snapshot_id, "--delete"]

        if unsafe_ignore_source:
            cmd.append("--unsafe-ignore-source")

        self._run(cmd, check=True)
        logger.info("Deleted snapshot %s", snapshot_id)

    def maintenance_run(self, full: bool = True) -> None:
        """Run 'kopia maintenance run' (default: --full)."""
        args = ["kopia", "maintenance", "run"]
        if full:
            args.append("--full")
        self._run(args, check=True)
        logger.info("Repository maintenance completed (full=%s)", full)

    # --------------- Utilities ---------------

    def list_backup_units(self) -> List[Dict[str, Any]]:
        """Infer backup units from recipe snapshots (tag type=recipe, tag unit=<name>)."""
        recipe_snaps = self.list_snapshots()
        units: Dict[str, Dict[str, Any]] = {}
        for s in recipe_snaps:
            tags = s.get("tags") or {}
            if tags.get("type") != "recipe":
                continue
            unit = tags.get("unit")
            if not unit:
                continue
            if unit not in units or (s.get("timestamp") or "") > units[unit].get("timestamp", ""):
                units[unit] = {
                    "name": unit,
                    "timestamp": s.get("timestamp", ""),
                    "snapshot_id": s.get("id", ""),
                }
        return list(units.values())

    # --------------- Repo creation helper for CLI (exact path) ---------------

    def create_filesystem_repo_at_path(
        self,
        path: Union[str, Path],
        *,
        profile: Optional[str] = None,
        password: Optional[str] = None,
        set_default: bool = False,
    ) -> Dict[str, Any]:
        """
        Create & connect a filesystem repository at PATH (exact Kopia semantics),
        using the given profile (or this instance's), and optional password override.
        Returns a small info dict {path, profile, config_file}.
        """
        # Effective profile & config file
        prof = profile or self.profile_name
        cfg_file = str(Path.home() / ".config" / "kopia" / f"repository-{prof}.config")
        Path(cfg_file).parent.mkdir(parents=True, exist_ok=True)

        # Effective env
        env = self._get_env().copy()
        if password:
            env["KOPIA_PASSWORD"] = password

        # Create directory
        repo_dir = Path(path).expanduser().resolve()
        repo_dir.mkdir(parents=True, exist_ok=True)

        # 1) Create
        cmd_create = [
            "kopia",
            "repository",
            "create",
            "filesystem",
            "--path",
            str(repo_dir),
            "--description",
            f"Kopi-Docka Backup Repository ({prof})",
            "--config-file",
            cfg_file,
        ]
        p = subprocess.run(cmd_create, env=env, text=True, capture_output=True)
        if p.returncode != 0:
            if "existing data in storage location" not in (p.stderr or ""):
                raise RuntimeError((p.stderr or p.stdout or "").strip())

        # 2) Connect (idempotent)
        cmd_connect = [
            "kopia",
            "repository",
            "connect",
            "filesystem",
            "--path",
            str(repo_dir),
            "--config-file",
            cfg_file,
        ]
        pc = subprocess.run(cmd_connect, env=env, text=True, capture_output=True)
        if pc.returncode != 0:
            # final status attempt for clearer error
            ps = subprocess.run(
                ["kopia", "repository", "status", "--config-file", cfg_file],
                env=env,
                text=True,
                capture_output=True,
            )
            raise RuntimeError((pc.stderr or pc.stdout or ps.stderr or ps.stdout or "").strip())

        # 3) Verify with status (must be connected)
        ps = subprocess.run(
            ["kopia", "repository", "status", "--json", "--config-file", cfg_file],
            env=env,
            text=True,
            capture_output=True,
        )
        if ps.returncode != 0:
            raise RuntimeError((ps.stderr or ps.stdout or "").strip())

        # 4) Optionally set default repository.config
        if set_default:
            src = Path(cfg_file)
            dst = Path.home() / ".config" / "kopia" / "repository.config"
            try:
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                try:
                    dst.symlink_to(src)
                except Exception:
                    from shutil import copy2

                    copy2(src, dst)
            except Exception as e:
                logger.warning("Could not set default kopia config: %s", e)

        return {"path": str(repo_dir), "profile": prof, "config_file": cfg_file}

    # --------------- JSON helper ---------------

    @staticmethod
    def _parse_single_json_line(s: str) -> Dict[str, Any]:
        s = (s or "").strip()
        if not s:
            return {}
        if "\n" in s:
            first = s.splitlines()[0].strip()
            try:
                return json.loads(first)
            except Exception:
                pass
        try:
            return json.loads(s)
        except Exception:
            return {}
