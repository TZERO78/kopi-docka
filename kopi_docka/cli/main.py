"""
Main CLI application using Typer

Entry point for Kopi-Docka v2 CLI.
"""

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape

from kopi_docka.i18n import set_language, get_current_language
from kopi_docka.cli import utils
from kopi_docka.cli import setup
from kopi_docka.cli import repo
from kopi_docka.cli import backup
from kopi_docka.cli import deps
from kopi_docka.cli import recovery
from kopi_docka.cli import config
from kopi_docka.cli import service

# Create Typer app
app = typer.Typer(
    name="kopi-docka",
    help="🔥 Kopi-Docka - Docker Cold Backup Tool with Kopia",
    add_completion=False,
)

console = Console()

# Register sub-commands
setup.register_to_main_app(app)
repo.register_to_main_app(app)
backup.register_to_main_app(app)
deps.register_to_main_app(app)
recovery.register_to_main_app(app)
config.register_to_main_app(app)
service.register_to_main_app(app)


@app.callback()
def main_callback(
    language: Optional[str] = typer.Option(
        None,
        "--language", "-l",
        help="Interface language (en/de)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
):
    """
    Kopi-Docka v2 - Docker Cold Backup Tool
    
    Use 'kopi-docka setup' to configure your backup backend.
    """
    # Set language if provided
    if language:
        try:
            set_language(language)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    # Set debug mode (could be used for verbose output)
    if debug:
        console.print("[dim]Debug mode enabled[/dim]")


@app.command()
def version():
    """Show version information"""
    try:
        from kopi_docka.helpers.constants import VERSION
        console.print(f"[cyan]Kopi-Docka[/cyan] v{VERSION}")
    except ImportError:
        console.print("[cyan]Kopi-Docka[/cyan] v2.1.0")


@app.command()
def info():
    """Show system information and current language"""
    import platform
    
    lang = get_current_language()
    
    utils.print_header("Kopi-Docka System Information")
    
    console.print(f"[cyan]Language:[/cyan] {lang.upper()}")
    console.print(f"[cyan]OS:[/cyan] {platform.system()} {platform.release()}")
    console.print(f"[cyan]Python:[/cyan] {platform.python_version()}")
    console.print(f"[cyan]Architecture:[/cyan] {platform.machine()}")


def cli_main():
    """
    Entry point for CLI
    
    This function is called by the console script entry point.
    """
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
