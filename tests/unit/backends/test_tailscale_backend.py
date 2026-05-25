"""
Unit tests for Tailscale backend dependency checking.

Tests REQUIRED_TOOLS enforcement for Tailscale SSH-based backup backend.
"""

from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from kopi_docka.backends.tailscale import TailscaleBackend
from kopi_docka.backends.base import DependencyError
from kopi_docka.helpers.dependency_helper import ToolInfo


@pytest.fixture
def tailscale_backend():
    """Create a TailscaleBackend instance for testing."""
    # Mock config to avoid initialization issues
    mock_config = Mock()
    backend = TailscaleBackend(config=mock_config)
    return backend


class TestRequiredTools:
    """Test REQUIRED_TOOLS definition."""

    def test_required_tools_defined(self, tailscale_backend):
        """Test that REQUIRED_TOOLS includes all necessary tools."""
        assert hasattr(tailscale_backend, 'REQUIRED_TOOLS')
        assert tailscale_backend.REQUIRED_TOOLS == [
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ]

    def test_required_tools_is_list(self, tailscale_backend):
        """Test that REQUIRED_TOOLS is a list."""
        assert isinstance(tailscale_backend.REQUIRED_TOOLS, list)
        assert len(tailscale_backend.REQUIRED_TOOLS) == 4


class TestCheckDependencies:
    """Test check_dependencies method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_all_present(self, mock_missing, tailscale_backend):
        """Test check_dependencies when all tools are present."""
        mock_missing.return_value = []

        result = tailscale_backend.check_dependencies()

        assert result == []
        mock_missing.assert_called_once_with([
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_tailscale_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when tailscale is missing."""
        mock_missing.return_value = ["tailscale"]

        result = tailscale_backend.check_dependencies()

        assert result == ["tailscale"]
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_tools_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        result = tailscale_backend.check_dependencies()

        assert "ssh" in result
        assert "ssh-keygen" in result
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_multiple_missing(self, mock_missing, tailscale_backend):
        """Test check_dependencies when multiple tools are missing."""
        mock_missing.return_value = ["tailscale", "ssh", "ssh-copy-id"]

        result = tailscale_backend.check_dependencies()

        assert len(result) == 3
        assert "tailscale" in result
        assert "ssh" in result
        assert "ssh-copy-id" in result


