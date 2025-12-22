# Code Examples - Before/After UI Refactoring

**Version:** 4.0.0
**Date:** 2025-12-22

This document shows concrete before/after code examples for the UI refactoring.

---

## 1. Setup Wizard Header

### Before (setup_commands.py)
```python
typer.echo("═" * 70)
typer.echo("🔥 Kopi-Docka Complete Setup Wizard")
typer.echo("═" * 70)
typer.echo("")
typer.echo("This wizard will guide you through:")
typer.echo("  1. ✅ Dependency verification")
typer.echo("  2. 📦 Repository storage selection")
typer.echo("  3. ⚙️  Configuration")
typer.echo("  4. 🔐 Repository initialization")
typer.echo("")

if not typer.confirm("Continue?", default=True):
    raise typer.Exit(0)
```

### After (setup_commands.py)
```python
from rich.console import Console
from rich.panel import Panel
from ..helpers.ui_utils import print_header, prompt_confirm

console = Console()

console.print()
console.print(Panel.fit(
    "[bold cyan]Kopi-Docka Complete Setup Wizard[/bold cyan]\n\n"
    "This wizard will guide you through:\n"
    "  [1] Dependency verification\n"
    "  [2] Repository storage selection\n"
    "  [3] Configuration\n"
    "  [4] Repository initialization",
    border_style="cyan"
))
console.print()

if not prompt_confirm("Continue?", default=True):
    raise typer.Exit(0)
```

---

## 2. Step Indicator

### Before
```python
typer.echo("")
typer.echo("─" * 70)
typer.echo("Step 1/4: Checking Dependencies")
typer.echo("─" * 70)
```

### After
```python
from ..helpers.ui_utils import print_step

print_step(1, 4, "Checking Dependencies")
# Output: Step 1/4: Checking Dependencies (in cyan panel)
```

**New ui_utils.py function:**
```python
def print_step(current: int, total: int, description: str) -> None:
    """Print step indicator in a styled panel."""
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Step {current}/{total}: {description}[/bold cyan]",
        border_style="cyan"
    ))
    console.print()
```

---

## 3. Success/Error Messages

### Before
```python
if meta.success:
    typer.echo(f"✓ {u.name} completed in {int(meta.duration_seconds)}s")
    typer.echo(f"   Volumes: {meta.volumes_backed_up}")
else:
    typer.echo(f"✗ {u.name} failed in {int(meta.duration_seconds)}s")
    for err in meta.errors or [meta.error_message]:
        if err:
            typer.echo(f"   - {err}")
```

### After
```python
from ..helpers.ui_utils import print_success, print_error, console

if meta.success:
    print_success(f"{u.name} completed in {int(meta.duration_seconds)}s")
    console.print(f"   [dim]Volumes:[/dim] {meta.volumes_backed_up}")
else:
    print_error(f"{u.name} failed in {int(meta.duration_seconds)}s")
    for err in meta.errors or [meta.error_message]:
        if err:
            console.print(f"   [red]- {err}[/red]")
```

---

## 4. Menu Display

### Before (config_commands.py)
```python
typer.echo("Available repository types:")
typer.echo("  1. Local Filesystem  - Store on local disk/NAS mount")
typer.echo("  2. AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)")
typer.echo("  3. Backblaze B2     - Cost-effective cloud storage")
typer.echo("  4. Azure Blob       - Microsoft Azure storage")
typer.echo("  5. Google Cloud     - GCS storage")
typer.echo("  6. SFTP             - Remote server via SSH")
typer.echo("  7. Tailscale        - P2P encrypted network")
typer.echo("  8. Rclone           - Universal (70+ cloud providers)")
typer.echo("")

backend_choice = typer.prompt("Select repository type", type=int, default=1)
```

### After
```python
from ..helpers.ui_utils import print_menu, console

print_menu("Repository Storage", [
    ("1", "Local Filesystem  - Store on local disk/NAS mount"),
    ("2", "AWS S3           - Amazon S3 or compatible (Wasabi, MinIO)"),
    ("3", "Backblaze B2     - Cost-effective cloud storage"),
    ("4", "Azure Blob       - Microsoft Azure storage"),
    ("5", "Google Cloud     - GCS storage"),
    ("6", "SFTP             - Remote server via SSH"),
    ("7", "Tailscale        - P2P encrypted network"),
    ("8", "Rclone           - Universal (70+ cloud providers)"),
])

backend_choice = int(console.input("[cyan]Select repository type [1]:[/cyan] ") or "1")
```

