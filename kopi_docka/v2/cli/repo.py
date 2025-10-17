"""
Repository management commands for Kopi-Docka v2

Commands for initializing, connecting, and managing Kopia repositories.
"""

import subprocess
import sys
from typing import Optional

import typer
from rich.console import Console

from kopi_docka.v2.cli import utils
from kopi_docka.v2.config import (
    load_backend_config,
    update_repository_status,
    is_repository_initialized,
    ConfigError,
)

# Create sub-app for repo commands
app = typer.Typer(help="Repository management commands")

console = Console()


@app.command(name="init")
def repo_init(
    password: Optional[str] = typer.Option(
        None,
        "--password", "-p",
        help="Repository password (will prompt if not provided)",
    ),
):
    """
    Initialize Kopia repository
    
    Creates a new Kopia repository using the configured backend.
    """
    utils.print_header("Repository Initialization")
    
    # Load config
    try:
        config = load_backend_config()
    except ConfigError as e:
        utils.print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    
    if config is None:
        utils.print_error("No backend configured")
        utils.print_info("Run 'kopi-docka setup backend' first")
        raise typer.Exit(1)
    
    # Check if already initialized
    if is_repository_initialized():
        utils.print_warning("Repository already initialized")
        
        if not utils.prompt_confirm("Re-initialize? (This will NOT delete existing data)", default=False):
            utils.print_info("Cancelled")
            raise typer.Exit(0)
    
    # Get password if not provided
    if not password:
        utils.print_info("Enter repository password (will be used for encryption)")
        password = utils.prompt_text("Password", password=True)
        password_confirm = utils.prompt_text("Confirm password", password=True)
        
        if password != password_confirm:
            utils.print_error("Passwords do not match")
            raise typer.Exit(1)
    
    utils.print_separator()
    utils.print_info("Initializing repository...")
    
    # Build kopia command
    backend_type = config["backend_type"]
    backend_config = config["backend_config"]
    
    try:
        cmd = _build_kopia_create_command(backend_type, backend_config, password)
        
        utils.print_info(f"Running: kopia repository create {backend_config.get('type', backend_type)}")
        
        # Execute kopia command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            # Mark as initialized
            update_repository_status(initialized=True)
            
            utils.print_separator()
            utils.print_success("Repository initialized successfully!")
            utils.print_info("You can now create backups with kopia")
            
        else:
            utils.print_error("Repository initialization failed")
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
            raise typer.Exit(1)
            
    except subprocess.TimeoutExpired:
        utils.print_error("Repository initialization timed out")
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)


