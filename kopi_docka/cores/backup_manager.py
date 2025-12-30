################################################################################
# KOPI-DOCKA
#
# @file:        backup_manager.py
# @module:      kopi_docka.cores
# @description: Orchestriert Cold-Backups: Stop -> Rezepte -> Volumes -> Start.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Alle Snapshots eines Laufs teilen sich dieselbe 'backup_id' (Pflicht-Tag)
# - Rezepte: Compose + docker inspect (ENV-Secrets redacted)
# - Volumes: tar-Stream mit Owner/ACLs/xattrs, deterministische mtimes
################################################################################
"""
Backup management module for Kopi-Docka.

Cold backup strategy:
1) Stop containers
2) Backup recipes (compose + inspect with secrets redacted)
3) Backup volumes (tar stream → Kopia)
4) Start containers
5) Optionally update disaster recovery bundle
"""

import json
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError
from ..types import BackupUnit, ContainerInfo, VolumeInfo, BackupMetadata
from ..helpers.config import Config
from ..cores.repository_manager import KopiaRepository
from ..cores.kopia_policy_manager import KopiaPolicyManager
from ..cores.hooks_manager import HooksManager
from ..cores.notification_manager import NotificationManager, BackupStats
from ..cores.safe_exit_manager import SafeExitManager, ServiceContinuityHandler
from ..helpers.constants import (
    CONTAINER_STOP_TIMEOUT,
    CONTAINER_START_TIMEOUT,
    RECIPE_BACKUP_DIR,
    VOLUME_BACKUP_DIR,
    NETWORK_BACKUP_DIR,
    DOCKER_CONFIG_BACKUP_DIR,
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
    BACKUP_FORMAT_TAR,
    BACKUP_FORMAT_DIRECT,
    BACKUP_FORMAT_DEFAULT,
    STAGING_BASE_DIR,
)

logger = get_logger(__name__)


