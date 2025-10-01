#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        repository_manager.py
# @module:      kopi_docka.cores.repository_manager
# @description: Kopia CLI wrapper with profile-specific config handling.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.2.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Changelog v1.2.0:
# - Password handling via Config.get_password() method
# - Support for systemd-creds and password_file references
# - Fallback to default password for initial setup
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
from pathlib import Path
from typing import Any, Dict, IO, List, Optional, Tuple, Union

from ..helpers.config import Config
from ..helpers.logging import get_logger

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
        self.repo_path = config.kopia_repository_path
        # Password wird dynamisch über get_password() geholt
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
        
        # Hole Passwort dynamisch über Config.get_password()
        try:
            password = self.config.get_password()
            if password:
                env["KOPIA_PASSWORD"] = password
        except ValueError as e:
            logger.warning(f"Could not get password: {e}")
            # Fallback zu direktem Config-Wert für Kompatibilität
            password = self.config.get('kopia', 'password', fallback='')
            if password:
                env["KOPIA_PASSWORD"] = password

        cache_dir = self.config.kopia_cache_directory
        if cache_dir:
            env["KOPIA_CACHE_DIRECTORY"] = str(cache_dir)

        # Optional: also expose path via env (we *also* pass --config-file explicitly)
        env.setdefault("KOPIA_CONFIG_PATH", self._get_config_file())
        return env

    def _run(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """
        Run Kopia command with our env and config.
        Raises with stderr/stdout if check=True and rc!=0.
        """
        if "--config-file" not in args:
            args = [*args, "--config-file", self._get_config_file()]

        proc = subprocess.run(
            args,
            env=self._get_env(),
            text=True,
            capture_output=True,
        )
        if check and proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"{' '.join(args)} failed: {msg}")
        return proc

    # --------------- Backend helpers ---------------

    def _detect_backend(self, repo_path: Union[str, Path]) -> Tuple[str, Dict[str, str]]:
        """Detect Kopia backend and split args for create/connect."""
        if isinstance(repo_path, Path):
            return "filesystem", {"path": str(repo_path)}

        rp = str(repo_path)
        if "://" not in rp:
            return "filesystem", {"path": rp}

        rp_lower = rp.lower()
        if rp_lower.startswith("s3://"):
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

        logger.warning("Unrecognized repository scheme '%s', assuming filesystem", rp)
        return "filesystem", {"path": rp}

    @staticmethod
    def _backend_args(backend: str, args: Dict[str, str]) -> List[str]:
        """Map parsed args to Kopia CLI flags for create/connect."""
        if backend == "filesystem":
            return ["--path", args["path"]]
        if backend in {"s3", "b2", "gcs"}:
            out = ["--bucket", args["bucket"]]
            if args.get("prefix"):
                out += ["--prefix", args["prefix"]]
            return out
        if backend == "azure":
            out = ["--container", args["container"]]
            if args.get("prefix"):
                out += ["--prefix", args["prefix"]]
            return out
        return []

    @staticmethod
    def _split_bucket_prefix(rest: str) -> Tuple[str, str]:
        parts = rest.split("/", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

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
        
        backend, args = self._detect_backend(self.repo_path)

        # Try connect
        proc = self._run([
            "kopia", "repository", "connect", backend,
            *self._backend_args(backend, args)
        ], check=False)
        
        if proc.returncode == 0:
            logger.info("Connected to repository (%s)", backend)
            return

        # Failed - check why
        err_msg = (proc.stderr or proc.stdout or "").lower()
        if "not found" in err_msg or "does not exist" in err_msg or "not initialized" in err_msg:
            raise RuntimeError(
                f"Repository not found at {self.repo_path}. "
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
        Create new repository at repo_path and connect to it (idempotent).
        If repository already exists, just connects to it.
        Verifies connection with 'repository status' and applies default policies.
        """
        backend, args = self._detect_backend(self.repo_path)
        
        # Check if already connected to this repo
        if self.is_connected():
            logger.info("Already connected to repository")
            return
        
        if backend == "filesystem":
            Path(args["path"]).expanduser().mkdir(parents=True, exist_ok=True)

        # Try to create (may fail if exists)
        proc = self._run([
            "kopia", "repository", "create", backend,
            *self._backend_args(backend, args),
            "--description", f"Kopi-Docka Backup Repository ({self.profile_name})",
        ], check=False)
        
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
            self._run([
                "kopia", "repository", "connect", backend,
                *self._backend_args(backend, args)
            ], check=True)
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

    # --------------- Snapshots ---------------

    def create_snapshot(self, path: str, tags: Optional[Dict[str, str]] = None) -> str:
        """
        Create a directory/file snapshot at 'path' with optional tags.
        Returns snapshot ID.
        """
        args = ["kopia", "snapshot", "create", path, "--json"]
        if tags:
            for k, v in tags.items():
                args += ["--tags", f"{k}:{v}"]
        proc = self._run(args, check=True)
        snap = self._parse_single_json_line(proc.stdout)
        snap_id = snap.get("snapshotID") or snap.get("id") or ""
        if not snap_id:
            raise RuntimeError(f"Could not determine snapshot ID from output: {proc.stdout[:200]}")
        return snap_id

    def create_snapshot_from_stdin(self, stdin: IO[bytes], dest_virtual_path: str,
                                   tags: Optional[Dict[str, str]] = None) -> str:
        """
        Create a snapshot from stdin (single virtual file).
        IMPORTANT: Use '--stdin-file <name>' **and** '-' as source to indicate stdin.
        """
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
            err = proc.stderr.decode("utf-8", "replace") if isinstance(proc.stderr, (bytes, bytearray)) else proc.stderr
            raise RuntimeError(f"stdin snapshot failed: {err.strip()}")

        out = proc.stdout.decode("utf-8", "replace") if isinstance(proc.stdout, (bytes, bytearray)) else proc.stdout
        snap = self._parse_single_json_line(out)
        snap_id = snap.get("snapshotID") or snap.get("id") or ""
        if not snap_id:
            raise RuntimeError(f"Could not determine snapshot ID from output: {out[:200]}")
        return snap_id

    def list_snapshots(self, tag_filter: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        List snapshots (NDJSON). If tag_filter provided, filter client-side.
        Returns simplified dicts: id, path, timestamp, tags, size.
        """
        proc = self._run(["kopia", "snapshot", "list", "--json"], check=True)
        snaps: List[Dict[str, Any]] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            tags = obj.get("tags") or {}
            if tag_filter and any(tags.get(k) != v for k, v in tag_filter.items()):
                continue

            src = obj.get("source") or {}
            stats = obj.get("stats") or {}
            snaps.append({
                "id": obj.get("id", ""),
                "path": src.get("path", ""),
                "timestamp": obj.get("startTime") or obj.get("time") or "",
                "tags": tags,
                "size": stats.get("totalSize") or 0,
            })
        return snaps

    # --------------- Restore / Verify / Maintenance ---------------

    def restore_snapshot(self, snapshot_id: str, target_path: str) -> None:
        """Restore snapshot to target directory."""
        self._run(["kopia", "snapshot", "restore", snapshot_id, target_path], check=True)
        logger.info("Restored snapshot %s to %s", snapshot_id, target_path)

    def verify_snapshot(self, snapshot_id: str, verify_percent: int = 10) -> bool:
        """Run snapshot verification (downloads a random % of files)."""
        proc = self._run(
            ["kopia", "snapshot", "verify", f"--verify-files-percent={verify_percent}", snapshot_id],
            check=False,
        )
        return proc.returncode == 0

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
            "kopia", "repository", "create", "filesystem",
            "--path", str(repo_dir),
            "--description", f"Kopi-Docka Backup Repository ({prof})",
            "--config-file", cfg_file,
        ]
        p = subprocess.run(cmd_create, env=env, text=True, capture_output=True)
        if p.returncode != 0:
            if "existing data in storage location" not in (p.stderr or ""):
                raise RuntimeError((p.stderr or p.stdout or "").strip())

        # 2) Connect (idempotent)
        cmd_connect = [
            "kopia", "repository", "connect", "filesystem",
            "--path", str(repo_dir),
            "--config-file", cfg_file,
        ]
        pc = subprocess.run(cmd_connect, env=env, text=True, capture_output=True)
        if pc.returncode != 0:
            # final status attempt for clearer error
            ps = subprocess.run(
                ["kopia", "repository", "status", "--config-file", cfg_file],
                env=env, text=True, capture_output=True
            )
            raise RuntimeError((pc.stderr or pc.stdout or ps.stderr or ps.stdout or "").strip())

        # 3) Verify with status (must be connected)
        ps = subprocess.run(
            ["kopia", "repository", "status", "--json", "--config-file", cfg_file],
            env=env, text=True, capture_output=True
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