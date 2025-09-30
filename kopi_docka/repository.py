################################################################################
# KOPI-DOCKA
#
# @file:        repository.py
# @module:      kopi_docka.repository
# @description: Wraps Kopia CLI interactions for snapshots, restore, and maintenance tasks.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Prepares kopia environment variables via _get_env
# - Supports snapshots from directories and streaming stdin sources
# - Provides portable mount helpers that restore into temporary paths
################################################################################

"""
Kopia repository management module.

This module handles all interactions with the Kopia backup repository,
including initialization, connection, snapshot creation (dir & stdin),
listing, restore, and a portable 'mount' (restore-to-temp) helper.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, IO, Tuple, Union

from .config import Config
from .logging import get_logger

logger = get_logger(__name__)


class KopiaRepository:
    """
    Manages Kopia repository operations.

    Provides a Python interface to Kopia commands for repository management,
    snapshot creation, listing, verification, and restoration.
    """

    def __init__(self, config: Config):
        self.config = config
        self.repo_path: Union[str, Path] = (
            config.kopia_repository_path
        )  # str for remote, Path for local
        self.password: str = config.kopia_password

    # ---------------------------------------------------------------------
    # Repository lifecycle
    # ---------------------------------------------------------------------

    def is_initialized(self) -> bool:
        """Return True if repository is accessible."""
        try:
            result = subprocess.run(
                ["kopia", "repository", "status", "--json"],
                env=self._get_env(),
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.error("Kopia binary not found")
            return False
        except Exception as e:
            logger.error(f"Failed to check repository status: {e}")
            return False

    def initialize(self):
        """
        Initialize (create) a Kopia repository.

        Local filesystem repos werden erstellt. Für Remote-Repos wird ebenfalls
        versucht, die Erstellung durchzuführen (erfordert passende Credentials
        via Env/CLI). Falls das fehlschlägt: Logs prüfen & manuell verbinden.
        """
        backend, args = self._detect_backend(self.repo_path)
        logger.info(f"Initializing Kopia repository ({backend})")

        cmd: List[str] = ["kopia", "repository", "create", backend]
        cmd.extend(self._backend_args(backend, args))
        # Compression/Encryption aus Config
        #compression = self.config.get("kopia", "compression")
        #encryption = self.config.get("kopia", "encryption")
        #if compression:
        #    cmd.extend(["--compression", compression])
        #if encryption:
        #    cmd.extend(["--encryption", encryption])

        # Für filesystem: Zielverzeichnis anlegen
        if backend == "filesystem":
            p = Path(args["path"]).expanduser()
            p.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                cmd,
                env=self._get_env(),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Repository initialized successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to initialize repository: {e.stderr.strip()}")
            raise

    def connect(self):
        """Connect to an existing Kopia repository."""
        backend, args = self._detect_backend(self.repo_path)
        logger.debug(f"Connecting to Kopia repository ({backend})")
        cmd: List[str] = ["kopia", "repository", "connect", backend]
        cmd.extend(self._backend_args(backend, args))

        try:
            subprocess.run(
                cmd,
                env=self._get_env(),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Connected to repository")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to connect to repository: {e.stderr.strip()}")
            raise

    # ---------------------------------------------------------------------
    # Snapshots
    # ---------------------------------------------------------------------

    def create_snapshot(self, path: str, tags: Optional[Dict[str, str]] = None) -> str:
        """
        Create a directory snapshot.

        Args:
            path: Source directory to snapshot
            tags: Optional tags to attach

        Returns:
            Snapshot ID
        """
        cmd = ["kopia", "snapshot", "create", path, "--json"]
        if tags:
            for k, v in tags.items():
                cmd.extend(["--tags", f"{k}:{v}"])

        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            # Kopia gibt in --json i. d. R. eine einzelne JSON-Zeile zurück
            data = self._parse_single_json_line(result.stdout)
            snap_id = data.get("snapshotID") or data.get("id") or ""
            if not snap_id:
                raise ValueError(
                    f"Could not determine snapshot ID from: {result.stdout[:200]}"
                )
            logger.info(f"Created snapshot: {snap_id}")
            return snap_id
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create snapshot: {e.stderr.strip()}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse Kopia output: {e}")
            raise

    def create_snapshot_from_stdin(
        self,
        stdin: IO[bytes],
        path: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create a snapshot from a binary stream (stdin). Ideal für Tar-Streams.

        Args:
            stdin: Binary stream (do NOT open in text mode)
            path: Virtual file path shown inside the snapshot
            tags: Optional tags

        Returns:
            Snapshot ID
        """
        cmd = ["kopia", "snapshot", "create", "--stdin", "--stdin-file", path, "--json"]
        if tags:
            for k, v in tags.items():
                cmd.extend(["--tags", f"{k}:{v}"])

        try:
            result = subprocess.run(
                cmd,
                stdin=stdin,  # binary stream
                env=self._get_env(),
                capture_output=True,
                check=True,
                text=False,  # IMPORTANT: binary-safe
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            data = self._parse_single_json_line(stdout)
            snap_id = data.get("snapshotID") or data.get("id") or ""
            if not snap_id:
                raise ValueError(
                    f"Could not determine snapshot ID from: {stdout[:200]}"
                )
            logger.info(f"Created snapshot from stdin: {snap_id}")
            return snap_id
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="replace")
            logger.error(f"Failed to create snapshot from stdin: {err.strip()}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse Kopia output: {e}")
            raise

    def list_snapshots(
        self, tag_filter: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List snapshots as dictionaries (id, path, timestamp, tags, size).
        """
        cmd = ["kopia", "snapshot", "list", "--json"]
        if tag_filter:
            for k, v in tag_filter.items():
                cmd.extend(["--tags", f"{k}:{v}"])

        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            snaps: List[Dict[str, Any]] = []
            for line in result.stdout.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    snap = json.loads(line)
                    snaps.append(
                        {
                            "id": snap.get("id", ""),
                            "path": (snap.get("source") or {}).get("path", ""),
                            "timestamp": snap.get("startTime", ""),
                            "tags": snap.get("tags", {}) or {},
                            "size": ((snap.get("stats") or {}).get("totalSize")) or 0,
                        }
                    )
                except json.JSONDecodeError:
                    continue
            return snaps
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list snapshots: {e.stderr.strip()}")
            return []

    def restore_snapshot(self, snapshot_id: str, target_path: str):
        """Restore a snapshot to a directory."""
        logger.info(f"Restoring snapshot {snapshot_id} to {target_path}")
        try:
            subprocess.run(
                ["kopia", "snapshot", "restore", snapshot_id, target_path],
                env=self._get_env(),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"Snapshot restored to {target_path}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restore snapshot: {e.stderr.strip()}")
            raise

    def verify_snapshot(self, snapshot_id: str) -> bool:
        """Run a partial verify for a snapshot."""
        try:
            res = subprocess.run(
                [
                    "kopia",
                    "snapshot",
                    "verify",
                    "--verify-files-percent=10",
                    snapshot_id,
                ],
                env=self._get_env(),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # Portable "mount" (restore-to-temp) helpers
    # ---------------------------------------------------------------------

    def mount_snapshot(
        self, snapshot_id: str, mount_path: Optional[str] = None
    ) -> Path:
        """
        Provide a portable 'mount' by restoring to a temp dir.

        Why not 'kopia mount'? That requires FUSE and a long-running process.
        For scripted restores and inspection we restore to a temp directory
        and return its Path. Use `unmount()` to clean up.
        """
        if mount_path is None:
            mount_dir = Path(tempfile.mkdtemp(prefix="kopia-mount-"))
        else:
            mount_dir = Path(mount_path)
            mount_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Portable-mount snapshot {snapshot_id} -> {mount_dir}")
        self.restore_snapshot(snapshot_id, str(mount_dir))
        return mount_dir

    def unmount(self, mount_path: str):
        """
        'Unmount' a portable mount by deleting the directory.
        """
        p = Path(mount_path)
        if p.exists():
            try:
                shutil.rmtree(p)
                logger.debug(f"Unmounted (removed) {p}")
            except Exception as e:
                logger.warning(f"Failed to remove {p}: {e}")

    # Backwards-compat alias if some code calls unmount_snapshot()
    def unmount_snapshot(self, mount_path: str):
        self.unmount(mount_path)

    # ---------------------------------------------------------------------
    # Maintenance & units
    # ---------------------------------------------------------------------

    def list_backup_units(self) -> List[Dict[str, Any]]:
        """
        List backup units by scanning recipe snapshots (most-recent per unit).
        """
        recipe_snaps = self.list_snapshots(tag_filter={"type": "recipe"})
        units: Dict[str, Dict[str, Any]] = {}
        for s in recipe_snaps:
            unit = (s.get("tags") or {}).get("unit")
            if not unit:
                continue
            if unit not in units or s["timestamp"] > units[unit]["timestamp"]:
                units[unit] = {
                    "name": unit,
                    "timestamp": s["timestamp"],
                    "snapshot_id": s["id"],
                }
        return list(units.values())

    def maintenance_run(self, full: bool = True):
        """Run kopia maintenance."""
        logger.info("Running repository maintenance")
        try:
            cmd = ["kopia", "maintenance", "run"]
            if full:
                cmd.append("--full")
            subprocess.run(
                cmd,
                env=self._get_env(),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Maintenance completed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Maintenance failed: {e.stderr.strip()}")

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _get_env(self) -> Dict[str, str]:
        """Build environment for Kopia CLI."""
        import os

        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = self.password or ""
        cache_dir = self.config.get("kopia", "cache_directory")
        if cache_dir:
            env["KOPIA_CACHE_DIRECTORY"] = str(Path(cache_dir).expanduser())
        return env

    def _detect_backend(
        self, repo_path: Union[str, Path]
    ) -> Tuple[str, Dict[str, str]]:
        """
        Detect Kopia backend & parse connection args from repo_path.

        Returns:
            (backend, args_dict)
        """
        if isinstance(repo_path, Path):
            # Local filesystem
            return "filesystem", {"path": str(repo_path)}

        rp = str(repo_path)
        # Filesystem via string (absolute path)
        if "://" not in rp:
            return "filesystem", {"path": rp}

        # Remote URLs
        rp_lower = rp.lower()
        if rp_lower.startswith("s3://"):
            # s3://bucket/prefix...
            bucket, prefix = self._split_bucket_prefix(rp[5:])
            args = {"bucket": bucket}
            if prefix:
                args["prefix"] = prefix
            return "s3", args

        if rp_lower.startswith("b2://"):
            bucket, prefix = self._split_bucket_prefix(rp[5:])
            args = {"bucket": bucket}
            if prefix:
                args["prefix"] = prefix
            return "b2", args

        if rp_lower.startswith("azure://"):
            # azure://container/prefix...
            container, prefix = self._split_bucket_prefix(rp[8:])
            args = {"container": container}
            if prefix:
                args["prefix"] = prefix
            return "azure", args

        if rp_lower.startswith("gs://"):
            bucket, prefix = self._split_bucket_prefix(rp[5:])
            args = {"bucket": bucket}
            if prefix:
                args["prefix"] = prefix
            return "gcs", args

        # Fallback: treat as filesystem path if unknown scheme
        logger.warning(
            f"Unrecognized repository scheme for '{rp}', assuming filesystem"
        )
        return "filesystem", {"path": rp}

    def _backend_args(self, backend: str, args: Dict[str, str]) -> List[str]:
        """Map parsed args to kopia CLI flags for create/connect."""
        if backend == "filesystem":
            return ["--path", args["path"]]

        if backend == "s3":
            out = ["--bucket", args["bucket"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

        if backend == "b2":
            out = ["--bucket", args["bucket"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

        if backend == "azure":
            out = ["--container", args["container"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

        if backend == "gcs":
            out = ["--bucket", args["bucket"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

        # Unknown backend -> no extra flags
        return []

    def _split_bucket_prefix(self, rest: str) -> Tuple[str, str]:
        """Split 'bucket/prefix/...' -> ('bucket', 'prefix/...')."""
        parts = rest.split("/", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    def _parse_single_json_line(self, s: str) -> Dict[str, Any]:
        """Parse either a single JSON object or take the first JSON line."""
        s = (s or "").strip()
        if not s:
            return {}
        # Some kopia subcommands may output one JSON object per line.
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
