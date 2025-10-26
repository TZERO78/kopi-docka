"""
Service commands for Kopi-Docka v2

Systemd service and daemon management.
"""

import subprocess
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language

# Create sub-app for service commands
app = typer.Typer(
    help="Systemd service and daemon commands",
)

console = Console()


@app.command(name="daemon")
def service_daemon(
    interval_minutes: Optional[int] = typer.Option(
        None,
        "--interval-minutes",
        help="Run backup every N minutes (default: from config)"
    ),
    backup_cmd: str = typer.Option(
        "/usr/bin/env kopi-docka backup",
        "--backup-cmd",
        help="Command to run for backups"
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Logging level (DEBUG/INFO/WARNING/ERROR)"
    ),
):
    """
    Run the systemd-friendly daemon (service mode)
    
    This command runs continuously and executes backups at regular intervals.
    Designed to be run as a systemd service.
    """
    from kopi_docka.cores.service_manager import KopiDockaService, ServiceConfig
    
    utils.print_header(
        "🔄 Kopi-Docka Service Daemon",
        "Running automated backup service"
    )
    
    console.print(f"[cyan]Backup Command:[/cyan] {backup_cmd}")
    if interval_minutes:
        console.print(f"[cyan]Interval:[/cyan] {interval_minutes} minutes")
    console.print(f"[cyan]Log Level:[/cyan] {log_level}")
    console.print()
    
    utils.print_info("Starting daemon... (Ctrl+C to stop)")
    utils.print_separator()
    
    try:
        cfg = ServiceConfig(
            backup_cmd=backup_cmd,
            interval_minutes=interval_minutes,
            log_level=log_level,
        )
        svc = KopiDockaService(cfg)
        rc = svc.start()
        raise typer.Exit(code=rc)
        
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning("Daemon stopped by user")
        raise typer.Exit(0)
    except Exception as e:
        utils.print_error(f"Daemon failed: {e}")
        raise typer.Exit(1)


@app.command(name="install")
def service_install(
    output_dir: Path = typer.Option(
        Path("/etc/systemd/system"),
        "--output-dir", "-o",
        help="Directory for systemd unit files"
    ),
    interval: str = typer.Option(
        "daily",
        "--interval",
        help="Backup interval (daily, hourly, or custom systemd timer spec)"
    ),
):
    """
    Install systemd service and timer units
    
    Creates systemd service and timer files for automated backups.
    Requires root/sudo privileges.
    """
    from kopi_docka.cores.service_manager import write_systemd_units
    
    # Check sudo
    utils.require_sudo("systemd unit installation")
    
    utils.print_header(
        "📦 Install Systemd Service",
        "Creating service and timer units"
    )
    
    console.print(f"[cyan]Output Directory:[/cyan] {output_dir}")
    console.print(f"[cyan]Backup Interval:[/cyan] {interval}")
    console.print()
    
    if not output_dir.exists():
        utils.print_error(f"Directory not found: {output_dir}")
        utils.print_info("Create it or specify a different --output-dir")
        raise typer.Exit(1)
    
    try:
        # Write unit files
        utils.print_info("Writing systemd unit files...")
        write_systemd_units(output_dir)
        
        service_file = output_dir / "kopi-docka.service"
        timer_file = output_dir / "kopi-docka.timer"
        
        utils.print_separator()
        utils.print_success("✓ Unit files created:")
        console.print(f"  • {service_file}")
        console.print(f"  • {timer_file}")
        
        # Reload systemd
        console.print()
        utils.print_info("Reloading systemd daemon...")
        try:
            subprocess.run(
                ["systemctl", "daemon-reload"],
                check=True,
                capture_output=True
            )
            utils.print_success("✓ Systemd daemon reloaded")
        except subprocess.CalledProcessError as e:
            utils.print_warning(f"⚠️  Failed to reload systemd: {e}")
        
        # Show next steps
        utils.print_separator()
        utils.print_header("📖 Next Steps")
        console.print()
        console.print("[yellow]1. Enable and start the timer:[/yellow]")
        console.print("   sudo systemctl enable --now kopi-docka.timer")
        console.print()
        console.print("[yellow]2. Check status:[/yellow]")
        console.print("   systemctl status kopi-docka.timer")
        console.print("   systemctl status kopi-docka.service")
        console.print()
        console.print("[yellow]3. View logs:[/yellow]")
        console.print("   journalctl -u kopi-docka.service -f")
        
    except Exception as e:
        utils.print_error(f"Failed to install units: {e}")
        raise typer.Exit(1)