class TestGetDependencyStatus:
    """Test get_dependency_status method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_all_installed(self, mock_check_all, tailscale_backend):
        """Test get_dependency_status when all tools are installed."""
        mock_check_all.return_value = {
            "tailscale": ToolInfo(
                name="tailscale",
                installed=True,
                path="/usr/bin/tailscale",
                version="1.56.1"
            ),
            "ssh": ToolInfo(
                name="ssh",
                installed=True,
                path="/usr/bin/ssh",
                version="8.9"
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
            "ssh-copy-id": ToolInfo(
                name="ssh-copy-id",
                installed=True,
                path="/usr/bin/ssh-copy-id",
                version="8.9"
            ),
        }

        result = tailscale_backend.get_dependency_status()

        assert len(result) == 4
        assert all(tool.installed for tool in result.values())
        assert result["tailscale"].version == "1.56.1"
        assert result["ssh"].installed is True
        mock_check_all.assert_called_once_with([
            "tailscale", "ssh", "ssh-keygen", "ssh-copy-id"
        ])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_some_missing(self, mock_check_all, tailscale_backend):
        """Test get_dependency_status when some tools are missing."""
        mock_check_all.return_value = {
            "tailscale": ToolInfo(
                name="tailscale",
                installed=False,
                path=None,
                version=None
            ),
            "ssh": ToolInfo(
                name="ssh",
                installed=True,
                path="/usr/bin/ssh",
                version="8.9"
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
            "ssh-copy-id": ToolInfo(
                name="ssh-copy-id",
                installed=False,
                path=None,
                version=None
            ),
        }

        result = tailscale_backend.get_dependency_status()

        assert result["tailscale"].installed is False
        assert result["ssh"].installed is True
        assert result["ssh-copy-id"].installed is False
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_returns_dict(self, mock_check_all, tailscale_backend):
        """Test that get_dependency_status returns a dictionary."""
        mock_check_all.return_value = {
            tool: ToolInfo(name=tool, installed=True, path=f"/usr/bin/{tool}", version="1.0")
            for tool in ["tailscale", "ssh", "ssh-keygen", "ssh-copy-id"]
        }

        result = tailscale_backend.get_dependency_status()

        assert isinstance(result, dict)
        assert all(isinstance(info, ToolInfo) for info in result.values())


class TestSetupInteractiveDependencyCheck:
    """Test that setup_interactive checks dependencies."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_setup_interactive_raises_on_missing_dependencies(
        self, mock_prompt, mock_missing, tailscale_backend
    ):
        """Test that setup_interactive raises DependencyError when tools are missing."""
        mock_missing.return_value = ["tailscale", "ssh"]

        with pytest.raises(DependencyError) as exc_info:
            tailscale_backend.setup_interactive()

        assert "tailscale" in str(exc_info.value).lower()
        assert "ssh" in str(exc_info.value).lower()
        # Prompt should not be called if dependencies are missing
        mock_prompt.assert_not_called()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_setup_interactive_proceeds_when_dependencies_present(
        self, mock_prompt, mock_missing, tailscale_backend
    ):
        """Test that setup_interactive proceeds when all dependencies are present."""
        mock_missing.return_value = []
        # Mock prompts to avoid interactive input
        mock_prompt.side_effect = ["test-target", "22", "testuser"]

        # Should not raise DependencyError
        try:
            result = tailscale_backend.setup_interactive()
            # If it gets here, dependencies were checked and passed
            assert mock_missing.called
        except (SystemExit, Exception) as e:
            # Other errors are OK for this test - we just care that DependencyError wasn't raised
            if isinstance(e, DependencyError):
                pytest.fail("DependencyError should not be raised when dependencies are present")


# ---------------------------------------------------------------------------
# Phase 1 (Plan 0029): wizard must emit kopia_params with separate
# --path/--host/--username/--keyfile/--known-hosts flags — Kopia's SFTP
# backend rejects --path=HOST:PATH and refuses to connect without
# --username, which silently broke every v7.0.0–v7.3.13 wizard run.
# ---------------------------------------------------------------------------


def _run_setup_interactive(backend, *, known_hosts_return, ssh_user="root", remote_path="/mnt/backup"):
    """Drive setup_interactive() to completion with all SSH/peer work mocked.

    Returns the dict produced by the wizard.
    """
    from pathlib import Path as _Path

    peer = Mock()
    peer.hostname = "TZERO-SERVER"
    peer.fqdn = "tzero-server.beetal-vega.ts.net"
    peer.ip = "100.64.0.2"
    peer.online = True
    peer.os = "linux"

    with patch.object(TailscaleBackend, '_is_running', return_value=True), \
         patch.object(TailscaleBackend, '_list_peers', return_value=[peer]), \
         patch.object(TailscaleBackend, '_setup_ssh_key', return_value=True), \
         patch.object(TailscaleBackend, '_ensure_key_on_remote', return_value=None), \
         patch('kopi_docka.backends.tailscale.ensure_known_hosts', return_value=known_hosts_return), \
         patch.object(_Path, 'exists', return_value=True), \
         patch('kopi_docka.helpers.ui_utils.prompt_select', return_value=peer), \
         patch('kopi_docka.helpers.ui_utils.prompt_text', side_effect=[remote_path, ssh_user]), \
         patch('kopi_docka.helpers.ui_utils.prompt_confirm', return_value=True), \
         patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing', return_value=[]):
        return backend.setup_interactive()


