"""
Setup commands for Kopi-Docka v2

Interactive wizard for backend configuration.
"""

from typing import Optional

import typer
from rich.console import Console

from kopi_docka.v2.cli import utils
from kopi_docka.v2.i18n import t, get_current_language

# Create sub-app for setup commands
app = typer.Typer(
    help="Setup and configuration commands",
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()


@app.callback()
def setup_callback(ctx: typer.Context):
    """Setup callback - runs wizard if no subcommand"""
    if ctx.invoked_subcommand is None:
        # No subcommand provided, run the wizard
        from kopi_docka.v2.cli.wizard import run_setup_wizard
        run_setup_wizard()
        raise typer.Exit(0)


@app.command(name="backend")
def setup_backend(
    backend: Optional[str] = typer.Option(
        None,
        "--backend", "-b",
        help="Backend type (local, s3, tailscale)",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language", "-l",
        help="Language (en/de)",
    ),
):
    """
    Interactive setup wizard for backup backends
    
    Configure where your backups will be stored.
    """
    from kopi_docka.v2.i18n import set_language
    
    # Check sudo
    utils.require_sudo("backend setup")
    
    # Set language if provided
    if language:
        try:
            set_language(language)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    lang = get_current_language()
    
    # Show welcome header
    utils.print_header(
        t("setup.title", lang),
        t("setup.subtitle", lang)
    )
    
    # Get available backends
    available_backends = ["local", "s3", "tailscale"]
    
    # If backend not specified, prompt for selection
    if not backend:
        backend = utils.prompt_select(
            t("setup.select_backend", lang),
            available_backends,
            display_fn=lambda b: _get_backend_display_name(b, lang)
        )
    else:
        # Validate backend
        if backend not in available_backends:
            utils.print_error(f"Unknown backend: {backend}")
            utils.print_info(f"Available: {', '.join(available_backends)}")
            raise typer.Exit(1)
    
    utils.print_info(f"Selected backend: {backend}")
    utils.print_separator()
    
    # Run backend-specific setup
    try:
        if backend == "local":
            config = _setup_local_backend(lang)
        elif backend == "s3":
            config = _setup_s3_backend(lang)
        elif backend == "tailscale":
            config = _setup_tailscale_backend(lang)
        else:
            utils.print_error(f"Backend '{backend}' not implemented yet")
            raise typer.Exit(1)
        
        if config:
            # Save configuration
            from kopi_docka.v2.config import save_backend_config, get_config_path
            
            try:
                config_path = save_backend_config(backend, config)
                
                utils.print_separator()
                utils.print_success(t("setup.success", lang))
                utils.print_info(f"Configuration saved to: {config_path}")
                utils.print_warning("Repository not initialized yet")
                utils.print_info("Run 'kopi-docka repo init' to initialize the repository")
                
            except Exception as e:
                utils.print_error(f"Failed to save configuration: {e}")
                raise typer.Exit(1)
        else:
            utils.print_warning(t("setup.cancelled", lang))
            raise typer.Exit(1)
            
    except KeyboardInterrupt:
        console.print("\n")
        utils.print_warning(t("setup.cancelled", lang))
        raise typer.Exit(1)
    except Exception as e:
        utils.print_error(f"Setup failed: {e}")
        if "--debug" in typer.get_app_dir("kopi-docka"):
            raise
        raise typer.Exit(1)


def _get_backend_display_name(backend: str, lang: str) -> str:
    """Get display name for backend"""
    names = {
        "local": "📁 Local Filesystem",
        "s3": "☁️  S3 / Object Storage",
        "tailscale": "🔥 Tailscale (Recommended)",
    }
    return names.get(backend, backend)


def _setup_local_backend(lang: str) -> dict:
    """Setup local filesystem backend"""
    utils.print_header("Local Filesystem Backend")
    
    # Get repository path
    default_path = "/backup/kopia"
    repo_path = utils.prompt_text(
        "Repository path",
        default=default_path
    )
    
    if not repo_path.startswith("/"):
        utils.print_error("Path must be absolute (start with /)")
        raise typer.Exit(1)
    
    utils.print_info(f"Repository will be stored at: {repo_path}")
    
    return {
        "type": "filesystem",
        "repository_path": repo_path,
    }


def _setup_s3_backend(lang: str) -> dict:
    """Setup S3 backend"""
    utils.print_header("S3 / Object Storage Backend")
    
    # Get S3 details
    endpoint = utils.prompt_text("S3 Endpoint", default="s3.amazonaws.com")
    bucket = utils.prompt_text("Bucket name")
    access_key = utils.prompt_text("Access Key ID")
    secret_key = utils.prompt_text("Secret Access Key", password=True)
    
    region = utils.prompt_text("Region", default="us-east-1")
    
    return {
        "type": "s3",
        "endpoint": endpoint,
        "bucket": bucket,
        "credentials": {
            "access_key": access_key,
            "secret_key": secret_key,
        },
        "region": region,
    }


def _setup_tailscale_backend(lang: str) -> dict:
    """Setup Tailscale backend"""
    from kopi_docka.v2.backends.tailscale import TailscaleBackend
    
    utils.print_header("Tailscale Backend Setup")
    utils.print_info("🔥 Secure offsite backups via your Tailnet")
    utils.print_separator()
    
    # Create backend instance and run interactive setup
    backend = TailscaleBackend()
    
    try:
        config = backend.setup_interactive()
        return config
    except Exception as e:
        utils.print_error(f"Setup failed: {e}")
        raise


# Register setup commands to main app
def register_to_main_app(main_app: typer.Typer):
    """Register setup commands to main CLI app"""
    main_app.add_typer(app, name="setup")
