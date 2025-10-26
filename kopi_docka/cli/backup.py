"""
Backup commands for Kopi-Docka v2

Docker backup and restore commands with Rich CLI.
"""

from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language

# Create sub-app for backup commands
app = typer.Typer(
    help="Backup and restore commands",
)

console = Console()


@app.command(name="list")
def backup_list(
    units: bool = typer.Option(True, "--units", help="List discovered backup units"),
    snapshots: bool = typer.Option(False, "--snapshots", help="List repository snapshots"),
):
    """
    List backup units or repository snapshots
    
    Shows discovered Docker containers/volumes or existing Kopia snapshots.
    """
    from kopi_docka.cores.docker_discovery import DockerDiscovery
    from kopi_docka.config import load_backend_config
    from kopi_docka.cores.repository_manager import KopiaRepository
    from kopi_docka.helpers.config import Config
    
    # Check sudo
    utils.require_sudo("backup list")
    
    lang = get_current_language()
    
    if not (units or snapshots):
        units = True
    
    try:
        if units:
            utils.print_header(
                "Docker Backup Units",
                "Discovered containers and volumes"
            )
            
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            
            if not found:
                utils.print_warning("No backup units found")
                return
            
            # Create table
            table = utils.create_table(
                "Backup Units",
                [
                    ("Name", "cyan", 25),
                    ("Type", "white", 12),
                    ("Containers", "green", 12),
                    ("Volumes", "yellow", 10),
                    ("Status", "white", 15),
                ]
            )
            
            for unit in found:
                unit_type = "🐳 Stack" if unit.type == "stack" else "📦 Standalone"
                status = "🟢 Ready" if all(c.is_running for c in unit.containers) else "🔴 Stopped"
                
                table.add_row(
                    unit.name,
                    unit_type,
                    str(len(unit.containers)),
                    str(len(unit.volumes)),
                    status
                )
            
            console.print(table)
            utils.print_info(f"\nTotal: {len(found)} backup units")
        
        if snapshots:
            utils.print_separator()
            utils.print_header(
                "Repository Snapshots",
                "Existing Kopia snapshots"
            )
            
            cfg = Config()
            repo = KopiaRepository(cfg)
            
            if not repo.is_connected():
                utils.print_info("Connecting to repository...")
                repo.connect()
            
            snaps = repo.list_snapshots()
            
            if not snaps:
                utils.print_warning("No snapshots found")
                return
            
            # Create table
            table = utils.create_table(
                "Snapshots",
                [
                    ("ID", "cyan", 12),
                    ("Unit", "white", 20),
                    ("Type", "green", 10),
                    ("Timestamp", "yellow", 20),
                ]
            )
            
            for snap in snaps:
                snap_id = snap.get("id", "")[:10] + "..."
                unit_name = snap.get("tags", {}).get("unit", "-")
                snap_type = snap.get("tags", {}).get("type", "-")
                timestamp = snap.get("timestamp", "-")
                
                table.add_row(snap_id, unit_name, snap_type, timestamp)
            
            console.print(table)
            utils.print_info(f"\nTotal: {len(snaps)} snapshots")
            
    except Exception as e:
        utils.print_error(f"Failed to list: {e}")
        raise typer.Exit(1)


@app.command(name="backup")
def backup_run(
    unit: Optional[List[str]] = typer.Option(None, "--unit", "-u", help="Backup only these units"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate backup without making changes"),
    update_recovery: Optional[bool] = typer.Option(
        None,
        "--update-recovery/--no-update-recovery",
        help="Update disaster recovery bundle"
    ),
):
    """
    Run a cold backup for selected units (or all)
    
    Stops containers, backs up volumes and recipes, then restarts containers.
    """
    from kopi_docka.cores.docker_discovery import DockerDiscovery
    from kopi_docka.cores.backup_manager import BackupManager
    from kopi_docka.cores.dry_run_manager import DryRunReport
    from kopi_docka.helpers.config import Config
    
    # Check sudo
    utils.require_sudo("backup")
    
    lang = get_current_language()
    
    try:
        utils.print_header(
            "🔥 Docker Cold Backup",
            "Backing up Docker containers and volumes"
        )
        
        # Discover units
        utils.print_info("Discovering Docker backup units...")
        discovery = DockerDiscovery()
        all_units = discovery.discover_backup_units()
        
        # Filter by name if specified
        if unit:
            selected = [u for u in all_units if u.name in unit]
            if not selected:
                utils.print_error(f"No units found matching: {', '.join(unit)}")
                raise typer.Exit(1)
        else:
            selected = all_units
        
        if not selected:
            utils.print_warning("No backup units found")
            return
        
        utils.print_success(f"Found {len(selected)} unit(s) to backup")
        
        # Dry run mode
        if dry_run:
            utils.print_separator()
            utils.print_info("🔍 DRY RUN MODE - No changes will be made")
            
            cfg = Config()
            report = DryRunReport(cfg)
            report.generate(selected, update_recovery)
            return
        
        # Real backup
        utils.print_separator()
        cfg = Config()
        backup_manager = BackupManager(cfg)
        
        overall_success = True
        
        for unit_obj in selected:
            utils.print_separator()
            console.print(f"\n[bold cyan]→ Backing up unit: {unit_obj.name}[/bold cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Processing {unit_obj.name}...", total=None)
                
                try:
                    metadata = backup_manager.backup_unit(unit_obj, update_recovery_bundle=update_recovery)
                    
                    progress.update(task, completed=True)
                    
                    if metadata.success:
                        utils.print_success(
                            f"✓ {unit_obj.name} completed in {int(metadata.duration_seconds)}s"
                        )
                        if metadata.kopia_snapshot_ids:
                            utils.print_info(f"   Snapshots: {len(metadata.kopia_snapshot_ids)} created")
                        utils.print_info(f"   Volumes: {metadata.volumes_backed_up} backed up")
                    else:
                        overall_success = False
                        utils.print_error(f"✗ {unit_obj.name} failed in {int(metadata.duration_seconds)}s")
                        for error in metadata.errors:
                            utils.print_warning(f"   - {error}")
                
                except Exception as e:
                    overall_success = False
                    progress.update(task, completed=True)
                    utils.print_error(f"✗ {unit_obj.name} failed: {e}")
        
        # Summary
        utils.print_separator()
        if overall_success:
            utils.print_success("🎉 All backups completed successfully!")
        else:
            utils.print_warning("⚠️  Some backups failed - check logs for details")
            raise typer.Exit(1)
            
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning("Backup cancelled by user")
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Backup failed: {e}")
        raise typer.Exit(1)


@app.command(name="restore")
def backup_restore():
    """
    Launch the interactive restore wizard
    
    Guides you through restoring Docker containers and volumes from backup.
    """
    from kopi_docka.cores.restore_manager import RestoreManager
    from kopi_docka.helpers.config import Config
    
    # Check sudo
    utils.require_sudo("restore")
    
    try:
        utils.print_header(
            "🔄 Docker Restore Wizard",
            "Restore containers and volumes from backup"
        )
        
        cfg = Config()
        restore_manager = RestoreManager(cfg)
        restore_manager.interactive_restore()
        
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning("Restore cancelled by user")
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Restore failed: {e}")
        raise typer.Exit(1)


# Register backup commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register backup commands to main CLI app"""
    main_app.add_typer(app, name="backup")