class TestSetupInteractiveKopiaParams:
    """Plan 0029 / Phase 1 — kopia_params shape correctness."""

    def test_kopia_params_contains_all_required_flags(self, tailscale_backend):
        result = _run_setup_interactive(
            tailscale_backend,
            known_hosts_return=Path("/root/.ssh/known_hosts"),
        )
        params = result["kopia_params"]
        assert params.startswith("sftp ")
        assert "--path=" in params
        assert "--host=tzero-server.beetal-vega.ts.net" in params
        assert "--username=root" in params
        assert "--keyfile=" in params

    def test_kopia_params_path_has_no_host_prefix(self, tailscale_backend):
        """Regression: the v7.0–v7.3.13 bug shipped --path=HOST:PATH."""
        result = _run_setup_interactive(
            tailscale_backend,
            known_hosts_return=Path("/root/.ssh/known_hosts"),
            remote_path="/mnt/user/backups/kopi-docka",
        )
        params = result["kopia_params"]

        # Find the --path= value via the same shlex split production uses
        import shlex as _shlex
        for tok in _shlex.split(params):
            if tok.startswith("--path="):
                path_value = tok.split("=", 1)[1]
                break
        else:
            pytest.fail(f"No --path= flag in {params!r}")

        assert ":" not in path_value, (
            f"--path={path_value!r} still contains a host prefix — that is the "
            f"exact wizard bug Plan 0029 fixes."
        )
        assert path_value == "/mnt/user/backups/kopi-docka"

    def test_known_hosts_flag_added_when_present(self, tailscale_backend):
        result = _run_setup_interactive(
            tailscale_backend,
            known_hosts_return=Path("/root/.ssh/known_hosts"),
        )
        assert "--known-hosts=" in result["kopia_params"]
        assert result["credentials"]["known_hosts"] == "/root/.ssh/known_hosts"

    def test_known_hosts_flag_missing_when_keyscan_fails(self, tailscale_backend):
        """If ssh-keyscan fails, the wizard must drop --known-hosts entirely
        (rather than emitting --known-hosts= with an empty value, which
        Kopia would reject)."""
        result = _run_setup_interactive(
            tailscale_backend,
            known_hosts_return=None,
        )
        assert "--known-hosts" not in result["kopia_params"]
        assert result["credentials"]["known_hosts"] == ""

    def test_credentials_record_ssh_user(self, tailscale_backend):
        result = _run_setup_interactive(
            tailscale_backend,
            known_hosts_return=Path("/root/.ssh/known_hosts"),
            ssh_user="backupuser",
        )
        assert result["credentials"]["ssh_user"] == "backupuser"
        assert "--username=backupuser" in result["kopia_params"]


# Tests for the (now-extracted) ensure_known_hosts() helper live in
# tests/unit/test_helpers/test_backend_helper.py — the behaviour moved
# from TailscaleBackend._ensure_known_hosts to kopi_docka.helpers.backend_helper
# in v7.6.1 (Plan 0038) so the direct SFTP wizard can use it too.


# ---------------------------------------------------------------------------
# Phase 4 (Plan 0029): _mirror_key_to_persistent_path must classify the
# remote's SSH layout via inode comparison and skip the redundant mirror
# on modern Unraid where /root/.ssh is already symlinked to
# /boot/config/ssh/root/.
# ---------------------------------------------------------------------------


def _fake_probe(token: str, *, returncode: int = 0):
    """Return a Mock that mimics run_command()'s CompletedProcess-ish shape."""
    p = Mock()
    p.returncode = returncode
    p.stdout = token + "\n"
    p.stderr = ""
    return p


class TestClassifyRemoteSshLayout:
    """_classify_remote_ssh_layout reads the trailing token from the probe."""

    def test_modern_symlinked(self, tailscale_backend):
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            return_value=_fake_probe(TailscaleBackend._LAYOUT_UNRAID_SYMLINKED),
        ):
            result = tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            )
        assert result == TailscaleBackend._LAYOUT_UNRAID_SYMLINKED

    def test_modern_separate(self, tailscale_backend):
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            return_value=_fake_probe(TailscaleBackend._LAYOUT_UNRAID_SEPARATE),
        ):
            assert tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            ) == TailscaleBackend._LAYOUT_UNRAID_SEPARATE

    def test_legacy(self, tailscale_backend):
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            return_value=_fake_probe(TailscaleBackend._LAYOUT_UNRAID_LEGACY),
        ):
            assert tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            ) == TailscaleBackend._LAYOUT_UNRAID_LEGACY

    def test_standard_linux(self, tailscale_backend):
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            return_value=_fake_probe(TailscaleBackend._LAYOUT_STANDARD_LINUX),
        ):
            assert tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            ) == TailscaleBackend._LAYOUT_STANDARD_LINUX

    def test_returns_unknown_on_failure(self, tailscale_backend):
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            return_value=_fake_probe("", returncode=255),
        ):
            assert tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            ) == TailscaleBackend._LAYOUT_UNKNOWN

    def test_returns_unknown_on_subprocess_error(self, tailscale_backend):
        from kopi_docka.helpers.ui_utils import SubprocessError
        with patch(
            'kopi_docka.backends.tailscale.run_command',
            side_effect=SubprocessError("ssh exploded", 255),
        ):
            assert tailscale_backend._classify_remote_ssh_layout(
                "peer", Path("/tmp/key")
            ) == TailscaleBackend._LAYOUT_UNKNOWN