@app.command(name="status")
def service_status():
    """
    Show systemd service status
    
    Displays the current status of the kopi-docka service and timer.
    """
    utils.print_header(
        "📊 Service Status",
        "Systemd service and timer information"
    )
    
    # Check if units exist
    service_exists = Path("/etc/systemd/system/kopi-docka.service").exists()
    timer_exists = Path("/etc/systemd/system/kopi-docka.timer").exists()
    
    if not service_exists and not timer_exists:
        utils.print_warning("⚠️  Systemd units not installed")
        console.print()
        utils.print_info("Install with: kopi-docka service install")
        raise typer.Exit(1)
    
    # Create status table
    table = utils.create_table(
        "Systemd Units",
        [
            ("Unit", "cyan", 30),
            ("Status", "white", 15),
            ("Active", "green", 15),
            ("Details", "white", 40),
        ]
    )
    
    # Check service status
    for unit_name in ["kopi-docka.service", "kopi-docka.timer"]:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", unit_name],
                capture_output=True,
                text=True
            )
            is_active = result.stdout.strip()
            active_color = "green" if is_active == "active" else "red"
            
            # Get enabled status
            result_enabled = subprocess.run(
                ["systemctl", "is-enabled", unit_name],
                capture_output=True,
                text=True
            )
            is_enabled = result_enabled.stdout.strip()
            
            # Get status details
            result_status = subprocess.run(
                ["systemctl", "status", unit_name, "--no-pager", "-l"],
                capture_output=True,
                text=True
            )
            
            # Extract first line of status
            status_lines = result_status.stdout.split('\n')
            status_detail = ""
            for line in status_lines[1:4]:  # Get a few lines
                if line.strip():
                    status_detail = line.strip()[:40]
                    break
            
            status = "✓ Installed" if service_exists or timer_exists else "✗ Missing"
            
            table.add_row(
                unit_name,
                status,
                f"[{active_color}]{is_active}[/{active_color}] ({is_enabled})",
                status_detail or "-"
            )
            
        except Exception as e:
            table.add_row(
                unit_name,
                "✗ Error",
                "-",
                str(e)[:40]
            )
    
    console.print(table)
    
    # Show recent logs
    console.print()
    utils.print_header("Recent Logs")
    try:
        result = subprocess.run(
            ["journalctl", "-u", "kopi-docka.service", "-n", "5", "--no-pager"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            console.print(result.stdout)
        else:
            utils.print_info("No recent logs")
    except Exception as e:
        utils.print_warning(f"Could not fetch logs: {e}")
    
    # Show timer schedule
    console.print()
    utils.print_header("Timer Schedule")
    try:
        result = subprocess.run(
            ["systemctl", "list-timers", "kopi-docka.timer", "--no-pager"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            console.print(result.stdout)
        else:
            utils.print_info("Timer not scheduled")
    except Exception as e:
        utils.print_warning(f"Could not fetch timer info: {e}")


@app.command(name="enable")
def service_enable():
    """
    Enable and start the systemd timer
    
    Activates automatic backups according to the timer schedule.
    """
    # Check sudo
    utils.require_sudo("service enable")
    
    utils.print_header(
        "🚀 Enable Service",
        "Activating automatic backups"
    )
    
    try:
        utils.print_info("Enabling kopi-docka.timer...")
        subprocess.run(
            ["systemctl", "enable", "--now", "kopi-docka.timer"],
            check=True,
            capture_output=True
        )
        
        utils.print_success("✓ Timer enabled and started")
        console.print()
        console.print("Automatic backups are now active.")
        console.print()
        console.print("Check status with:")
        console.print("  kopi-docka service status")
        
    except subprocess.CalledProcessError as e:
        utils.print_error(f"Failed to enable timer: {e}")
        console.print()
        console.print("Make sure systemd units are installed:")
        console.print("  kopi-docka service install")
        raise typer.Exit(1)


@app.command(name="disable")
def service_disable():
    """
    Disable and stop the systemd timer
    
    Deactivates automatic backups.
    """
    # Check sudo
    utils.require_sudo("service disable")
    
    utils.print_header(
        "🛑 Disable Service",
        "Deactivating automatic backups"
    )
    
    try:
        utils.print_info("Disabling kopi-docka.timer...")
        subprocess.run(
            ["systemctl", "disable", "--now", "kopi-docka.timer"],
            check=True,
            capture_output=True
        )
        
        utils.print_success("✓ Timer disabled and stopped")
        console.print()
        console.print("Automatic backups are now inactive.")
        console.print()
        console.print("Re-enable with:")
        console.print("  kopi-docka service enable")
        
    except subprocess.CalledProcessError as e:
        utils.print_error(f"Failed to disable timer: {e}")
        raise typer.Exit(1)


@app.command(name="logs")
def service_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of log lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
):
    """
    Show service logs
    
    Displays journalctl logs for the kopi-docka service.
    """
    utils.print_header(
        "📜 Service Logs",
        f"Last {lines} lines from kopi-docka.service"
    )
    
    cmd = ["journalctl", "-u", "kopi-docka.service", "-n", str(lines), "--no-pager"]
    
    if follow:
        cmd.remove("--no-pager")
        cmd.append("-f")
        utils.print_info("Following logs... (Ctrl+C to stop)")
        console.print()
    
    try:
        if follow:
            # Interactive follow mode
            subprocess.run(cmd)
        else:
            # One-time output
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.stdout.strip():
                console.print(result.stdout)
            else:
                utils.print_info("No logs found")
                console.print()
                console.print("Service might not have run yet.")
                console.print("Check status: kopi-docka service status")
    
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_info("Stopped following logs")
    except Exception as e:
        utils.print_error(f"Failed to show logs: {e}")
        raise typer.Exit(1)


# Register service commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register service commands to main CLI app"""
    main_app.add_typer(app, name="service")
