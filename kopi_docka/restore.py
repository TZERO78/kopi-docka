"""
Restore management module for Kopi-Docka.

This module handles interactive restoration of Docker containers and volumes
from Kopia backups.
"""

import json
import logging
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .types import RestorePoint, BackupUnit
from .config import Config
from .repository import KopiaRepository
from .restore_db import DatabaseRestoreManager
from .constants import (
    RECIPE_BACKUP_DIR,
    VOLUME_BACKUP_DIR,
    DATABASE_BACKUP_DIR
)


logger = logging.getLogger(__name__)


class RestoreManager:
    """
    Manages restoration of Docker containers and volumes from backups.
    
    This class provides an interactive wizard for selecting and restoring
    backup units from Kopia snapshots.
    """
    
    def __init__(self, config: Config):
        """
        Initialize restore manager.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.repo = KopiaRepository(config)
        self.db_manager = DatabaseRestoreManager()
    
    def interactive_restore(self):
        """
        Launch interactive restore wizard.
        
        This guides the user through selecting a backup to restore
        and provides commands to restore the service.
        """
        print("\n" + "=" * 60)
        print("Kopi-Docka Restore Wizard")
        print("=" * 60)
        
        # List available restore points
        restore_points = self._find_restore_points()
        
        if not restore_points:
            print("\nNo backups found to restore.")
            return
        
        # Display available restore points
        print("\nAvailable restore points:\n")
        for idx, point in enumerate(restore_points, 1):
            print(f"{idx}. {point.unit_name} - {point.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Volumes: {len(point.volume_snapshots)}, "
                  f"Databases: {len(point.database_snapshots)}")
        
        # Select restore point
        while True:
            try:
                choice = input("\nSelect restore point (number): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(restore_points):
                    selected = restore_points[idx]
                    break
                print("Invalid selection. Please try again.")
            except (ValueError, KeyboardInterrupt):
                print("\nRestore cancelled.")
                return
        
        print(f"\nSelected: {selected.unit_name} from {selected.timestamp}")
        
        # Confirm restoration
        print("\nThis will guide you through restoring:")
        print(f"  - Recipe/configuration files")
        print(f"  - {len(selected.volume_snapshots)} volumes")
        print(f"  - {len(selected.database_snapshots)} database dumps")
        
        confirm = input("\nProceed with restore? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Restore cancelled.")
            return
        
        # Perform restore
        self._restore_unit(selected)
    
    def _find_restore_points(self) -> List[RestorePoint]:
        """
        Find all available restore points.
        
        Returns:
            List of restore points
        """
        restore_points = []
        
        # Get all recipe snapshots (they define restore points)
        snapshots = self.repo.list_snapshots(tag_filter={'type': 'recipe'})
        
        for snap in snapshots:
            tags = snap.get('tags', {})
            unit_name = tags.get('unit')
            timestamp_str = tags.get('timestamp')
            
            if not unit_name or not timestamp_str:
                continue
            
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                continue
            
            # Find associated volume and database snapshots
            point = RestorePoint(
                unit_name=unit_name,
                timestamp=timestamp,
                recipe_snapshot=snap['id']
            )
            
            # Find volume snapshots
            volume_snaps = self.repo.list_snapshots(
                tag_filter={
                    'type': 'volume',
                    'unit': unit_name
                }
            )
            for vol_snap in volume_snaps:
                vol_tags = vol_snap.get('tags', {})
                vol_timestamp = vol_tags.get('timestamp')
                if vol_timestamp and self._timestamps_match(timestamp_str, vol_timestamp):
                    volume_name = vol_tags.get('volume')
                    if volume_name:
                        point.volume_snapshots[volume_name] = vol_snap['id']
            
            # Find database snapshots
            db_snaps = self.repo.list_snapshots(
                tag_filter={
                    'type': 'database',
                    'unit': unit_name
                }
            )
            for db_snap in db_snaps:
                db_tags = db_snap.get('tags', {})
                db_timestamp = db_tags.get('timestamp')
                if db_timestamp and self._timestamps_match(timestamp_str, db_timestamp):
                    container_name = db_tags.get('container')
                    if container_name:
                        point.database_snapshots[container_name] = db_snap['id']
            
            restore_points.append(point)
        
        # Sort by timestamp (newest first)
        restore_points.sort(key=lambda p: p.timestamp, reverse=True)
        
        return restore_points
    
    def _timestamps_match(self, ts1: str, ts2: str, tolerance_seconds: int = 300) -> bool:
        """
        Check if two timestamps are close enough to be from the same backup.
        
        Args:
            ts1: First timestamp string
            ts2: Second timestamp string
            tolerance_seconds: Maximum difference in seconds
            
        Returns:
            True if timestamps match within tolerance
        """
        try:
            dt1 = datetime.fromisoformat(ts1)
            dt2 = datetime.fromisoformat(ts2)
            diff = abs((dt1 - dt2).total_seconds())
            return diff <= tolerance_seconds
        except ValueError:
            return False
    
    def _restore_unit(self, restore_point: RestorePoint):
        """
        Restore a backup unit.
        
        Args:
            restore_point: Restore point to restore
        """
        print("\n" + "-" * 60)
        print("Starting restoration process...")
        print("-" * 60)
        
        # Create restore directory
        restore_dir = Path(tempfile.mkdtemp(prefix='kopi-docka-restore-'))
        print(f"\nRestore directory: {restore_dir}")
        
        try:
            # Step 1: Restore recipes
            print("\n1. Restoring configuration files...")
            recipe_dir = self._restore_recipe(restore_point, restore_dir)
            
            # Check if it's a compose stack or standalone
            compose_file = recipe_dir / 'recipes' / restore_point.unit_name / 'docker-compose.yml'
            is_stack = compose_file.exists()
            
            if is_stack:
                print(f"\n✓ Found Docker Compose stack: {restore_point.unit_name}")
                print(f"  Compose file: {compose_file}")
            else:
                print(f"\n✓ Found standalone container(s)")
            
            # Step 2: Stop existing containers if they exist
            print("\n2. Checking for existing containers...")
            self._stop_existing_containers(restore_point, recipe_dir)
            
            # Step 3: Restore volumes
            if restore_point.volume_snapshots:
                print("\n3. Restoring volumes...")
                self._restore_volumes(restore_point, restore_dir)
            
            # Step 4: Restore databases (if needed later)
            if restore_point.database_snapshots:
                print("\n4. Database dumps available for restore after container start")
                db_restore_dir = restore_dir / 'databases'
                db_restore_dir.mkdir(parents=True, exist_ok=True)
                for container_name, snapshot_id in restore_point.database_snapshots.items():
                    print(f"   - {container_name}: Will restore after container starts")
            
            # Step 5: Start containers/stack
            print("\n5. Starting services...")
            if is_stack:
                self._start_compose_stack(compose_file, restore_point)
            else:
                self._start_standalone_containers(recipe_dir, restore_point)
            
            # Wait a moment for containers to initialize
            if restore_point.database_snapshots:
                print("\n   Waiting for containers to initialize...")
                time.sleep(10)
            
            # Step 6: Restore databases after containers are running
            if restore_point.database_snapshots:
                self._restore_databases(restore_point, restore_dir)
            
            print("\n" + "=" * 60)
            print("✓ Restoration complete!")
            print("=" * 60)
            print(f"\nRestore data kept in: {restore_dir}")
            print("You can delete this directory after verifying everything works.")
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            print(f"\n✗ Error during restore: {e}")
            print(f"Restore directory kept for debugging: {restore_dir}")
    
    def _stop_existing_containers(self, restore_point: RestorePoint, recipe_dir: Path):
        """
        Stop existing containers that will be replaced.
        
        Args:
            restore_point: Restore point
            recipe_dir: Directory with recipes
        """
        # Load container names from inspect files
        inspect_files = list((recipe_dir / 'recipes' / restore_point.unit_name).glob('*_inspect.json'))
        
        for inspect_file in inspect_files:
            try:
                with open(inspect_file) as f:
                    inspect_data = json.load(f)
                    container_name = inspect_data.get('Name', '').lstrip('/')
                    
                    if container_name:
                        # Check if container exists
                        result = subprocess.run(
                            ['docker', 'ps', '-a', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
                            capture_output=True,
                            text=True
                        )
                        
                        if container_name in result.stdout:
                            print(f"   Stopping existing container: {container_name}")
                            subprocess.run(['docker', 'stop', container_name], capture_output=True)
                            subprocess.run(['docker', 'rm', container_name], capture_output=True)
            except Exception as e:
                logger.debug(f"Could not process {inspect_file}: {e}")
    
    def _restore_volumes(self, restore_point: RestorePoint, restore_dir: Path):
        """
        Actually restore the volumes.
        
        Args:
            restore_point: Restore point
            restore_dir: Directory for restoration
        """
        for volume_name, snapshot_id in restore_point.volume_snapshots.items():
            try:
                print(f"\n   Restoring volume: {volume_name}")
                
                # Create temporary directory for volume data
                volume_restore_dir = restore_dir / 'volumes' / volume_name
                volume_restore_dir.mkdir(parents=True, exist_ok=True)
                
                # Restore snapshot from Kopia
                print(f"     - Extracting from Kopia...")
                self.repo.restore_snapshot(snapshot_id, str(volume_restore_dir))
                
                # Check if volume exists, if yes remove it
                result = subprocess.run(
                    ['docker', 'volume', 'ls', '--format', '{{.Name}}'],
                    capture_output=True,
                    text=True
                )
                
                if volume_name in result.stdout:
                    print(f"     - Removing existing volume")
                    subprocess.run(['docker', 'volume', 'rm', '-f', volume_name], check=True, capture_output=True)
                
                # Create new volume
                print(f"     - Creating new volume")
                subprocess.run(['docker', 'volume', 'create', volume_name], check=True, capture_output=True)
                
                # Copy data to volume
                print(f"     - Copying data to volume")
                subprocess.run([
                    'docker', 'run', '--rm',
                    '-v', f'{volume_name}:/restore',
                    '-v', f'{volume_restore_dir}:/backup:ro',
                    'alpine',
                    'sh', '-c', 'cd /backup && cp -a . /restore/'
                ], check=True, capture_output=True)
                
                print(f"     ✓ Volume {volume_name} restored")
                
            except Exception as e:
                print(f"     ✗ Failed to restore volume {volume_name}: {e}")
                logger.error(f"Volume restore failed for {volume_name}: {e}")
    
    def _start_compose_stack(self, compose_file: Path, restore_point: RestorePoint):
        """
        Start a Docker Compose stack.
        
        Args:
            compose_file: Path to docker-compose.yml
            restore_point: Restore point
        """
        print(f"\n   Starting Docker Compose stack: {restore_point.unit_name}")
        
        compose_dir = compose_file.parent
        
        try:
            # Use docker-compose up
            result = subprocess.run(
                ['docker-compose', 'up', '-d'],
                cwd=compose_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"   ✓ Stack {restore_point.unit_name} started successfully")
                
                # Show running containers
                subprocess.run(['docker-compose', 'ps'], cwd=compose_dir)
            else:
                print(f"   ✗ Failed to start stack: {result.stderr}")
                
        except FileNotFoundError:
            # Try docker compose (newer version)
            try:
                result = subprocess.run(
                    ['docker', 'compose', 'up', '-d'],
                    cwd=compose_dir,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"   ✓ Stack {restore_point.unit_name} started successfully")
                    subprocess.run(['docker', 'compose', 'ps'], cwd=compose_dir)
                else:
                    print(f"   ✗ Failed to start stack: {result.stderr}")
                    
            except Exception as e:
                print(f"   ✗ Could not start compose stack: {e}")
                print(f"   Manual command: cd {compose_dir} && docker-compose up -d")
    
    def _start_standalone_containers(self, recipe_dir: Path, restore_point: RestorePoint):
        """
        Start standalone containers from inspect data.
        
        Args:
            recipe_dir: Directory with recipes
            restore_point: Restore point
        """
        inspect_files = list((recipe_dir / 'recipes' / restore_point.unit_name).glob('*_inspect.json'))
        
        for inspect_file in inspect_files:
            try:
                with open(inspect_file) as f:
                    inspect_data = json.load(f)
                
                container_name = inspect_data.get('Name', '').lstrip('/')
                print(f"\n   Starting container: {container_name}")
                
                # Build docker run command
                docker_cmd = RestoreHelper.build_docker_run_command(inspect_data)
                
                # Execute
                result = subprocess.run(docker_cmd, capture_output=True, text=True, shell=True)
                
                if result.returncode == 0:
                    print(f"   ✓ Container {container_name} started")
                else:
                    print(f"   ✗ Failed to start {container_name}: {result.stderr}")
                    print(f"   Manual command: {docker_cmd}")
                    
            except Exception as e:
                print(f"   ✗ Could not restore from {inspect_file}: {e}")
    
    def _restore_databases(self, restore_point: RestorePoint, restore_dir: Path):
        """
        Restore database dumps into running containers.
        
        Args:
            restore_point: Restore point
            restore_dir: Directory with restore data
        """
        if not restore_point.database_snapshots:
            return
            
        print("\n" + "=" * 60)
        print("DATABASE RESTORATION")
        print("=" * 60)
        
        print("\n⚠️  Important: Databases need special handling!")
        print("   Containers must be fully initialized before importing dumps.")
        print("   This process will guide you through it.\n")
        
        for container_name, snapshot_id in restore_point.database_snapshots.items():
            try:
                print(f"\n━━━ Database: {container_name} ━━━")
                
                # Extract dump and metadata
                db_file = restore_dir / 'databases' / f'{container_name}.dump'
                db_file.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"1. Extracting dump from backup...")
                
                # Get snapshot info to extract metadata
                snapshots = self.repo.list_snapshots()
                metadata = None
                for snap in snapshots:
                    if snap['id'] == snapshot_id:
                        metadata_str = snap.get('tags', {}).get('metadata')
                        if metadata_str:
                            try:
                                metadata = json.loads(metadata_str)
                            except json.JSONDecodeError:
                                pass
                        break
                
                # Restore dump file
                self.repo.restore_snapshot(snapshot_id, str(db_file))
                print(f"   ✓ Dump saved to: {db_file}")
                
                # Check container status
                print(f"\n2. Checking container status...")
                result = subprocess.run(
                    ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Status}}'],
                    capture_output=True,
                    text=True
                )
                
                if not result.stdout:
                    print(f"   ✗ Container {container_name} is not running!")
                    print(f"   Please start it first and retry.")
                    print(f"\n   Manual restore commands:")
                    print(self.db_manager.get_manual_restore_commands(
                        container_name, 
                        metadata.get('database_type', 'unknown') if metadata else 'unknown',
                        db_file,
                        metadata
                    ))
                    continue
                
                status = result.stdout.strip()
                print(f"   ✓ Container is running: {status}")
                
                # Detect database type
                result = subprocess.run(
                    ['docker', 'inspect', container_name, '--format', '{{.Config.Image}}'],
                    capture_output=True,
                    text=True
                )
                image = result.stdout.strip().lower()
                
                # Use metadata if available, otherwise detect from image
                if metadata and 'database_type' in metadata:
                    db_type = metadata['database_type']
                else:
                    db_type = self._detect_database_type(image)
                
                print(f"   ✓ Database type: {db_type}")
                
                # Restore using the new DatabaseRestoreManager
                print(f"\n3. Starting restore process...")
                success = self.db_manager.restore_database(
                    container_name,
                    db_type,
                    db_file,
                    metadata
                )
                
                if success:
                    print(f"   ✓ Database restored successfully!")
                else:
                    print(f"   ✗ Automatic restore failed.")
                    print(f"\n   Manual restore commands:")
                    print(self.db_manager.get_manual_restore_commands(
                        container_name,
                        db_type,
                        db_file,
                        metadata
                    ))
                    
            except Exception as e:
                print(f"   ✗ Error: {e}")
                logger.error(f"Database restore failed for {container_name}: {e}")
                print(f"\n   Dump file kept at: {db_file}")
                print(f"   You can manually restore it later.")
        
        print("\n" + "=" * 60)
        print("Database restoration phase complete.")
        print("Please verify your databases are working correctly!")
        print("=" * 60)
    
    def _detect_database_type(self, image: str) -> str:
        """Detect database type from image name."""
        image_lower = image.lower()
        
        if 'postgres' in image_lower or 'postgis' in image_lower:
            return 'postgresql'
        elif 'mariadb' in image_lower:
            return 'mariadb'
        elif 'mysql' in image_lower:
            return 'mysql'
        elif 'mongo' in image_lower:
            return 'mongodb'
        elif 'redis' in image_lower:
            return 'redis'
        else:
            return 'unknown'
    
    def _restore_recipe(self, restore_point: RestorePoint, restore_dir: Path) -> Path:
        """
        Restore recipe files.
        
        Args:
            restore_point: Restore point
            restore_dir: Directory to restore to
            
        Returns:
            Path to restored recipe directory
        """
        recipe_dir = restore_dir / 'recipes'
        recipe_dir.mkdir(parents=True, exist_ok=True)
        
        # Restore recipe snapshot
        self.repo.restore_snapshot(restore_point.recipe_snapshot, str(recipe_dir))
        
        print(f"   ✓ Recipes restored to: {recipe_dir}")
        
        # List restored files
        for file in recipe_dir.rglob('*'):
            if file.is_file():
                print(f"     - {file.relative_to(recipe_dir)}")
        
        return recipe_dir
    
    def _display_volume_restore_instructions(self, restore_point: RestorePoint, restore_dir: Path):
        """
        Display instructions for restoring volumes.
        
        Args:
            restore_point: Restore point
            restore_dir: Directory for restoration
        """
        print("\n   To restore volumes, run these commands:\n")
        
        for volume_name, snapshot_id in restore_point.volume_snapshots.items():
            volume_restore_dir = restore_dir / 'volumes' / volume_name
            
            print(f"   # Restore volume: {volume_name}")
            print(f"   mkdir -p {volume_restore_dir}")
            print(f"   kopia snapshot restore {snapshot_id} {volume_restore_dir}")
            print(f"   docker volume create {volume_name}")
            print(f"   docker run --rm -v {volume_name}:/restore -v {volume_restore_dir}:/backup \\")
            print(f"          alpine sh -c 'cd /restore && tar -xzf /backup/*.tar.gz'")
            print()
    
    def _display_database_restore_instructions(self, restore_point: RestorePoint, restore_dir: Path):
        """
        Display instructions for restoring databases.
        
        Args:
            restore_point: Restore point
            restore_dir: Directory for restoration
        """
        print("\n   Database restore commands:\n")
        
        for container_name, snapshot_id in restore_point.database_snapshots.items():
            db_restore_file = restore_dir / 'databases' / f"{container_name}.sql"
            
            print(f"   # Restore database dump for: {container_name}")
            print(f"   mkdir -p {db_restore_file.parent}")
            print(f"   kopia snapshot restore {snapshot_id} {db_restore_file}")
            print(f"   # Then import into running container:")
            print(f"   docker exec -i {container_name} sh -c 'cat > /tmp/restore.sql'")
            print(f"   # Run appropriate restore command based on database type")
            print()
    
    def _display_restart_instructions(self, recipe_dir: Path):
        """
        Display instructions for restarting services.
        
        Args:
            recipe_dir: Directory containing restored recipes
        """
        compose_file = recipe_dir / 'docker-compose.yml'
        
        if compose_file.exists():
            print("\n   To restart using Docker Compose:")
            print(f"   cd {recipe_dir}")
            print(f"   docker-compose up -d")
        else:
            print("\n   To restart containers manually:")
            print("   Review the inspect JSON files in the recipe directory")
            print("   and use 'docker run' with the appropriate parameters.")
            print(f"   Inspect files location: {recipe_dir}")


class RestoreHelper:
    """
    Helper class for restoration operations.
    
    Provides utility methods for reconstructing Docker commands
    from inspect data.
    """
    
    @staticmethod
    def build_docker_run_command(inspect_data: Dict[str, Any]) -> str:
        """
        Build docker run command from inspect data.
        
        Args:
            inspect_data: Docker inspect JSON data
            
        Returns:
            Docker run command string
        """
        cmd_parts = ['docker run -d']
        
        config = inspect_data.get('Config', {})
        host_config = inspect_data.get('HostConfig', {})
        
        # Name
        name = inspect_data.get('Name', '').lstrip('/')
        if name:
            cmd_parts.append(f'--name {name}')
        
        # Environment variables
        for env in config.get('Env', []):
            if '=' in env and not env.startswith('PATH='):
                cmd_parts.append(f'-e "{env}"')
        
        # Ports
        for container_port, host_bindings in host_config.get('PortBindings', {}).items():
            if host_bindings:
                for binding in host_bindings:
                    host_port = binding.get('HostPort')
                    if host_port:
                        port_num = container_port.split('/')[0]
                        cmd_parts.append(f'-p {host_port}:{port_num}')
        
        # Volumes
        for mount in inspect_data.get('Mounts', []):
            if mount['Type'] == 'volume':
                cmd_parts.append(f'-v {mount["Name"]}:{mount["Destination"]}')
            elif mount['Type'] == 'bind':
                cmd_parts.append(f'-v {mount["Source"]}:{mount["Destination"]}')
        
        # Network mode
        network_mode = host_config.get('NetworkMode')
        if network_mode and network_mode != 'default':
            cmd_parts.append(f'--network {network_mode}')
        
        # Restart policy
        restart = host_config.get('RestartPolicy', {})
        if restart.get('Name'):
            if restart['Name'] == 'always':
                cmd_parts.append('--restart always')
            elif restart['Name'] == 'unless-stopped':
                cmd_parts.append('--restart unless-stopped')
            elif restart['Name'] == 'on-failure':
                max_retry = restart.get('MaximumRetryCount', 0)
                cmd_parts.append(f'--restart on-failure:{max_retry}')
        
        # Image (must be last before command)
        image = config.get('Image')
        if image:
            cmd_parts.append(image)
        
        # Command
        cmd = config.get('Cmd')
        if cmd:
            cmd_parts.extend(cmd)
        
        return ' '.join(cmd_parts)