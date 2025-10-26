"""
Disaster Recovery commands for Kopi-Docka v2

Create and manage encrypted disaster recovery bundles.
"""

from typing import Optional
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language

# Create sub-app for recovery commands
app = typer.Typer(
    help="Disaster recovery bundle commands",
)

console = Console()


@app.command(name="create")
def recovery_create(
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir", "-o",
        help="Output directory for recovery bundle"
    ),
    no_password_file: bool = typer.Option(
        False,
        "--no-password-file",
        help="Don't create password sidecar file (less secure but more private)"
    ),
):
    """
    Create encrypted disaster recovery bundle
    
    Creates a bundle containing:
    - Kopia repository configuration
    - Kopia password
    - Kopi-Docka configuration
    - Recovery script (recover.sh)
    - Recovery instructions
    - Recent backup status
    
    The bundle is encrypted with AES-256-CBC and a strong random password.
    """
    from kopi_docka.cores.disaster_recovery_manager import DisasterRecoveryManager
    from kopi_docka.helpers.config import Config
    
    # Check sudo
    utils.require_sudo("recovery bundle creation")
    
    utils.print_header(
        "🔐 Disaster Recovery Bundle",
        "Creating encrypted recovery bundle"
    )
    
    try:
        # Load config
        utils.print_info("Loading configuration...")
        cfg = Config()
        
        # Create recovery manager
        recovery_mgr = DisasterRecoveryManager(cfg)
        
        # Determine output directory
        if not output_dir:
            output_dir = Path(
                cfg.get("backup", "recovery_bundle_path", "/backup/recovery")
            ).expanduser()
        
        utils.print_info(f"Output directory: {output_dir}")
        utils.print_separator()
        
        # Create bundle with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating recovery bundle...", total=None)
            
            try:
                bundle_path = recovery_mgr.create_recovery_bundle(
                    output_dir=output_dir,
                    write_password_file=not no_password_file
                )
                progress.update(task, completed=True)
                
            except Exception as e:
                progress.update(task, completed=True)
                utils.print_error(f"Failed to create bundle: {e}")
                raise typer.Exit(1)
        
        # Success
        utils.print_separator()
        utils.print_success("✓ Recovery bundle created successfully!")
        
        console.print()
        console.print(f"[cyan]Archive:[/cyan] {bundle_path}")
        console.print(f"[cyan]README:[/cyan]  {bundle_path}.README")
        
        if not no_password_file:
            password_file = Path(f"{bundle_path}.PASSWORD")
            console.print(f"[cyan]Password:[/cyan] {password_file}")
            console.print()
            utils.print_warning("⚠️  SECURITY WARNING:")
            console.print("  • The password is stored in a separate file")
            console.print("  • Keep the password file SECURE and SEPARATE from the archive")
            console.print("  • Consider moving it to a password manager or secure location")
            console.print("  • Delete it from this location after securing it elsewhere")
        else:
            console.print()
            utils.print_warning("⚠️  PASSWORD NOT SAVED:")
            console.print("  • The encryption password was NOT written to disk")
            console.print("  • Check the logs for the password (if logging is enabled)")
            console.print("  • You MUST store this password securely NOW")
            console.print("  • Without it, the recovery bundle is USELESS")
        
        # Calculate and show checksum
        try:
            import hashlib
            sha256 = hashlib.sha256()
            with open(bundle_path, 'rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()
            
            console.print()
            console.print(f"[cyan]SHA256:[/cyan] {checksum}")
        except Exception:
            pass
        
        # Usage hint
        console.print()
        utils.print_header("📖 Usage")
        console.print("To decrypt and restore on a new system:")
        console.print()
        console.print("  1. Copy the archive to the new system")
        console.print("  2. Decrypt with OpenSSL:")
        console.print(f"     openssl enc -aes-256-cbc -salt -pbkdf2 -d \\")
        console.print(f"       -in {bundle_path.name} \\")
        console.print(f"       -out recovery.tar.gz \\")
        console.print(f"       -pass pass:'<PASSWORD>'")
        console.print()
        console.print("  3. Extract: tar -xzf recovery.tar.gz")
        console.print("  4. Run: sudo ./recover.sh")
        console.print()
        console.print(f"See {bundle_path}.README for detailed instructions")
        
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning("Recovery bundle creation cancelled")
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Failed to create recovery bundle: {e}")
        raise typer.Exit(1)


@app.command(name="info")
def recovery_info(
    bundle: Optional[Path] = typer.Argument(
        None,
        help="Path to recovery bundle (.tar.gz.enc file)"
    ),
):
    """
    Show information about a recovery bundle
    
    Displays metadata from the README file without decrypting the bundle.
    """
    utils.print_header(
        "📦 Recovery Bundle Info",
        "Bundle information and instructions"
    )
    
    # If no bundle specified, list bundles in default location
    if not bundle:
        utils.print_info("Searching for recovery bundles...")
        
        from kopi_docka.helpers.config import Config
        try:
            cfg = Config()
            default_dir = Path(
                cfg.get("backup", "recovery_bundle_path", "/backup/recovery")
            ).expanduser()
        except Exception:
            default_dir = Path("/backup/recovery")
        
        if not default_dir.exists():
            utils.print_warning(f"Recovery bundle directory not found: {default_dir}")
            utils.print_info("Create a bundle with: kopi-docka recovery create")
            raise typer.Exit(1)
        
        # Find all bundles
        bundles = sorted(default_dir.glob("kopi-docka-recovery-*.tar.gz.enc"))
        
        if not bundles:
            utils.print_warning("No recovery bundles found")
            utils.print_info(f"Directory: {default_dir}")
            utils.print_info("Create a bundle with: kopi-docka recovery create")
            raise typer.Exit(1)
        
        # Show list
        utils.print_success(f"Found {len(bundles)} recovery bundle(s):\n")
        
        from rich.table import Table
        table = utils.create_table(
            "Recovery Bundles",
            [
                ("#", "white", 5),
                ("Bundle", "cyan", 60),
                ("Size", "green", 12),
                ("Created", "yellow", 20),
            ]
        )
        
        import os
        from datetime import datetime
        
        for idx, bundle_path in enumerate(bundles, 1):
            size = os.path.getsize(bundle_path)
            size_mb = size / (1024 * 1024)
            created = datetime.fromtimestamp(os.path.getmtime(bundle_path))
            
            table.add_row(
                str(idx),
                bundle_path.name,
                f"{size_mb:.1f} MB",
                created.strftime("%Y-%m-%d %H:%M")
            )
        
        console.print(table)
        console.print()
        utils.print_info("Use: kopi-docka recovery info <path> to see details")
        return
    
    # Show specific bundle info
    bundle = Path(bundle)
    
    if not bundle.exists():
        utils.print_error(f"Bundle not found: {bundle}")
        raise typer.Exit(1)
    
    # Read README file
    readme_path = Path(f"{bundle}.README")
    
    if readme_path.exists():
        console.print(f"\n[cyan]Bundle:[/cyan] {bundle}")
        console.print()
        
        readme_content = readme_path.read_text()
        console.print(readme_content)
    else:
        utils.print_warning("README file not found")
        console.print(f"Expected: {readme_path}")
    
    # Check for password file
    password_path = Path(f"{bundle}.PASSWORD")
    if password_path.exists():
        console.print()
        utils.print_warning("⚠️  Password file exists:")
        console.print(f"  {password_path}")
        console.print("  Keep this file secure!")
    
    # Show file sizes
    import os
    console.print()
    console.print("[cyan]Files:[/cyan]")
    console.print(f"  Bundle:   {os.path.getsize(bundle) / (1024*1024):.1f} MB")
    if readme_path.exists():
        console.print(f"  README:   {os.path.getsize(readme_path)} bytes")
    if password_path.exists():
        console.print(f"  Password: {os.path.getsize(password_path)} bytes")


# Register recovery commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register recovery commands to main CLI app"""
    main_app.add_typer(app, name="recovery")