**New ui_utils.py function:**
```python
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
```

---

## 5. Password Display Box

### Before
```python
typer.echo("═════════════════════════════════════════════════════════════")
typer.echo("🔑 GENERATED PASSWORD (save this NOW!):")
typer.echo("")
typer.echo(f"   {password}")
typer.echo("")
typer.echo("═════════════════════════════════════════════════════════════")
typer.echo("⚠️  Copy this to:")
typer.echo("   • Password manager (recommended)")
typer.echo("   • Encrypted USB drive")
typer.echo("   • Secure physical location")
typer.echo("═════════════════════════════════════════════════════════════")
```

### After
```python
from rich.panel import Panel

console.print()
console.print(Panel.fit(
    f"[bold yellow]GENERATED PASSWORD[/bold yellow]\n"
    f"[bold white]{password}[/bold white]\n\n"
    "[dim]Copy this password to:[/dim]\n"
    "  [yellow]•[/yellow] Password manager (recommended)\n"
    "  [yellow]•[/yellow] Encrypted USB drive\n"
    "  [yellow]•[/yellow] Secure physical location\n\n"
    "[red]If you lose this password, backups are UNRECOVERABLE![/red]",
    title="[bold yellow]Save This Now![/bold yellow]",
    border_style="yellow"
))
console.print()
```

---

## 6. Wizard Summary Box

### Before
```python
typer.echo("╭──────────────────────────────────────────╮")
typer.echo("│ Setup Complete! Next Steps:              │")
typer.echo("╰──────────────────────────────────────────╯")
typer.echo("")
typer.echo("1. Initialize repository:")
typer.echo("   sudo kopi-docka init")
typer.echo("")
typer.echo("2. List Docker containers:")
typer.echo("   sudo kopi-docka list --units")
```

### After
```python
console.print(Panel.fit(
    "[bold green]Setup Complete![/bold green]\n\n"
    "[bold]Next Steps:[/bold]\n\n"
    "[1] Initialize repository:\n"
    "    [cyan]sudo kopi-docka admin repo init[/cyan]\n\n"
    "[2] List Docker containers:\n"
    "    [cyan]sudo kopi-docka admin snapshot list[/cyan]\n\n"
    "[3] Test backup (dry-run):\n"
    "    [cyan]sudo kopi-docka dry-run[/cyan]\n\n"
    "[4] Create first backup:\n"
    "    [cyan]sudo kopi-docka backup[/cyan]",
    title="[bold green]Success[/bold green]",
    border_style="green"
))
```

---

## 7. Backup Scope Display

### Before (backup_commands.py)
```python
typer.echo(f"\n📦 Backup Scope: {scope_info['name']}")
typer.echo(f"   {scope_info['description']}")
typer.echo(f"   Includes: {', '.join(scope_info['includes'])}\n")
```

### After
```python
console.print()
console.print(Panel.fit(
    f"[bold cyan]Backup Scope: {scope_info['name']}[/bold cyan]\n\n"
    f"{scope_info['description']}\n\n"
    f"[dim]Includes:[/dim] {', '.join(scope_info['includes'])}",
    border_style="cyan"
))
console.print()
```

---

## 8. Unit Discovery List

### Before (dry_run_commands.py)
```python
typer.echo("=" * 70)
typer.echo(f"DISCOVERED BACKUP UNITS ({len(units)} total)")
typer.echo("=" * 70)

if stacks:
    typer.echo("\n📚 Docker Compose Stacks:")
    for unit in stacks:
        running = len(unit.running_containers)
        total = len(unit.containers)
        status = "🟢" if running == total else "🟡" if running > 0 else "🔴"

        typer.echo(f"\n  {status} {unit.name}")
        typer.echo(f"     Type: {unit.type}")
        typer.echo(f"     Containers: {running}/{total} running")
```

