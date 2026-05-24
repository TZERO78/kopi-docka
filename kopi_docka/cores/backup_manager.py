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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError
from ..types import BackupUnit, BackupSource, ContainerInfo, BackupMetadata, BackupErrorDetail
from ..helpers.config import Config
from ..cores.repository_manager import KopiaRepository, KopiaCommandError
from ..cores.kopia_policy_manager import KopiaPolicyManager
from ..cores.hooks_manager import HooksManager
from ..cores.notification_manager import NotificationManager, BackupStats
from ..cores.safe_exit_manager import SafeExitManager, ServiceContinuityHandler
from ..cores.backup_volume_handler import BackupVolumeHandler
from ..backends.base import BackendUnreachableError
from ..helpers.constants import (
    CONTAINER_STOP_TIMEOUT,
    CONTAINER_START_TIMEOUT,
    DOCKER_CONFIG_BACKUP_DIR,
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
    BACKUP_SCOPE_FULL,
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

        self.stop_timeout = self.config.getint("backup", "stop_timeout", CONTAINER_STOP_TIMEOUT)
        self.start_timeout = self.config.getint("backup", "start_timeout", CONTAINER_START_TIMEOUT)

        self.exclude_patterns = self.config.getlist("backup", "exclude_patterns", [])
        self.volume_handler = BackupVolumeHandler(self.repo, self.exclude_patterns)

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

        _preflight_error: Optional[BackendUnreachableError] = None
        _containers_stopped = False

        metadata.docker_config_backed_up = False

        try:
            # 0) Pre-backup hook
            logger.info("Executing pre-backup hook...", extra={"unit_name": unit.name})
            if not self.hooks_manager.execute_pre_backup(unit.name):
                logger.warning(
                    "Pre-backup hook failed, aborting backup", extra={"unit_name": unit.name}
                )
                metadata.errors.append("Pre-backup hook failed")
                metadata.success = False
                return metadata

            # Pre-flight is done once per backup run (in _run_backup), not per unit (Plan 0026).

            # 1) Discovery — collect every BackupSource BEFORE stopping containers.
            #    Plan 0028 Phase 3: staging dirs + docker inspect happen while
            #    containers are running (Inspect needs them alive); the snapshot
            #    loop below runs after the stop and only touches static paths.
            logger.info("Collecting backup sources...", extra={"unit_name": unit.name})
            sources = self._collect_backup_sources(unit, backup_id, backup_scope)

            # 2) Stop containers
            logger.info(
                f"Stopping {len(unit.containers)} containers...",
                extra={"unit_name": unit.name},
            )
            self._stop_containers(unit.containers, service_handler)
            _containers_stopped = True

            # 3) Snapshot loop — sequential per Plan 0028.
            #    repo.create_snapshots() returns one ID per source in order;
            #    empty string marks per-source failure (already logged).
            from ..helpers.constants import BACKUP_FORMAT_DEFAULT, BACKUP_FORMAT_DIRECT

            snapshot_ids = self.repo.create_snapshots(sources)
            for src, snap_id in zip(sources, snapshot_ids):
                if not snap_id:
                    label = src.tags.get("volume") or src.kind
                    metadata.errors.append(f"Failed to snapshot {src.kind}: {label}")
                    continue
                metadata.kopia_snapshot_ids.append(snap_id)
                if src.kind == "volume":
                    metadata.volumes_backed_up += 1
                elif src.kind == "network":
                    metadata.networks_backed_up = int(src.tags.get("network_count", "0"))
                elif src.kind == "docker_config":
                    metadata.docker_config_backed_up = True

            # 4) TAR-mode volume fallback (legacy).
            #    Direct mode's volumes are already covered by _collect_volume_sources
            #    above. TAR mode pipes through stdin and can't be expressed as a
            #    BackupSource, so it stays on the legacy per-volume call. No
            #    parallelism — sequential by Plan 0028 design.
            if BACKUP_FORMAT_DEFAULT != BACKUP_FORMAT_DIRECT:
                for volume in unit.volumes:
                    try:
                        snap_id = self.volume_handler.backup_volume(
                            volume, unit, backup_id, backup_scope
                        )
                    except Exception as e:
                        metadata.errors.append(
                            f"Error backing up volume {volume.name}: {e}"
                        )
                        logger.error(
                            f"Exception during TAR-mode volume backup {volume.name}: {e}",
                            extra={"unit_name": unit.name},
                        )
                        continue
                    if snap_id:
                        metadata.kopia_snapshot_ids.append(snap_id)
                        metadata.volumes_backed_up += 1
                    else:
                        metadata.errors.append(f"Failed to backup volume: {volume.name}")

        except BackendUnreachableError as e:
            _preflight_error = e
            metadata.errors.append(f"Pre-flight check failed: {e}")
            metadata.success = False
            logger.error(
                f"Pre-flight check failed for unit {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )

        except KopiaCommandError as e:
            metadata.error_details.append(
                BackupErrorDetail(
                    phase=e.phase or "kopia",
                    message=str(e),
                    exit_code=e.returncode,
                    stderr_tail=e.stderr_tail,
                )
            )
            metadata.errors.append(f"Backup failed: {e}")
            logger.error(f"Kopia command error during backup: {e}", extra={"unit_name": unit.name})

        except Exception as e:
            metadata.errors.append(f"Backup failed: {str(e)}")
            logger.error(f"Critical error during backup: {e}", extra={"unit_name": unit.name})

        finally:
            safe_exit.unregister_handler(service_handler)

            if _containers_stopped:
                # 4) Restart containers only if they were stopped
                logger.info(
                    f"Starting {len(unit.containers)} containers...",
                    extra={"unit_name": unit.name},
                )
                self._start_containers(unit.containers, service_handler)

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
            if _preflight_error is not None:
                self.notification_manager.send_connectivity_alert(
                    unit_name=unit.name,
                    backend=_preflight_error.backend,
                    reason=_preflight_error.reason,
                )
            elif metadata.success:
                self.notification_manager.send_success(stats)
            else:
                self.notification_manager.send_failure(stats)
        except Exception as e:
            logger.debug(f"Notification failed (non-blocking): {e}")

        # Post-run missed-backup check (fire-and-forget)
        if _preflight_error is None:
            self._check_missed_backups_post_run(unit.name, success=metadata.success)

        return metadata

    def _check_missed_backups_post_run(self, completed_unit: str, success: bool) -> None:
        """After a backup run, check all units for missed backups and alert."""
        try:
            from ..cores.missed_backup_checker import MissedBackupChecker
            from ..helpers.metadata_reader import MetadataReader

            metadata_dir = self.config.backup_base_path / "metadata"
            reader = MetadataReader(metadata_dir)
            checker = MissedBackupChecker(self.config, reader)

            # Reset alert suppression for this unit if it just succeeded
            if success:
                checker.reset_unit(completed_unit)

            missed = checker.check_all_units()
            to_alert = checker.get_units_to_alert(missed)

            if to_alert:
                checker.mark_alerted(to_alert)
                self.notification_manager.send_missed_backup_alert(to_alert)
                logger.warning(
                    f"Missed-backup alert sent for {len(to_alert)} unit(s): "
                    f"{[u.name for u in to_alert]}"
                )
        except Exception as e:
            logger.debug(f"Missed-backup check failed (non-blocking): {e}")

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
                    timeout=self.start_timeout + 10,  # config timeout + safety margin
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

    def _collect_recipe_sources(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> List[BackupSource]:
        """Stage compose files + redacted container inspects and return one
        BackupSource pointing at the staging dir.

        Plan 0028 Phase 2 split: this does the *discovery* (filesystem work,
        secret redaction, tag construction) and stops at the boundary before
        ``kopia snapshot create``. Returns an empty list if staging fails so
        the caller doesn't try to snapshot a half-built directory.
        """
        import shutil
        import json as _json

        try:
            staging_dir = self._prepare_staging_dir("recipes", unit.name)

            compose_files_saved = []
            compose_dirs_processed = set()

            for compose_file in unit.compose_files:
                if compose_file.exists():
                    dest = staging_dir / compose_file.name
                    shutil.copy2(compose_file, dest)
                    compose_files_saved.append(compose_file.name)
                    compose_dirs_processed.add(compose_file.parent)

            if compose_files_saved:
                (staging_dir / "compose_order.json").write_text(
                    _json.dumps(compose_files_saved, indent=2)
                )
                logger.info(
                    f"Backed up {len(compose_files_saved)} compose file(s): {', '.join(compose_files_saved)}",
                    extra={"unit_name": unit.name},
                )

            project_files_dir = staging_dir / "project-files"
            project_files_dir.mkdir(exist_ok=True)

            config_patterns = [".env*", "*.conf", "*.config", "*.toml"]

            backed_up_files = []
            for compose_dir in compose_dirs_processed:
                for pattern in config_patterns:
                    for config_file in compose_dir.glob(pattern):
                        if config_file.is_file() and config_file.name not in compose_files_saved:
                            try:
                                dest = project_files_dir / config_file.name
                                if not dest.exists():
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

            SENSITIVE = (
                "PASS", "SECRET", "KEY", "TOKEN",
                "CREDENTIAL", "API", "AUTH",
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

            return [
                BackupSource(
                    path=str(staging_dir),
                    kind="recipe",
                    tags={
                        "type": "recipe",
                        "unit": unit.name,
                        "backup_id": backup_id,
                        "backup_scope": backup_scope,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            ]
        except Exception as e:
            logger.error(
                f"Failed to collect recipe source for {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )
            return []

    def _backup_recipes(self, unit: BackupUnit, backup_id: str, backup_scope: str) -> Optional[str]:
        """Backup compose files and container inspect data (with secret redaction)."""
        sources = self._collect_recipe_sources(unit, backup_id, backup_scope)
        if not sources:
            return None
        src = sources[0]
        logger.debug(
            f"Creating recipe snapshot from stable staging path: {src.path}",
            extra={"unit_name": unit.name},
        )
        try:
            return self.repo.create_snapshot(src.path, tags=src.tags)
        except Exception as e:
            logger.error(
                f"Failed to snapshot recipes for {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )
            return None

    def _collect_network_sources(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> List[BackupSource]:
        """Stage custom Docker network configurations and return a single
        BackupSource. Returns ``[]`` when the unit uses no custom networks
        (default Docker networks bridge/host/none are intentionally ignored).
        """
        import json as _json

        try:
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
                    f"No custom networks found for unit {unit.name}",
                    extra={"unit_name": unit.name},
                )
                return []

            logger.info(
                f"Backing up {len(networks_to_backup)} custom networks: {', '.join(sorted(networks_to_backup))}",
                extra={"unit_name": unit.name},
            )

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
                return []

            staging_dir = self._prepare_staging_dir("networks", unit.name)
            (staging_dir / "networks.json").write_text(_json.dumps(network_configs, indent=2))

            metadata = {
                "unit_name": unit.name,
                "backup_timestamp": datetime.now(timezone.utc).isoformat(),
                "network_count": len(network_configs),
                "network_names": [nc.get("Name") for nc in network_configs],
            }
            (staging_dir / "networks_metadata.json").write_text(_json.dumps(metadata, indent=2))

            return [
                BackupSource(
                    path=str(staging_dir),
                    kind="network",
                    tags={
                        "type": "networks",
                        "unit": unit.name,
                        "backup_id": backup_id,
                        "backup_scope": backup_scope,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "network_count": str(len(network_configs)),
                    },
                )
            ]
        except Exception as e:
            logger.error(
                f"Failed to collect network sources for {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )
            return []

    def _backup_networks(self, unit: BackupUnit, backup_id: str, backup_scope: str) -> Tuple[Optional[str], int]:
        """Backup custom Docker networks used by this unit.

        Returns:
            Tuple of (snapshot_id, network_count). The network count is parsed
            back out of the BackupSource tags so callers don't have to know
            whether the helper short-circuited or staged a snapshot.
        """
        sources = self._collect_network_sources(unit, backup_id, backup_scope)
        if not sources:
            return None, 0

        src = sources[0]
        network_count = int(src.tags.get("network_count", "0"))
        logger.debug(
            f"Creating networks snapshot from stable staging path: {src.path}",
            extra={"unit_name": unit.name},
        )
        try:
            snapshot_id = self.repo.create_snapshot(src.path, tags=src.tags)
        except Exception as e:
            logger.error(
                f"Failed to snapshot networks for {unit.name}: {e}",
                extra={"unit_name": unit.name},
            )
            return None, 0

        logger.info(
            f"Successfully backed up {network_count} networks for {unit.name}",
            extra={"unit_name": unit.name, "network_count": network_count},
        )
        return snapshot_id, network_count

    def _collect_docker_config_sources(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> List[BackupSource]:
        """Stage Docker daemon config files (daemon.json + systemd overrides)
        and return at most one BackupSource. Errors are non-fatal: the helper
        logs and returns ``[]`` rather than raising — Docker config is a
        nice-to-have for DR, not a hard requirement.
        """
        import shutil

        try:
            staging_dir = self._prepare_staging_dir(DOCKER_CONFIG_BACKUP_DIR, unit.name)
            files_backed_up = []

            daemon_json = Path("/etc/docker/daemon.json")
            if daemon_json.exists() and daemon_json.is_file():
                try:
                    shutil.copy2(daemon_json, staging_dir / "daemon.json")
                    files_backed_up.append("daemon.json")
                except PermissionError as e:
                    logger.warning(f"Cannot read {daemon_json}: {e}")

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
                return []

            logger.info(f"Backing up Docker daemon config: {', '.join(files_backed_up)}")
            return [
                BackupSource(
                    path=str(staging_dir),
                    kind="docker_config",
                    tags={
                        "type": "docker_config",
                        "unit": unit.name,
                        "backup_id": backup_id,
                        "backup_scope": backup_scope,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "files": ",".join(files_backed_up),
                    },
                )
            ]
        except Exception as e:
            logger.warning(f"Docker config collection failed (non-fatal): {e}", exc_info=True)
            return []

    def _backup_docker_config(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> Optional[str]:
        """Backup Docker daemon configuration for disaster recovery.

        Only backs up known configuration files, not entire /etc/docker directory.
        Errors are non-fatal — logs warning and returns None.
        """
        sources = self._collect_docker_config_sources(unit, backup_id, backup_scope)
        if not sources:
            return None
        src = sources[0]
        try:
            return self.repo.create_snapshot(src.path, tags=src.tags)
        except Exception as e:
            logger.warning(f"Docker config snapshot failed (non-fatal): {e}", exc_info=True)
            return None

    def _collect_volume_sources(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> List[BackupSource]:
        """Return one BackupSource per Direct-mode volume in the unit.

        Plan 0028 Phase 2: only the Direct-mode path emits BackupSources here.
        TAR-mode still goes through the legacy ``BackupVolumeHandler.backup_volume_tar``
        because it pipes through stdin and has no usable filesystem path —
        Phase 3 will revisit that. For now ``backup_unit()`` still routes
        volumes through ``volume_handler.backup_volume()`` and this helper
        exists so callers can introspect the planned snapshot list ahead of
        time.
        """
        from ..helpers.constants import BACKUP_FORMAT_DEFAULT, BACKUP_FORMAT_DIRECT

        if BACKUP_FORMAT_DEFAULT != BACKUP_FORMAT_DIRECT:
            return []

        sources: List[BackupSource] = []
        for volume in unit.volumes:
            sources.append(
                BackupSource(
                    path=volume.mountpoint,
                    kind="volume",
                    tags={
                        "type": "volume",
                        "unit": unit.name,
                        "volume": volume.name,
                        "backup_id": backup_id,
                        "backup_scope": backup_scope,
                        "backup_format": BACKUP_FORMAT_DIRECT,
                        "size_bytes": str(getattr(volume, "size_bytes", 0) or "0"),
                    },
                )
            )
        return sources

    def _collect_backup_sources(
        self, unit: BackupUnit, backup_id: str, backup_scope: str
    ) -> List[BackupSource]:
        """Aggregate every BackupSource ``backup_unit()`` would snapshot.

        Returns sources in the order the snapshot loop will produce them:
        recipes → networks → docker_config → volumes. Side-effects (staging
        dirs being written) match what the corresponding ``_backup_*`` helper
        would do.

        Plan 0028 Phase 2 introduces this as the *future* single entry point.
        ``backup_unit()`` still calls the individual ``_backup_*`` helpers,
        so the aggregate stays observation-only until Phase 3 wires
        ``repo.create_snapshots(sources)`` to it. Tests may use this method
        today to verify discovery in isolation.
        """
        sources: List[BackupSource] = []
        if backup_scope != BACKUP_SCOPE_MINIMAL:
            sources.extend(self._collect_recipe_sources(unit, backup_id, backup_scope))
        if backup_scope in (BACKUP_SCOPE_STANDARD, BACKUP_SCOPE_FULL):
            sources.extend(self._collect_network_sources(unit, backup_id, backup_scope))
        if backup_scope == BACKUP_SCOPE_FULL:
            sources.extend(self._collect_docker_config_sources(unit, backup_id, backup_scope))
        sources.extend(self._collect_volume_sources(unit, backup_id, backup_scope))
        return sources

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

