# Kopi-Docka

Docker backup tool using Kopia. Stops containers during backup to ensure data consistency while minimizing downtime through sequential processing.

## What it does

Kopi-Docka is a thin wrapper around Kopia that adds Docker-specific intelligence:

- **Docker-aware**: Discovers containers and groups them (Compose stacks stay together)
- **Smart sequencing**: Stops each group, backs up, restarts - one group at a time
- **Version-aware database handling**: Creates native dumps with version-specific commands
- **Container configs**: Backs up docker-compose.yml and inspect output
- **Automated restore**: Actually restores volumes, databases and restarts containers

Everything else (encryption, deduplication, cloud storage) is handled by Kopia.

## Requirements

- Linux
- Docker 20.10+
- Python 3.8+
- Kopia
- Root/sudo access

## Installation

### Install Kopia

```bash
# Debian/Ubuntu
curl -s https://kopia.io/signing-key | sudo apt-key add -
echo "deb http://packages.kopia.io/apt/ stable main" | sudo tee /etc/apt/sources.list.d/kopia.list
sudo apt update
sudo apt install kopia

# Or direct download
wget https://github.com/kopia/kopia/releases/latest/download/kopia_linux_amd64
chmod +x kopia_linux_amd64
sudo mv kopia_linux_amd64 /usr/local/bin/kopia
```

### Install Kopi-Docka

```bash
git clone https://github.com/yourusername/kopi-docka.git
cd kopi-docka
pip install -e .
```

## Usage

### Initial Setup

```bash
# Create config
kopi-docka config --init

# Initialize repository
kopi-docka install

# Check system
kopi-docka check
```

### Backup

```bash
# Test run (no changes)
kopi-docka backup --dry-run

# Run backup
kopi-docka backup

# Backup with recovery bundle update
kopi-docka backup --update-recovery

# Backup specific stack
kopi-docka backup --unit my-stack
```

Configure automatic recovery bundle updates in config:
```ini
[backup]
# Auto-update recovery bundle after each backup
update_recovery_bundle = true
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3  # Keep last 3 bundles
```

### Restore

```bash
# Interactive restore wizard (actually restores!)
kopi-docka restore

# List backups
kopi-docka list --units
```

The restore process will:
1. Let you select a backup point
2. Stop existing containers (if they exist)
3. Restore volumes automatically
4. Start the stack/containers using original configuration
5. Wait for databases to be ready
6. Import database dumps with version-appropriate commands
7. Verify restore success

Database restore features:
- Waits for database readiness (pg_isready, mysqladmin ping, etc.)
- Tries multiple authentication methods
- Provides exact manual commands if automatic restore fails
- Version-aware restore (handles different DB versions correctly)

## How it Works

1. **Discovery**: Finds all running containers
2. **Grouping**: Docker Compose stacks are treated as single units
3. **Sequential Backup**: For each unit:
   - Stop containers
   - Backup compose files and container configs
   - Backup volumes (tar → Kopia)
   - Backup databases (native dumps → Kopia)
   - Start containers
4. **Storage**: Everything goes into Kopia repository (encrypted, deduplicated)

## Configuration

Default location: `/etc/kopi-docka.conf`

Key settings:
```ini
[kopia]
repository_path = /backup/kopia-repository
compression = zstd

[backup]
parallel_workers = auto  # or specific number
stop_timeout = 30
database_backup = true
```

## Scheduling

### Cron
```bash
0 2 * * * /usr/local/bin/kopi-docka backup >> /var/log/kopi-docka-cron.log 2>&1
```

### Systemd Timer

`/etc/systemd/system/kopi-docka.service`:
```ini
[Unit]
Description=Kopi-Docka Backup
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kopi-docka backup
User=root
```

`/etc/systemd/system/kopi-docka.timer`:
```ini
[Unit]
Description=Daily Backup

[Timer]
OnCalendar=daily
Persistent=true
```

```bash
systemctl enable --now kopi-docka.timer
```

## Database Support

Automatically detects database versions and uses appropriate backup/restore methods:

