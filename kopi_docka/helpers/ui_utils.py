"""
CLI Utilities for Kopi-Docka v4

Rich-based helpers for beautiful CLI output.
Provides consistent UI components across all commands.
"""

import os
import sys
from typing import Any, Callable, List, Optional, Tuple, TypeVar

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
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


# =============================================================================
# New Components for v4.0.0
# =============================================================================

def print_panel(
    content: str,
    title: str = "",
    style: str = "cyan"
) -> None:
    """
    Print content in a styled panel.

    Args:
        content: Panel content (Rich markup supported)
        title: Optional panel title
        style: Border and title style (cyan, green, red, yellow)
    """
    console.print()
    if title:
        console.print(Panel.fit(
            content,
            title=f"[bold {style}]{title}[/bold {style}]",
            border_style=style
        ))
    else:
        console.print(Panel.fit(content, border_style=style))
    console.print()


def print_menu(
    title: str,
    options: List[Tuple[str, str]],
    border_style: str = "cyan"
) -> None:
    """
    Print a consistent menu with numbered options.

    Args:
        title: Menu title
        options: List of (key, description) tuples
        border_style: Panel border color
    """
    content = f"[bold cyan]{title}[/bold cyan]\n\n"
    for key, description in options:
        content += f"[{key}] {description}\n"

    console.print()
    console.print(Panel.fit(content.strip(), border_style=border_style))
    console.print()


def print_step(current: int, total: int, description: str) -> None:
    """
    Print step indicator for wizards.

    Args:
        current: Current step number
        total: Total number of steps
        description: Step description
    """
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Step {current}/{total}: {description}[/bold cyan]",
        border_style="cyan"
    ))
    console.print()


def print_divider(title: str = "") -> None:
    """
    Print a styled horizontal divider with optional title.

    Args:
        title: Optional title to display in the divider
    """
    if title:
        console.print(f"\n[cyan]{'─' * 10} {title} {'─' * (50 - len(title))}[/cyan]\n")
    else:
        console.print(f"\n[dim]{'─' * 60}[/dim]\n")


def confirm_action(message: str, default_no: bool = True) -> bool:
    """
    Confirm action with clear y/N or Y/n prompt.

    Args:
        message: Question to ask
        default_no: If True, default is No (y/N); if False, default is Yes (Y/n)

    Returns:
        True if user confirmed, False otherwise
    """
    if default_no:
        prompt = f"{message} [y/N]"
    else:
        prompt = f"{message} [Y/n]"

    response = console.input(f"[cyan]{prompt}:[/cyan] ").strip().lower()

    if response in ("y", "yes"):
        return True
    elif response in ("n", "no"):
        return False
    else:
        # Empty = use default
        return not default_no


def create_status_table(title: str = "") -> Table:
    """
    Create a pre-configured status table (Property | Value format).

    Args:
        title: Optional table title

    Returns:
        Configured Rich Table
    """
    table = Table(title=title, box=box.SIMPLE, show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")
    return table


def print_success_panel(message: str, title: str = "Success") -> None:
    """Print success message in green panel."""
    console.print()
    console.print(Panel.fit(
        f"[green]✓ {message}[/green]",
        title=f"[bold green]{title}[/bold green]",
        border_style="green"
    ))
    console.print()


def print_error_panel(message: str, title: str = "Error") -> None:
    """Print error message in red panel."""
    console.print()
    console.print(Panel.fit(
        f"[red]✗ {message}[/red]",
        title=f"[bold red]{title}[/bold red]",
        border_style="red"
    ))
    console.print()


def print_warning_panel(message: str, title: str = "Warning") -> None:
    """Print warning message in yellow panel."""
    console.print()
    console.print(Panel.fit(
        f"[yellow]⚠ {message}[/yellow]",
        title=f"[bold yellow]{title}[/bold yellow]",
        border_style="yellow"
    ))
    console.print()


def print_info_panel(message: str, title: str = "Info") -> None:
    """Print info message in cyan panel."""
    console.print()
    console.print(Panel.fit(
        f"[cyan]→ {message}[/cyan]",
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan"
    ))
    console.print()


def print_next_steps(steps: List[str]) -> None:
    """
    Print a list of next steps in a styled panel.

    Args:
        steps: List of step descriptions
    """
    content = "[bold]Next Steps:[/bold]\n\n"
    for i, step in enumerate(steps, 1):
        content += f"[{i}] {step}\n"

    console.print()
    console.print(Panel.fit(
        content.strip(),
        title="[bold cyan]What's Next[/bold cyan]",
        border_style="cyan"
    ))
    console.print()


def get_menu_choice(prompt_text: str = "Select", valid_choices: List[str] = None) -> str:
    """
    Get a menu choice from the user with validation.

    Args:
        prompt_text: Text to show in prompt
        valid_choices: List of valid choices (optional)

    Returns:
        User's choice as string
    """
    while True:
        choice = console.input(f"[cyan]{prompt_text}:[/cyan] ").strip()
        if valid_choices is None or choice in valid_choices:
            return choice
        print_error(f"Invalid choice. Valid options: {', '.join(valid_choices)}")
