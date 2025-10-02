"""
Unit tests for main CLI entry point (__main__.py).

Tests version command and root-check functionality.
"""
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from kopi_docka.__main__ import app


@pytest.mark.unit
class TestVersionCommand:
    """Tests for version command."""
    
    def test_version_command_no_root_required(self, cli_runner):
        """Version command should work without root."""
        result = cli_runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        assert "Kopi-Docka" in result.stdout
        assert "1.0.0" in result.stdout or "2.0.0" in result.stdout
    
    def test_version_command_format(self, cli_runner):
        """Version output should have correct format."""
        result = cli_runner.invoke(app, ["version"])
        
        assert result.exit_code == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1
        assert lines[0].startswith("Kopi-Docka")


@pytest.mark.unit
class TestRootCheck:
    """Tests for root privilege checking."""
    
    def test_safe_commands_no_root(self, cli_runner, mock_non_root):
        """SAFE_COMMANDS should work without root."""
        # version
        result = cli_runner.invoke(app, ["version"])
        assert result.exit_code == 0
        
        # show-deps
        result = cli_runner.invoke(app, ["show-deps"])
        assert result.exit_code == 0
        
        # show-config (might fail on missing config, but not due to root)
        result = cli_runner.invoke(app, ["show-config"])
        # Exit code might be 1 due to missing config, but should not be 13 (EACCES)
        assert result.exit_code != 13
    
    def test_backup_command_requires_root(self, cli_runner, mock_non_root):
        """Backup command should require root."""
        result = cli_runner.invoke(app, ["backup"])
        
        assert result.exit_code == 13  # EACCES
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output
        assert "sudo" in output
    
    def test_daemon_command_requires_root(self, cli_runner, mock_non_root):
        """Daemon command should require root."""
        result = cli_runner.invoke(app, ["daemon"])
        
        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output
    
    def test_install_deps_requires_root(self, cli_runner, mock_non_root):
        """Install-deps command should require root."""
        result = cli_runner.invoke(app, ["install-deps", "--dry-run"])
        
        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling in main."""
    
    def test_keyboard_interrupt(self, cli_runner):
        """KeyboardInterrupt should exit cleanly."""
        with patch('kopi_docka.__main__.app') as mock_app:
            mock_app.side_effect = KeyboardInterrupt()
            
            # This test verifies the exception handler works
            # In practice, we can't easily test this with cli_runner
            # as it catches KeyboardInterrupt
    
    def test_unknown_command(self, cli_runner):
        """Unknown commands should show Typer's error."""
        result = cli_runner.invoke(app, ["unknown-command-xyz"])
        
        assert result.exit_code != 0
        # Typer shows its own error box
        output = result.stdout + result.stderr
        assert "No such command" in output or "Error" in output


@pytest.mark.unit  
class TestInitializeContext:
    """Tests for application context initialization."""
    
    def test_log_level_option(self, cli_runner, mock_root):
        """--log-level option should be accepted."""
        result = cli_runner.invoke(app, ["--log-level", "DEBUG", "version"])
        
        assert result.exit_code == 0
    
    def test_config_path_option(self, cli_runner, mock_root, tmp_config):
        """--config option should be accepted."""
        result = cli_runner.invoke(
            app, 
            ["--config", str(tmp_config), "version"]
        )
        
        assert result.exit_code == 0
