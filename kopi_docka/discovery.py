"""
Docker discovery module for Kopi-Docka.

This module handles discovering Docker containers, volumes, and grouping
them into logical backup units (stacks or standalone containers).
"""

import json
import logging
import subprocess
from typing import List, Dict, Optional, Any
from pathlib import Path

from .types import BackupUnit, ContainerInfo, VolumeInfo
from .constants import (
    DOCKER_COMPOSE_PROJECT_LABEL,
    DOCKER_COMPOSE_CONFIG_LABEL,
    DOCKER_COMPOSE_SERVICE_LABEL,
    DATABASE_IMAGES
)


logger = logging.getLogger(__name__)


class DockerDiscovery:
    """
    Discovers Docker containers and volumes, grouping them into backup units.
    
    This class interfaces with the Docker daemon to discover running containers,
    their volumes, and groups them into logical units for backup.
    """
    
    def __init__(self, docker_socket: str = '/var/run/docker.sock'):
        """
        Initialize Docker discovery.
        
        Args:
            docker_socket: Path to Docker socket
        """
        self.docker_socket = docker_socket
        self._validate_docker_access()
    
    def _validate_docker_access(self):
        """Validate Docker daemon accessibility."""
        try:
            result = subprocess.run(
                ['docker', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError(f"Docker daemon not accessible: {result.stderr}")
        except Exception as e:
            logger.error(f"Failed to access Docker: {e}")
            raise
    
    def _run_docker_command(self, args: List[str]) -> str:
        """
        Run a Docker command and return output.
        
        Args:
            args: Docker command arguments
            
        Returns:
            Command output as string
        """
        cmd = ['docker'] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker command failed: {' '.join(cmd)}")
            logger.error(f"Error: {e.stderr}")
            raise
    
    def discover_backup_units(self) -> List[BackupUnit]:
        """
        Discover all backup units.
        
        Returns:
            List of discovered backup units
        """
        logger.info("Starting Docker discovery...")
        
        containers = self._discover_containers()
        volumes = self._discover_volumes()
        
        # Group containers into units
        units = self._group_into_units(containers, volumes)
        
        logger.info(f"Discovered {len(units)} backup units")
        for unit in units:
            logger.info(f"  - {unit.name}: {len(unit.containers)} containers, "
                       f"{len(unit.volumes)} volumes")
        
        return units
    
    def _discover_containers(self) -> List[ContainerInfo]:
        """
        Discover all running containers.
        
        Returns:
            List of container information
        """
        # Get container IDs
        output = self._run_docker_command(['ps', '-q'])
        if not output.strip():
            logger.warning("No running containers found")
            return []
        
        container_ids = output.strip().split('\n')
        containers = []
        
        for container_id in container_ids:
            try:
                # Get detailed container information
                inspect_output = self._run_docker_command(['inspect', container_id])
                inspect_data = json.loads(inspect_output)[0]
                
                container = self._parse_container_info(inspect_data)
                containers.append(container)
                
            except Exception as e:
                logger.error(f"Failed to inspect container {container_id}: {e}")
                continue
        
        return containers
    
    def _parse_container_info(self, inspect_data: Dict[str, Any]) -> ContainerInfo:
        """
        Parse container information from Docker inspect output.
        
        Args:
            inspect_data: Docker inspect JSON data
            
        Returns:
            ContainerInfo object
        """
        # Extract basic information
        container_id = inspect_data['Id']
        name = inspect_data['Name'].lstrip('/')
        image = inspect_data['Config']['Image']
        status = inspect_data['State']['Status']
        labels = inspect_data['Config'].get('Labels', {}) or {}
        
        # Extract environment variables
        env_list = inspect_data['Config'].get('Env', [])
        environment = {}
        for env_str in env_list:
            if '=' in env_str:
                key, value = env_str.split('=', 1)
                environment[key] = value
        
        # Extract volumes
        volumes = []
        mounts = inspect_data.get('Mounts', [])
        for mount in mounts:
            if mount['Type'] == 'volume':
                volumes.append(mount['Name'])
        
        # Check for compose file
        compose_file = None
        if DOCKER_COMPOSE_CONFIG_LABEL in labels:
            compose_files = labels[DOCKER_COMPOSE_CONFIG_LABEL]
            if compose_files:
                # Take the first file if multiple
                compose_file = Path(compose_files.split(',')[0])
        
        # Detect database type
        database_type = self._detect_database_type(image)
        
        return ContainerInfo(
            id=container_id,
            name=name,
            image=image,
            status=status,
            labels=labels,
            environment=environment,
            volumes=volumes,
            compose_file=compose_file,
            inspect_data=inspect_data,
            database_type=database_type
        )
    
    def _detect_database_type(self, image: str) -> Optional[str]:
        """
        Detect if container is a database based on image name.
        
        Args:
            image: Docker image name
            
        Returns:
            Database type or None
        """
        image_lower = image.lower()
        
        for db_type, db_info in DATABASE_IMAGES.items():
            for pattern in db_info['patterns']:
                if pattern in image_lower:
                    return db_type
        
        return None
    
    def _discover_volumes(self) -> List[VolumeInfo]:
        """
        Discover all Docker volumes.
        
        Returns:
            List of volume information
        """
        output = self._run_docker_command(['volume', 'ls', '--format', 'json'])
        if not output.strip():
            return []
        
        volumes = []
        for line in output.strip().split('\n'):
            try:
                volume_data = json.loads(line)
                volume_name = volume_data['Name']
                
                # Get detailed volume information
                inspect_output = self._run_docker_command(['volume', 'inspect', volume_name])
                inspect_data = json.loads(inspect_output)[0]
                
                volume = VolumeInfo(
                    name=inspect_data['Name'],
                    driver=inspect_data['Driver'],
                    mountpoint=inspect_data['Mountpoint'],
                    labels=inspect_data.get('Labels', {}) or {}
                )
                
                # Try to estimate size (this is approximate)
                volume.size_bytes = self._estimate_volume_size(volume.mountpoint)
                
                volumes.append(volume)
                
            except Exception as e:
                logger.error(f"Failed to inspect volume: {e}")
                continue
        
        return volumes
    
    def _estimate_volume_size(self, mountpoint: str) -> Optional[int]:
        """
        Estimate volume size using du command.
        
        Args:
            mountpoint: Volume mount point
            
        Returns:
            Size in bytes or None if cannot determine
        """
        try:
            result = subprocess.run(
                ['du', '-sb', mountpoint],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                size_str = result.stdout.split('\t')[0]
                return int(size_str)
        except Exception as e:
            logger.debug(f"Could not estimate volume size: {e}")
        
        return None
    
    def _group_into_units(self, 
                         containers: List[ContainerInfo],
                         volumes: List[VolumeInfo]) -> List[BackupUnit]:
        """
        Group containers and volumes into backup units.
        
        Args:
            containers: List of discovered containers
            volumes: List of discovered volumes
            
        Returns:
            List of backup units
        """
        units = []
        processed_containers = set()
        
        # Create a mapping of volume names to volume info
        volume_map = {v.name: v for v in volumes}
        
        # Group by Docker Compose stacks
        stacks = {}
        for container in containers:
            stack_name = container.stack_name
            if stack_name:
                if stack_name not in stacks:
                    stacks[stack_name] = []
                stacks[stack_name].append(container)
                processed_containers.add(container.id)
        
        # Create units for stacks
        for stack_name, stack_containers in stacks.items():
            unit = BackupUnit(
                name=stack_name,
                type='stack',
                containers=stack_containers
            )
            
            # Find compose file
            for container in stack_containers:
                if container.compose_file:
                    unit.compose_file = container.compose_file
                    break
            
            # Collect volumes used by stack
            unit_volume_names = set()
            for container in stack_containers:
                unit_volume_names.update(container.volumes)
            
            unit.volumes = [volume_map[vn] for vn in unit_volume_names 
                          if vn in volume_map]
            
            # Update volume container associations
            for volume in unit.volumes:
                for container in stack_containers:
                    if volume.name in container.volumes:
                        volume.container_ids.append(container.id)
            
            units.append(unit)
        
        # Create units for standalone containers
        for container in containers:
            if container.id not in processed_containers:
                unit = BackupUnit(
                    name=container.name,
                    type='standalone',
                    containers=[container]
                )
                
                # Collect volumes
                unit.volumes = [volume_map[vn] for vn in container.volumes 
                              if vn in volume_map]
                
                # Update volume container associations
                for volume in unit.volumes:
                    volume.container_ids.append(container.id)
                
                units.append(unit)
        
        # Sort units by priority (databases first, then by name)
        units.sort(key=lambda u: (
            0 if u.has_databases else 1,
            u.name
        ))
        
        return units