### PostgreSQL
- Version detection for optimal flags
- Uses `pg_dumpall` for complete backup (databases + roles)
- PostgreSQL 12+: Uses `--no-role-passwords` flag
- Automatic restore with verification

### MySQL
- Version-aware backup strategies
- MySQL 8.0+: Uses `--column-statistics=0` flag
- Secure password handling via environment variables
- Handles authentication plugin differences

### MariaDB
- Detects MariaDB vs MySQL
- MariaDB 10.3+: Uses `mariadb-dump`/`mariadb` commands
- Older versions: Falls back to `mysqldump`/`mysql`
- Automatic version detection

### MongoDB
- Archive format with `mongodump --archive`
- MongoDB 4.0+: Includes `--oplog` for point-in-time
- Handles authentication automatically

### Redis
- RDB snapshot via `redis-cli --rdb`
- Special restore handling (copies RDB file and restarts)
- Preserves all data structures

Credentials are read from container environment variables automatically.

## Performance

RAM-based worker allocation:
- ≤2GB: 1 worker
- ≤4GB: 2 workers
- ≤8GB: 4 workers
- ≤16GB: 8 workers
- >16GB: 12 workers

## Limitations

- Requires stopping containers (cold backup)
- Linux only
- Database restore needs containers running first (handled automatically with wait logic)

## Kopia Features

Kopi-Docka uses Kopia's native features:
- **Storage**: Local, S3, B2, Azure, GCS (configured via repository_path)
- **Encryption**: AES256-GCM by default
- **Deduplication**: Automatic block-level
- **Compression**: zstd by default
- **Verification**: Use `kopia snapshot verify`
- **Mounting**: Use `kopia mount` to browse snapshots

For advanced Kopia features (policies, retention, scheduling), use Kopia directly:
```bash
kopia policy set --global --retention-count-daily=7
kopia maintenance run
```

## Disaster Recovery

Kopi-Docka includes a complete disaster recovery system for when your server fails:

### Create Recovery Bundle

```bash
# Create encrypted recovery bundle with everything needed
kopi-docka disaster-recovery

# Or specify output directory
kopi-docka disaster-recovery --output /safe/location/
```

This creates:
- `kopi-docka-recovery-[timestamp].tar.gz.enc` - Encrypted bundle
- `.README` file - Instructions and password
- `.PASSWORD` file - Just the password (chmod 600)

### What's in the Bundle

The encrypted archive contains:
- Kopia repository configuration
- Repository password (encrypted)
- Cloud storage connection details  
- Your Kopi-Docka configuration
- Automated recovery script
- Step-by-step instructions
- Last backup status

### Recovery Process

On a fresh server:

```bash
# 1. Decrypt the bundle
openssl enc -aes-256-cbc -salt -pbkdf2 -d \
    -in kopi-docka-recovery-*.tar.gz.enc \
    -out recovery.tar.gz \
    -pass pass:'[PASSWORD FROM .README FILE]'

# 2. Extract
tar -xzf recovery.tar.gz
cd kopi-docka-recovery-*

# 3. Run recovery script
sudo ./recover.sh

# 4. Restore your containers
kopi-docka restore
```

### Cloud Storage Recovery

The bundle handles cloud repositories (S3, B2, Azure, GCS):
- Connection details are preserved
- Recovery script prompts for credentials
- Automatic repository reconnection

### Best Practices

1. **Multiple Copies**: Store bundle in several locations:
   - Password manager (encrypted)
   - USB drive in safe
   - Secure cloud storage
   - Printed password in physical safe

2. **Regular Updates**: Create new bundle after major changes

3. **Test Recovery**: Practice on a test server quarterly

4. **Secure the Password**: The `.PASSWORD` file is critical - without it, recovery is impossible

### Database Restore Issues

**PostgreSQL won't restore**
```bash
# Check if PostgreSQL is ready
docker exec container_name pg_isready -U postgres

# Manual restore with different user
docker exec -i container_name psql -U postgres < dump.sql
```