@app.command(name="status")
def repo_status():
    """
    Show repository status
    
    Displays information about the configured repository.
    """
    utils.print_header("Repository Status")
    
    # Load config
    try:
        config = load_backend_config()
    except ConfigError as e:
        utils.print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    
    if config is None:
        utils.print_error("No backend configured")
        utils.print_info("Run 'kopi-docka setup backend' first")
        raise typer.Exit(0)
    
    # Display config info
    backend_type = config.get("backend_type", "unknown")
    backend_config = config.get("backend_config", {})
    repo_info = config.get("repository", {})
    metadata = config.get("metadata", {})
    
    console.print(f"\n[cyan]Backend:[/cyan] {backend_type}")
    console.print(f"[cyan]Repository Path:[/cyan] {backend_config.get('repository_path', 'N/A')}")
    console.print(f"[cyan]Initialized:[/cyan] {'Yes' if repo_info.get('initialized') else 'No'}")
    
    if repo_info.get('created_at'):
        console.print(f"[cyan]Created:[/cyan] {repo_info['created_at']}")
    
    if repo_info.get('last_check'):
        console.print(f"[cyan]Last Check:[/cyan] {repo_info['last_check']}")
    
    console.print(f"\n[dim]Config created by: {metadata.get('created_by', 'N/A')}[/dim]")
    console.print(f"[dim]Hostname: {metadata.get('hostname', 'N/A')}[/dim]")
    
    # Check if repository is actually accessible
    if repo_info.get('initialized'):
        utils.print_separator()
        utils.print_info("Checking repository connection...")
        
        try:
            result = subprocess.run(
                ["kopia", "repository", "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                utils.print_success("Repository is accessible")
            else:
                utils.print_warning("Repository not connected")
                utils.print_info("Run 'kopia repository connect' to connect")
        except Exception as e:
            utils.print_warning(f"Could not check repository: {e}")


@app.command(name="connect")
def repo_connect(
    password: Optional[str] = typer.Option(
        None,
        "--password", "-p",
        help="Repository password",
    ),
):
    """
    Connect to existing repository
    
    Connects to an already initialized Kopia repository.
    """
    utils.print_header("Connect to Repository")
    
    # Load config
    try:
        config = load_backend_config()
    except ConfigError as e:
        utils.print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    
    if config is None:
        utils.print_error("No backend configured")
        utils.print_info("Run 'kopi-docka setup backend' first")
        raise typer.Exit(1)
    
    # Get password if not provided
    if not password:
        password = utils.prompt_text("Repository password", password=True)
    
    utils.print_info("Connecting to repository...")
    
    # Build kopia connect command
    backend_type = config["backend_type"]
    backend_config = config["backend_config"]
    
    try:
        cmd = _build_kopia_connect_command(backend_type, backend_config, password)
        
        # Execute kopia command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            utils.print_success("Connected to repository!")
        else:
            utils.print_error("Connection failed")
            if result.stderr:
                console.print(f"[red]{result.stderr}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        utils.print_error(f"Connection failed: {e}")
        raise typer.Exit(1)


def _build_kopia_create_command(backend_type: str, backend_config: dict, password: str) -> list:
    """Build kopia repository create command"""
    cmd = ["kopia", "repository", "create"]
    
    # Add backend type
    kopia_backend = backend_config.get("type", backend_type)
    cmd.append(kopia_backend)
    
    # Add backend-specific arguments
    if kopia_backend == "filesystem":
        cmd.extend(["--path", backend_config["repository_path"]])
        
    elif kopia_backend == "sftp":
        cmd.extend(["--path", backend_config["repository_path"]])
        if "credentials" in backend_config and "ssh_key" in backend_config["credentials"]:
            cmd.extend(["--sftp-key-file", backend_config["credentials"]["ssh_key"]])
            
    elif kopia_backend == "rclone":
        cmd.extend(["--remote-path", backend_config["repository_path"]])
        if "credentials" in backend_config and "rclone_config" in backend_config["credentials"]:
            cmd.extend(["--embed-rclone-config", backend_config["credentials"]["rclone_config"]])
    
    # Add password
    cmd.extend(["--password", password])
    
    return cmd


def _build_kopia_connect_command(backend_type: str, backend_config: dict, password: str) -> list:
    """Build kopia repository connect command"""
    cmd = ["kopia", "repository", "connect"]
    
    # Add backend type
    kopia_backend = backend_config.get("type", backend_type)
    cmd.append(kopia_backend)
    
    # Add backend-specific arguments (same as create)
    if kopia_backend == "filesystem":
        cmd.extend(["--path", backend_config["repository_path"]])
        
    elif kopia_backend == "sftp":
        cmd.extend(["--path", backend_config["repository_path"]])
        if "credentials" in backend_config and "ssh_key" in backend_config["credentials"]:
            cmd.extend(["--sftp-key-file", backend_config["credentials"]["ssh_key"]])
            
    elif kopia_backend == "rclone":
        cmd.extend(["--remote-path", backend_config["repository_path"]])
        if "credentials" in backend_config and "rclone_config" in backend_config["credentials"]:
            cmd.extend(["--embed-rclone-config", backend_config["credentials"]["rclone_config"]])
    
    # Add password
    cmd.extend(["--password", password])
    
    return cmd


# Register repo commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register repo commands to main CLI app"""
    main_app.add_typer(app, name="repo")
