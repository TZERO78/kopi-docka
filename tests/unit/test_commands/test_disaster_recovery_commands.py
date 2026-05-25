"""Unit tests for kopi_docka.commands.disaster_recovery_commands.

v7.6.3 regression: the streaming path used ``Console.print(..., err=True)``
which Rich's API does not support — every invocation of
``disaster-recovery export --stream`` blew up with ``TypeError: Console.print()
got an unexpected keyword argument 'err'`` before any ZIP content was
emitted. Tests below verify the stream path runs without that TypeError
and exits 1 (with a usable error message) when --passphrase is missing.
"""

from unittest.mock import patch

import pytest

from kopi_docka.__main__ import app


@pytest.fixture
def _stream_env(tmp_path):
    """Common fixture: a minimal config plus a stubbed manager that
    pretends to stream a bundle without touching the network."""
    import json
    cfg_file = tmp_path / "kopi-docka.json"
    cfg_file.write_text(json.dumps({
        "kopia": {
            "kopia_params": "filesystem --path /tmp/repo",
            "password": "test-password-123",
            "profile": "test",
            "compression": "zstd",
            "encryption": "AES256-GCM-HMAC-SHA256",
            "cache_directory": "/tmp/cache",
        },
        "backup": {"base_path": str(tmp_path)},
        "docker": {"socket": "/var/run/docker.sock"},
        "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 5},
        "logging": {"level": "INFO", "file": str(tmp_path / "k.log")},
    }))
    return cfg_file


def _patches():
    """Common patches: pretend kopia is installed + stub the DR manager.

    CI runners don't have kopia binaries, so the command's
    dependency-check would exit before reaching the streaming branch.
    """
    return [
        patch(
            "kopi_docka.helpers.dependency_helper.DependencyHelper.exists",
            return_value=True,
        ),
        patch(
            "kopi_docka.commands.disaster_recovery_commands.DisasterRecoveryManager"
        ),
    ]


@pytest.mark.unit
class TestStreamErrorPath:
    """The --stream-without-passphrase path must exit 1 with a clear
    message — and must NOT crash with TypeError on Console.print()."""

    def test_missing_passphrase_exits_one_cleanly(
        self, cli_runner, mock_root, _stream_env
    ):
        patches = _patches()
        for p in patches:
            p.start()
        try:
            result = cli_runner.invoke(
                app,
                ["--config", str(_stream_env),
                 "disaster-recovery", "export", "--stream"],
            )
        finally:
            for p in patches:
                p.stop()

        assert result.exit_code == 1, result.output
        # The actual user-facing hint must be present
        assert "--stream requires --passphrase" in result.output
        # Regression: the bug crashed before this message could be shown
        assert "unexpected keyword argument" not in result.output
        assert "Console.print()" not in result.output


@pytest.mark.unit
class TestStreamHappyPath:
    """The --stream-with-passphrase path must invoke the manager's
    export_to_stream() without crashing on the surrounding console
    messages."""

    def test_stream_with_passphrase_does_not_crash_on_console_call(
        self, cli_runner, mock_root, _stream_env
    ):
        with patch(
            "kopi_docka.helpers.dependency_helper.DependencyHelper.exists",
            return_value=True,
        ), patch(
            "kopi_docka.commands.disaster_recovery_commands.DisasterRecoveryManager"
        ) as mock_mgr_cls:
            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.export_to_stream.return_value = None

            result = cli_runner.invoke(
                app,
                ["--config", str(_stream_env),
                 "disaster-recovery", "export",
                 "--stream", "--passphrase", "test-pp"],
            )

        # The pre-fix bug exited non-zero with a TypeError trace; fix
        # must run cleanly through to the manager call.
        assert "unexpected keyword argument" not in result.output, result.output
        assert "Console.print()" not in result.output, result.output
        assert "TypeError" not in result.output, result.output
        # The manager should have been told to stream
        mock_mgr.export_to_stream.assert_called_once()
