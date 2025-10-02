"""
Unit tests for repository commands.

Tests the repository_commands.py module with mocked Kopia operations.
"""
import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock, Mock
from kopi_docka.__main__ import app


@pytest.mark.unit
class TestInitCommand:
    """Tests for init command."""
    
    def test_init_requires_root(self, cli_runner, mock_non_root):
        """init command requires root privileges."""
        result = cli_runner.invoke(app, ["init"])
        
        assert result.exit_code == 13
        output = result.stdout + result.stderr
        assert "Root-Rechte" in output or "benötigt Root" in output
    
    @patch('kopi_docka.commands.repository_commands.shutil.which')
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    def test_init_creates_repository(
        self,
        mock_repo_class,
        mock_which,
        cli_runner,
        mock_root,
        tmp_config
    ):
        """init creates and connects to repository."""
        mock_which.return_value = "/usr/bin/kopia"
        mock_repo = mock_repo_class.return_value
        mock_repo.profile_name = "test-profile"
        mock_repo.repo_path = "/tmp/test-repo"
        
        result = cli_runner.invoke(
            app,
            ["init", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "Repository initialized" in result.stdout
        mock_repo.initialize.assert_called_once()
    
    @patch('kopi_docka.commands.repository_commands.shutil.which')
    def test_init_fails_without_kopia(
        self,
        mock_which,
        cli_runner,
        mock_root,
        tmp_config
    ):
        """init fails when Kopia is not installed."""
        mock_which.return_value = None
        
        result = cli_runner.invoke(
            app,
            ["init", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 1
        assert "Kopia is not installed" in result.stdout


@pytest.mark.unit
class TestRepoStatusCommand:
    """Tests for repo-status command."""
    
    def test_repo_status_requires_root(self, cli_runner, mock_non_root):
        """repo-status requires root privileges."""
        result = cli_runner.invoke(app, ["repo-status"])
        
        assert result.exit_code == 13
    
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    def test_repo_status_shows_info(
        self,
        mock_repo_class,
        cli_runner,
        mock_root,
        tmp_config,
        sample_snapshots
    ):
        """repo-status shows repository information."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_repo.profile_name = "test-profile"
        mock_repo.repo_path = "/tmp/test-repo"
        mock_repo.list_snapshots.return_value = sample_snapshots
        mock_repo.list_backup_units.return_value = []
        
        result = cli_runner.invoke(
            app,
            ["repo-status", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "KOPIA REPOSITORY STATUS" in result.stdout
        assert "Connected" in result.stdout


@pytest.mark.unit
class TestRepoWhichConfigCommand:
    """Tests for repo-which-config command."""
    
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    def test_which_config_works(
        self,
        mock_repo_class,
        cli_runner,
        mock_root,
        tmp_config
    ):
        """repo-which-config shows config paths."""
        mock_repo = mock_repo_class.return_value
        mock_repo.profile_name = "test-profile"
        mock_repo._get_config_file.return_value = "/home/user/.config/kopia/repository-test.config"
        
        result = cli_runner.invoke(
            app,
            ["repo-which-config", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "Profile" in result.stdout
        assert "test-profile" in result.stdout


@pytest.mark.unit
class TestRepoSetDefaultCommand:
    """Tests for repo-set-default command."""
    
    def test_set_default_requires_root(self, cli_runner, mock_non_root):
        """repo-set-default requires root privileges."""
        result = cli_runner.invoke(app, ["repo-set-default"])
        
        assert result.exit_code == 13
    
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    @patch('kopi_docka.commands.repository_commands.Path')
    def test_set_default_creates_symlink(
        self,
        mock_path_class,
        mock_repo_class,
        cli_runner,
        mock_root,
        tmp_config
    ):
        """repo-set-default creates symlink to profile config."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_repo._get_config_file.return_value = "/home/user/.config/kopia/repository-test.config"
        
        # Mock Path operations
        mock_dst = MagicMock()
        mock_dst.exists.return_value = False
        mock_dst.is_symlink.return_value = False
        mock_path_class.home.return_value = Path("/home/user")
        
        result = cli_runner.invoke(
            app,
            ["repo-set-default", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "Default kopia config set" in result.stdout


@pytest.mark.unit
class TestRepoMaintenanceCommand:
    """Tests for repo-maintenance command."""
    
    def test_maintenance_requires_root(self, cli_runner, mock_non_root):
        """repo-maintenance requires root privileges."""
        result = cli_runner.invoke(app, ["repo-maintenance"])
        
        assert result.exit_code == 13
    
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    def test_maintenance_runs(
        self,
        mock_repo_class,
        cli_runner,
        mock_root,
        tmp_config
    ):
        """repo-maintenance runs maintenance tasks."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        
        result = cli_runner.invoke(
            app,
            ["repo-maintenance", "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "Maintenance completed" in result.stdout
        mock_repo.maintenance_run.assert_called_once()


@pytest.mark.unit
class TestRepoInitPathCommand:
    """Tests for repo-init-path command."""
    
    def test_init_path_requires_root(self, cli_runner, mock_non_root, tmp_path):
        """repo-init-path requires root privileges."""
        result = cli_runner.invoke(
            app,
            ["repo-init-path", str(tmp_path / "repo")]
        )
        
        assert result.exit_code == 13
    
    @patch('kopi_docka.commands.repository_commands.subprocess.run')
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    def test_init_path_creates_repo(
        self,
        mock_repo_class,
        mock_subprocess,
        cli_runner,
        mock_root,
        tmp_config,
        tmp_path
    ):
        """repo-init-path creates repository at specified path."""
        repo_path = tmp_path / "test-repo"
        
        mock_repo = mock_repo_class.return_value
        mock_repo._get_env.return_value = {}
        mock_repo._get_config_file.return_value = str(tmp_path / "config.json")
        mock_repo.profile_name = "test-profile"
        
        # Mock subprocess calls (create, connect, status)
        mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")
        
        result = cli_runner.invoke(
            app,
            ["repo-init-path", str(repo_path), "--config", str(tmp_config)]
        )
        
        assert result.exit_code == 0
        assert "Repository created & connected" in result.stdout


@pytest.mark.unit
class TestRepoSelftestCommand:
    """Tests for repo-selftest command."""
    
    def test_selftest_requires_root(self, cli_runner, mock_non_root):
        """repo-selftest requires root privileges."""
        result = cli_runner.invoke(app, ["repo-selftest"])
        
        assert result.exit_code == 13
    
    @patch('kopi_docka.commands.repository_commands.KopiaRepository')
    @patch('kopi_docka.commands.repository_commands.Config')
    def test_selftest_creates_ephemeral(
        self,
        mock_config_class,
        mock_repo_class,
        cli_runner,
        mock_root,
        tmp_path
    ):
        """repo-selftest creates and tests ephemeral repository."""
        mock_repo = mock_repo_class.return_value
        mock_repo.is_connected.return_value = True
        mock_repo.create_snapshot.return_value = "test-snapshot-id"
        mock_repo.list_snapshots.return_value = [{"id": "test-snapshot-id"}]
        
        result = cli_runner.invoke(
            app,
            ["repo-selftest", "--tmpdir", str(tmp_path), "--keep"]
        )
        
        assert result.exit_code == 0
        assert "Selftest" in result.stdout
        mock_repo.initialize.assert_called_once()
        mock_repo.create_snapshot.assert_called_once()
