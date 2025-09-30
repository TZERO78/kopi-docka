################################################################################
# KOPI-DOCKA
#
# @file:        repository.py
# @module:      kopi_docka.repository
# @description: Wraps Kopia CLI interactions with profile support
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Kopia repository management module with profile support.

This module handles all interactions with the Kopia backup repository,
including profile-based management, initialization, connection, and snapshots.
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
    Manages Kopia repository operations with profile support.
    
    Kopia supports multiple repository profiles, allowing different backup
    configurations to coexist. This class uses a dedicated 'kopi-docka' profile.
    """

    def __init__(self, config: Config):
        self.config = config
        self.repo_path = config.kopia_repository_path  # Uses property
        self.password = config.kopia_password  # Uses property (includes ENV override)
        self.profile_name = config.kopia_profile  # Uses Config property

    # ---------------------------------------------------------------------
    # Profile Management
    # ---------------------------------------------------------------------

    def get_current_profile(self) -> Optional[str]:
        """Get the currently active Kopia profile."""
        try:
            result = subprocess.run(
                ["kopia", "repository", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                data = self._parse_single_json_line(result.stdout)
                # Extract profile name from status if available
                return data.get("configFile", "").split(".")[-1] if "." in data.get("configFile", "") else "default"
        except:
            return None

    def set_profile(self) -> bool:
        """Set the Kopia profile to kopi-docka."""
        try:
            result = subprocess.run(
                ["kopia", "repository", "set-client", self.profile_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def profile_exists(self) -> bool:
        """Check if the kopi-docka profile exists."""
        config_path = Path.home() / ".config" / "kopia" / f"repository-{self.profile_name}.config"
        return config_path.exists()

    # ---------------------------------------------------------------------
    # Repository lifecycle with Profile Support
    # ---------------------------------------------------------------------

    def is_initialized(self) -> bool:
        """Return True if repository is accessible with our profile."""
        try:
            # Use profile-specific check
            cmd = ["kopia", "repository", "status", "--json"]
            
            # If profile exists, use it
            if self.profile_exists():
                cmd.extend(["--config-file", self._get_config_file()])
            
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Check if it's our repository
                data = self._parse_single_json_line(result.stdout)
                repo_desc = data.get("description", "")
                
                # Mark as ours if it contains our identifier or if we're using our profile
                if "kopi-docka" in repo_desc.lower() or self.profile_exists():
                    return True
                    
            return False
            
        except FileNotFoundError:
            logger.error("Kopia binary not found")
            return False
        except Exception as e:
            logger.debug(f"Repository check failed: {e}")
            return False

    def initialize(self):
        """
        Initialize or connect to a Kopia repository with profile support.
        """
        backend, args = self._detect_backend(self.repo_path)
        logger.info(f"Initializing Kopia repository ({backend}) with profile: {self.profile_name}")

        # First, try to connect to existing repository
        if self._try_connect(backend, args):
            logger.info("Connected to existing repository")
            return

        # If connect failed, try to create new repository
        cmd: List[str] = ["kopia", "repository", "create", backend]
        cmd.extend(self._backend_args(backend, args))
        
        # Add profile configuration
        cmd.extend(["--description", f"Kopi-Docka Backup Repository ({self.profile_name})"])
        
        # Use our profile config file
        config_file = self._get_config_file()
        cmd.extend(["--config-file", config_file])
        
        # For filesystem: ensure directory exists
        if backend == "filesystem":
            p = Path(args["path"]).expanduser()
            p.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if "existing data in storage location" in result.stderr:
                    logger.info("Repository exists at location, attempting to connect...")
                    if self._try_connect(backend, args, force=True):
                        logger.info("Successfully connected to existing repository")
                        return
                    else:
                        raise Exception("Repository exists but cannot connect. Check password or use different path.")
                else:
                    raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
            
            logger.info("Repository created successfully")
            
            # Display password warning on first initialization
            if self.password:
                # Check if this is a generated password (not default)
                if len(self.password) >= 20 and self.password != 'CHANGE_ME_TO_A_SECURE_PASSWORD':
                    print("\n" + "="*70)
                    print("🔐 REPOSITORY INITIALIZED")
                    print("="*70)
                    print("Repository is encrypted with the password from your config.")
                    print("This password is REQUIRED for all restore operations!")
                    print("")
                    print("Make sure you have backed up:")
                    print(f"  • Config file: {self.config.config_file}")
                    print(f"  • Password file (if exists): {self.config.config_file.parent / f'.{self.config.config_file.stem}.password'}")
                    print("="*70 + "\n")
            
            # Set default policies
            self._set_default_policies()
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to initialize repository: {e.stderr.strip()}")
            raise

    def connect(self):
        """Connect to an existing Kopia repository with profile support."""
        backend, args = self._detect_backend(self.repo_path)
        logger.debug(f"Connecting to Kopia repository ({backend}) with profile: {self.profile_name}")
        
        if not self._try_connect(backend, args):
            raise Exception("Failed to connect to repository")

    def _try_connect(self, backend: str, args: Dict[str, str], force: bool = False) -> bool:
        """
        Try to connect to a repository.
        
        Args:
            backend: Repository backend type
            args: Backend-specific arguments
            force: Force connection even if repository exists
            
        Returns:
            True if connection successful, False otherwise
        """
        cmd: List[str] = ["kopia", "repository", "connect", backend]
        cmd.extend(self._backend_args(backend, args))
        
        # Use our profile
        config_file = self._get_config_file()
        cmd.extend(["--config-file", config_file])
        
        if force:
            cmd.append("--no-check-for-updates")
            cmd.append("--override-hostname")
            cmd.append("--override-username")

        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Connected to repository with profile: {self.profile_name}")
                return True
            
            # Check for specific errors
            if "repository not initialized" in result.stderr.lower():
                logger.debug("Repository not initialized at this location")
                return False
            elif "invalid password" in result.stderr.lower():
                logger.error("Invalid password for repository")
                return False
            else:
                logger.debug(f"Connection failed: {result.stderr.strip()}")
                return False
                
        except Exception as e:
            logger.debug(f"Connection attempt failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from the repository (profile-specific)."""
        try:
            cmd = ["kopia", "repository", "disconnect"]
            cmd.extend(["--config-file", self._get_config_file()])
            
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.info(f"Disconnected from repository (profile: {self.profile_name})")
        except:
            pass

    # ---------------------------------------------------------------------
    # Snapshots (with profile support)
    # ---------------------------------------------------------------------

    def create_snapshot(self, path: str, tags: Optional[Dict[str, str]] = None) -> str:
        """Create a directory snapshot using our profile."""
        cmd = ["kopia", "snapshot", "create", path, "--json"]
        cmd.extend(["--config-file", self._get_config_file()])
        
        if tags:
            for k, v in tags.items():
                cmd.extend(["--tags", f"{k}:{v}"])
        
        # Add profile tag
        cmd.extend(["--tags", f"profile:{self.profile_name}"])

        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True,
            )
            data = self._parse_single_json_line(result.stdout)
            snap_id = data.get("snapshotID") or data.get("id") or ""
            if not snap_id:
                raise ValueError(f"Could not determine snapshot ID from: {result.stdout[:200]}")
            logger.info(f"Created snapshot: {snap_id}")
            return snap_id
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create snapshot: {e.stderr.strip()}")
            raise

    def create_snapshot_from_stdin(
        self,
        stdin: IO[bytes],
        path: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create a snapshot from a binary stream using our profile."""
        cmd = ["kopia", "snapshot", "create", "--stdin", "--stdin-file", path, "--json"]
        cmd.extend(["--config-file", self._get_config_file()])
        
        if tags:
            for k, v in tags.items():
                cmd.extend(["--tags", f"{k}:{v}"])
        
        # Add profile tag
        cmd.extend(["--tags", f"profile:{self.profile_name}"])

        try:
            result = subprocess.run(
                cmd,
                stdin=stdin,
                env=self._get_env(),
                capture_output=True,
                check=True,
                text=False,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            data = self._parse_single_json_line(stdout)
            snap_id = data.get("snapshotID") or data.get("id") or ""
            if not snap_id:
                raise ValueError(f"Could not determine snapshot ID from: {stdout[:200]}")
            logger.info(f"Created snapshot from stdin: {snap_id}")
            return snap_id
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="replace")
            logger.error(f"Failed to create snapshot from stdin: {err.strip()}")
            raise

    def list_snapshots(
        self, tag_filter: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """List snapshots from our profile."""
        cmd = ["kopia", "snapshot", "list", "--json"]
        cmd.extend(["--config-file", self._get_config_file()])
        
        # Always filter by our profile
        cmd.extend(["--tags", f"profile:{self.profile_name}"])
        
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

    # ---------------------------------------------------------------------
    # Helper Methods
    # ---------------------------------------------------------------------

    def _get_config_file(self) -> str:
        """Get the profile-specific config file path."""
        config_dir = Path.home() / ".config" / "kopia"
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir / f"repository-{self.profile_name}.config")

    def _set_default_policies(self):
        """Set default policies for the repository from configuration."""
        try:
            # Set compression policy from config
            compression = self.config.get("kopia", "compression", "zstd")
            policy_cmd = [
                "kopia", "policy", "set", "--global",
                "--compression", compression,
                "--config-file", self._get_config_file()
            ]
            subprocess.run(
                policy_cmd,
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            
            # Set retention policy from config
            retention_cmd = [
                "kopia", "policy", "set", "--global",
                "--keep-latest", "10",
                "--keep-daily", str(self.config.getint('retention', 'daily', 7)),
                "--keep-weekly", str(self.config.getint('retention', 'weekly', 4)),
                "--keep-monthly", str(self.config.getint('retention', 'monthly', 12)),
                "--keep-yearly", str(self.config.getint('retention', 'yearly', 5)),
                "--config-file", self._get_config_file()
            ]
            subprocess.run(
                retention_cmd,
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            
            logger.info("Default policies set from configuration")
            
        except Exception as e:
            logger.warning(f"Could not set default policies: {e}")

    def _get_env(self) -> Dict[str, str]:
        """Build environment for Kopia CLI."""
        import os
        env = os.environ.copy()
        env["KOPIA_PASSWORD"] = self.password or ""
        
        # Use Config property instead of direct get()
        cache_dir = self.config.kopia_cache_directory
        if cache_dir:
            env["KOPIA_CACHE_DIRECTORY"] = str(cache_dir)
        
        return env

    def _detect_backend(
        self, repo_path: Union[str, Path]
    ) -> Tuple[str, Dict[str, str]]:
        """Detect Kopia backend & parse connection args from repo_path."""
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

        logger.warning(f"Unrecognized repository scheme for '{rp}', assuming filesystem")
        return "filesystem", {"path": rp}

    def _backend_args(self, backend: str, args: Dict[str, str]) -> List[str]:
        """Map parsed args to kopia CLI flags for create/connect."""
        if backend == "filesystem":
            return ["--path", args["path"]]

        if backend in ["s3", "b2", "gcs"]:
            out = ["--bucket", args["bucket"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

        if backend == "azure":
            out = ["--container", args["container"]]
            if "prefix" in args and args["prefix"]:
                out += ["--prefix", args["prefix"]]
            return out

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

    # ---------------------------------------------------------------------
    # Restore & Maintenance
    # ---------------------------------------------------------------------

    def restore_snapshot(self, snapshot_id: str, target_path: str):
        """Restore a snapshot to a directory using our profile."""
        logger.info(f"Restoring snapshot {snapshot_id} to {target_path}")
        try:
            cmd = ["kopia", "snapshot", "restore", snapshot_id, target_path]
            cmd.extend(["--config-file", self._get_config_file()])
            
            subprocess.run(
                cmd,
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
            cmd = ["kopia", "snapshot", "verify", "--verify-files-percent=10", snapshot_id]
            cmd.extend(["--config-file", self._get_config_file()])
            
            res = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    def maintenance_run(self, full: bool = True):
        """Run kopia maintenance with our profile."""
        logger.info("Running repository maintenance")
        try:
            cmd = ["kopia", "maintenance", "run"]
            if full:
                cmd.append("--full")
            cmd.extend(["--config-file", self._get_config_file()])
            
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

    def list_backup_units(self) -> List[Dict[str, Any]]:
        """List backup units by scanning recipe snapshots (profile-filtered)."""
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