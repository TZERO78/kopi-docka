"""
Service mode for Kopi-Docka.

This module provides daemon functionality with systemd integration,
proper logging, and signal handling.
"""

import logging
import signal
import sys
import time
import fcntl
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

try:
    from systemd import journal
    HAS_SYSTEMD = True
except ImportError:
    HAS_SYSTEMD = False


logger = logging.getLogger(__name__)


class SystemdHandler(logging.Handler):
    """
    Log handler that sends messages to systemd journal.
    """
    
    def __init__(self):
        super().__init__()
        self.journal = journal if HAS_SYSTEMD else None
    
    def emit(self, record):
        """Send log record to systemd journal."""
        if not self.journal:
            return
        
        # Map Python log levels to systemd priorities
        priority_map = {
            logging.DEBUG: journal.LOG_DEBUG,
            logging.INFO: journal.LOG_INFO,
            logging.WARNING: journal.LOG_WARNING,
            logging.ERROR: journal.LOG_ERR,
            logging.CRITICAL: journal.LOG_CRIT,
        }
        
        priority = priority_map.get(record.levelno, journal.LOG_INFO)
        
        # Send to journal with metadata
        self.journal.send(
            record.getMessage(),
            PRIORITY=priority,
            LOGGER=record.name,
            CODE_FILE=record.pathname,
            CODE_LINE=record.lineno,
            CODE_FUNC=record.funcName,
            SYSLOG_IDENTIFIER='kopi-docka'
        )


class LockFile:
    """
    Prevents multiple instances from running simultaneously.
    """
    
    def __init__(self, path: str = '/var/run/kopi-docka.lock'):
        """
        Initialize lock file.
        
        Args:
            path: Path to lock file
        """
        self.path = Path(path)
        self.fd = None
    
    def acquire(self) -> bool:
        """
        Try to acquire lock.
        
        Returns:
            True if lock acquired, False if already locked
        """
        try:
            # Ensure directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open or create lock file
            self.fd = open(self.path, 'w')
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write PID to lock file
            self.fd.write(str(os.getpid()))
            self.fd.flush()
            
            return True
            
        except IOError:
            # Lock is held by another process
            if self.fd:
                self.fd.close()
                self.fd = None
            return False
    
    def release(self):
        """Release the lock."""
        if self.fd:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                self.fd.close()
                self.path.unlink(missing_ok=True)
            except Exception:
                pass
            finally:
                self.fd = None
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError("Could not acquire lock - another instance may be running")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


