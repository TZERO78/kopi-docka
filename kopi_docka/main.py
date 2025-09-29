#!/usr/bin/env python3
"""
Main entry point for the Kopi-Docka command-line tool.

This module handles command-line argument parsing and delegates to appropriate
subcommands for backup, restore, and other operations.
"""

import sys
import argparse
import logging
from pathlib import Path

from .config import Config, create_default_config
from .discovery import DockerDiscovery
from .backup import BackupManager
from .restore import RestoreManager
from .repository import KopiaRepository
from .system_utils import SystemUtils
from .dry_run import DryRunReport
from .constants import DEFAULT_CONFIG_PATHS


def setup_logging(verbose: bool = False):
    """
    Configure logging for the application.
    
    Args:
        verbose: Enable verbose logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_backup(args, config):
    """
    Execute backup command.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    discovery = DockerDiscovery()
    backup_manager = BackupManager(config)
    
    # Determine if recovery bundle should be updated
    update_recovery = None
    if hasattr(args, 'update_recovery'):
        update_recovery = args.update_recovery
    
    if args.dry_run:
        report = DryRunReport(config)
        units = discovery.discover_backup_units()
        report.generate(units, update_recovery_bundle=update_recovery)
        return
    
    units = discovery.discover_backup_units()
    
    if args.unit:
        units = [u for u in units if u.name == args.unit]
        if not units:
            logging.error(f"Backup unit '{args.unit}' not found")
            sys.exit(1)
    
    success_count = 0
    for unit in units:
        metadata = backup_manager.backup_unit(unit, update_recovery_bundle=update_recovery)
        if metadata.success:
            success_count += 1
    
    # Log summary
    logging.info(f"Backup complete: {success_count}/{len(units)} units successful")


def cmd_restore(args, config):
    """
    Execute restore command.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    restore_manager = RestoreManager(config)
    restore_manager.interactive_restore()


def cmd_list(args, config):
    """
    List backups command.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    repo = KopiaRepository(config)
    
    if args.units:
        units = repo.list_backup_units()
        for unit in units:
            print(f"Unit: {unit['name']} - Last backup: {unit['timestamp']}")
    else:
        snapshots = repo.list_snapshots()
        for snap in snapshots:
            print(f"Snapshot: {snap['id']} - {snap['path']} - {snap['timestamp']}")


def cmd_check(args, config):
    """
    Check system requirements.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    utils = SystemUtils()
    
    print("System Check Report")
    print("=" * 50)
    
    # Check Docker
    if utils.check_docker():
        print("✓ Docker is installed and running")
    else:
        print("✗ Docker is not available")
    
    # Check Kopia
    if utils.check_kopia():
        print("✓ Kopia is installed")
    else:
        print("✗ Kopia is not installed")
    
    # Check system resources
    ram_gb = utils.get_available_ram()
    print(f"✓ Available RAM: {ram_gb:.2f} GB")
    print(f"✓ Recommended workers: {utils.get_optimal_workers()}")
    
    # Check repository
    try:
        repo = KopiaRepository(config)
        if repo.is_initialized():
            print("✓ Kopia repository is initialized")
        else:
            print("✗ Kopia repository not initialized")
    except Exception as e:
        print(f"✗ Repository check failed: {e}")


def cmd_config(args, config):
    """
    Configuration management command.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    if args.show:
        config.display()
    elif args.init:
        create_default_config(force=True)
        print("Configuration file created successfully")
    elif args.edit:
        import subprocess
        import os
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.call([editor, str(config.config_file)])


def cmd_install(args, config):
    """
    Install and initialize Kopia repository.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    repo = KopiaRepository(config)
    
    if repo.is_initialized():
        print("Repository already initialized")
        return
    
    repo.initialize()
    print("Kopia repository initialized successfully")


def cmd_daemon(args, config):
    """
    Run in daemon mode.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    from .service import ServiceManager
    
    manager = ServiceManager(config)
    
    if args.oneshot:
        manager.run_oneshot()
    else:
        manager.run_daemon()


