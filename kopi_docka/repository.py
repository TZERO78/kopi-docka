"""
Kopia repository management module.

This module handles all interactions with the Kopia backup repository,
including initialization, snapshot creation, and restoration.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, IO

from .config import Config


logger = logging.getLogger(__name__)


class KopiaRepository:
    """
    Manages Kopia repository operations.
    
    This class provides a Python interface to Kopia commands for
    repository management, snapshot creation, and restoration.
    """
    
    def __init__(self, config: Config):
        """
        Initialize Kopia repository manager.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.repo_path = config.kopia_repository_path
        self.password = config.kopia_password
    
    def is_initialized(self) -> bool:
        """
        Check if Kopia repository is initialized.
        
        Returns:
            True if repository exists and is accessible
        """
        try:
            result = subprocess.run(
                ['kopia', 'repository', 'status', '--json'],
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.error("Kopia binary not found")
            return False
        except Exception as e:
            logger.error(f"Failed to check repository status: {e}")
            return False
    
    def initialize(self):
        """Initialize Kopia repository."""
        logger.info(f"Initializing Kopia repository at {self.repo_path}")
        
        # Create repository directory
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        try:
            subprocess.run(
                [
                    'kopia', 'repository', 'create',
                    'filesystem',
                    '--path', str(self.repo_path),
                    '--compression', self.config.get('kopia', 'compression'),
                    '--encryption', self.config.get('kopia', 'encryption')
                ],
                env=self._get_env(),
                check=True,
                capture_output=True
            )
            logger.info("Repository initialized successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to initialize repository: {e.stderr}")
            raise
    
    def connect(self):
        """Connect to existing Kopia repository."""
        try:
            subprocess.run(
                [
                    'kopia', 'repository', 'connect',
                    'filesystem',
                    '--path', str(self.repo_path)
                ],
                env=self._get_env(),
                check=True,
                capture_output=True
            )
            logger.debug("Connected to repository")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to connect to repository: {e.stderr}")
            raise
    
    def create_snapshot(self, path: str, tags: Optional[Dict[str, str]] = None) -> str:
        """
        Create a Kopia snapshot of a directory.
        
        Args:
            path: Path to snapshot
            tags: Optional tags to add to snapshot
            
        Returns:
            Snapshot ID
        """
        cmd = ['kopia', 'snapshot', 'create', path, '--json']
        
        # Add tags
        if tags:
            for key, value in tags.items():
                cmd.extend(['--tags', f'{key}:{value}'])
        
        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse JSON output to get snapshot ID
            output = json.loads(result.stdout)
            snapshot_id = output.get('snapshotID', '')
            
            logger.info(f"Created snapshot: {snapshot_id}")
            return snapshot_id
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create snapshot: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Kopia output: {e}")
            raise
    
    def create_snapshot_from_stdin(self, 
                                  stdin: IO,
                                  path: str,
                                  tags: Optional[Dict[str, str]] = None) -> str:
        """
        Create a Kopia snapshot from stdin.
        
        Args:
            stdin: Input stream
            path: Virtual path for the snapshot
            tags: Optional tags to add to snapshot
            
        Returns:
            Snapshot ID
        """
        cmd = ['kopia', 'snapshot', 'create', '--stdin', '--stdin-file', path, '--json']
        
        # Add tags
        if tags:
            for key, value in tags.items():
                cmd.extend(['--tags', f'{key}:{value}'])
        
        try:
            result = subprocess.run(
                cmd,
                stdin=stdin,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse JSON output to get snapshot ID
            output = json.loads(result.stdout)
            snapshot_id = output.get('snapshotID', '')
            
            logger.info(f"Created snapshot from stdin: {snapshot_id}")
            return snapshot_id
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create snapshot from stdin: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Kopia output: {e}")
            raise
    
    def list_snapshots(self, tag_filter: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        List snapshots in repository.
        
        Args:
            tag_filter: Optional tag filter
            
        Returns:
            List of snapshot information
        """
        cmd = ['kopia', 'snapshot', 'list', '--json']
        
        # Add tag filters
        if tag_filter:
            for key, value in tag_filter.items():
                cmd.extend(['--tags', f'{key}:{value}'])
        
        try:
            result = subprocess.run(
                cmd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=True
            )
            
            snapshots = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        snapshot = json.loads(line)
                        snapshots.append({
                            'id': snapshot.get('id', ''),
                            'path': snapshot.get('source', {}).get('path', ''),
                            'timestamp': snapshot.get('startTime', ''),
                            'tags': snapshot.get('tags', {}),
                            'size': snapshot.get('stats', {}).get('totalSize', 0)
                        })
                    except json.JSONDecodeError:
                        continue
            
            return snapshots
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list snapshots: {e.stderr}")
            return []
    
    def restore_snapshot(self, snapshot_id: str, target_path: str):
        """
        Restore a snapshot to a directory.
        
        Args:
            snapshot_id: Snapshot ID to restore
            target_path: Target directory for restoration
        """
        logger.info(f"Restoring snapshot {snapshot_id} to {target_path}")
        
        try:
            subprocess.run(
                [
                    'kopia', 'snapshot', 'restore',
                    snapshot_id,
                    target_path
                ],
                env=self._get_env(),
                check=True,
                capture_output=True
            )
            logger.info(f"Snapshot restored to {target_path}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restore snapshot: {e.stderr}")
            raise
    
    def verify_snapshot(self, snapshot_id: str) -> bool:
        """
        Verify snapshot integrity.
        Note: Consider using 'kopia snapshot verify' directly for more options.
        
        Args:
            snapshot_id: Snapshot ID to verify
            
        Returns:
            True if snapshot is valid
        """
        try:
            result = subprocess.run(
                ['kopia', 'snapshot', 'verify', '--verify-files-percent=10', snapshot_id],
                env=self._get_env(),
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except subprocess.CalledProcessError:
            return False
    
    def list_backup_units(self) -> List[Dict[str, Any]]:
        """
        List all backup units in repository.
        
        Returns:
            List of backup unit information
        """
        snapshots = self.list_snapshots(tag_filter={'type': 'recipe'})
        
        units = {}
        for snap in snapshots:
            unit_name = snap['tags'].get('unit')
            if unit_name:
                if unit_name not in units or snap['timestamp'] > units[unit_name]['timestamp']:
                    units[unit_name] = {
                        'name': unit_name,
                        'timestamp': snap['timestamp'],
                        'snapshot_id': snap['id']
                    }
        
        return list(units.values())
    
    def maintenance_run(self):
        """
        Run Kopia maintenance.
        Note: Consider setting up Kopia's automatic maintenance instead:
        kopia maintenance set --enable-full
        """
        logger.info("Running repository maintenance")
        
        try:
            subprocess.run(
                ['kopia', 'maintenance', 'run', '--full'],
                env=self._get_env(),
                check=True,
                capture_output=True
            )
            logger.info("Maintenance completed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Maintenance failed: {e.stderr}")
    
    def _get_env(self) -> Dict[str, str]:
        """
        Get environment variables for Kopia commands.
        
        Returns:
            Dictionary of environment variables
        """
        import os
        env = os.environ.copy()
        env['KOPIA_PASSWORD'] = self.password
        
        cache_dir = self.config.get('kopia', 'cache_directory')
        if cache_dir:
            env['KOPIA_CACHE_DIRECTORY'] = cache_dir
        
        return env