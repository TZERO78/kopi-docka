"""
Complete Setup Wizard for Kopi-Docka v2

Guides users through the entire setup process:
1. Dependencies check & installation
2. Backend selection
3. Backend configuration
4. Repository initialization
"""

import shutil
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape

from kopi_docka.cli import utils
from kopi_docka.i18n import t, get_current_language
from kopi_docka.config import save_backend_config, update_repository_status
from kopi_docka.helpers.dependency_installer import DependencyInstaller

console = Console()


def run_setup_wizard(language: Optional[str] = None):
    """
    Complete setup wizard that guides user through everything
    
    Steps:
    1. Check & install core dependencies (Kopia)
    2. Select backend
    3. Check & install backend-specific dependencies
    4. Configure backend
    5. Initialize repository
    """
    from kopi_docka.i18n import set_language
    from kopi_docka.config import load_backend_config
    
    # Check sudo FIRST
    utils.require_sudo("setup wizard")
    
    # Check if config already exists (idempotency)
    existing_config = load_backend_config()
    if existing_config:
        backend_type = existing_config.get("backend_type", "unknown")
        utils.print_warning(f"Existing configuration found ({backend_type} backend)")
        
        if not utils.prompt_confirm("Overwrite existing configuration?", default=False):
            utils.print_info("Keeping existing configuration")
            raise typer.Exit(0)
        
        utils.print_info("Proceeding with new setup...")
    
    # Set language if provided
    if language:
        try:
            set_language(language)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {escape(str(e))}")
            raise typer.Exit(1)
    
    lang = get_current_language()
    
    # Welcome
    utils.print_header(
        "🔥 Kopi-Docka Setup Wizard",
        "Complete backup system configuration"
    )
    
    try:
        # Step 1: Core Dependencies
        if not check_and_install_core_dependencies():
            utils.print_error("Failed to install core dependencies")
            raise typer.Exit(1)
        
        # Step 2: Backend Selection
        backend_type = select_backend()
        
        # Step 3: Backend Dependencies
        if not check_and_install_backend_dependencies(backend_type):
            utils.print_error(f"Failed to install {backend_type} backend dependencies")
            raise typer.Exit(1)
        
        # Step 4: Backend Configuration
        utils.print_separator()
        utils.print_header("📦 Backend Configuration")
        
        backend_config = configure_backend(backend_type)
        
        if not backend_config:
            utils.print_warning("Setup cancelled")
            raise typer.Exit(1)
        
        # Step 5: Save Config
        utils.print_separator()
        utils.print_info("Saving configuration...")
        
        config_path = save_backend_config(backend_type, backend_config)
        utils.print_success(f"Configuration saved to: {config_path}")
        
        # Step 6: Repository Initialization
        utils.print_separator()
        
        if utils.prompt_confirm("Initialize repository now?", default=True):
            if initialize_repository():
                utils.print_success("Repository initialized successfully!")
            else:
                utils.print_warning("Repository initialization failed")
                utils.print_info("You can initialize later with: kopi-docka repo init")
        else:
            utils.print_info("Skipped repository initialization")
            utils.print_info("Run 'kopi-docka repo init' when ready")
        
        # Step 7: Success Summary
        show_success_summary(backend_type, backend_config)
        
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning("Setup cancelled by user")
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Setup failed: {e}")
        raise typer.Exit(1)


def check_and_install_core_dependencies() -> bool:
    """Check and install core dependencies (Kopia)"""
    utils.print_separator()
    utils.print_header("🔍 Checking Core Dependencies")
    
    # Check Kopia
    if shutil.which("kopia"):
        utils.print_success("✓ Kopia found")
        return True
    else:
        utils.print_warning("✗ Kopia not found")
        
        if utils.prompt_confirm("Install Kopia?", default=True):
            utils.print_info("Installing Kopia...")
            installer = DependencyInstaller()
            
            if installer.install_kopia():
                utils.print_success("✓ Kopia installed successfully!")
                return True
            else:
                utils.print_error("✗ Kopia installation failed")
                return False
        else:
            utils.print_error("Kopia is required for backups")
            return False


def select_backend() -> str:
    """Interactive backend selection"""
    utils.print_separator()
    utils.print_header("📦 Backend Selection")
    
    backends = {
        "local": {
            "name": "📁 Local Filesystem",
            "desc": "Store backups on local disk or NAS",
            "extra_tools": []
        },
        "tailscale": {
            "name": "🔥 Tailscale Network",
            "desc": "Secure offsite backups via Tailscale (Recommended!)",
            "extra_tools": ["tailscale"]
        },
        "rclone": {
            "name": "☁️  Rclone / Cloud Storage",
            "desc": "70+ cloud providers supported",
            "extra_tools": ["rclone"]
        }
    }
    
    # Show backends
    for key, info in backends.items():
        console.print(f"\n[cyan]{info['name']}[/cyan]")
        console.print(f"  {info['desc']}")
        if info['extra_tools']:
            console.print(f"  [dim]Requires: {', '.join(info['extra_tools'])}[/dim]")
    
    # Prompt for selection
    options = list(backends.keys())
    selected = utils.prompt_select(
        "\nSelect backend",
        options,
        display_fn=lambda k: backends[k]["name"]
    )
    
    return selected