class TestMirrorPersistentPath:
    """_mirror_key_to_persistent_path dispatches on the classified layout."""

    def test_unraid_modern_symlinked_skips_mirror(self, tailscale_backend):
        with patch.object(
            TailscaleBackend,
            '_classify_remote_ssh_layout',
            return_value=TailscaleBackend._LAYOUT_UNRAID_SYMLINKED,
        ), patch('kopi_docka.backends.tailscale.run_command') as mock_run:
            tailscale_backend._mirror_key_to_persistent_path("peer", Path("/tmp/key"))

        # No ssh-write call should fire for the symlinked case.
        assert mock_run.call_count == 0

    def test_standard_linux_skips_mirror(self, tailscale_backend):
        with patch.object(
            TailscaleBackend,
            '_classify_remote_ssh_layout',
            return_value=TailscaleBackend._LAYOUT_STANDARD_LINUX,
        ), patch('kopi_docka.backends.tailscale.run_command') as mock_run:
            tailscale_backend._mirror_key_to_persistent_path("peer", Path("/tmp/key"))
        assert mock_run.call_count == 0

    def test_unknown_layout_skips_mirror(self, tailscale_backend):
        with patch.object(
            TailscaleBackend,
            '_classify_remote_ssh_layout',
            return_value=TailscaleBackend._LAYOUT_UNKNOWN,
        ), patch('kopi_docka.backends.tailscale.run_command') as mock_run:
            tailscale_backend._mirror_key_to_persistent_path("peer", Path("/tmp/key"))
        assert mock_run.call_count == 0

    def test_unraid_modern_separate_writes_into_root_directory(self, tailscale_backend):
        with patch.object(
            TailscaleBackend,
            '_classify_remote_ssh_layout',
            return_value=TailscaleBackend._LAYOUT_UNRAID_SEPARATE,
        ), patch('kopi_docka.backends.tailscale.run_command') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="persistent-write-ok\n", stderr="")
            tailscale_backend._mirror_key_to_persistent_path("peer", Path("/tmp/key"))

        assert mock_run.call_count == 1
        # The remote command (positional arg 0 → ssh argv list, last element
        # is the shell command) must target the file inside the dir.
        ssh_argv = mock_run.call_args[0][0]
        remote_cmd = ssh_argv[-1]
        assert "/boot/config/ssh/root/authorized_keys" in remote_cmd
        # And not the legacy file-on-the-directory-path form
        assert "touch /boot/config/ssh/root\n" not in remote_cmd

    def test_unraid_legacy_writes_to_root_file(self, tailscale_backend):
        with patch.object(
            TailscaleBackend,
            '_classify_remote_ssh_layout',
            return_value=TailscaleBackend._LAYOUT_UNRAID_LEGACY,
        ), patch('kopi_docka.backends.tailscale.run_command') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="persistent-write-ok\n", stderr="")
            tailscale_backend._mirror_key_to_persistent_path("peer", Path("/tmp/key"))

        assert mock_run.call_count == 1
        ssh_argv = mock_run.call_args[0][0]
        remote_cmd = ssh_argv[-1]
        assert "touch /boot/config/ssh/root " in remote_cmd  # space after = file
        assert "/boot/config/ssh/root/authorized_keys" not in remote_cmd
