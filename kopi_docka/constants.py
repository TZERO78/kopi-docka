"""
Constants used throughout the Kopi-Docka application.

This module defines all constant values used across different modules
to ensure consistency and ease of maintenance.
"""

import os
from pathlib import Path

# Version information
VERSION = "1.0.0"

# Default paths
DEFAULT_CONFIG_PATHS = {
    'root': Path('/etc/kopi-docka.conf'),
    'user': Path.home() / '.config' / 'kopi-docker' / 'config.conf'
}

# Docker labels
DOCKER_COMPOSE_PROJECT_LABEL = 'com.docker.compose.project'
DOCKER_COMPOSE_CONFIG_LABEL = 'com.docker.compose.project.config_files'
DOCKER_COMPOSE_SERVICE_LABEL = 'com.docker.compose.service'

# Backup paths
DEFAULT_BACKUP_BASE = '/backup/kopi-docka'
RECIPE_BACKUP_DIR = 'recipes'
VOLUME_BACKUP_DIR = 'volumes'
DATABASE_BACKUP_DIR = 'databases'

# Database detection patterns
DATABASE_IMAGES = {
    'postgres': {
        'patterns': ['postgres:', 'postgresql:', 'postgis/'],
        'dump_command': 'pg_dumpall -U {user}',
        'env_user': 'POSTGRES_USER',
        'default_user': 'postgres'
    },
    'mysql': {
        'patterns': ['mysql:', 'mariadb:', 'percona:'],
        'dump_command': 'mysqldump --all-databases -u{user} -p{password}',
        'env_user': 'MYSQL_USER',
        'env_password': 'MYSQL_PASSWORD',
        'env_root_password': 'MYSQL_ROOT_PASSWORD',
        'default_user': 'root'
    },
    'mongodb': {
        'patterns': ['mongo:', 'mongodb:'],
        'dump_command': 'mongodump --archive',
        'env_user': 'MONGO_INITDB_ROOT_USERNAME',
        'env_password': 'MONGO_INITDB_ROOT_PASSWORD'
    },
    'redis': {
        'patterns': ['redis:', 'redis/'],
        'dump_command': 'redis-cli --rdb -',
        'env_password': 'REDIS_PASSWORD'
    }
}

# System thresholds
RAM_WORKER_THRESHOLDS = [
    (2, 1),    # <= 2GB: 1 worker
    (4, 2),    # <= 4GB: 2 workers
    (8, 4),    # <= 8GB: 4 workers
    (16, 8),   # <= 16GB: 8 workers
    (float('inf'), 12)  # > 16GB: 12 workers
]

# Timeouts (in seconds)
CONTAINER_STOP_TIMEOUT = 30
CONTAINER_START_TIMEOUT = 60
BACKUP_OPERATION_TIMEOUT = 3600  # 1 hour

# Logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'