def check_and_install_backend_dependencies(backend_type: str) -> bool:
    """Check and install backend-specific dependencies"""
    utils.print_separator()
    utils.print_header(f"🔍 Checking {backend_type.title()} Dependencies")
    
    # Filesystem needs nothing extra
    if backend_type == "local":
        utils.print_success("✓ No extra tools needed for filesystem backend")
        return True
    
    # Tailscale backend
    elif backend_type == "tailscale":
        if shutil.which("tailscale"):
            utils.print_success("✓ Tailscale found")
            return True
        else:
            utils.print_warning("✗ Tailscale not found")
            
            if utils.prompt_confirm("Install Tailscale?", default=True):
                utils.print_info("Installing Tailscale...")
                installer = DependencyInstaller()
                
                if installer.install_tailscale():
                    utils.print_success("✓ Tailscale installed!")
                    utils.print_warning("Please run 'sudo tailscale up' to connect")
                    
                    if utils.prompt_confirm("Connect to Tailscale now?", default=True):
                        import subprocess
                        try:
                            subprocess.run(["sudo", "tailscale", "up"], check=True)
                            utils.print_success("✓ Connected to Tailscale")
                        except subprocess.CalledProcessError:
                            utils.print_warning("Failed to connect. Please run 'sudo tailscale up' manually")
                    
                    return True
                else:
                    utils.print_error("✗ Tailscale installation failed")
                    return False
            else:
                utils.print_error("Tailscale is required for this backend")
                return False
    
    # Rclone backend
    elif backend_type == "rclone":
        if shutil.which("rclone"):
            utils.print_success("✓ Rclone found")
            return True
        else:
            utils.print_warning("✗ Rclone not found")
            
            if utils.prompt_confirm("Install Rclone?", default=True):
                utils.print_info("Installing Rclone...")
                installer = DependencyInstaller()
                
                if installer.install_rclone():
                    # Double-check if rclone is now available
                    if shutil.which("rclone"):
                        utils.print_success("✓ Rclone installed!")
                        return True
                    else:
                        utils.print_error("✗ Rclone installed but not in PATH. Please restart terminal.")
                        return False
                else:
                    utils.print_error("✗ Rclone installation failed")
                    return False
            else:
                utils.print_error("Rclone is required for this backend")
                return False
    
    return True


def configure_backend(backend_type: str) -> Optional[dict]:
    """Configure selected backend"""
    if backend_type == "local":
        from kopi_docka.backends.filesystem import FilesystemBackend
        backend = FilesystemBackend()
        return backend.setup_interactive()
    
    elif backend_type == "tailscale":
        from kopi_docka.backends.tailscale import TailscaleBackend
        backend = TailscaleBackend()
        return backend.setup_interactive()
    
    elif backend_type == "rclone":
        from kopi_docka.backends.rclone import RcloneBackend
        backend = RcloneBackend()
        return backend.setup_interactive()
    
    return None


def initialize_repository() -> bool:
    """Initialize Kopia repository"""
    from kopi_docka.config import load_backend_config
    from kopi_docka.cli.repo import _build_kopia_create_command
    import subprocess
    
    utils.print_header("🔐 Repository Initialization")
    
    # Load config
    config = load_backend_config()
    if not config:
        utils.print_error("No configuration found")
        return False
    
    # Get password
    utils.print_info("Enter repository password (used for encryption)")
    password = utils.prompt_text("Password", password=True)
    password_confirm = utils.prompt_text("Confirm password", password=True)
    
    if password != password_confirm:
        utils.print_error("Passwords do not match")
        return False
    
    utils.print_separator()
    utils.print_info("Initializing repository...")
    
    # Build kopia command
    backend_type = config["backend_type"]
    backend_config = config["backend_config"]
    
    try:
        cmd = _build_kopia_create_command(backend_type, backend_config, password)
        
        # Execute
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            # Mark as initialized
            update_repository_status(initialized=True)
            return True
        else:
            utils.print_error(f"Initialization failed: {result.stderr}")
            return False
            
    except Exception as e:
        utils.print_error(f"Initialization failed: {e}")
        return False


def show_success_summary(backend_type: str, backend_config: dict):
    """Show success summary and next steps"""
    utils.print_separator()
    utils.print_header("🎉 Setup Complete!")
    
    console.print(f"\n[green]✓[/green] Backend: [cyan]{backend_type}[/cyan]")
    console.print(f"[green]✓[/green] Repository: [cyan]{backend_config.get('repository_path', 'N/A')}[/cyan]")
    console.print(f"[green]✓[/green] Status: [green]Ready for backups![/green]")
    
    utils.print_separator()
    utils.print_header("📝 Next Steps")
    
    console.print("\n[cyan]Create your first backup:[/cyan]")
    console.print("  kopia snapshot create /path/to/data")
    
    console.print("\n[cyan]View repository status:[/cyan]")
    console.print("  kopi-docka repo status")
    
    console.print("\n[cyan]List snapshots:[/cyan]")
    console.print("  kopia snapshot list")
    
    console.print("\n[dim]For more commands, run:[/dim] kopi-docka --help\n")
