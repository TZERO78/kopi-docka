"""Unit tests for backup_commands.py."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestSpinnerText:
    """ensure_repository() chooses spinner text based on backend type."""

    def _invoke_ensure(self, kopia_params: str):
        """Run ensure_repository() with a fake repo and capture the spinner text."""
        from kopi_docka.commands import backup_commands

        fake_repo = MagicMock()
        fake_repo.kopia_params = kopia_params
        fake_repo.is_connected.return_value = True

        ctx = MagicMock()
        ctx.obj = {"repository": fake_repo, "config": MagicMock()}

        captured = {}

        class _StatusCM:
            def __init__(self, text, **_kw):
                captured["text"] = text

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        with patch.object(backup_commands.console, "status", side_effect=_StatusCM):
            backup_commands.ensure_repository(ctx)

        return captured["text"]

    def test_rclone_backend_shows_long_wait_hint(self):
        text = self._invoke_ensure("rclone --remote-path=gdrive:backups")
        assert "rclone cold-start" in text

    def test_sftp_backend_shows_plain_hint(self):
        text = self._invoke_ensure(
            "sftp --path=/backup --host=peer.ts.net "
            "--username=root --keyfile=/root/.ssh/id_ed25519"
        )
        assert "rclone" not in text.lower()
        assert "Connecting to repository" in text

    def test_filesystem_backend_shows_plain_hint(self):
        text = self._invoke_ensure("filesystem --path /mnt/backup")
        assert "rclone" not in text.lower()

    def test_empty_params_shows_plain_hint(self):
        text = self._invoke_ensure("")
        assert "rclone" not in text.lower()
