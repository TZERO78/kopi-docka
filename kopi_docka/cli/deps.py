"""
Dependency commands for Kopi-Docka v2

System requirements and dependency management.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language

# Create sub-app for dependency commands
app = typer.Typer(
    help="Dependency and system requirements commands",
)

console = Console()


@app.command(name="check")
def deps_check(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """
    Check system requirements and dependencies
    
    Verifies that all required tools (Docker, Kopia, etc.) are installed.
    """
    from kopi_docka.cores.dependency_manager import DependencyManager
    from kopi_docka.cores.repository_manager import KopiaRepository
    from kopi_docka.helpers.config import Config
    from pathlib import Path
    
    utils.print_header(
        "System Dependencies Check",
        "Checking required tools and configuration"
    )
    
    # Use DependencyManager's built-in print_status method
    deps = DependencyManager()
    deps.print_status(verbose=verbose)
    
    # Repository check (if config exists)
    utils.print_separator()
    utils.print_header("Configuration Check")
    
    config_paths = [
        Path("/etc/kopi-docka.conf"),
        Path.home() / ".config" / "kopi-docka" / "config.conf"
    ]
    
    config_found = False
    for config_path in config_paths:
        if config_path.exists():
            config_found = True
            utils.print_success(f"Config found: {config_path}")
            
            try:
                cfg = Config(config_path)
                repo = KopiaRepository(cfg)
                
                if repo.is_connected():
                    utils.print_success("✓ Kopia repository is connected")
                    if verbose:
                        utils.print_info(f"  Profile: {repo.profile_name}")
                        utils.print_info(f"  Repository: {repo.repo_path}")
                        try:
                            snapshots = repo.list_snapshots()
                            utils.print_info(f"  Snapshots: {len(snapshots)}")
                        except Exception:
                            pass
                else:
                    utils.print_warning("✗ Kopia repository not connected")
                    utils.print_info("  Run: kopi-docka repo init")
            except Exception as e:
                utils.print_warning(f"✗ Repository check failed: {e}")
            break
    
    if not config_found:
        utils.print_warning("✗ No configuration found")
        utils.print_info("  Run: kopi-docka setup backend")
    
    # Summary
    utils.print_separator()
    missing = deps.get_missing()
    if missing:
        utils.print_error(f"Missing {len(missing)} required dependencies")
        utils.print_info("Run: kopi-docka deps install")
        raise typer.Exit(1)
    else:
        utils.print_success("✓ All required dependencies installed")
        if not config_found:
            utils.print_info("\n💡 Next: kopi-docka setup backend")


@app.command(name="install")
def deps_install(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be installed"),
):
    """
    Install missing system dependencies
    
    Automatically installs required tools like Docker and Kopia.
    """
    from kopi_docka.cores.dependency_manager import DependencyManager
    from pathlib import Path
    
    # Check sudo
    utils.require_sudo("dependency installation")
    
    utils.print_header(
        "Dependency Installation",
        "Installing missing system requirements"
    )
    
    deps = DependencyManager()
    missing = deps.get_missing()
    
    if not missing:
        utils.print_success("✓ All required dependencies already installed")
        
        # Check config hint
        config_paths = [
            Path("/etc/kopi-docka.conf"),
            Path.home() / ".config" / "kopi-docka" / "config.conf"
        ]
        if not any(p.exists() for p in config_paths):
            utils.print_info("\n💡 Next: kopi-docka setup backend")
        return
    
    # Show what will be installed
    utils.print_info(f"Found {len(missing)} missing dependencies:\n")
    for dep_name in missing:
        console.print(f"  • [cyan]{dep_name}[/cyan]")
    
    console.print()
    
    # Dry run mode
    if dry_run:
        utils.print_info("🔍 DRY RUN MODE - Showing installation commands\n")
        deps.install_missing(dry_run=True)
        return
    
    # Confirm installation
    if not force:
        utils.print_separator()
        if not typer.confirm("Install missing dependencies?", default=True):
            utils.print_warning("Installation cancelled")
            raise typer.Exit(0)
    
    # Install
    utils.print_separator()
    console.print()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Installing dependencies...", total=None)
        
        try:
            success = deps.auto_install(force=True)
            progress.update(task, completed=True)
            
            if success:
                utils.print_success(f"\n✓ Installed {len(missing)} dependencies")
                
                # Hint about next steps
                config_paths = [
                    Path("/etc/kopi-docka.conf"),
                    Path.home() / ".config" / "kopi-docka" / "config.conf"
                ]
                if not any(p.exists() for p in config_paths):
                    utils.print_info("\n💡 Next: kopi-docka setup backend")
            else:
                utils.print_error("\n✗ Installation failed")
                raise typer.Exit(1)
                
        except Exception as e:
            progress.update(task, completed=True)
            utils.print_error(f"\n✗ Installation error: {e}")
            raise typer.Exit(1)


@app.command(name="guide")
def deps_guide():
    """
    Show dependency installation guide
    
    Displays manual installation instructions for all dependencies.
    """
    from kopi_docka.cores.dependency_manager import DependencyManager
    
    utils.print_header(
        "Dependency Installation Guide",
        "Manual installation instructions"
    )
    
    deps = DependencyManager()
    deps.print_install_guide()


# Register dependency commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register dependency commands to main CLI app"""
    main_app.add_typer(app, name="deps")
