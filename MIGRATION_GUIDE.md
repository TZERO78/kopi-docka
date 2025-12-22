# Migration Guide - UI Refactoring Step-by-Step

**Version:** 4.0.0
**Date:** 2025-12-22

This guide provides a step-by-step process for implementing the UI consistency refactoring.

---

## Phase 2.1: Foundation

### Step 1: Add rich-click Dependency

**File:** `pyproject.toml`

```diff
 dependencies = [
     "psutil>=5.9.0",
     "typer>=0.9.0",
     "rich>=13.0.0",
+    "rich-click>=1.7.0",
 ]
```

**Verify:**
```bash
pip install -e .
python -c "import rich_click; print('OK')"
```

### Step 2: Configure rich-click in main.py

**File:** `kopi_docka/__main__.py`

Add at the top of the file (after imports):

```python
# rich-click configuration for beautiful --help output
try:
    import rich_click as click
    click.rich_click.USE_RICH_MARKUP = True
    click.rich_click.USE_MARKDOWN = True
    click.rich_click.SHOW_ARGUMENTS = True
    click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
    click.rich_click.STYLE_COMMANDS_TABLE = "bold cyan"
    click.rich_click.STYLE_OPTIONS_TABLE_LEADING = 1
    click.rich_click.STYLE_OPTIONS_TABLE_BOX = "SIMPLE"
except ImportError:
    pass  # Fallback to plain typer if rich-click not available
```

**Verify:**
```bash
kopi-docka --help
# Should show styled help output
```

### Step 3: Fix ui_utils.py Imports

**File:** `kopi_docka/helpers/ui_utils.py`

Add missing imports at the top:

```diff
 from rich.console import Console
 from rich.markup import escape
 from rich.panel import Panel
+from rich.progress import Progress, SpinnerColumn, TextColumn
 from rich.prompt import Confirm, Prompt
 from rich.table import Table
+from rich import box
```

### Step 4: Add New UI Components to ui_utils.py

**File:** `kopi_docka/helpers/ui_utils.py`

Add after existing functions (before the `with_spinner` function):

```python
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

Also update the `Tuple` import at the top:

```diff
-from typing import Any, Callable, List, Optional, TypeVar
+from typing import Any, Callable, List, Optional, Tuple, TypeVar
```

### Step 5: Create Tests for New Components

**File:** `tests/unit/test_ui_utils.py` (create new file)

```python
"""Tests for ui_utils module."""

import pytest
from io import StringIO
from unittest.mock import patch

from kopi_docka.helpers.ui_utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_step,
    print_menu,
    print_panel,
    create_status_table,
    confirm_action,
)


class TestPrintFunctions:
    """Test print utility functions."""

    def test_print_success(self, capsys):
        """Test success message formatting."""
        print_success("Test message")
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "Test message" in captured.out

    def test_print_error(self, capsys):
        """Test error message formatting."""
        print_error("Error message")
        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Error message" in captured.out

    def test_print_warning(self, capsys):
        """Test warning message formatting."""
        print_warning("Warning message")
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "Warning message" in captured.out

    def test_print_info(self, capsys):
        """Test info message formatting."""
        print_info("Info message")
        captured = capsys.readouterr()
        assert "→" in captured.out
        assert "Info message" in captured.out


class TestPrintStep:
    """Test step indicator function."""

    def test_print_step_format(self, capsys):
        """Test step indicator formatting."""
        print_step(1, 4, "Test Step")
        captured = capsys.readouterr()
        assert "Step 1/4" in captured.out
        assert "Test Step" in captured.out


class TestCreateStatusTable:
    """Test status table creation."""

    def test_table_has_two_columns(self):
        """Test table is created with correct columns."""
        table = create_status_table("Test Title")
        assert len(table.columns) == 2


class TestConfirmAction:
    """Test confirm action function."""

    @patch('kopi_docka.helpers.ui_utils.console')
    def test_confirm_yes(self, mock_console):
        """Test confirmation with 'y' response."""
        mock_console.input.return_value = "y"
        result = confirm_action("Proceed?")
        assert result is True

    @patch('kopi_docka.helpers.ui_utils.console')
    def test_confirm_no(self, mock_console):
        """Test confirmation with 'n' response."""
        mock_console.input.return_value = "n"
        result = confirm_action("Proceed?")
        assert result is False

    @patch('kopi_docka.helpers.ui_utils.console')
    def test_confirm_default_no(self, mock_console):
        """Test confirmation with empty response (default no)."""
        mock_console.input.return_value = ""
        result = confirm_action("Proceed?", default_no=True)
        assert result is False

    @patch('kopi_docka.helpers.ui_utils.console')
    def test_confirm_default_yes(self, mock_console):
        """Test confirmation with empty response (default yes)."""
        mock_console.input.return_value = ""
        result = confirm_action("Proceed?", default_no=False)
        assert result is True
```

**Verify:**
```bash
pytest tests/unit/test_ui_utils.py -v
```

---

## Phase 2.2: High-Priority Commands

### Step 6: Refactor setup_commands.py

**File:** `kopi_docka/commands/setup_commands.py`

Add imports at top:

```python
from rich.console import Console
from rich.panel import Panel

