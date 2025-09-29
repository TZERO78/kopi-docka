"""
Database backup module for Kopi-Docka.

This module handles database-specific backup operations with version-aware
handling for different database systems.
"""

import logging
import subprocess
import json
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from .types import ContainerInfo


logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """
    Handles database-specific backup operations.
    
    Provides version-aware backup strategies for different database systems.
    """
    
    def __init__(self):
        """Initialize database backup manager."""
        self.strategies = {
            'postgresql': PostgreSQLBackup(),
            'mysql': MySQLBackup(),
            'mariadb': MariaDBBackup(),
            'mongodb': MongoDBBackup(),
            'redis': RedisBackup(),
        }
    
    def backup_database(self, container: ContainerInfo) -> Tuple[Optional[subprocess.Popen], Optional[str]]:
        """
        Create database backup based on container type.
        
        Args:
            container: Database container
            
        Returns:
            Tuple of (dump process, backup metadata)
        """
        if not container.database_type:
            return None, None
        
        strategy = self.strategies.get(container.database_type)
        if not strategy:
            logger.warning(f"No backup strategy for database type: {container.database_type}")
            return None, None
        
        try:
            # Detect version
            version = self._detect_version(container)
            logger.info(f"Detected {container.database_type} version: {version}")
            
            # Get backup command
            backup_cmd = strategy.get_backup_command(container, version)
            if not backup_cmd:
                logger.error(f"Could not determine backup command for {container.name}")
                return None, None
            
            logger.debug(f"Backup command for {container.name}: {' '.join(backup_cmd)}")
            
            # Execute backup
            process = subprocess.Popen(
                backup_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Create metadata
            metadata = {
                'database_type': container.database_type,
                'version': version,
                'container_name': container.name,
                'backup_method': strategy.get_method_name(),
                'format': strategy.get_backup_format()
            }
            
            return process, json.dumps(metadata)
            
        except Exception as e:
            logger.error(f"Database backup failed for {container.name}: {e}")
            return None, None
    
    def _detect_version(self, container: ContainerInfo) -> Optional[str]:
        """
        Detect database version from container.
        
        Args:
            container: Database container
            
        Returns:
            Version string or None
        """
        strategy = self.strategies.get(container.database_type)
        if strategy:
            return strategy.detect_version(container)
        return None


class DatabaseBackupStrategy:
    """Base class for database backup strategies."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """Get backup command for database."""
        raise NotImplementedError
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect database version."""
        raise NotImplementedError
    
    def get_method_name(self) -> str:
        """Get backup method name."""
        raise NotImplementedError
    
    def get_backup_format(self) -> str:
        """Get backup format."""
        return "sql"


class PostgreSQLBackup(DatabaseBackupStrategy):
    """PostgreSQL backup strategy."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """
        Get PostgreSQL backup command.
        
        Uses pg_dumpall for complete backup including roles and databases.
        For PostgreSQL 12+ uses --no-role-passwords to avoid password prompt issues.
        """
        env = container.environment
        user = env.get('POSTGRES_USER', 'postgres')
        
        # Base command
        cmd = ['docker', 'exec', container.id]
        
        # Check version for specific flags
        version_major = self._parse_major_version(version)
        
        if version_major and version_major >= 12:
            # PostgreSQL 12+ - use --no-role-passwords
            cmd.extend(['pg_dumpall', '-U', user, '--no-role-passwords'])
        else:
            # Older versions
            cmd.extend(['pg_dumpall', '-U', user])
        
        # Add clean option for safer restore
        cmd.append('--clean')
        
        return cmd
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect PostgreSQL version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container.id, 'postgres', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse "postgres (PostgreSQL) 14.5"
                version_str = result.stdout.strip()
                parts = version_str.split()
                for part in parts:
                    if part[0].isdigit():
                        return part
        except Exception as e:
            logger.debug(f"Could not detect PostgreSQL version: {e}")
        
        return None
    
    def _parse_major_version(self, version: Optional[str]) -> Optional[int]:
        """Parse major version number."""
        if not version:
            return None
        try:
            return int(version.split('.')[0])
        except (ValueError, IndexError):
            return None
    
    def get_method_name(self) -> str:
        return "pg_dumpall"
    
    def get_backup_format(self) -> str:
        return "sql"


class MySQLBackup(DatabaseBackupStrategy):
    """MySQL backup strategy."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """
        Get MySQL backup command.
        
        Handles authentication differences between MySQL 5.7 and 8.0.
        """
        env = container.environment
        
        # Try to get credentials
        password = env.get('MYSQL_ROOT_PASSWORD', '')
        user = 'root'
        
        # If no root password, try regular user
        if not password:
            user = env.get('MYSQL_USER', 'root')
            password = env.get('MYSQL_PASSWORD', '')
        
        # Base command
        cmd = ['docker', 'exec', container.id, 'mysqldump']
        
        # Version-specific handling
        version_major = self._parse_major_version(version)
        
        if version_major and version_major >= 8:
            # MySQL 8.0+ 
            cmd.extend(['--all-databases', '--single-transaction'])
            
            # Handle authentication
            if password:
                # Use environment variable to avoid password on command line
                cmd = ['docker', 'exec', f'-e', f'MYSQL_PWD={password}', 
                      container.id, 'mysqldump', '--all-databases', 
                      '--single-transaction', '-u', user]
            else:
                cmd.extend(['-u', user])
            
            # Add column-statistics flag for MySQL 8.0+
            cmd.append('--column-statistics=0')
        else:
            # MySQL 5.7 and earlier
            cmd.extend(['--all-databases', '--single-transaction'])
            
            if password:
                # Older versions accept password in command
                cmd.extend([f'-u{user}', f'-p{password}'])
            else:
                cmd.extend([f'-u{user}'])
        
        # Add routines and events
        cmd.extend(['--routines', '--events'])
        
        return cmd
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect MySQL version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container.id, 'mysql', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse "mysql  Ver 8.0.33 for Linux"
                version_str = result.stdout.strip()
                parts = version_str.split()
                for i, part in enumerate(parts):
                    if part == 'Ver':
                        if i + 1 < len(parts):
                            return parts[i + 1]
        except Exception as e:
            logger.debug(f"Could not detect MySQL version: {e}")
        
        return None
    
    def _parse_major_version(self, version: Optional[str]) -> Optional[int]:
        """Parse major version number."""
        if not version:
            return None
        try:
            # Handle versions like "8.0.33-0ubuntu0.20.04.1"
            clean_version = version.split('-')[0]
            major = int(clean_version.split('.')[0])
            return major
        except (ValueError, IndexError):
            return None
    
    def get_method_name(self) -> str:
        return "mysqldump"


class MariaDBBackup(DatabaseBackupStrategy):
    """MariaDB backup strategy."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """
        Get MariaDB backup command.
        
        MariaDB 10.3+ has mariadb-dump, earlier versions use mysqldump.
        """
        env = container.environment
        
        # Get credentials
        password = env.get('MYSQL_ROOT_PASSWORD', env.get('MARIADB_ROOT_PASSWORD', ''))
        user = 'root'
        
        if not password:
            user = env.get('MYSQL_USER', env.get('MARIADB_USER', 'root'))
            password = env.get('MYSQL_PASSWORD', env.get('MARIADB_PASSWORD', ''))
        
        # Detect which dump command to use
        version_major = self._parse_major_version(version)
        
        if version_major and version_major >= 10.3:
            dump_cmd = 'mariadb-dump'
        else:
            dump_cmd = 'mysqldump'
        
        # Build command
        if password:
            cmd = ['docker', 'exec', '-e', f'MYSQL_PWD={password}',
                  container.id, dump_cmd, '--all-databases',
                  '--single-transaction', '-u', user]
        else:
            cmd = ['docker', 'exec', container.id, dump_cmd,
                  '--all-databases', '--single-transaction', f'-u{user}']
        
        # Add extra options
        cmd.extend(['--routines', '--events'])
        
        # MariaDB-specific options
        if version_major and version_major >= 10:
            cmd.append('--skip-log-queries')
        
        return cmd
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect MariaDB version."""
        try:
            # Try mariadb --version first (newer versions)
            result = subprocess.run(
                ['docker', 'exec', container.id, 'mariadb', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                # Fallback to mysql --version
                result = subprocess.run(
                    ['docker', 'exec', container.id, 'mysql', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            
            if result.returncode == 0:
                # Parse "mariadb  Ver 15.1 Distrib 10.6.12-MariaDB"
                version_str = result.stdout.strip()
                if 'MariaDB' in version_str:
                    parts = version_str.split()
                    for part in parts:
                        if '-MariaDB' in part:
                            return part.split('-')[0]
        except Exception as e:
            logger.debug(f"Could not detect MariaDB version: {e}")
        
        return None
    
    def _parse_major_version(self, version: Optional[str]) -> Optional[float]:
        """Parse major.minor version number."""
        if not version:
            return None
        try:
            parts = version.split('.')
            if len(parts) >= 2:
                return float(f"{parts[0]}.{parts[1]}")
            return float(parts[0])
        except (ValueError, IndexError):
            return None
    
    def get_method_name(self) -> str:
        return "mariadb-dump/mysqldump"


class MongoDBBackup(DatabaseBackupStrategy):
    """MongoDB backup strategy."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """
        Get MongoDB backup command.
        
        Uses mongodump with --archive for streaming backup.
        """
        env = container.environment
        
        # Build base command
        cmd = ['docker', 'exec', container.id, 'mongodump', '--archive']
        
        # Add authentication if configured
        username = env.get('MONGO_INITDB_ROOT_USERNAME')
        password = env.get('MONGO_INITDB_ROOT_PASSWORD')
        
        if username and password:
            cmd.extend([
                '--username', username,
                '--password', password,
                '--authenticationDatabase', 'admin'
            ])
        
        # Version-specific options
        version_major = self._parse_major_version(version)
        
        if version_major and version_major >= 4:
            # MongoDB 4.0+ supports --oplog for point-in-time
            cmd.append('--oplog')
        
        return cmd
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect MongoDB version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container.id, 'mongod', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse "db version v5.0.6"
                for line in result.stdout.split('\n'):
                    if 'db version' in line:
                        parts = line.split()
                        for part in parts:
                            if part.startswith('v'):
                                return part[1:]  # Remove 'v' prefix
        except Exception as e:
            logger.debug(f"Could not detect MongoDB version: {e}")
        
        return None
    
    def _parse_major_version(self, version: Optional[str]) -> Optional[int]:
        """Parse major version number."""
        if not version:
            return None
        try:
            return int(version.split('.')[0])
        except (ValueError, IndexError):
            return None
    
    def get_method_name(self) -> str:
        return "mongodump"
    
    def get_backup_format(self) -> str:
        return "archive"


class RedisBackup(DatabaseBackupStrategy):
    """Redis backup strategy."""
    
    def get_backup_command(self, container: ContainerInfo, version: Optional[str]) -> Optional[list]:
        """
        Get Redis backup command.
        
        Uses BGSAVE and then extracts the dump.rdb file.
        """
        env = container.environment
        
        # Build command to trigger save and output RDB
        cmd = ['docker', 'exec', container.id, 'sh', '-c']
        
        # Check if password is set
        password = env.get('REDIS_PASSWORD', '')
        
        if password:
            # Save and output RDB with auth
            save_cmd = f'redis-cli -a {password} --no-auth-warning --rdb -'
        else:
            # Save and output RDB without auth
            save_cmd = 'redis-cli --rdb -'
        
        cmd.append(save_cmd)
        
        return cmd
    
    def detect_version(self, container: ContainerInfo) -> Optional[str]:
        """Detect Redis version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container.id, 'redis-server', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse "Redis server v=6.2.6"
                version_str = result.stdout.strip()
                parts = version_str.split()
                for part in parts:
                    if part.startswith('v='):
                        return part[2:]
        except Exception as e:
            logger.debug(f"Could not detect Redis version: {e}")
        
        return None
    
    def get_method_name(self) -> str:
        return "redis-cli --rdb"
    
    def get_backup_format(self) -> str:
        return "rdb"