class ServiceManager:
    """
    Manages Kopi-Docka as a service/daemon.
    """
    
    def __init__(self, config):
        """
        Initialize service manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.running = False
        self.lock = LockFile()
        self._setup_signal_handlers()
        self._setup_logging()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGHUP, self._handle_reload)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        
        # Notify systemd we're stopping
        if HAS_SYSTEMD:
            journal.send("Stopping Kopi-Docka service", PRIORITY=journal.LOG_INFO)
    
    def _handle_reload(self, signum, frame):
        """Handle reload signal (SIGHUP)."""
        logger.info("Received SIGHUP, reloading configuration...")
        # In a real implementation, reload config here
        self.config = self.config.__class__(self.config.config_file)
    
    def _setup_logging(self):
        """Setup logging with systemd journal support."""
        root_logger = logging.getLogger()
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler (for non-systemd environments)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        root_logger.addHandler(console_handler)
        
        # Systemd journal handler
        if HAS_SYSTEMD:
            systemd_handler = SystemdHandler()
            root_logger.addHandler(systemd_handler)
        
        # File handler (optional, based on config)
        log_file = self.config.get('logging', 'file')
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(
                    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                )
                root_logger.addHandler(file_handler)
            except Exception as e:
                logger.warning(f"Could not create file handler: {e}")
        
        # Set log level
        level = self.config.get('logging', 'level', 'INFO')
        root_logger.setLevel(getattr(logging, level.upper()))
    
    def notify_systemd(self, state: str, status: Optional[str] = None):
        """
        Notify systemd about service state.
        
        Args:
            state: Service state (READY, STOPPING, etc.)
            status: Optional status message
        """
        if not HAS_SYSTEMD:
            return
        
        try:
            import systemd.daemon
            
            notifications = [f"STATE={state}"]
            if status:
                notifications.append(f"STATUS={status}")
            
            systemd.daemon.notify('\n'.join(notifications))
            
        except ImportError:
            pass
    
    def run_scheduled_backup(self):
        """Run a scheduled backup."""
        from .discovery import DockerDiscovery
        from .backup import BackupManager
        
        try:
            # Notify systemd we're running
            self.notify_systemd("BUSY", "Running scheduled backup")
            
            # Perform backup
            discovery = DockerDiscovery()
            backup_manager = BackupManager(self.config)
            
            units = discovery.discover_backup_units()
            logger.info(f"Starting scheduled backup of {len(units)} units")
            
            success_count = 0
            for unit in units:
                try:
                    metadata = backup_manager.backup_unit(unit)
                    if metadata.success:
                        success_count += 1
                        logger.info(f"Successfully backed up: {unit.name}")
                    else:
                        logger.error(f"Backup failed for: {unit.name}")
                except Exception as e:
                    logger.error(f"Error backing up {unit.name}: {e}")
            
            logger.info(f"Scheduled backup complete: {success_count}/{len(units)} successful")
            
            # Notify systemd we're idle
            self.notify_systemd("READY", f"Last backup: {datetime.now()}")
            
        except Exception as e:
            logger.error(f"Scheduled backup failed: {e}")
            self.notify_systemd("READY", f"Last backup failed: {e}")
    
    def run_daemon(self):
        """
        Run as daemon with scheduled backups.
        
        This is the main service loop when running under systemd.
        """
        logger.info("Starting Kopi-Docka daemon")
        
        # Try to acquire lock
        if not self.lock.acquire():
            logger.error("Another instance is already running")
            sys.exit(1)
        
        try:
            self.running = True
            
            # Notify systemd we're ready
            self.notify_systemd("READY", "Waiting for scheduled backup")
            
            # Calculate next backup time
            schedule_enabled = self.config.getboolean('schedule', 'enabled')
            if not schedule_enabled:
                logger.warning("Scheduled backups are disabled in configuration")
                # Keep running for manual triggers via systemd
                while self.running:
                    time.sleep(60)
                return
            
            # Parse schedule
            daily_time = self.config.get('schedule', 'daily_at', '02:00')
            hour, minute = map(int, daily_time.split(':'))
            
            while self.running:
                now = datetime.now()
                
                # Calculate next run time
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
                
                # Wait until next run or shutdown
                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"Next backup scheduled at {next_run}")
                
                # Wait with periodic checks for shutdown
                waited = 0
                while waited < wait_seconds and self.running:
                    time.sleep(min(60, wait_seconds - waited))
                    waited += 60
                
                # Run backup if still running
                if self.running:
                    self.run_scheduled_backup()
            
        finally:
            self.lock.release()
            logger.info("Kopi-Docka daemon stopped")
    
    def run_oneshot(self):
        """
        Run single backup and exit (for systemd timer usage).
        """
        logger.info("Running one-shot backup")
        
        with self.lock:
            self.run_scheduled_backup()
        
        logger.info("One-shot backup complete")


def write_systemd_units(output_dir: Path = Path('/etc/systemd/system')):
    """
    Write systemd service and timer unit files.
    
    Args:
        output_dir: Directory to write unit files to
    """
    # Service unit for daemon mode
    service_content = """[Unit]
Description=Kopi-Docka Docker Backup Service
Documentation=https://github.com/yourusername/kopi-docka
After=docker.service
Requires=docker.service

[Service]
Type=notify
ExecStart=/usr/local/bin/kopi-docka daemon
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kopi-docka

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/backup /var/lib/docker /var/run/docker.sock /var/log
RuntimeDirectory=kopi-docka
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
"""
    
    # Timer unit for scheduled backups (alternative to daemon)
    timer_content = """[Unit]
Description=Daily Kopi-Docka Backup
Documentation=https://github.com/yourusername/kopi-docka

[Timer]
OnCalendar=daily
OnCalendar=02:00:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
"""
    
    # One-shot service for timer
    oneshot_content = """[Unit]
Description=Kopi-Docka Docker Backup
Documentation=https://github.com/yourusername/kopi-docka
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kopi-docka backup
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kopi-docka-backup

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/backup /var/lib/docker /var/run/docker.sock /var/log
"""
    
    # Write files
    output_dir.mkdir(parents=True, exist_ok=True)
    
    (output_dir / 'kopi-docka.service').write_text(service_content)
    (output_dir / 'kopi-docka.timer').write_text(timer_content)
    (output_dir / 'kopi-docka-backup.service').write_text(oneshot_content)
    
    print(f"Systemd units written to {output_dir}")
    print("\nTo enable daemon mode:")
    print("  systemctl daemon-reload")
    print("  systemctl enable --now kopi-docka.service")
    print("\nTo enable timer mode:")
    print("  systemctl daemon-reload")
    print("  systemctl enable --now kopi-docka.timer")