def cmd_systemd_install(args, config):
    """
    Install systemd unit files.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    from .service import write_systemd_units
    from pathlib import Path
    
    output_dir = Path('/etc/systemd/system')
    if args.user:
        output_dir = Path.home() / '.config/systemd/user'
    
    write_systemd_units(output_dir)
    
    print("\nNext steps:")
    if args.user:
        print("  systemctl --user daemon-reload")
        print("  systemctl --user enable --now kopi-docka.timer")
    else:
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable --now kopi-docka.timer")


def cmd_disaster_recovery(args, config):
    """
    Create disaster recovery bundle.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration object
    """
    from .disaster_recovery import DisasterRecoveryManager
    from pathlib import Path
    
    manager = DisasterRecoveryManager(config)
    
    output_path = Path(args.output) if args.output else Path.cwd()
    
    print("\n" + "=" * 60)
    print("CREATING DISASTER RECOVERY BUNDLE")
    print("=" * 60)
    
    bundle_path = manager.create_recovery_bundle(output_path)
    
    print("\n✓ Recovery bundle created successfully!")
    print(f"  Bundle: {bundle_path}")
    print(f"  README: {bundle_path}.README")
    print(f"  Password: {bundle_path}.PASSWORD")
    print("\n⚠️  IMPORTANT:")
    print("  1. Store the .PASSWORD file securely")
    print("  2. Keep bundle copies in multiple locations")
    print("  3. Test recovery procedure regularly")
    print("=" * 60)


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        prog='kopi-docka',
        description='Robust backup solution for Docker environments using Kopia'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '-c', '--config',
        type=Path,
        help='Path to configuration file'
    )
    
    subparsers = parser.add_subparsers(
        title='Commands',
        dest='command',
        help='Available commands'
    )
    
    # Backup command
    backup_parser = subparsers.add_parser(
        'backup',
        help='Backup Docker containers and volumes'
    )
    backup_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate backup without making changes'
    )
    backup_parser.add_argument(
        '--unit',
        type=str,
        help='Backup specific unit only'
    )
    backup_parser.add_argument(
        '--update-recovery',
        action='store_true',
        help='Update disaster recovery bundle after backup'
    )
    
    # Restore command
    restore_parser = subparsers.add_parser(
        'restore',
        help='Restore Docker containers and volumes'
    )
    
    # List command
    list_parser = subparsers.add_parser(
        'list',
        help='List available backups'
    )
    list_parser.add_argument(
        '--units',
        action='store_true',
        help='List backup units instead of snapshots'
    )
    
    # Check command
    check_parser = subparsers.add_parser(
        'check',
        help='Check system requirements and status'
    )
    
    # Config command
    config_parser = subparsers.add_parser(
        'config',
        help='Configuration management'
    )
    config_parser.add_argument(
        '--show',
        action='store_true',
        help='Show current configuration'
    )
    config_parser.add_argument(
        '--init',
        action='store_true',
        help='Initialize configuration file'
    )
    config_parser.add_argument(
        '--edit',
        action='store_true',
        help='Edit configuration file'
    )
    
    # Install command
    install_parser = subparsers.add_parser(
        'install',
        help='Initialize Kopia repository'
    )
    
    # Daemon command
    daemon_parser = subparsers.add_parser(
        'daemon',
        help='Run in daemon mode (for systemd)'
    )
    daemon_parser.add_argument(
        '--oneshot',
        action='store_true',
        help='Run once and exit'
    )
    
    # Systemd install command
    systemd_parser = subparsers.add_parser(
        'systemd-install',
        help='Install systemd service files'
    )
    systemd_parser.add_argument(
        '--user',
        action='store_true',
        help='Install as user service'
    )
    
    # Disaster recovery command
    dr_parser = subparsers.add_parser(
        'disaster-recovery',
        help='Create disaster recovery bundle'
    )
    dr_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output directory for recovery bundle'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    setup_logging(args.verbose)
    
    # Load configuration
    config_path = args.config if hasattr(args, 'config') and args.config else None
    config = Config(config_path)
    
    # Execute command
    commands = {
        'backup': cmd_backup,
        'restore': cmd_restore,
        'list': cmd_list,
        'check': cmd_check,
        'config': cmd_config,
        'install': cmd_install,
        'daemon': cmd_daemon,
        'systemd-install': cmd_systemd_install,
        'disaster-recovery': cmd_disaster_recovery,
    }
    
    try:
        commands[args.command](args, config)
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Command failed: {e}")
        if args.verbose:
            logging.exception("Full traceback:")
        sys.exit(1)


if __name__ == '__main__':
    main()