### After
```python
from rich.table import Table
from rich import box

console.print()
console.print(Panel.fit(
    f"[bold cyan]Discovered Backup Units[/bold cyan]\n"
    f"[dim]{len(units)} total[/dim]",
    border_style="cyan"
))
console.print()

if stacks:
    table = Table(title="Docker Compose Stacks", box=box.ROUNDED, show_header=True)
    table.add_column("Status", width=8)
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Containers", width=15)
    table.add_column("Volumes", width=10)

    for unit in stacks:
        running = len(unit.running_containers)
        total = len(unit.containers)

        if running == total:
            status = "[green]Online[/green]"
        elif running > 0:
            status = "[yellow]Partial[/yellow]"
        else:
            status = "[red]Offline[/red]"

        table.add_row(
            status,
            unit.name,
            f"{running}/{total}",
            str(len(unit.volumes))
        )

    console.print(table)
    console.print()
```

---

## 9. Error Handling

### Before (__main__.py)
```python
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    typer.echo(f"Unexpected error: {e}", err=True)
    typer.echo("\nFor details, check logs or run with --log-level=DEBUG", err=True)
    sys.exit(1)
```

### After
```python
from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)

except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    console.print(Panel.fit(
        f"[red]Unexpected error:[/red]\n{e}\n\n"
        "[dim]For details, run with --log-level=DEBUG[/dim]",
        title="[bold red]Error[/bold red]",
        border_style="red"
    ))
    sys.exit(1)
```

---

## 10. Progress Spinner

### Before (with bug - imports missing)
```python
# helpers/ui_utils.py has:
def with_spinner(message: str, func: Callable, *args, **kwargs):
    with Progress(  # Progress not imported!
        SpinnerColumn(),  # Not imported!
        TextColumn("[progress.description]{task.description}"),  # Not imported!
        console=console,
    ) as progress:
        progress.add_task(description=message, total=None)
        return func(*args, **kwargs)
```

### After (fixed)
```python
from rich.progress import Progress, SpinnerColumn, TextColumn

def with_spinner(message: str, func: Callable, *args, **kwargs):
    """
    Execute a function with a spinner animation.

    Args:
        message: Message to show while spinning
        func: Function to execute
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Return value of func
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(description=message, total=None)
        return func(*args, **kwargs)
```

---

## 11. Confirmation Dialog

### Before (various files)
```python
if not typer.confirm("Continue?", default=True):
    raise typer.Exit(0)
```

### After (using ui_utils)
```python
from ..helpers.ui_utils import prompt_confirm

if not prompt_confirm("Continue?", default=True):
    raise typer.Exit(0)
```

**Note:** `prompt_confirm` already exists in ui_utils.py and uses Rich's `Confirm.ask()`.

---

## 12. Dangerous Operation Warning

### Before (config_commands.py)
```python
typer.echo("=" * 70)
typer.echo("⚠️  DANGER ZONE: CONFIGURATION RESET")
typer.echo("=" * 70)
typer.echo("")
typer.echo("This operation will:")
typer.echo("  1. DELETE the existing configuration")
typer.echo("  2. Generate a COMPLETELY NEW password")
typer.echo("  3. Make existing backups INACCESSIBLE")
```

### After
```python
console.print()
console.print(Panel.fit(
    "[bold red]DANGER ZONE: Configuration Reset[/bold red]\n\n"
    "[yellow]This operation will:[/yellow]\n"
    "  [red]1.[/red] DELETE the existing configuration\n"
    "  [red]2.[/red] Generate a COMPLETELY NEW password\n"
    "  [red]3.[/red] Make existing backups INACCESSIBLE\n\n"
    "[dim]Only proceed if you understand the consequences.[/dim]",
    title="[bold red]Warning[/bold red]",
    border_style="red"
))
console.print()
```

---

## 13. New ui_utils.py Components (Complete)

```python
"""
CLI Utilities for Kopi-Docka v4.0.0

Rich-based helpers for beautiful CLI output.
"""

import os
import sys
from typing import Any, Callable, List, Optional, Tuple, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

console = Console()


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
```

---

**End of Code Examples**