from ..helpers.ui_utils import (
    console,
    print_step,
    print_success,
    print_warning,
    prompt_confirm,
)
```

Replace the wizard header:

```python
# Before
typer.echo("═" * 70)
typer.echo("🔥 Kopi-Docka Complete Setup Wizard")
...

# After
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
```

Replace step indicators:

```python
# Before
typer.echo("─" * 70)
typer.echo("Step 1/4: Checking Dependencies")
typer.echo("─" * 70)

# After
print_step(1, 4, "Checking Dependencies")
```

Replace success/error messages:

```python
# Before
typer.echo("✓ Kopia found")

# After
print_success("Kopia found")
```

**Verify:**
```bash
sudo kopi-docka setup --help
# Test the actual wizard if possible
```

### Step 7: Refactor config_commands.py

Focus on `cmd_new_config()` function - replace all typer.echo() calls.

**Key replacements:**
1. Header box → Panel.fit()
2. Repository selection menu → print_menu()
3. Password display → Panel.fit() with yellow border
4. Summary box → Panel.fit() with green border

### Step 8: Refactor backup_commands.py

Replace `typer.echo()` with Rich equivalents throughout.

### Step 9: Refactor dry_run_commands.py

Replace `typer.echo()` with Rich equivalents throughout.

---

## Phase 2.3: Remaining Commands

### Step 10: Refactor repository_commands.py

Standardize remaining functions that still use typer.echo().

### Step 11: Refactor dependency_commands.py

Full Rich conversion.

### Step 12: Refactor advanced/snapshot_commands.py

Full Rich conversion.

---

## Phase 2.4: Documentation & Version Bump

### Step 13: Update Version

**File:** `kopi_docka/helpers/constants.py`

```diff
-VERSION = "3.9.1"
+VERSION = "4.0.0"
```

**File:** `pyproject.toml`

```diff
-version = "3.9.1"
+version = "4.0.0"
```

### Step 14: Update README.md

Add new "What's New in v4.0.0" section after the "What's New in v3.9.1" section:

```markdown
## What's New in v4.0.0

- **Unified Rich UI** - All commands now use consistent Rich-based output
  - Beautiful panels, tables, and progress indicators
  - Consistent color scheme (green=success, red=error, yellow=warning, cyan=info)
  - Improved readability and visual feedback

- **Beautiful --help Output** - Integration of rich-click
  - Styled command and option tables
  - Markdown support in help text
  - Better visual hierarchy

- **Extended UI Components** - New reusable components in ui_utils.py
  - print_panel(), print_menu(), print_step()
  - print_success_panel(), print_error_panel(), print_warning_panel()
  - confirm_action(), create_status_table()

- **Wizard Improvements** - Setup and configuration wizards
  - Step indicators (Step 1/4: Description)
  - Consistent panel-based design
  - Improved visual feedback

**Note:** No breaking changes - all command APIs remain the same.
```

### Step 15: Update docs/FEATURES.md

Add a new section documenting the UI improvements.

### Step 16: Create/Update CHANGELOG.md

**File:** `CHANGELOG.md` (create if not exists)

```markdown
# Changelog

All notable changes to Kopi-Docka will be documented in this file.

## [4.0.0] - 2025-12-XX

### Added
- Complete UI consistency refactoring with Rich-based output
- Beautiful --help output via rich-click integration
- New UI components in ui_utils.py:
  - print_panel(), print_menu(), print_step()
  - print_success_panel(), print_error_panel(), print_warning_panel()
  - confirm_action(), create_status_table()
- Step indicators for wizards (Step 1/4: Description)

### Changed
- All commands now use consistent Rich panels and tables
- Color scheme enforced across all commands:
  - Green: Success, completed
  - Red: Errors, failures
  - Yellow: Warnings
  - Cyan: Info, menus, headers
- Wizard headers now use Panel.fit() instead of ASCII dividers

### Fixed
- with_spinner() in ui_utils.py - added missing imports

### Documentation
- Updated README.md with "What's New in v4.0.0"
- Updated FEATURES.md with UI improvements section
- Created ARCHITECTURE.md, CODE_EXAMPLES.md, MIGRATION_GUIDE.md

## [3.9.1] - 2025-XX-XX

... (previous releases)
```

---

## Verification Checklist

After completing all steps, verify:

- [ ] `kopi-docka --help` shows beautiful styled output
- [ ] `kopi-docka setup` shows Rich panels
- [ ] `kopi-docka doctor` displays correctly (was already good)
- [ ] `kopi-docka backup --dry-run` shows Rich output
- [ ] `kopi-docka admin config new` shows Rich panels
- [ ] `kopi-docka admin service manage` still works (was already good)
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No typer.echo() calls for user-facing output (except errors to stderr)

---

## Rollback Plan

If issues are found:

1. Revert to previous commit
2. Fix the specific issue
3. Re-apply changes incrementally
4. Test after each change

---

**End of Migration Guide**