class BackupManager:
    """Orchestrates cold backups for Docker units."""

    def __init__(self, config: Config):
        self.config = config
        self.repo = KopiaRepository(config)
        self.policy_manager = KopiaPolicyManager(self.repo)
        self.hooks_manager = HooksManager(config)
        self.notification_manager = NotificationManager(config)
        self.max_workers = config.parallel_workers

        self.stop_timeout = self.config.getint("backup", "stop_timeout", CONTAINER_STOP_TIMEOUT)
        self.start_timeout = self.config.getint("backup", "start_timeout", CONTAINER_START_TIMEOUT)

        self.exclude_patterns = self.config.getlist("backup", "exclude_patterns", [])

    def backup_unit(
        self,
        unit: BackupUnit,
        backup_scope: str = BACKUP_SCOPE_STANDARD,
        update_recovery_bundle: bool = None,
    ) -> BackupMetadata:
        """
        Perform full cold backup of a unit.

        Returns:
            BackupMetadata
        """
        logger.info(
            f"Starting backup of unit: {unit.name} (scope: {backup_scope})",
            extra={"unit_name": unit.name, "backup_scope": backup_scope},
        )
        start_time = time.time()

        # Create a consistent backup_id for all snapshots in this run (required)
        backup_id = str(uuid.uuid4())

        metadata = BackupMetadata(
            unit_name=unit.name,
            timestamp=datetime.now(),
            duration_seconds=0,
            backup_id=backup_id,
            backup_scope=backup_scope,
        )

        # Setup ServiceContinuityHandler for emergency container restart on abort
        safe_exit = SafeExitManager.get_instance()
        service_handler = ServiceContinuityHandler()
        safe_exit.register_handler(service_handler)

        try:
            # Apply retention policies up front
            self._ensure_policies(unit)

            # 0) Pre-backup hook
            logger.info("Executing pre-backup hook...", extra={"unit_name": unit.name})
            if not self.hooks_manager.execute_pre_backup(unit.name):
                logger.warning(
                    "Pre-backup hook failed, aborting backup", extra={"unit_name": unit.name}
                )
                metadata.errors.append("Pre-backup hook failed")
                metadata.success = False
                return metadata

            # 1) Stop containers
            logger.info(
                f"Stopping {len(unit.containers)} containers...",
                extra={"unit_name": unit.name},
            )
            self._stop_containers(unit.containers, service_handler)

            # 2) Recipes (skip for minimal scope)
            if backup_scope != BACKUP_SCOPE_MINIMAL:
                logger.info("Backing up recipes...", extra={"unit_name": unit.name})
                recipe_snapshot = self._backup_recipes(unit, backup_id, backup_scope)
                if recipe_snapshot:
                    metadata.kopia_snapshot_ids.append(recipe_snapshot)
            else:
                logger.info(
                    "Skipping recipes backup (minimal scope)", extra={"unit_name": unit.name}
                )

            # 2.5) Networks (standard and full scopes)
            if backup_scope in [BACKUP_SCOPE_STANDARD, BACKUP_SCOPE_FULL]:
                logger.info("Backing up networks...", extra={"unit_name": unit.name})
                network_snapshot, network_count = self._backup_networks(unit, backup_id, backup_scope)
                if network_snapshot:
                    metadata.kopia_snapshot_ids.append(network_snapshot)
                    metadata.networks_backed_up = network_count
            else:
                logger.debug(
                    f"Skipping networks backup (scope: {backup_scope})",
                    extra={"unit_name": unit.name},
                )

            # 2.6) Docker daemon config (full scope only)
            if backup_scope == BACKUP_SCOPE_FULL:
                logger.info("Backing up Docker daemon configuration...", extra={"unit_name": unit.name})
                docker_config_snapshot = self._backup_docker_config(unit, backup_id, backup_scope)
                if docker_config_snapshot:
                    metadata.kopia_snapshot_ids.append(docker_config_snapshot)
                    metadata.docker_config_backed_up = True
                else:
                    metadata.docker_config_backed_up = False
            else:
                metadata.docker_config_backed_up = False

            # 3) Volumes (parallel)
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for volume in unit.volumes:
                    futures.append(
                        (
                            volume.name,
                            executor.submit(self._backup_volume, volume, unit, backup_id, backup_scope),
                        )
                    )

                task_timeout = max(0, self.config.getint("backup", "task_timeout", 0))
                for vol_name, fut in futures:
                    try:
                        snap_id = fut.result(timeout=task_timeout or None)
                        if snap_id:
                            metadata.kopia_snapshot_ids.append(snap_id)
                            metadata.volumes_backed_up += 1
                            logger.debug(
                                f"Completed volume backup: {vol_name}",
                                extra={"unit_name": unit.name, "volume": vol_name},
                            )
                        else:
                            metadata.errors.append(f"Failed to backup volume: {vol_name}")
                            logger.warning(
                                f"No snapshot created for volume: {vol_name}",
                                extra={"unit_name": unit.name},
                            )
                    except Exception as e:
                        metadata.errors.append(f"Error backing up volume {vol_name}: {str(e)}")
                        logger.error(
                            f"Exception during volume backup {vol_name}: {e}",
                            extra={"unit_name": unit.name},
                        )

        except Exception as e:
            metadata.errors.append(f"Backup failed: {str(e)}")
            logger.error(f"Critical error during backup: {e}", extra={"unit_name": unit.name})

        finally:
            # 4) Always try to restart containers
            logger.info(
                f"Starting {len(unit.containers)} containers...",
                extra={"unit_name": unit.name},
            )
            self._start_containers(unit.containers, service_handler)

            # Unregister ServiceContinuityHandler (cleanup complete)
            safe_exit.unregister_handler(service_handler)

            # 5) Post-backup hook
            logger.info("Executing post-backup hook...", extra={"unit_name": unit.name})
            if not self.hooks_manager.execute_post_backup(unit.name):
                logger.warning("Post-backup hook failed", extra={"unit_name": unit.name})
                metadata.errors.append("Post-backup hook failed")

        # Track executed hooks
        metadata.hooks_executed = self.hooks_manager.get_executed_hooks()

        # Duration & success
        metadata.duration_seconds = time.time() - start_time
        metadata.success = len(metadata.errors) == 0

        # Save metadata JSON
        self._save_metadata(metadata)

        # 5) Optional DR bundle
        should_update_bundle = update_recovery_bundle
        if should_update_bundle is None:
            should_update_bundle = self.config.getboolean("backup", "update_recovery_bundle", False)

        if should_update_bundle and metadata.success:
            logger.info("Updating disaster recovery bundle...", extra={"operation": "dr_bundle"})
            try:
                from ..cores.disaster_recovery_manager import DisasterRecoveryManager

                dr_manager = DisasterRecoveryManager(self.config)
                dr_manager.create_recovery_bundle()
            except Exception as e:
                logger.error(
                    f"Failed to update disaster recovery bundle: {e}",
                    extra={"operation": "dr_bundle"},
                )

        # Final log
        if metadata.errors:
            logger.warning(
                f"Backup of {unit.name} completed with errors in {metadata.duration_seconds:.2f}s",
                extra={
                    "unit_name": unit.name,
                    "duration": metadata.duration_seconds,
                    "errors": len(metadata.errors),
                },
            )
        else:
            logger.info(
                f"Backup of {unit.name} completed successfully in {metadata.duration_seconds:.2f}s",
                extra={"unit_name": unit.name, "duration": metadata.duration_seconds},
            )

        # Send notification (fire-and-forget, never blocks)
        try:
            stats = BackupStats.from_metadata(metadata)
            if metadata.success:
                self.notification_manager.send_success(stats)
            else:
                self.notification_manager.send_failure(stats)
        except Exception as e:
            logger.debug(f"Notification failed (non-blocking): {e}")

        return metadata

    def _stop_containers(self, containers: List[ContainerInfo], service_handler: ServiceContinuityHandler):
        """Stop containers gracefully and register them for emergency restart."""
        for c in containers:
            if c.is_running:
                try:
                    run_command(
                        ["docker", "stop", "-t", str(self.stop_timeout), c.id],
                        f"Stopping {c.name}",
                        timeout=self.stop_timeout + 10,  # Docker timeout + safety margin
                    )
                    logger.debug(f"Stopped container: {c.name}", extra={"container": c.name})
                    # Register with ServiceContinuityHandler for emergency restart on abort
                    service_handler.register_container(c.id, c.name)
                except SubprocessError as e:
                    logger.error(
                        f"Failed to stop container {c.name}: {e.stderr}",
                        extra={"container": c.name},
                    )

    def _start_containers(self, containers: List[ContainerInfo], service_handler: ServiceContinuityHandler):
        """Start containers in original order and wait (healthcheck if present)."""
        for c in containers:
            try:
                run_command(
                    ["docker", "start", c.id],
                    f"Starting {c.name}",
                    timeout=30,
                )
                logger.debug(f"Started container: {c.name}", extra={"container": c.name})
                # Unregister from emergency restart (normal startup successful)
                service_handler.unregister_container(c.id)
                self._wait_container_healthy(c, timeout=self.start_timeout)
            except SubprocessError as e:
                logger.error(
                    f"Failed to start container {c.name}: {e.stderr}",
                    extra={"container": c.name},
                )

    def _wait_container_healthy(self, container: ContainerInfo, timeout: int = 60):
        """If healthcheck exists, poll until healthy/unhealthy/timeout; else short sleep."""
        try:
            # Check if container has a healthcheck defined
            result = run_command(
                ["docker", "inspect", "-f", "{{json .State.Health}}", container.id],
                f"Checking health config for {container.name}",
                timeout=10,
                check=False,  # Don't fail if no healthcheck
            )
            insp = result.stdout.strip() if result.stdout else ""
            if insp in ("null", "{}", "") or result.returncode != 0:
                time.sleep(2)
                return

            start = time.time()
            while time.time() - start < timeout:
                result = run_command(
                    ["docker", "inspect", "-f", "{{.State.Health.Status}}", container.id],
                    f"Polling health status for {container.name}",
                    timeout=10,
                    check=False,
                )
                status = result.stdout.strip() if result.stdout else ""
                if status == "healthy":
                    logger.debug(
                        f"Container {container.name} is healthy",
                        extra={"container": container.name},
                    )
                    return
                if status == "unhealthy":
                    logger.warning(
                        f"Container {container.name} is unhealthy",
                        extra={"container": container.name},
                    )
                    return
                time.sleep(2)

            logger.warning(
                f"Container {container.name} not healthy after {timeout}s",
                extra={"container": container.name},
            )
        except Exception as e:
            logger.debug(
                f"Health check failed for {container.name}: {e}",
                extra={"container": container.name},
            )
            time.sleep(2)

    def _prepare_staging_dir(self, subdir: str, unit_name: str) -> Path:
        """
        Prepare a clean staging directory for backup operations.

        Creates the staging directory structure and clears any previous content
        to ensure a clean state for each backup. This enables stable paths for
        Kopia snapshots, allowing retention policies to work correctly.

        Args:
            subdir: Subdirectory type ("recipes", "networks", or "configs")
            unit_name: Name of the backup unit

        Returns:
            Path object for the prepared staging directory
        """
        import shutil

        staging_dir = STAGING_BASE_DIR / subdir / unit_name

        # Create staging directory (idempotent)
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Clear any previous content to ensure clean state
        for item in staging_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

        return staging_dir

    def _backup_recipes(self, unit: BackupUnit, backup_id: str, backup_scope: str) -> Optional[str]:
        """Backup compose files and container inspect data (with secret redaction)."""
        import shutil

        try:
            # Prepare clean staging directory with stable path
            staging_dir = self._prepare_staging_dir("recipes", unit.name)

            # Compose files (all from label, including overrides)
            compose_files_saved = []
            compose_dirs_processed = set()

            for compose_file in unit.compose_files:
                if compose_file.exists():
                    # Save with original filename
                    dest = staging_dir / compose_file.name
                    shutil.copy2(compose_file, dest)
                    compose_files_saved.append(compose_file.name)
                    compose_dirs_processed.add(compose_file.parent)

            # Save compose order for restore (critical for override precedence)
            if compose_files_saved:
                import json as _json

                (staging_dir / "compose_order.json").write_text(
                    _json.dumps(compose_files_saved, indent=2)
                )
                logger.info(
                    f"Backed up {len(compose_files_saved)} compose file(s): {', '.join(compose_files_saved)}",
                    extra={"unit_name": unit.name},
                )

            # Save related project files from ALL compose directories
            project_files_dir = staging_dir / "project-files"
            project_files_dir.mkdir(exist_ok=True)

            config_patterns = [
                ".env*",  # Environment files (critical!)
                "*.conf",
                "*.config",  # Config files
                "*.toml",  # TOML configs
            ]

            backed_up_files = []
            for compose_dir in compose_dirs_processed:
                for pattern in config_patterns:
                    for config_file in compose_dir.glob(pattern):
                        # Skip compose files (already saved above)
                        if config_file.is_file() and config_file.name not in compose_files_saved:
                            try:
                                dest = project_files_dir / config_file.name
                                if not dest.exists():  # Avoid duplicates
                                    shutil.copy2(config_file, dest)
                                    backed_up_files.append(config_file.name)
                            except Exception as e:
                                logger.warning(
                                    f"Could not backup config file {config_file.name}: {e}",
                                    extra={"unit_name": unit.name},
                                )

            if backed_up_files:
                logger.info(
                    f"Backed up {len(backed_up_files)} project files: {', '.join(backed_up_files[:5])}{'...' if len(backed_up_files) > 5 else ''}",
                    extra={"unit_name": unit.name},
                )

            # Inspect (redact env secrets)
            import json as _json

            SENSITIVE = (
                "PASS",
                "SECRET",
                "KEY",
                "TOKEN",
                "CREDENTIAL",
                "API",
                "AUTH",
            )
            for c in unit.containers:
                result = run_command(
                    ["docker", "inspect", c.id],
                    f"Inspecting {c.name}",
                    timeout=10,
                )
                data = _json.loads(result.stdout)
                if isinstance(data, list) and data:
                    cfg = data[0].get("Config", {})
                    if cfg and "Env" in cfg and isinstance(cfg["Env"], list):
                        red = []
                        for e in cfg["Env"]:
                            k, _, v = e.partition("=")
                            if any(s in k.upper() for s in SENSITIVE):
                                red.append(f"{k}=***REDACTED***")
                            else:
                                red.append(e)
                        data[0]["Config"]["Env"] = red
                (staging_dir / f"{c.name}_inspect.json").write_text(_json.dumps(data, indent=2))

            # Snapshot with stable path (enables Kopia retention policies)
            logger.debug(
                f"Creating recipe snapshot from stable staging path: {staging_dir}",
                extra={"unit_name": unit.name},
            )
            return self.repo.create_snapshot(
                str(staging_dir),
                tags={
                    "type": "recipe",
                    "unit": unit.name,
                    "backup_id": backup_id,
                    "backup_scope": backup_scope,
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to backup recipes for {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )
            # Note: Keep staging directory on error for debugging
            return None

    def _backup_networks(self, unit: BackupUnit, backup_id: str, backup_scope: str) -> Tuple[Optional[str], int]:
        """
        Backup custom Docker networks used by this unit.

        Returns:
            Tuple of (snapshot_id, network_count)
        """
        import json as _json

        try:
            # Collect all networks from unit's containers
            networks_to_backup = set()
            default_networks = {"bridge", "host", "none"}

            for container in unit.containers:
                inspect_data = container.inspect_data
                if not inspect_data:
                    continue

                container_networks = inspect_data.get("NetworkSettings", {}).get("Networks", {})

                for net_name in container_networks.keys():
                    if net_name not in default_networks:
                        networks_to_backup.add(net_name)

            if not networks_to_backup:
                logger.debug(
                    f"No custom networks found for unit {unit.name}", extra={"unit_name": unit.name}
                )
                return None, 0

            logger.info(
                f"Backing up {len(networks_to_backup)} custom networks: {', '.join(sorted(networks_to_backup))}",
                extra={"unit_name": unit.name},
            )

            # Export network configurations
            network_configs = []
            for net_name in networks_to_backup:
                try:
                    result = run_command(
                        ["docker", "network", "inspect", net_name],
                        f"Inspecting network {net_name}",
                        timeout=10,
                    )
                    net_data = _json.loads(result.stdout)
                    if isinstance(net_data, list) and net_data:
                        network_configs.append(net_data[0])
                except SubprocessError as e:
                    logger.warning(
                        f"Failed to inspect network {net_name}: {e.stderr}",
                        extra={"unit_name": unit.name, "network": net_name},
                    )
                except Exception as e:
                    logger.warning(
                        f"Error inspecting network {net_name}: {e}",
                        extra={"unit_name": unit.name, "network": net_name},
                    )

            if not network_configs:
                logger.warning(
                    f"Could not retrieve any network configurations for unit {unit.name}",
                    extra={"unit_name": unit.name},
                )
                return None, 0

            # Prepare clean staging directory with stable path
            staging_dir = self._prepare_staging_dir("networks", unit.name)

            # Save network configurations
            networks_file = staging_dir / "networks.json"
            networks_file.write_text(_json.dumps(network_configs, indent=2))

            # Create metadata file with additional info
            metadata_file = staging_dir / "networks_metadata.json"
            metadata = {
                "unit_name": unit.name,
                "backup_timestamp": datetime.now().isoformat(),
                "network_count": len(network_configs),
                "network_names": [nc.get("Name") for nc in network_configs],
            }
            metadata_file.write_text(_json.dumps(metadata, indent=2))

            # Create snapshot with stable path (enables Kopia retention policies)
            logger.debug(
                f"Creating networks snapshot from stable staging path: {staging_dir}",
                extra={"unit_name": unit.name},
            )
            snapshot_id = self.repo.create_snapshot(
                str(staging_dir),
                tags={
                    "type": "networks",
                    "unit": unit.name,
                    "backup_id": backup_id,
                    "backup_scope": backup_scope,
                    "timestamp": datetime.now().isoformat(),
                    "network_count": str(len(network_configs)),
                },
            )

            logger.info(
                f"Successfully backed up {len(network_configs)} networks for {unit.name}",
                extra={"unit_name": unit.name, "network_count": len(network_configs)},
            )

            return snapshot_id, len(network_configs)

        except Exception as e:
            logger.error(
                f"Failed to backup networks for {unit.name}: {e}", extra={"unit_name": unit.name}
            )
            # Note: Keep staging directory on error for debugging
            return None, 0

    def _backup_docker_config(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """
        Backup Docker daemon configuration for disaster recovery.

        Only backs up known configuration files, not entire /etc/docker directory.
        Errors are non-fatal - logs warning and returns None.

        Args:
            unit: Backup unit context
            backup_id: Unique backup run identifier
            backup_scope: Backup scope (always "full" when this is called)

        Returns:
            Snapshot ID if successful, None otherwise
        """
        import shutil

        try:
            staging_dir = self._prepare_staging_dir(DOCKER_CONFIG_BACKUP_DIR, unit.name)
            files_backed_up = []

            # 1. Main Docker daemon configuration
            daemon_json = Path("/etc/docker/daemon.json")
            if daemon_json.exists() and daemon_json.is_file():
                try:
                    shutil.copy2(daemon_json, staging_dir / "daemon.json")
                    files_backed_up.append("daemon.json")
                except PermissionError as e:
                    logger.warning(f"Cannot read {daemon_json}: {e}")

            # 2. systemd service overrides
            systemd_overrides = Path("/etc/systemd/system/docker.service.d")
            if systemd_overrides.exists() and systemd_overrides.is_dir():
                try:
                    override_dir = staging_dir / "docker.service.d"
                    shutil.copytree(systemd_overrides, override_dir)
                    files_backed_up.append("docker.service.d/")
                except PermissionError as e:
                    logger.warning(f"Cannot read {systemd_overrides}: {e}")

            if not files_backed_up:
                logger.info("No Docker config files found (normal on default installations)")
                return None

            logger.info(f"Backing up Docker daemon config: {', '.join(files_backed_up)}")

            # Create snapshot with backup_scope tag
            return self.repo.create_snapshot(
                str(staging_dir),
                tags={
                    "type": "docker_config",
                    "unit": unit.name,
                    "backup_id": backup_id,
                    "backup_scope": backup_scope,
                    "timestamp": datetime.now().isoformat(),
                    "files": ",".join(files_backed_up),
                },
            )

        except Exception as e:
            logger.warning(f"Docker config backup failed (non-fatal): {e}", exc_info=True)
            return None

    def _backup_volume(self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str) -> Optional[str]:
        """Backup a single volume using the configured backup format.

        Dispatcher that routes to the appropriate backup method based on
        BACKUP_FORMAT_DEFAULT setting.

        Args:
            volume: Volume to backup
            unit: Parent backup unit
            backup_id: Unique ID for this backup run
            backup_scope: Backup scope (minimal/standard/full)

        Returns:
            Snapshot ID if successful, None otherwise
        """
        backup_format = BACKUP_FORMAT_DEFAULT

        if backup_format == BACKUP_FORMAT_DIRECT:
            return self._backup_volume_direct(volume, unit, backup_id, backup_scope)
        else:
            return self._backup_volume_tar(volume, unit, backup_id, backup_scope)

    def _backup_volume_direct(
        self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup a single volume via direct Kopia snapshot (v5.0+).

        This method creates a direct Kopia snapshot of the volume directory,
        enabling block-level deduplication. Only changed blocks are stored
        in subsequent backups.

        Args:
            volume: Volume to backup
            unit: Parent backup unit
            backup_id: Unique ID for this backup run
            backup_scope: Backup scope (minimal/standard/full)

        Returns:
            Snapshot ID if successful, None otherwise
        """
        try:
            volume_path = Path(volume.mountpoint)

            # Verify volume path exists and is accessible
            if not volume_path.exists():
                logger.error(
                    f"Volume path does not exist: {volume_path}",
                    extra={"unit_name": unit.name, "volume": volume.name},
                )
                return None

            if not volume_path.is_dir():
                logger.error(
                    f"Volume path is not a directory: {volume_path}",
                    extra={"unit_name": unit.name, "volume": volume.name},
                )
                return None

            logger.debug(
                f"Backing up volume (direct): {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "path": str(volume_path),
                    "size_bytes": getattr(volume, "size_bytes", 0),
                    "backup_format": BACKUP_FORMAT_DIRECT,
                },
            )

            # Create direct Kopia snapshot of volume directory
            # Pass exclude patterns from config (same as TAR mode)
            snap_id = self.repo.create_snapshot(
                str(volume_path),
                tags={
                    "type": "volume",
                    "unit": unit.name,
                    "volume": volume.name,
                    "backup_id": backup_id,
                    "backup_scope": backup_scope,
                    "timestamp": datetime.now().isoformat(),
                    "size_bytes": str(getattr(volume, "size_bytes", 0) or "0"),
                    "backup_format": BACKUP_FORMAT_DIRECT,
                },
                exclude_patterns=self.exclude_patterns if self.exclude_patterns else None,
            )

            logger.debug(
                f"Created direct snapshot for volume: {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "snapshot_id": snap_id,
                },
            )

            return snap_id

        except Exception as e:
            logger.error(
                f"Failed to backup volume {volume.name} (direct): {e}",
                extra={"unit_name": unit.name, "volume": volume.name},
            )
            return None

    def _backup_volume_tar(
        self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup a single volume via tar stream → Kopia (legacy).

        DEPRECATED: This method uses tar streams which prevent Kopia's
        block-level deduplication. Use _backup_volume_direct() instead.

        Note: stderr is written to a temporary file instead of a pipe to prevent
        deadlock when tar produces large amounts of warnings (e.g., "file changed
        as we read it" on thousands of files). The OS pipe buffer (typically 64KB)
        would fill up, causing tar to block while Python waits for tar to finish.
        """
        import tempfile

        try:
            logger.debug(
                f"Backing up volume (tar): {volume.name}",
                extra={
                    "unit_name": unit.name,
                    "volume": volume.name,
                    "size_bytes": getattr(volume, "size_bytes", 0),
                    "backup_format": BACKUP_FORMAT_TAR,
                },
            )

            tar_cmd = [
                "tar",
                "-cf",
                "-",
                "--numeric-owner",
                "--xattrs",
                "--acls",
                "--one-file-system",
                "--mtime=@0",
                "--clamp-mtime",
                "--sort=name",
            ]
            for pattern in self.exclude_patterns:
                tar_cmd.extend(["--exclude", pattern])
            tar_cmd.extend(["-C", volume.mountpoint, "."])

            # Use a temporary file for stderr to avoid deadlock.
            # If tar produces >64KB of warnings, a pipe would fill up and block.
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                tar_process = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=stderr_file)

                snap_id = self.repo.create_snapshot_from_stdin(
                    tar_process.stdout,
                    dest_virtual_path=f"{VOLUME_BACKUP_DIR}/{unit.name}/{volume.name}",
                    tags={
                        "type": "volume",
                        "unit": unit.name,
                        "volume": volume.name,
                        "backup_id": backup_id,
                        "backup_scope": backup_scope,
                        "timestamp": datetime.now().isoformat(),
                        "size_bytes": str(getattr(volume, "size_bytes", 0) or "0"),
                        "backup_format": BACKUP_FORMAT_TAR,
                    },
                )

                tar_process.wait()
                if tar_process.stdout:
                    tar_process.stdout.close()

                if tar_process.returncode != 0:
                    # Read stderr from temp file (seek to beginning first)
                    stderr_file.seek(0)
                    stderr_content = stderr_file.read().decode(errors="replace")
                    # Truncate very long error output for logging
                    if len(stderr_content) > 4096:
                        stderr_content = stderr_content[:4096] + "\n... (truncated)"
                    logger.error(
                        f"Tar failed for volume {volume.name}: {stderr_content}",
                        extra={"unit_name": unit.name, "volume": volume.name},
                    )
                    return None

            return snap_id
        except Exception as e:
            logger.error(
                f"Failed to backup volume {volume.name} (tar): {e}",
                extra={"unit_name": unit.name, "volume": volume.name},
            )
            return None

    def _save_metadata(self, metadata: BackupMetadata):
        """Persist backup metadata JSON."""
        metadata_dir = self.config.backup_base_path / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{metadata.unit_name}_{metadata.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        with open(metadata_dir / filename, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)
        logger.debug(
            f"Saved metadata to {metadata_dir / filename}",
            extra={"unit_name": metadata.unit_name},
        )

    def _ensure_policies(self, unit: BackupUnit):
        """Set Kopia retention policies for this unit (volumes + recipes + networks).

        Note: In Direct Mode, policies are applied to actual volume mountpoints
        (e.g., /var/lib/docker/volumes/...) to match snapshot paths.
        In TAR Mode, policies are applied to virtual paths (e.g., volumes/unit_name).
        """
        # Static targets: recipes and networks (same path in both modes)
        static_targets = [
            f"{RECIPE_BACKUP_DIR}/{unit.name}",
            f"{NETWORK_BACKUP_DIR}/{unit.name}",
        ]

        # Apply policies to static targets
        for target in static_targets:
            try:
                self.policy_manager.set_retention_for_target(
                    target,
                    keep_latest=self.config.getint("retention", "latest", 10),
                    keep_hourly=self.config.getint("retention", "hourly", 0),
                    keep_daily=self.config.getint("retention", "daily", 7),
                    keep_weekly=self.config.getint("retention", "weekly", 4),
                    keep_monthly=self.config.getint("retention", "monthly", 12),
                    keep_annual=self.config.getint("retention", "annual", 3),
                )
                logger.debug(
                    f"Applied Kopia retention policy on {target}",
                    extra={"unit_name": unit.name, "target": target},
                )
            except Exception as e:
                logger.warning(
                    f"Could not apply Kopia policy on {target}: {e}",
                    extra={"unit_name": unit.name, "target": target},
                )

        # Volume targets depend on backup format
        if BACKUP_FORMAT_DEFAULT == BACKUP_FORMAT_DIRECT:
            # Direct Mode: apply policies to actual volume mountpoints
            for volume in unit.volumes:
                try:
                    self.policy_manager.set_retention_for_target(
                        volume.mountpoint,
                        keep_latest=self.config.getint("retention", "latest", 10),
                        keep_hourly=self.config.getint("retention", "hourly", 0),
                        keep_daily=self.config.getint("retention", "daily", 7),
                        keep_weekly=self.config.getint("retention", "weekly", 4),
                        keep_monthly=self.config.getint("retention", "monthly", 12),
                        keep_annual=self.config.getint("retention", "annual", 3),
                    )
                    logger.debug(
                        f"Applied Kopia retention policy on volume {volume.name} "
                        f"at {volume.mountpoint}",
                        extra={
                            "unit_name": unit.name,
                            "volume": volume.name,
                            "target": volume.mountpoint,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not apply Kopia policy on volume {volume.name} "
                        f"at {volume.mountpoint}: {e}",
                        extra={
                            "unit_name": unit.name,
                            "volume": volume.name,
                            "target": volume.mountpoint,
                        },
                    )
        else:
            # TAR Mode: apply policy to virtual path (legacy behavior)
            target = f"{VOLUME_BACKUP_DIR}/{unit.name}"
            try:
                self.policy_manager.set_retention_for_target(
                    target,
                    keep_latest=self.config.getint("retention", "latest", 10),
                    keep_hourly=self.config.getint("retention", "hourly", 0),
                    keep_daily=self.config.getint("retention", "daily", 7),
                    keep_weekly=self.config.getint("retention", "weekly", 4),
                    keep_monthly=self.config.getint("retention", "monthly", 12),
                    keep_annual=self.config.getint("retention", "annual", 3),
                )
                logger.debug(
                    f"Applied Kopia retention policy on {target}",
                    extra={"unit_name": unit.name, "target": target},
                )
            except Exception as e:
                logger.warning(
                    f"Could not apply Kopia policy on {target}: {e}",
                    extra={"unit_name": unit.name, "target": target},
                )
