"""
Unit tests for smart repository initialization wizard.

Tests the detection, wizard, password retry, and overwrite logic.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from kopi_docka.commands.repository_commands import (
    _detect_existing_filesystem_repo,
    _smart_init_wizard,
    _connect_with_password_retry,
    _overwrite_repository,
)


class TestDetectExistingFilesystemRepo:
    """Tests for _detect_existing_filesystem_repo()"""

    def test_non_filesystem_backend_returns_false(self):
        """Non-filesystem backends should return (False, None)."""
        assert _detect_existing_filesystem_repo("s3 --bucket my-bucket") == (False, None)
        assert _detect_existing_filesystem_repo("b2 --bucket my-bucket") == (False, None)
        assert _detect_existing_filesystem_repo("azure --container foo") == (False, None)
        assert _detect_existing_filesystem_repo("gcs --bucket my-bucket") == (False, None)
        assert _detect_existing_filesystem_repo("sftp --path /remote") == (False, None)

    def test_filesystem_without_path_returns_false(self):
        """Filesystem backend without --path should return (False, None)."""
        assert _detect_existing_filesystem_repo("filesystem") == (False, None)
        assert _detect_existing_filesystem_repo("filesystem --other-flag") == (False, None)

    def test_nonexistent_path_returns_false(self, tmp_path):
        """Non-existent path should return (False, None)."""
        nonexistent = tmp_path / "does-not-exist"
        result = _detect_existing_filesystem_repo(f"filesystem --path {nonexistent}")
        assert result == (False, None)

    def test_empty_directory_returns_false_with_path(self, tmp_path):
        """Empty directory should return (False, path) - no repo yet."""
        empty_dir = tmp_path / "empty-repo"
        empty_dir.mkdir()

        result = _detect_existing_filesystem_repo(f"filesystem --path {empty_dir}")
        assert result == (False, empty_dir)

    def test_directory_with_kopia_markers_returns_true(self, tmp_path):
        """Directory with Kopia markers should return (True, path)."""
        repo_dir = tmp_path / "kopia-repo"
        repo_dir.mkdir()

        # Create kopia.repository marker
        (repo_dir / "kopia.repository").touch()

        result = _detect_existing_filesystem_repo(f"filesystem --path {repo_dir}")
        assert result == (True, repo_dir)

    def test_directory_with_p_folder_returns_true(self, tmp_path):
        """Directory with p/ blob folder should return (True, path)."""
        repo_dir = tmp_path / "kopia-repo"
        repo_dir.mkdir()

        # Create p/ directory (Kopia blob storage)
        (repo_dir / "p").mkdir()

        result = _detect_existing_filesystem_repo(f"filesystem --path {repo_dir}")
        assert result == (True, repo_dir)

    def test_directory_with_content_but_no_markers(self, tmp_path):
        """Directory with content but no Kopia markers should return (False, path)."""
        content_dir = tmp_path / "some-content"
        content_dir.mkdir()
        (content_dir / "random-file.txt").write_text("hello")

        result = _detect_existing_filesystem_repo(f"filesystem --path {content_dir}")
        assert result == (False, content_dir)

    def test_path_with_quotes(self, tmp_path):
        """Path with quotes should be parsed correctly."""
        repo_dir = tmp_path / "quoted-repo"
        repo_dir.mkdir()
        (repo_dir / "kopia.repository").touch()

        # Test double quotes
        result = _detect_existing_filesystem_repo(f'filesystem --path="{repo_dir}"')
        assert result == (True, repo_dir)

        # Test single quotes
        result = _detect_existing_filesystem_repo(f"filesystem --path='{repo_dir}'")
        assert result == (True, repo_dir)

    def test_path_with_equals_sign(self, tmp_path):
        """Path specified with = should work."""
        repo_dir = tmp_path / "equals-repo"
        repo_dir.mkdir()
        (repo_dir / "kopia.repository").touch()

        result = _detect_existing_filesystem_repo(f"filesystem --path={repo_dir}")
        assert result == (True, repo_dir)

    def test_symlink_is_resolved(self, tmp_path):
        """Symlinks should be resolved to their target."""
        real_dir = tmp_path / "real-repo"
        real_dir.mkdir()
        (real_dir / "kopia.repository").touch()

        link_path = tmp_path / "repo-link"
        link_path.symlink_to(real_dir)

        result = _detect_existing_filesystem_repo(f"filesystem --path {link_path}")
        assert result[0] is True
        # Path should be resolved to real path
        assert result[1] == real_dir

    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """~ should be expanded to home directory."""
        # Create a mock home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        repo_dir = fake_home / "kopia-repo"
        repo_dir.mkdir()
        (repo_dir / "kopia.repository").touch()

        monkeypatch.setenv("HOME", str(fake_home))

        result = _detect_existing_filesystem_repo("filesystem --path ~/kopia-repo")
        assert result == (True, repo_dir)

    def test_file_instead_of_directory_returns_false(self, tmp_path):
        """If path is a file (not directory), return (False, None)."""
        file_path = tmp_path / "not-a-dir"
        file_path.write_text("I am a file")

        result = _detect_existing_filesystem_repo(f"filesystem --path {file_path}")
        assert result == (False, None)


class TestSmartInitWizard:
    """Tests for _smart_init_wizard()"""

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_returns_connect_on_choice_1(self, mock_console, mock_prompt, tmp_path):
        """Choice '1' should return 'connect'."""
        mock_prompt.return_value = "1"

        result = _smart_init_wizard(tmp_path)
        assert result == "connect"

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_returns_overwrite_on_choice_2(self, mock_console, mock_prompt, tmp_path):
        """Choice '2' should return 'overwrite'."""
        mock_prompt.return_value = "2"

        result = _smart_init_wizard(tmp_path)
        assert result == "overwrite"

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_returns_abort_on_choice_3(self, mock_console, mock_prompt, tmp_path):
        """Choice '3' should return 'abort'."""
        mock_prompt.return_value = "3"

        result = _smart_init_wizard(tmp_path)
        assert result == "abort"

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_accepts_text_choices(self, mock_console, mock_prompt, tmp_path):
        """Text choices like 'connect', 'overwrite', 'abort' should work."""
        mock_prompt.return_value = "connect"
        assert _smart_init_wizard(tmp_path) == "connect"

        mock_prompt.return_value = "overwrite"
        assert _smart_init_wizard(tmp_path) == "overwrite"

        mock_prompt.return_value = "abort"
        assert _smart_init_wizard(tmp_path) == "abort"


class TestConnectWithPasswordRetry:
    """Tests for _connect_with_password_retry()"""

    @patch("kopi_docka.commands.repository_commands.getpass.getpass")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_success_on_first_try_with_current_password(self, mock_console, mock_getpass):
        """Should succeed immediately if current password works."""
        mock_repo = Mock()
        mock_repo.connect.return_value = None  # Success
        mock_cfg = Mock()

        result = _connect_with_password_retry(mock_repo, mock_cfg, max_attempts=3)

        assert result is True
        mock_repo.connect.assert_called_once()
        # getpass should not be called since first attempt succeeded
        mock_getpass.assert_not_called()

    @patch("kopi_docka.commands.repository_commands.getpass.getpass")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_success_on_second_attempt(self, mock_console, mock_getpass):
        """Should succeed after password retry."""
        mock_repo = Mock()
        mock_repo.connect.side_effect = [
            Exception("invalid password"),  # First attempt fails
            None,  # Second attempt succeeds
        ]
        mock_repo.config = Mock()

        mock_cfg = Mock()
        mock_cfg.config_file = Path("/tmp/test.json")

        mock_getpass.return_value = "correct-password"

        with patch("kopi_docka.commands.repository_commands.Config") as MockConfig:
            MockConfig.return_value = Mock()
            result = _connect_with_password_retry(mock_repo, mock_cfg, max_attempts=3)

        assert result is True
        assert mock_repo.connect.call_count == 2

    @patch("kopi_docka.commands.repository_commands.getpass.getpass")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_fails_after_max_attempts(self, mock_console, mock_getpass):
        """Should fail after exhausting all attempts."""
        mock_repo = Mock()
        mock_repo.connect.side_effect = Exception("invalid password")
        mock_repo.config = Mock()

        mock_cfg = Mock()
        mock_cfg.config_file = Path("/tmp/test.json")

        mock_getpass.return_value = "wrong-password"

        with patch("kopi_docka.commands.repository_commands.Config") as MockConfig:
            MockConfig.return_value = Mock()
            result = _connect_with_password_retry(mock_repo, mock_cfg, max_attempts=3)

        assert result is False
        # Initial attempt + 3 retries = 4 total connect calls
        assert mock_repo.connect.call_count == 4

    @patch("kopi_docka.commands.repository_commands.getpass.getpass")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_empty_password_skipped(self, mock_console, mock_getpass):
        """Empty password input should be skipped (continue to next attempt)."""
        mock_repo = Mock()
        mock_repo.connect.side_effect = [
            Exception("invalid password"),  # Initial
            None,  # After valid password
        ]
        mock_repo.config = Mock()

        mock_cfg = Mock()
        mock_cfg.config_file = Path("/tmp/test.json")

        # First empty, then valid password
        mock_getpass.side_effect = ["", "valid-password"]

        with patch("kopi_docka.commands.repository_commands.Config") as MockConfig:
            MockConfig.return_value = Mock()
            result = _connect_with_password_retry(mock_repo, mock_cfg, max_attempts=3)

        assert result is True


class TestOverwriteRepository:
    """Tests for _overwrite_repository()"""

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_abort_on_non_yes_confirmation(self, mock_console, mock_prompt, tmp_path):
        """Should return False if user doesn't type 'yes'."""
        mock_prompt.return_value = "no"
        mock_repo = Mock()

        result = _overwrite_repository(mock_repo, tmp_path)

        assert result is False
        # Repository should NOT be touched
        mock_repo.disconnect.assert_not_called()

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    @patch("kopi_docka.commands.repository_commands.shutil.rmtree")
    def test_successful_overwrite(self, mock_rmtree, mock_console, mock_prompt, tmp_path):
        """Should delete and reinitialize on 'yes' confirmation."""
        mock_prompt.return_value = "yes"
        mock_repo = Mock()
        mock_repo.disconnect.return_value = None
        mock_repo.initialize.return_value = None

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        result = _overwrite_repository(mock_repo, repo_path)

        assert result is True
        mock_rmtree.assert_called_once()
        mock_repo.initialize.assert_called_once()

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    @patch("kopi_docka.commands.repository_commands.shutil.rmtree")
    def test_permission_error_handling(self, mock_rmtree, mock_console, mock_prompt, tmp_path):
        """Should handle PermissionError gracefully."""
        mock_prompt.return_value = "yes"
        mock_rmtree.side_effect = PermissionError("Access denied")
        mock_repo = Mock()

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        result = _overwrite_repository(mock_repo, repo_path)

        assert result is False

    @patch("kopi_docka.commands.repository_commands.typer.prompt")
    @patch("kopi_docka.commands.repository_commands.console")
    def test_symlink_handling(self, mock_console, mock_prompt, tmp_path):
        """Should handle symlinks by removing the link, not target."""
        mock_prompt.return_value = "yes"
        mock_repo = Mock()
        mock_repo.disconnect.return_value = None
        mock_repo.initialize.return_value = None

        # Create real dir and symlink
        real_dir = tmp_path / "real-repo"
        real_dir.mkdir()
        (real_dir / "some-file.txt").write_text("data")

        link_path = tmp_path / "repo-link"
        link_path.symlink_to(real_dir)

        result = _overwrite_repository(mock_repo, link_path)

        assert result is True
        # Symlink should be removed
        assert not link_path.exists() or link_path.is_dir()
        mock_repo.initialize.assert_called_once()
