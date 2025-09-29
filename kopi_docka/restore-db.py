"""
Database restore module for Kopi-Docka.

This module handles database-specific restore operations with version-aware
handling for different database systems.
"""

import logging
import subprocess
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from .types import ContainerInfo


logger = logging.getLogger(__name__)


class DatabaseRestoreManager:
    """
    Handles database-specific restore operations.
    
    Provides version-aware restore strategies for different database systems.
    """
    
    def __init__(self):
        """Initialize database restore manager."""
        self.strategies = {
            'postgresql': PostgreSQLRestore(),
            'mysql': MySQLRestore(), 
            'mariadb': MariaDBRestore(),
            'mongodb': MongoDBRestore(),
            'redis': RedisRestore(),
        }
    
    def restore_database(self, 
                        container_name: str,
                        db_type: str,
                        dump_file: Path,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Restore database from dump file.
        
        Args:
            container_name: Target container name
            db_type: Database type
            dump_file: Path to dump file
            metadata: Optional backup metadata
            
        Returns:
            True if successful
        """
        strategy = self.strategies.get(db_type)
        if not strategy:
            logger.error(f"No restore strategy for database type: {db_type}")
            return False
        
        try:
            # Wait for database to be ready
            print(f"   Waiting for {db_type} to be ready", end="")
            if not strategy.wait_until_ready(container_name):
                print(" - Timeout!")
                return False
            print(" - Ready!")
            
            # Detect current version
            version = strategy.detect_version(container_name)
            if version:
                logger.info(f"Target {db_type} version: {version}")
            
            # Perform restore
            success = strategy.restore(container_name, dump_file, metadata, version)
            
            if success:
                # Verify restore
                if strategy.verify_restore(container_name):
                    print(f"   ✓ Restore verified successfully")
                    return True
                else:
                    print(f"   ⚠ Restore completed but verification failed")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            return False
    
    def get_manual_restore_commands(self,
                                   container_name: str,
                                   db_type: str,
                                   dump_file: Path,
                                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Get manual restore commands for a database.
        
        Args:
            container_name: Target container name
            db_type: Database type
            dump_file: Path to dump file
            metadata: Optional backup metadata
            
        Returns:
            Manual restore commands as string
        """
        strategy = self.strategies.get(db_type)
        if strategy:
            return strategy.get_manual_commands(container_name, dump_file, metadata)
        return f"# No manual restore commands available for {db_type}"


class DatabaseRestoreStrategy:
    """Base class for database restore strategies."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for database to be ready."""
        raise NotImplementedError
    
    def restore(self, container_name: str, dump_file: Path, 
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Perform database restore."""
        raise NotImplementedError
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify restore was successful."""
        raise NotImplementedError
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect database version."""
        raise NotImplementedError
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual restore commands."""
        raise NotImplementedError


class PostgreSQLRestore(DatabaseRestoreStrategy):
    """PostgreSQL restore strategy."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for PostgreSQL to be ready."""
        for i in range(max_attempts):
            try:
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'pg_isready', '-U', 'postgres'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def restore(self, container_name: str, dump_file: Path,
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Restore PostgreSQL database."""
        try:
            # Check if we need to create database first
            # pg_dumpall includes database creation, pg_dump doesn't
            
            with open(dump_file, 'rb') as f:
                # Check first few lines to detect dump type
                header = f.read(1024)
                f.seek(0)
                
                if b'-- PostgreSQL database cluster dump' in header:
                    # This is a pg_dumpall dump - restore directly
                    result = subprocess.run(
                        ['docker', 'exec', '-i', container_name, 'psql', '-U', 'postgres'],
                        stdin=f,
                        capture_output=True
                    )
                else:
                    # This might be a pg_dump - need target database
                    # First try to create database if needed
                    subprocess.run(
                        ['docker', 'exec', container_name, 'createdb', '-U', 'postgres', 'restored_db'],
                        capture_output=True
                    )
                    
                    result = subprocess.run(
                        ['docker', 'exec', '-i', container_name, 'psql', '-U', 'postgres', '-d', 'restored_db'],
                        stdin=f,
                        capture_output=True
                    )
            
            if result.returncode == 0:
                return True
            
            # Log error for debugging
            if result.stderr:
                logger.error(f"PostgreSQL restore error: {result.stderr.decode()}")
            
            return False
            
        except Exception as e:
            logger.error(f"PostgreSQL restore failed: {e}")
            return False
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify PostgreSQL restore."""
        try:
            # Check if we can list databases
            result = subprocess.run(
                ['docker', 'exec', container_name, 'psql', '-U', 'postgres', '-c', '\\l'],
                capture_output=True,
                text=True
            )
            
            # Check if we have more than default databases
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                # Count non-system databases
                db_count = 0
                for line in lines:
                    if '|' in line and not any(sys_db in line for sys_db in ['postgres', 'template0', 'template1']):
                        db_count += 1
                
                return db_count > 0 or 'restored_db' in result.stdout
            
        except Exception as e:
            logger.error(f"PostgreSQL verification failed: {e}")
        
        return False
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect PostgreSQL version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container_name, 'postgres', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Parse version
                parts = result.stdout.strip().split()
                for part in parts:
                    if part[0].isdigit():
                        return part
        except Exception:
            pass
        return None
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual PostgreSQL restore commands."""
        return f"""
# PostgreSQL Restore Commands:

# For pg_dumpall dumps (includes all databases and roles):
docker exec -i {container_name} psql -U postgres < {dump_file}

# For single database dumps:
docker exec {container_name} createdb -U postgres your_database
docker exec -i {container_name} psql -U postgres -d your_database < {dump_file}

# If you have permission issues:
docker exec -i {container_name} su - postgres -c "psql" < {dump_file}

# To list databases after restore:
docker exec {container_name} psql -U postgres -c "\\l"
"""


class MySQLRestore(DatabaseRestoreStrategy):
    """MySQL restore strategy."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for MySQL to be ready."""
        for i in range(max_attempts):
            try:
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'mysqladmin', 'ping', '-h', 'localhost'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def restore(self, container_name: str, dump_file: Path,
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Restore MySQL database."""
        try:
            # Try different authentication methods
            
            # Method 1: Try without password (might work for root with no password)
            with open(dump_file, 'rb') as f:
                result = subprocess.run(
                    ['docker', 'exec', '-i', container_name, 'mysql', '-uroot'],
                    stdin=f,
                    capture_output=True
                )
                
                if result.returncode == 0:
                    return True
            
            # Method 2: Try with MYSQL_PWD environment variable
            # First get the password from container environment
            inspect_result = subprocess.run(
                ['docker', 'inspect', container_name],
                capture_output=True,
                text=True
            )
            
            if inspect_result.returncode == 0:
                import json
                container_data = json.loads(inspect_result.stdout)[0]
                env_vars = container_data['Config']['Env']
                
                mysql_pwd = None
                for env in env_vars:
                    if env.startswith('MYSQL_ROOT_PASSWORD='):
                        mysql_pwd = env.split('=', 1)[1]
                        break
                
                if mysql_pwd:
                    with open(dump_file, 'rb') as f:
                        result = subprocess.run(
                            ['docker', 'exec', '-i', '-e', f'MYSQL_PWD={mysql_pwd}',
                             container_name, 'mysql', '-uroot'],
                            stdin=f,
                            capture_output=True
                        )
                        
                        if result.returncode == 0:
                            return True
            
            # Log last error
            if result.stderr:
                logger.error(f"MySQL restore error: {result.stderr.decode()}")
            
            return False
            
        except Exception as e:
            logger.error(f"MySQL restore failed: {e}")
            return False
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify MySQL restore."""
        try:
            # Try to list databases
            result = subprocess.run(
                ['docker', 'exec', container_name, 'mysql', '-uroot', '-e', 'SHOW DATABASES;'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Check for non-system databases
                databases = result.stdout.split('\n')
                user_dbs = [db for db in databases 
                           if db and db not in ['Database', 'information_schema', 
                                               'mysql', 'performance_schema', 'sys']]
                return len(user_dbs) > 0
            
        except Exception as e:
            logger.error(f"MySQL verification failed: {e}")
        
        return False
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect MySQL version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container_name, 'mysql', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Parse version
                parts = result.stdout.strip().split()
                for i, part in enumerate(parts):
                    if part == 'Ver':
                        if i + 1 < len(parts):
                            return parts[i + 1]
        except Exception:
            pass
        return None
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual MySQL restore commands."""
        return f"""
# MySQL Restore Commands:

# Without password:
docker exec -i {container_name} mysql -uroot < {dump_file}

# With password (you'll be prompted):
docker exec -i {container_name} mysql -uroot -p < {dump_file}

# With password in environment:
docker exec -i -e MYSQL_PWD=yourpassword {container_name} mysql -uroot < {dump_file}

# For specific database:
docker exec -i {container_name} mysql -uroot -p your_database < {dump_file}

# To list databases after restore:
docker exec {container_name} mysql -uroot -e "SHOW DATABASES;"
"""


class MariaDBRestore(DatabaseRestoreStrategy):
    """MariaDB restore strategy."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for MariaDB to be ready."""
        for i in range(max_attempts):
            try:
                # Try mariadb-admin first (newer versions)
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'mariadb-admin', 'ping'],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode != 0:
                    # Fallback to mysqladmin
                    result = subprocess.run(
                        ['docker', 'exec', container_name, 'mysqladmin', 'ping'],
                        capture_output=True,
                        timeout=5
                    )
                
                if result.returncode == 0:
                    return True
                    
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def restore(self, container_name: str, dump_file: Path,
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Restore MariaDB database."""
        try:
            # Determine which client to use
            version_major = 10.3  # Default to newer version
            if version:
                try:
                    version_major = float('.'.join(version.split('.')[:2]))
                except (ValueError, IndexError):
                    pass
            
            if version_major >= 10.3:
                client_cmd = 'mariadb'
            else:
                client_cmd = 'mysql'
            
            # Try restore
            with open(dump_file, 'rb') as f:
                # First try without password
                result = subprocess.run(
                    ['docker', 'exec', '-i', container_name, client_cmd, '-uroot'],
                    stdin=f,
                    capture_output=True
                )
                
                if result.returncode == 0:
                    return True
                
                # Try with password from environment
                f.seek(0)
                inspect_result = subprocess.run(
                    ['docker', 'inspect', container_name],
                    capture_output=True,
                    text=True
                )
                
                if inspect_result.returncode == 0:
                    import json
                    container_data = json.loads(inspect_result.stdout)[0]
                    env_vars = container_data['Config']['Env']
                    
                    pwd = None
                    for env in env_vars:
                        if env.startswith('MARIADB_ROOT_PASSWORD=') or env.startswith('MYSQL_ROOT_PASSWORD='):
                            pwd = env.split('=', 1)[1]
                            break
                    
                    if pwd:
                        f.seek(0)
                        result = subprocess.run(
                            ['docker', 'exec', '-i', '-e', f'MYSQL_PWD={pwd}',
                             container_name, client_cmd, '-uroot'],
                            stdin=f,
                            capture_output=True
                        )
                        
                        if result.returncode == 0:
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"MariaDB restore failed: {e}")
            return False
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify MariaDB restore."""
        try:
            # Try both mariadb and mysql clients
            for client in ['mariadb', 'mysql']:
                result = subprocess.run(
                    ['docker', 'exec', container_name, client, '-uroot', '-e', 'SHOW DATABASES;'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    databases = result.stdout.split('\n')
                    user_dbs = [db for db in databases 
                               if db and db not in ['Database', 'information_schema',
                                                   'mysql', 'performance_schema', 'sys']]
                    return len(user_dbs) > 0
            
        except Exception as e:
            logger.error(f"MariaDB verification failed: {e}")
        
        return False
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect MariaDB version."""
        try:
            # Try mariadb --version first
            result = subprocess.run(
                ['docker', 'exec', container_name, 'mariadb', '--version'],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'mysql', '--version'],
                    capture_output=True,
                    text=True
                )
            
            if result.returncode == 0:
                # Parse version
                if 'MariaDB' in result.stdout:
                    parts = result.stdout.split()
                    for part in parts:
                        if '-MariaDB' in part:
                            return part.split('-')[0]
        except Exception:
            pass
        return None
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual MariaDB restore commands."""
        return f"""
# MariaDB Restore Commands:

# For MariaDB 10.3+ (using mariadb client):
docker exec -i {container_name} mariadb -uroot < {dump_file}
docker exec -i {container_name} mariadb -uroot -p < {dump_file}

# For older versions (using mysql client):
docker exec -i {container_name} mysql -uroot < {dump_file}
docker exec -i {container_name} mysql -uroot -p < {dump_file}

# With password in environment:
docker exec -i -e MYSQL_PWD=yourpassword {container_name} mariadb -uroot < {dump_file}

# To list databases after restore:
docker exec {container_name} mariadb -uroot -e "SHOW DATABASES;"
"""


class MongoDBRestore(DatabaseRestoreStrategy):
    """MongoDB restore strategy."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for MongoDB to be ready."""
        for i in range(max_attempts):
            try:
                # Try mongosh first (newer versions)
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'mongosh', '--eval', 'db.adminCommand("ping")'],
                    capture_output=True,
                    timeout=5
                )
                
                if result.returncode != 0:
                    # Fallback to mongo
                    result = subprocess.run(
                        ['docker', 'exec', container_name, 'mongo', '--eval', 'db.adminCommand("ping")'],
                        capture_output=True,
                        timeout=5
                    )
                
                if result.returncode == 0:
                    return True
                    
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def restore(self, container_name: str, dump_file: Path,
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Restore MongoDB database."""
        try:
            # Check if dump is archive format
            with open(dump_file, 'rb') as f:
                # mongodump archive has specific header
                header = f.read(16)
                f.seek(0)
                
                if header.startswith(b'mongodump archive'):
                    # Archive format
                    result = subprocess.run(
                        ['docker', 'exec', '-i', container_name, 'mongorestore', '--archive'],
                        stdin=f,
                        capture_output=True
                    )
                else:
                    # Might be BSON or other format
                    result = subprocess.run(
                        ['docker', 'exec', '-i', container_name, 'mongorestore'],
                        stdin=f,
                        capture_output=True
                    )
                
                if result.returncode == 0:
                    return True
                
                # Try with authentication if failed
                f.seek(0)
                inspect_result = subprocess.run(
                    ['docker', 'inspect', container_name],
                    capture_output=True,
                    text=True
                )
                
                if inspect_result.returncode == 0:
                    import json
                    container_data = json.loads(inspect_result.stdout)[0]
                    env_vars = container_data['Config']['Env']
                    
                    username = None
                    password = None
                    
                    for env in env_vars:
                        if env.startswith('MONGO_INITDB_ROOT_USERNAME='):
                            username = env.split('=', 1)[1]
                        elif env.startswith('MONGO_INITDB_ROOT_PASSWORD='):
                            password = env.split('=', 1)[1]
                    
                    if username and password:
                        f.seek(0)
                        result = subprocess.run(
                            ['docker', 'exec', '-i', container_name, 'mongorestore',
                             '--username', username, '--password', password,
                             '--authenticationDatabase', 'admin', '--archive'],
                            stdin=f,
                            capture_output=True
                        )
                        
                        if result.returncode == 0:
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"MongoDB restore failed: {e}")
            return False
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify MongoDB restore."""
        try:
            # Try to list databases
            for client in ['mongosh', 'mongo']:
                result = subprocess.run(
                    ['docker', 'exec', container_name, client, '--eval', 'show dbs', '--quiet'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    # Check for non-system databases
                    databases = result.stdout.split('\n')
                    user_dbs = [db for db in databases 
                               if db and not any(sys_db in db for sys_db in ['admin', 'config', 'local'])]
                    return len(user_dbs) > 0
            
        except Exception as e:
            logger.error(f"MongoDB verification failed: {e}")
        
        return False
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect MongoDB version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container_name, 'mongod', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'db version' in line:
                        parts = line.split()
                        for part in parts:
                            if part.startswith('v'):
                                return part[1:]
        except Exception:
            pass
        return None
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual MongoDB restore commands."""
        return f"""
# MongoDB Restore Commands:

# For archive format dumps:
docker exec -i {container_name} mongorestore --archive < {dump_file}

# With authentication:
docker exec -i {container_name} mongorestore \\
    --username root --password yourpassword \\
    --authenticationDatabase admin --archive < {dump_file}

# For specific database:
docker exec -i {container_name} mongorestore --db your_database --archive < {dump_file}

# To list databases after restore:
docker exec {container_name} mongosh --eval "show dbs"
"""


class RedisRestore(DatabaseRestoreStrategy):
    """Redis restore strategy."""
    
    def wait_until_ready(self, container_name: str, max_attempts: int = 30) -> bool:
        """Wait for Redis to be ready."""
        for i in range(max_attempts):
            try:
                result = subprocess.run(
                    ['docker', 'exec', container_name, 'redis-cli', 'ping'],
                    capture_output=True,
                    timeout=5
                )
                
                if b'PONG' in result.stdout:
                    return True
                    
            except Exception:
                pass
            
            time.sleep(2)
        
        return False
    
    def restore(self, container_name: str, dump_file: Path,
               metadata: Optional[Dict[str, Any]], version: Optional[str]) -> bool:
        """Restore Redis database."""
        try:
            # Redis restore is different - we need to copy RDB file and restart
            
            # First, copy the dump file to container
            result = subprocess.run(
                ['docker', 'cp', str(dump_file), f'{container_name}:/data/dump.rdb'],
                capture_output=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to copy RDB file: {result.stderr}")
                return False
            
            # Set correct permissions
            subprocess.run(
                ['docker', 'exec', container_name, 'chown', 'redis:redis', '/data/dump.rdb'],
                capture_output=True
            )
            
            # Restart Redis to load the dump
            result = subprocess.run(
                ['docker', 'restart', container_name],
                capture_output=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to restart Redis: {result.stderr}")
                return False
            
            # Wait for Redis to come back up
            time.sleep(5)
            return self.wait_until_ready(container_name, max_attempts=15)
            
        except Exception as e:
            logger.error(f"Redis restore failed: {e}")
            return False
    
    def verify_restore(self, container_name: str) -> bool:
        """Verify Redis restore."""
        try:
            # Check if we have keys
            result = subprocess.run(
                ['docker', 'exec', container_name, 'redis-cli', 'DBSIZE'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Parse output like "(integer) 42"
                output = result.stdout.strip()
                if '(integer)' in output:
                    count = int(output.split()[-1])
                    return count > 0
            
        except Exception as e:
            logger.error(f"Redis verification failed: {e}")
        
        return False
    
    def detect_version(self, container_name: str) -> Optional[str]:
        """Detect Redis version."""
        try:
            result = subprocess.run(
                ['docker', 'exec', container_name, 'redis-server', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                for part in parts:
                    if part.startswith('v='):
                        return part[2:]
        except Exception:
            pass
        return None
    
    def get_manual_commands(self, container_name: str, dump_file: Path,
                           metadata: Optional[Dict[str, Any]]) -> str:
        """Get manual Redis restore commands."""
        return f"""
# Redis Restore Commands:

# Copy RDB file and restart:
docker cp {dump_file} {container_name}:/data/dump.rdb
docker exec {container_name} chown redis:redis /data/dump.rdb  
docker restart {container_name}

# Alternative using redis-cli (if RDB format):
docker exec -i {container_name} redis-cli --rdb - < {dump_file}

# To check key count after restore:
docker exec {container_name} redis-cli DBSIZE
docker exec {container_name} redis-cli INFO keyspace
"""