**MySQL/MariaDB authentication fails**
```bash
# Check version
docker exec container_name mysql --version

# Try with password in environment
docker exec -i -e MYSQL_PWD=yourpassword container_name mysql -uroot < dump.sql

# MariaDB 10.3+ uses different client
docker exec -i container_name mariadb -uroot < dump.sql
```

**MongoDB archive format issues**
```bash
# Verify it's archive format
file dump.archive

# Restore with authentication
docker exec -i container_name mongorestore \
  --username root --password pass \
  --authenticationDatabase admin --archive < dump.archive
```

**Redis restore not working**
```bash
# Redis needs RDB file copy and restart
docker cp dump.rdb container_name:/data/dump.rdb
docker exec container_name chown redis:redis /data/dump.rdb
docker restart container_name
```

### General Issues

```bash
# Verbose mode
kopi-docka -v backup

# Check logs
tail -f /var/log/kopi-docka.log

# Docker permissions
sudo usermod -aG docker $USER

# Repository issues
kopi-docka install  # reinitialize
```

## Project Structure

```
kopi_docka/
├── __main__.py       # CLI entry point
├── backup.py         # Backup orchestration
├── backup_db.py      # Database-specific backup logic
├── config.py         # Configuration management
├── constants.py      # Global constants
├── discovery.py      # Docker discovery
├── dry_run.py        # Dry run reports
├── repository.py     # Kopia interface
├── restore.py        # Restore orchestration
├── restore_db.py     # Database-specific restore logic
├── service.py        # Systemd integration & daemon mode
├── system_utils.py   # System utilities
└── types.py          # Data structures
```

## Similar Projects

- **docker-volume-backup**: Simpler, fewer features, no version-aware DB handling
- **Velero**: Kubernetes-focused, more complex
- **restic/borg scripts**: Usually DIY solutions without DB version detection
- **Duplicati/Duplicacy**: Generic backup tools, not Docker-specific

## Technical Details

### Backup Process

For each backup unit:
1. Stop containers gracefully
2. Create metadata snapshot:
   - docker-compose.yml (if exists)
   - Container inspect JSON (for rebuild)
3. Backup volumes (tar → Kopia)
4. Backup databases:
   - Detect version
   - Use version-appropriate dump command
   - Store metadata (version, method)
5. Restart containers

### Restore Process

1. **Volume Restore**: Direct extraction from Kopia
2. **Container Recreation**: 
   - Compose stacks: `docker-compose up -d`
   - Standalone: Rebuild from inspect JSON
3. **Database Restore**:
   - Read backup metadata
   - Wait for DB readiness
   - Apply version-specific restore
   - Verify data presence

### Database Version Detection

The tool automatically detects and handles:
- PostgreSQL 9.x, 10.x, 11.x, 12.x, 13.x, 14.x, 15.x
- MySQL 5.6, 5.7, 8.0
- MariaDB 10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.11
- MongoDB 3.x, 4.x, 5.x, 6.x
- Redis 5.x, 6.x, 7.x

## License

MIT

## Contributing

Pull requests welcome. Please include tests for new features.

## TODO

- [ ] Tests

## Acknowledgments

### Special Thanks

This project wouldn't exist without these amazing tools:

- **[Kopia](https://kopia.io)** - The fantastic backup engine that powers Kopi-Docka
  - Rock-solid deduplication and encryption
  - Cloud storage support out of the box
  - Incredible performance and reliability
  - Thanks to [Jarek Kowalski](https://github.com/jkowalski) and all Kopia contributors!

- **[Docker](https://docker.com)** - The containerization platform we all love
  - For making deployment and isolation simple
  - For the excellent API and tooling
  - For revolutionizing how we deploy software

### Built With

- Python 3.8+ - For clean, maintainable code
- systemd - For robust service management
- OpenSSL - For disaster recovery encryption

### Community

Thanks to everyone who uses, tests, and improves this tool. Your feedback and contributions make open source amazing.

---

*"Standing on the shoulders of giants"* - This tool is just a thin, intelligent layer connecting two excellent projects. All the heavy lifting is done by Kopia and Docker.