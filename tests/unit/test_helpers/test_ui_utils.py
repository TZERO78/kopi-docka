"""
Tests for ui_utils module.

Tests the Rich-based UI utility functions for Kopi-Docka v4.
"""

import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from kopi_docka.helpers.ui_utils import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_step,
    print_menu,
    print_panel,
    print_divider,
    create_status_table,
    create_table,
    confirm_action,
    print_success_panel,
    print_error_panel,
    print_warning_panel,
    print_info_panel,
    print_next_steps,
    get_menu_choice,
    console,
)


class TestBasicPrintFunctions:
    """Test basic print utility functions."""

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

    def test_print_step_different_numbers(self, capsys):
        """Test step indicator with different step numbers."""
        print_step(3, 5, "Processing")
        captured = capsys.readouterr()
        assert "Step 3/5" in captured.out
        assert "Processing" in captured.out


class TestPrintPanel:
    """Test panel printing function."""

    def test_print_panel_without_title(self, capsys):
        """Test panel without title."""
        print_panel("Panel content")
        captured = capsys.readouterr()
        assert "Panel content" in captured.out

    def test_print_panel_with_title(self, capsys):
        """Test panel with title."""
        print_panel("Content here", title="My Title")
        captured = capsys.readouterr()
        assert "Content here" in captured.out
        assert "My Title" in captured.out


class TestPrintMenu:
    """Test menu printing function."""

    def test_print_menu(self, capsys):
        """Test menu formatting."""
        options = [
            ("1", "First option"),
            ("2", "Second option"),
            ("0", "Exit"),
        ]
        print_menu("Test Menu", options)
        captured = capsys.readouterr()
        assert "Test Menu" in captured.out
        assert "First option" in captured.out
        assert "Second option" in captured.out
        assert "Exit" in captured.out


class TestPrintDivider:
    """Test divider printing function."""

    def test_print_divider_without_title(self, capsys):
        """Test divider without title."""
        print_divider()
        captured = capsys.readouterr()
        assert "─" in captured.out

    def test_print_divider_with_title(self, capsys):
        """Test divider with title."""
        print_divider("Section Title")
        captured = capsys.readouterr()
        assert "Section Title" in captured.out
        assert "─" in captured.out


class TestCreateTable:
    """Test table creation functions."""

    def test_create_table_structure(self):
        """Test table is created with correct columns."""
        table = create_table(
            "Test Table",
            [
                ("Name", "cyan", 20),
                ("Value", "white", 30),
            ],
        )
        assert len(table.columns) == 2
        assert table.title == "Test Table"

    def test_create_status_table(self):
        """Test status table creation."""
        table = create_status_table("Status Title")
        assert len(table.columns) == 2
        assert table.title == "Status Title"

    def test_create_status_table_no_title(self):
        """Test status table without title."""
        table = create_status_table()
        assert len(table.columns) == 2


class TestConfirmAction:
    """Test confirm action function."""

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_yes(self, mock_console):
        """Test confirmation with 'y' response."""
        mock_console.input.return_value = "y"
        result = confirm_action("Proceed?")
        assert result is True

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_yes_full(self, mock_console):
        """Test confirmation with 'yes' response."""
        mock_console.input.return_value = "yes"
        result = confirm_action("Proceed?")
        assert result is True

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_no(self, mock_console):
        """Test confirmation with 'n' response."""
        mock_console.input.return_value = "n"
        result = confirm_action("Proceed?")
        assert result is False

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_no_full(self, mock_console):
        """Test confirmation with 'no' response."""
        mock_console.input.return_value = "no"
        result = confirm_action("Proceed?")
        assert result is False

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_default_no(self, mock_console):
        """Test confirmation with empty response (default no)."""
        mock_console.input.return_value = ""
        result = confirm_action("Proceed?", default_no=True)
        assert result is False

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_confirm_default_yes(self, mock_console):
        """Test confirmation with empty response (default yes)."""
        mock_console.input.return_value = ""
        result = confirm_action("Proceed?", default_no=False)
        assert result is True


class TestPanelFunctions:
    """Test panel variant functions."""

    def test_print_success_panel(self, capsys):
        """Test success panel."""
        print_success_panel("Operation completed")
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "Operation completed" in captured.out
        assert "Success" in captured.out

    def test_print_error_panel(self, capsys):
        """Test error panel."""
        print_error_panel("Something went wrong")
        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Something went wrong" in captured.out
        assert "Error" in captured.out

    def test_print_warning_panel(self, capsys):
        """Test warning panel."""
        print_warning_panel("Be careful")
        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "Be careful" in captured.out
        assert "Warning" in captured.out

    def test_print_info_panel(self, capsys):
        """Test info panel."""
        print_info_panel("FYI")
        captured = capsys.readouterr()
        assert "→" in captured.out
        assert "FYI" in captured.out
        assert "Info" in captured.out

    def test_print_success_panel_custom_title(self, capsys):
        """Test success panel with custom title."""
        print_success_panel("Done!", title="Complete")
        captured = capsys.readouterr()
        assert "Done!" in captured.out
        assert "Complete" in captured.out


class TestPrintNextSteps:
    """Test next steps panel function."""

    def test_print_next_steps(self, capsys):
        """Test next steps formatting."""
        steps = [
            "Run the backup command",
            "Check the logs",
            "Verify the snapshots",
        ]
        print_next_steps(steps)
        captured = capsys.readouterr()
        assert "Next Steps" in captured.out
        assert "Run the backup command" in captured.out
        assert "Check the logs" in captured.out
        assert "Verify the snapshots" in captured.out


class TestGetMenuChoice:
    """Test menu choice input function."""

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_get_menu_choice_valid(self, mock_console):
        """Test getting valid menu choice."""
        mock_console.input.return_value = "1"
        result = get_menu_choice("Select", valid_choices=["1", "2", "3"])
        assert result == "1"

    @patch("kopi_docka.helpers.ui_utils.console")
    def test_get_menu_choice_no_validation(self, mock_console):
        """Test getting menu choice without validation."""
        mock_console.input.return_value = "anything"
        result = get_menu_choice("Select")
        assert result == "anything"
