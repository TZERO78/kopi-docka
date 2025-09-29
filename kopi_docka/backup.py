"""
Backup management module for Kopi-Docka.

This module handles the actual backup operations, including stopping containers,
backing up volumes and databases, and restarting containers.
"""

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import List, Optional, Dict, Any

from .logging import get_logger, log_manager
from .types import BackupUnit, ContainerInfo, VolumeInfo, BackupMetadata
from .config import Config
from .repository import KopiaRepository
from .backup_db import DatabaseBackupManager
from .constants import (
    CONTAINER_STOP_TIMEOUT,
    CONTAINER_START_TIMEOUT,
    RECIPE_BACKUP_DIR,
    VOLUME_BACKUP_DIR,
    DATABASE_BACKUP_DIR
)


logger = get_logger(__name__)


class BackupManager:
    """
    Manages backup operations for Docker backup units.
    
    This class orchestrates the backup process, including stopping containers,
    backing up data, and restarting containers.
    """
    
    def __init__(self, config: Config):
        """
        Initialize backup manager.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.repo = KopiaRepository(config)
        self.db_manager = DatabaseBackupManager()
        self.max_workers = config.parallel_workers
        
        # Timeouts aus Config (Fallback auf Konstanten)
        self.stop_timeout = self.config.getint('backup', 'stop_timeout', CONTAINER_STOP_TIMEOUT)
        self.start_timeout = self.config.getint('backup', 'start_timeout', CONTAINER_START_TIMEOUT)
        
        # Excludes einmal vorbereiten
        self.exclude_patterns = self.config.getlist('backup', 'exclude_patterns', [])
    
    def backup_unit(self, unit: BackupUnit, update_recovery_bundle: bool = None) -> BackupMetadata:
        """
        Perform complete backup of a backup unit.
        
        This implements the sequential "Cold Backup" strategy:
        1. Stop containers
        2. Backup recipes (compose files, inspect data)
        3. Backup volumes
        4. Backup databases
        5. Start containers
        6. Update disaster recovery bundle (if enabled)
        
        Args:
            unit: Backup unit to backup
            update_recovery_bundle: Override config setting for recovery bundle update
            
        Returns:
            Backup metadata with results
        """
        logger.info(f"Starting backup of unit: {unit.name}", 
                   extra={'unit_name': unit.name})
        start_time = time.time()
        backup_id = uuid4().hex
        started_iso = datetime.utcnow().isoformat(timespec="seconds")
        metadata = BackupMetadata(
            unit_name=unit.name,
            timestamp=datetime.now(),
            duration_seconds=0
        )
        
        try:
            # (optional) Retention-Policy für diese Unit an Kopia setzen
            self._ensure_policies(unit)
            
            # Step 1: Stop containers
            logger.info(f"Stopping {len(unit.containers)} containers...", 
                       extra={'unit_name': unit.name})
            self._stop_containers(unit.containers)
            
            # Step 2: Backup recipes
            logger.info("Backing up recipes...", 
                       extra={'unit_name': unit.name})
            recipe_snapshot = self._backup_recipes(unit, backup_id, started_iso)
            if recipe_snapshot:
                metadata.kopia_snapshot_ids.append(recipe_snapshot)
            
            # Step 3 & 4: Backup volumes and databases in parallel
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                # Submit volume backup tasks
                for volume in unit.volumes:
                    future = executor.submit(self._backup_volume, volume, unit, backup_id, started_iso)
                    futures.append(('volume', volume.name, future))
                
                # Submit database backup tasks if enabled
                if self.config.getboolean('backup', 'database_backup'):
                    for container in unit.get_database_containers():
                        future = executor.submit(self._backup_database, container, unit, backup_id, started_iso)
                        futures.append(('database', container.name, future))
                
                # Wait for all backups to complete
                task_timeout = max(0, self.config.getint('backup', 'task_timeout', 0))
                for backup_type, name, future in futures:
                    try:
                        snapshot_id = future.result(timeout=task_timeout or None)
                        if snapshot_id:
                            metadata.kopia_snapshot_ids.append(snapshot_id)
                            # Zähler für Statistik pflegen
                            if backup_type == 'volume':
                                metadata.volumes_backed_up += 1
                            elif backup_type == 'database':
                                metadata.databases_backed_up += 1
                            logger.debug(f"Completed {backup_type} backup: {name}",
                                       extra={'unit_name': unit.name, 'backup_type': backup_type})
                        else:
                            metadata.errors.append(f"Failed to backup {backup_type}: {name}")
                            logger.warning(f"No snapshot created for {backup_type}: {name}",
                                         extra={'unit_name': unit.name, 'backup_type': backup_type})
                    except Exception as e:
                        metadata.errors.append(f"Error backing up {backup_type} {name}: {str(e)}")
                        logger.error(f"Exception during {backup_type} backup {name}: {e}",
                                   extra={'unit_name': unit.name, 'backup_type': backup_type})
            
        except Exception as e:
            metadata.errors.append(f"Backup failed: {str(e)}")
            logger.error(f"Critical error during backup: {e}",
                        extra={'unit_name': unit.name})
        
        finally:
            # Always try to restart containers
            logger.info(f"Starting {len(unit.containers)} containers...",
                       extra={'unit_name': unit.name})
            self._start_containers(unit.containers)
        
        # Calculate duration
        metadata.duration_seconds = time.time() - start_time
        
        # Success ableiten und speichern
        metadata.success = (len(metadata.errors) == 0)
        self._save_metadata(metadata)
        
        # Update disaster recovery bundle if configured
        should_update_bundle = update_recovery_bundle
        if should_update_bundle is None:
            # Konsistent zur INI-Vorlage
            should_update_bundle = self.config.getboolean('backup', 'update_recovery_bundle', False)
        
        if should_update_bundle:
            logger.info("Updating disaster recovery bundle...",
                       extra={'operation': 'dr_bundle'})
            try:
                from .disaster_recovery import DisasterRecoveryManager
                dr_manager = DisasterRecoveryManager(self.config)
                dr_manager.create_recovery_bundle()
            except Exception as e:
                logger.error(f"Failed to update disaster recovery bundle: {e}",
                           extra={'operation': 'dr_bundle'})
        
        # Log final result
        if metadata.errors:
            logger.warning(f"Backup of {unit.name} completed with errors in {metadata.duration_seconds:.2f}s",
                          extra={'unit_name': unit.name, 'duration': metadata.duration_seconds, 
                                'errors': len(metadata.errors)})
        else:
            logger.info(f"Backup of {unit.name} completed successfully in {metadata.duration_seconds:.2f}s",
                       extra={'unit_name': unit.name, 'duration': metadata.duration_seconds})
        
        return metadata
    
    def _stop_containers(self, containers: List[ContainerInfo]):
        """
        Stop containers gracefully.
        
        Args:
            containers: List of containers to stop
        """
        for container in containers:
            if container.is_running:
                try:
                    subprocess.run(
                        ['docker', 'stop', '-t', str(self.stop_timeout), container.id],
                        check=True,
                        capture_output=True
                    )
                    logger.debug(f"Stopped container: {container.name}",
                               extra={'container': container.name})
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to stop container {container.name}: {e.stderr.decode()}",
                               extra={'container': container.name})
    
    def _start_containers(self, containers: List[ContainerInfo]):
        """
        Start containers in original order.
        
        Args:
            containers: List of containers to start
        """
        for container in containers:
            try:
                subprocess.run(
                    ['docker', 'start', container.id],
                    check=True,
                    capture_output=True
                )
                logger.debug(f"Started container: {container.name}",
                           extra={'container': container.name})
                
                # Optional: auf Health warten (falls konfiguriert)
                self._wait_container_healthy(container, timeout=self.start_timeout)
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to start container {container.name}: {e.stderr.decode()}",
                           extra={'container': container.name})
    
    def _wait_container_healthy(self, container: ContainerInfo, timeout: int = 60):
        """
        Warte optional auf Health=healthy, falls Healthcheck vorhanden.
        Fällt zurück auf kurzen Sleep wenn kein Health-Check.
        
        Args:
            container: Container to wait for
            timeout: Maximum wait time in seconds
        """
        try:
            # Prüfe ob Health konfiguriert ist
            insp = subprocess.check_output(
                ['docker', 'inspect', '-f', '{{json .State.Health}}', container.id],
                text=True
            ).strip()
            
            if insp == 'null' or insp == '{}' or not insp:
                # Kein Health-Check definiert - kurzer Sleep
                time.sleep(2)
                return
            
            # Health vorhanden → poll bis healthy/timeout
            start = time.time()
            while time.time() - start < timeout:
                status = subprocess.check_output(
                    ['docker', 'inspect', '-f', '{{.State.Health.Status}}', container.id],
                    text=True
                ).strip()
                
                if status == 'healthy':
                    logger.debug(f"Container {container.name} is healthy",
                               extra={'container': container.name})
                    return
                elif status == 'unhealthy':
                    logger.warning(f"Container {container.name} is unhealthy",
                                 extra={'container': container.name})
                    return
                
                time.sleep(2)
            
            logger.warning(f"Container {container.name} not healthy after {timeout}s",
                         extra={'container': container.name})
        except Exception as e:
            # Fallback ohne harte Fehler
            logger.debug(f"Health check failed for {container.name}: {e}",
                       extra={'container': container.name})
            time.sleep(2)
    
    def _backup_recipes(self, unit: BackupUnit, backup_id: str, started_iso: str) -> Optional[str]:
        """
        Backup compose files and container configurations.
        
        Args:
            unit: Backup unit
            backup_id: Stable identifier for this backup run
            started_iso: UTC start timestamp shared across artifacts
            
        Returns:
            Kopia snapshot ID or None
        """
        try:
            # Create temporary directory for recipes
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)
                
                # Save compose file if available
                if unit.compose_file and unit.compose_file.exists():
                    compose_dest = tmpdir / 'docker-compose.yml'
                    compose_dest.write_text(unit.compose_file.read_text())
                
                # Save container inspect data (mit Secrets-Redaktion)
                import json as _json
                SENSITIVE = ('PASS', 'SECRET', 'KEY', 'TOKEN', 'CREDENTIAL', 'API', 'AUTH')
                
                for container in unit.containers:
                    raw = subprocess.run(
                        ['docker', 'inspect', container.id],
                        capture_output=True, text=True, check=True
                    ).stdout
                    
                    data = _json.loads(raw)
                    if isinstance(data, list) and data:
                        # Redact sensitive environment variables
                        config = data[0].get('Config', {})
                        if config and 'Env' in config:
                            env = config.get('Env', [])
                            if isinstance(env, list):
                                redacted = []
                                for e in env:
                                    k, _, v = e.partition('=')
                                    if any(s in k.upper() for s in SENSITIVE):
                                        redacted.append(f"{k}=***REDACTED***")
                                    else:
                                        redacted.append(e)
                                data[0]['Config']['Env'] = redacted
                    
                    inspect_file = tmpdir / f"{container.name}_inspect.json"
                    inspect_file.write_text(_json.dumps(data, indent=2))
                
                # Create snapshot
                snapshot_id = self.repo.create_snapshot(
                    str(tmpdir),
                    tags={
                        'type': 'recipe',
                        'unit': unit.name,
                        'timestamp': started_iso,
                        'backup_id': backup_id,
                    }
                )
                
                return snapshot_id
                
        except Exception as e:
            logger.error(f"Failed to backup recipes for {unit.name}: {e}",
                        extra={'unit_name': unit.name})
            return None
    
    def _backup_volume(self, volume: VolumeInfo, unit: BackupUnit, backup_id: str, started_iso: str) -> Optional[str]:
        """
        Backup a single volume using tar stream.
        
        Args:
            volume: Volume to backup
            unit: Backup unit this volume belongs to
            backup_id: Stable identifier for this backup run
            started_iso: UTC start timestamp shared across artifacts
            
        Returns:
            Kopia snapshot ID or None
        """
        try:
            logger.debug(f"Backing up volume: {volume.name}",
                        extra={'unit_name': unit.name, 'volume': volume.name, 
                              'size_bytes': getattr(volume, 'size_bytes', 0)})
            
            # Basis tar-Kommando (funktioniert überall)
            base_cmd = ['tar', '-cf', '-', '--numeric-owner']
            
            # Versuche erweiterte Features (GNU tar)
            gnu_features = ['--xattrs', '--acls', '--one-file-system', 
                          '--mtime=@0', '--clamp-mtime', '--sort=name']
            
            # Test ob GNU tar verfügbar ist
            tar_cmd = base_cmd.copy()
            try:
                # Teste mit --version (GNU tar specific)
                test_result = subprocess.run(
                    ['tar', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if 'GNU tar' in test_result.stdout:
                    # GNU tar erkannt - nutze alle Features
                    tar_cmd.extend(gnu_features)
                    logger.debug("Using GNU tar with deterministic features")
                else:
                    # Non-GNU tar - nutze nur basis Features
                    logger.debug("Using basic tar (non-GNU)")
            except Exception:
                # Fallback auf Basis-Kommando
                logger.debug("Tar version detection failed, using basic tar")
            
            # Excludes aus Config anwenden
            for pattern in self.exclude_patterns:
                tar_cmd.extend(['--exclude', pattern])
            
            # Source directory
            tar_cmd.extend(['-C', volume.mountpoint, '.'])
            
            tar_process = subprocess.Popen(
                tar_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            snapshot_id = self.repo.create_snapshot_from_stdin(
                tar_process.stdout,
                path=f"{VOLUME_BACKUP_DIR}/{unit.name}/{volume.name}",
                tags={
                    'type': 'volume',
                    'unit': unit.name,
                    'volume': volume.name,
                    'timestamp': started_iso,
                    'backup_id': backup_id,
                    'size_bytes': str(volume.size_bytes) if volume.size_bytes else '0'
                }
            )
            
            # Warte auf tar-Prozess und räume sauber auf
            tar_process.wait()
            
            # Schließe Pipes sauber
            if tar_process.stdout:
                tar_process.stdout.close()
            
            # Lese stderr (falls vorhanden)
            if tar_process.stderr:
                err = tar_process.stderr.read().decode(errors='ignore')
                tar_process.stderr.close()
            else:
                err = ''
            
            if tar_process.returncode != 0:
                logger.error(f"Tar failed for volume {volume.name}: {err}",
                           extra={'unit_name': unit.name, 'volume': volume.name})
                return None
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to backup volume {volume.name}: {e}",
                        extra={'unit_name': unit.name, 'volume': volume.name})
            return None
    
    def _backup_database(self, container: ContainerInfo, unit: BackupUnit, backup_id: str, started_iso: str) -> Optional[str]:
        """
        Backup a database container.
        
        Args:
            container: Database container
            unit: Backup unit this container belongs to
            backup_id: Stable identifier for this backup run
            started_iso: UTC start timestamp shared across artifacts
            
        Returns:
            Kopia snapshot ID or None
        """
        if not container.database_type or not self.config.getboolean('backup', 'database_backup'):
            return None
        
        try:
            logger.debug(f"Backing up database: {container.name} ({container.database_type})",
                        extra={'unit_name': unit.name, 'container': container.name, 
                              'db_type': container.database_type})
            
            # Use the new DatabaseBackupManager
            dump_process, metadata = self.db_manager.backup_database(container)
            
            if not dump_process:
                logger.warning(f"Could not create backup for database {container.name}",
                             extra={'unit_name': unit.name, 'container': container.name})
                return None
            
            # Create snapshot from dump output with metadata
            snapshot_id = self.repo.create_snapshot_from_stdin(
                dump_process.stdout,
                path=f"{DATABASE_BACKUP_DIR}/{unit.name}/{container.name}",
                tags={
                    'type': 'database',
                    'database_type': container.database_type,
                    'unit': unit.name,
                    'container': container.name,
                    'timestamp': started_iso,
                    'backup_id': backup_id,
                    'metadata': metadata if metadata else ''
                }
            )
            
            # Wait for dump process to complete
            dump_process.wait()
            
            # Sauberes Aufräumen der Pipes
            if dump_process.stdout:
                dump_process.stdout.close()
            
            if dump_process.returncode != 0:
                # Lese stderr falls vorhanden
                if dump_process.stderr:
                    stderr = dump_process.stderr.read().decode(errors='ignore')
                    dump_process.stderr.close()
                else:
                    stderr = 'Unknown error'
                    
                logger.error(f"Database dump failed for {container.name}: {stderr}",
                           extra={'unit_name': unit.name, 'container': container.name})
                return None
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to backup database {container.name}: {e}",
                        extra={'unit_name': unit.name, 'container': container.name})
            return None
    
    def _save_metadata(self, metadata: BackupMetadata):
        """
        Save backup metadata.
        
        Args:
            metadata: Backup metadata to save
        """
        metadata_dir = self.config.backup_base_path / 'metadata'
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize unit name für Dateinamen
        import re
        safe_unit = re.sub(r'[^A-Za-z0-9._-]+', '_', metadata.unit_name)
        filename = f"{safe_unit}_{metadata.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        metadata_file = metadata_dir / filename
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        logger.debug(f"Saved metadata to {metadata_file}", 
                    extra={'unit_name': metadata.unit_name})
    
    def _ensure_policies(self, unit: BackupUnit):
        """
        Setze Kopia Retention-Policies für diese Unit.
        
        Args:
            unit: Backup unit für die Policies
        """
        # Hole Retention-Config
        retention = {
            'daily': self.config.getint('retention', 'daily', 7),
            'weekly': self.config.getint('retention', 'weekly', 4),
            'monthly': self.config.getint('retention', 'monthly', 12),
            'yearly': self.config.getint('retention', 'yearly', 2)
        }
        
        # Target-Pfade für diese Unit
        targets = [
            f"{VOLUME_BACKUP_DIR}/{unit.name}",
            f"{DATABASE_BACKUP_DIR}/{unit.name}",
            f"{RECIPE_BACKUP_DIR}/{unit.name}",
        ]
        
        for target in targets:
            try:
                cmd = [
                    'kopia', 'policy', 'set',
                    f'--keep-daily={retention["daily"]}',
                    f'--keep-weekly={retention["weekly"]}',
                    f'--keep-monthly={retention["monthly"]}',
                    f'--keep-yearly={retention["yearly"]}',
                    target
                ]
                
                subprocess.run(
                    cmd,
                    check=True, 
                    capture_output=True, 
                    text=True, 
                    env=self.repo._get_env()
                )
                
                logger.debug(f"Applied Kopia retention policy on {target}", 
                           extra={'unit_name': unit.name, 'target': target})
                           
            except subprocess.CalledProcessError as e:
                logger.warning(f"Could not apply Kopia policy on {target}: {e.stderr}",
                             extra={'unit_name': unit.name, 'target': target})
            except Exception as e:
                logger.warning(f"Could not apply Kopia policy on {target}: {e}",
                             extra={'unit_name': unit.name, 'target': target})