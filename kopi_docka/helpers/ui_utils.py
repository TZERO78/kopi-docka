"""
CLI Utilities for Kopi-Docka v2

Rich-based helpers for beautiful CLI output.
"""

import os
import sys
from typing import Any, Callable, List, Optional, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()


def require_sudo(command_name: str = "this command") -> None:
    """
    Check if running with sudo/root privileges.
    
    Exits with clear error message if not running as root.
    
    Args:
        command_name: Name of command requiring sudo (for error message)
    
    Raises:
        typer.Exit: If not running as root
    """
    if os.geteuid() != 0:
        print_error("❌ Root privileges required")
        print_separator()
        console.print("[yellow]Kopi-Docka needs sudo for:[/yellow]")
        console.print("  • Installing dependencies (Kopia, Tailscale, Rclone)")
        console.print("  • Creating backup directories")
        console.print("  • Accessing system resources")
        print_separator()
        print_info("Please run with sudo:")
        console.print(f"  [cyan]sudo {' '.join(sys.argv)}[/cyan]\n")
        raise typer.Exit(1)


def print_header(title: str, subtitle: str = ""):
    """Print styled header with optional subtitle"""
    content = f"[bold cyan]{title}[/bold cyan]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    
    panel = Panel(content, border_style="cyan")
    console.print(panel)


def print_success(message: str):
    """Print success message with green checkmark"""
    console.print(f"[green]✓[/green] {escape(message)}")


def print_error(message: str):
    """Print error message with red X"""
    console.print(f"[red]✗[/red] {escape(message)}")


def print_warning(message: str):
    """Print warning message with yellow warning symbol"""
    console.print(f"[yellow]⚠[/yellow]  {escape(message)}")


def print_info(message: str):
    """Print info message with cyan arrow"""
    console.print(f"[cyan]→[/cyan] {escape(message)}")


def print_separator():
    """Print a visual separator line"""
    console.print("\n" + "─" * 60 + "\n")


def create_table(title: str, columns: List[tuple]) -> Table:
    """
    Create a styled Rich table
    
    Args:
        title: Table title
        columns: List of (name, style, width) tuples
        
    Returns:
        Rich Table instance
        
    Example:
        table = create_table("Peers", [
            ("Name", "cyan", 20),
            ("IP", "white", 15),
            ("Status", "green", 10)
        ])
        table.add_row("server1", "10.0.0.1", "Online")
    """
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for name, style, width in columns:
        table.add_column(name, style=style, width=width)
    return table


def prompt_choice(
    message: str,
    choices: List[str],
    default: Optional[str] = None
) -> str:
    """
    Prompt user to choose from a list of options
    
    Args:
        message: Prompt message
        choices: List of valid choices
        default: Default choice if user presses Enter
        
    Returns:
        Selected choice
    """
    return Prompt.ask(message, choices=choices, default=default)


def prompt_text(
    message: str,
    default: Optional[str] = None,
    password: bool = False
) -> str:
    """
    Prompt user for text input
    
    Args:
        message: Prompt message
        default: Default value if user presses Enter
        password: If True, hide input (for passwords)
        
    Returns:
        User input string
    """
    return Prompt.ask(message, default=default, password=password)


def prompt_confirm(
    message: str,
    default: bool = True
) -> bool:
    """
    Prompt user for yes/no confirmation
    
    Args:
        message: Prompt message
        default: Default answer (True=Yes, False=No)
        
    Returns:
        True if user confirmed, False otherwise
    """
    return Confirm.ask(message, default=default)


def prompt_select(
    message: str,
    options: List[Any],
    display_fn: Optional[Callable[[Any], str]] = None
) -> Any:
    """
    Show numbered list and let user select one option
    
    Args:
        message: Prompt message
        options: List of options to choose from
        display_fn: Optional function to format option for display
        
    Returns:
        Selected option
        
    Example:
        peers = [peer1, peer2, peer3]
        selected = prompt_select(
            "Select peer", 
            peers,
            lambda p: f"{p.hostname} ({p.ip})"
        )
    """
    if not options:
        raise ValueError("Options list cannot be empty")
    
    # Display options
    console.print(f"\n[cyan]{message}:[/cyan]")
    for i, option in enumerate(options, 1):
        display = display_fn(option) if display_fn else str(option)
        console.print(f"  {i}. {display}")
    
    # Get selection
    while True:
        choice = Prompt.ask(
            f"\n[cyan]Select[/cyan]",
            default="1"
        )
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
            else:
                print_error(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            print_error("Please enter a valid number")


def with_spinner(message: str, func: Callable, *args, **kwargs):
    """
    Execute a function with a spinner animation
    
    Args:
        message: Message to show while spinning
        func: Function to execute
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
        
    Returns:
        Return value of func
        
    Example:
        result = with_spinner(
            "Loading peers...",
            load_peers_function,
            arg1, arg2
        )
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(description=message, total=None)
        return func(*args, **kwargs)
