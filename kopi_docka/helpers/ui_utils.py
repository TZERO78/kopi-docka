"""
CLI Utilities for Kopi-Docka v4

Rich-based helpers for beautiful CLI output.
Provides consistent UI components across all commands.
"""

import os
import shlex
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .logging import get_logger

console = Console()
logger = get_logger(__name__)


def require_sudo() -> None:
    """
    Check if running with sudo/root privileges.

    Exits with clear error message if not running as root.

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


def prompt_choice(message: str, choices: List[str], default: Optional[str] = None) -> str:
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


def prompt_text(message: str, default: Optional[str] = None, password: bool = False) -> str:
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


def prompt_confirm(message: str, default: bool = True) -> bool:
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
    message: str, options: List[Any], display_fn: Optional[Callable[[Any], str]] = None
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
        choice = Prompt.ask(f"\n[cyan]Select[/cyan]", default="1")

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


def print_panel(content: str, title: str = "", style: str = "cyan") -> None:
    """
    Print content in a styled panel.

    Args:
        content: Panel content (Rich markup supported)
        title: Optional panel title
        style: Border and title style (cyan, green, red, yellow)
    """
    console.print()
    if title:
        console.print(
            Panel.fit(content, title=f"[bold {style}]{title}[/bold {style}]", border_style=style)
        )
    else:
        console.print(Panel.fit(content, border_style=style))
    console.print()


def print_menu(title: str, options: List[Tuple[str, str]], border_style: str = "cyan") -> None:
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
    console.print(
        Panel.fit(
            f"[bold cyan]Step {current}/{total}: {description}[/bold cyan]", border_style="cyan"
        )
    )
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
    console.print(
        Panel.fit(
            f"[green]✓ {message}[/green]",
            title=f"[bold green]{title}[/bold green]",
            border_style="green",
        )
    )
    console.print()


def print_error_panel(message: str, title: str = "Error") -> None:
    """Print error message in red panel."""
    console.print()
    console.print(
        Panel.fit(
            f"[red]✗ {message}[/red]", title=f"[bold red]{title}[/bold red]", border_style="red"
        )
    )
    console.print()


def print_warning_panel(message: str, title: str = "Warning") -> None:
    """Print warning message in yellow panel."""
    console.print()
    console.print(
        Panel.fit(
            f"[yellow]⚠ {message}[/yellow]",
            title=f"[bold yellow]{title}[/bold yellow]",
            border_style="yellow",
        )
    )
    console.print()


def print_info_panel(message: str, title: str = "Info") -> None:
    """Print info message in cyan panel."""
    console.print()
    console.print(
        Panel.fit(
            f"[cyan]→ {message}[/cyan]",
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
        )
    )
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
    console.print(
        Panel.fit(content.strip(), title="[bold cyan]What's Next[/bold cyan]", border_style="cyan")
    )
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


# =============================================================================
# Subprocess Utilities (v5.3.0)
# =============================================================================


class SubprocessError(Exception):
    """
    Raised when a subprocess command fails.

    Provides structured access to command details for error handling.

    Attributes:
        cmd: The command that failed (as list)
        returncode: Exit code from the process
        stderr: Captured stderr output
    """

    def __init__(self, cmd: List[str], returncode: int, stderr: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        cmd_str = shlex.join(cmd) if cmd else ""
        super().__init__(f"Command failed: {cmd_str} (exit {returncode})")


def run_command(
    cmd: Union[str, List[str]],
    description: str,
    timeout: Optional[int] = None,
    check: bool = True,
    show_output: bool = False,
    success_msg: Optional[str] = None,
    error_msg: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """
    Execute a subprocess command with visual feedback and logging.

    Provides consistent UX across all subprocess calls:
    - Spinner animation for background operations
    - Live output streaming for long-running commands
    - Rich error panels instead of raw stderr dumps
    - Integrated logging with duration tracking
    - Automatic subprocess tracking for zombie prevention (v5.5.0)

    Args:
        cmd: Command to execute. Can be a string ("docker ps") or list (["docker", "ps"]).
             Strings are split using shlex.split() for safe parsing.
        description: Human-readable description shown in spinner (e.g., "Checking Docker")
        timeout: Maximum seconds to wait. None means no timeout.
        check: If True, raise SubprocessError on non-zero exit. Default True.
        show_output: If True, stream output live (no spinner). Use for long operations.
        success_msg: Optional message to print on success. If None, no message shown.
        error_msg: Optional custom error message. If None, uses stderr.
        env: Optional environment variables to merge with current environment.

    Returns:
        subprocess.CompletedProcess with stdout/stderr captured.

    Raises:
        SubprocessError: If check=True and command returns non-zero exit code.
        subprocess.TimeoutExpired: If timeout is exceeded.

    Example:
        # Simple command with spinner
        result = run_command("docker ps", "Checking Docker", timeout=10)

        # Long operation with live output
        run_command(
            ["kopia", "snapshot", "create", "/data"],
            "Creating backup snapshot",
            show_output=True
        )

        # Custom environment
        run_command(
            ["kopia", "repository", "status"],
            "Checking repository",
            env={"KOPIA_PASSWORD": "secret"}
        )
    """
    # Lazy import to avoid circular dependency
    from ..cores.safe_exit_manager import SafeExitManager

    # Convert string command to list
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = list(cmd)

    cmd_str = shlex.join(cmd_list)
    logger.debug(f"Running command: {cmd_str}")

    # Prepare environment
    run_env = None
    if env:
        run_env = os.environ.copy()
        run_env.update(env)

    start_time = time.time()
    safe_exit = SafeExitManager.get_instance()
    cleanup_id = None
    process = None

    try:
        if show_output:
            # Live output mode: no spinner, stream to console
            console.print(f"[cyan]→[/cyan] {escape(description)}")

            # Start process without capturing output
            process = subprocess.Popen(
                cmd_list,
                env=run_env,
                text=True,
                # Don't capture - let output flow to terminal
                stdout=None,
                stderr=None,
            )

            # Register for cleanup tracking
            cleanup_id = safe_exit.register_process(process.pid, cmd_str[:50])

            # Wait for completion
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise

            # Build result object
            result = subprocess.CompletedProcess(
                args=cmd_list,
                returncode=process.returncode,
                stdout="",  # Not captured in live mode
                stderr="",
            )

        else:
            # Spinner mode: capture output, show spinner
            with console.status(f"[cyan]{description}...[/cyan]", spinner="dots"):
                # Start process with captured output
                process = subprocess.Popen(
                    cmd_list,
                    env=run_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                # Register for cleanup tracking
                cleanup_id = safe_exit.register_process(process.pid, cmd_str[:50])

                # Wait for completion and capture output
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    raise

                # Build result object
                result = subprocess.CompletedProcess(
                    args=cmd_list,
                    returncode=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                )

        duration = time.time() - start_time
        logger.debug(f"Command completed in {duration:.2f}s (exit {result.returncode})")

        # Handle success
        if result.returncode == 0:
            if success_msg:
                print_success(success_msg)
            return result

        # Handle failure
        if check:
            stderr_text = result.stderr.strip() if result.stderr else ""
            display_error = (
                error_msg or stderr_text or f"Command exited with code {result.returncode}"
            )

            # Log the error
            logger.error(
                f"Command failed: {cmd_str}",
                extra={
                    "returncode": result.returncode,
                    "stderr": stderr_text[:500] if stderr_text else None,
                    "duration": duration,
                },
            )

            # Show error panel to user
            error_content = f"[bold]{description}[/bold]\n\n"
            error_content += f"[dim]Command:[/dim] {escape(cmd_str)}\n"
            error_content += f"[dim]Exit code:[/dim] {result.returncode}\n"
            if stderr_text:
                # Truncate very long error messages
                stderr_display = stderr_text[:500]
                if len(stderr_text) > 500:
                    stderr_display += "\n... (truncated)"
                error_content += f"\n[dim]Details:[/dim]\n{escape(stderr_display)}"

            console.print()
            console.print(
                Panel.fit(
                    error_content, title="[bold red]Command Failed[/bold red]", border_style="red"
                )
            )

            raise SubprocessError(cmd_list, result.returncode, stderr_text)

        return result

    except subprocess.TimeoutExpired as e:
        duration = time.time() - start_time
        logger.warning(
            f"Command timed out after {timeout}s: {cmd_str}",
            extra={"timeout": timeout, "duration": duration},
        )

        # Show timeout warning panel
        timeout_content = f"[bold]{description}[/bold]\n\n"
        timeout_content += f"[dim]Command:[/dim] {escape(cmd_str)}\n"
        timeout_content += f"[dim]Timeout:[/dim] {timeout} seconds"

        console.print()
        console.print(
            Panel.fit(
                timeout_content,
                title="[bold yellow]Command Timed Out[/bold yellow]",
                border_style="yellow",
            )
        )

        if check:
            raise

        # Return a fake CompletedProcess for non-check mode
        return subprocess.CompletedProcess(
            args=cmd_list,
            returncode=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
        )

    finally:
        # Always deregister process from tracking
        if cleanup_id is not None:
            safe_exit.unregister_process(cleanup_id)
