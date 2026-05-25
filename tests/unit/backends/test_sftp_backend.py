"""
Unit tests for SFTP backend.

Covers dependency checking (REQUIRED_TOOLS) and — since v7.6.1 (Plan
0038) — the canonical kopia_params shape produced by the wizard and the
``rebuild_kopia_params`` repair hook.
"""

import shlex
from unittest.mock import patch, Mock
import pytest

from kopi_docka.backends.sftp import SFTPBackend
from kopi_docka.backends.base import DependencyError, MissingCredentialsError
from kopi_docka.helpers.dependency_helper import ToolInfo


@pytest.fixture
def sftp_backend():
    """Create an SFTPBackend instance for testing."""
    # Mock config to avoid initialization issues
    mock_config = Mock()
    backend = SFTPBackend(config=mock_config)
    return backend


class TestRequiredTools:
    """Test REQUIRED_TOOLS definition."""

    def test_required_tools_defined(self, sftp_backend):
        """Test that REQUIRED_TOOLS includes SSH tools."""
        assert hasattr(sftp_backend, 'REQUIRED_TOOLS')
        assert sftp_backend.REQUIRED_TOOLS == ["ssh", "ssh-keygen"]

    def test_required_tools_is_list(self, sftp_backend):
        """Test that REQUIRED_TOOLS is a list."""
        assert isinstance(sftp_backend.REQUIRED_TOOLS, list)
        assert len(sftp_backend.REQUIRED_TOOLS) == 2


class TestCheckDependencies:
    """Test check_dependencies method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_all_present(self, mock_missing, sftp_backend):
        """Test check_dependencies when all SSH tools are present."""
        mock_missing.return_value = []

        result = sftp_backend.check_dependencies()

        assert result == []
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when ssh is missing."""
        mock_missing.return_value = ["ssh"]

        result = sftp_backend.check_dependencies()

        assert result == ["ssh"]
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_ssh_keygen_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when ssh-keygen is missing."""
        mock_missing.return_value = ["ssh-keygen"]

        result = sftp_backend.check_dependencies()

        assert result == ["ssh-keygen"]
        mock_missing.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_dependencies_both_missing(self, mock_missing, sftp_backend):
        """Test check_dependencies when both SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        result = sftp_backend.check_dependencies()

        assert len(result) == 2
        assert "ssh" in result
        assert "ssh-keygen" in result


class TestGetDependencyStatus:
    """Test get_dependency_status method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_all_installed(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when all SSH tools are installed."""
        mock_check_all.return_value = {
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
        }

        result = sftp_backend.get_dependency_status()

        assert len(result) == 2
        assert all(tool.installed for tool in result.values())
        assert result["ssh"].version == "8.9"
        assert result["ssh-keygen"].installed is True
        mock_check_all.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_ssh_missing(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when ssh is missing."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(
                name="ssh",
                installed=False,
                path=None,
                version=None
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert result["ssh"].installed is False
        assert result["ssh"].path is None
        assert result["ssh-keygen"].installed is True
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_both_missing(self, mock_check_all, sftp_backend):
        """Test get_dependency_status when both tools are missing."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(
                name="ssh",
                installed=False,
                path=None,
                version=None
            ),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=False,
                path=None,
                version=None
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert result["ssh"].installed is False
        assert result["ssh-keygen"].installed is False
        mock_check_all.assert_called_once()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check_all')
    def test_get_dependency_status_returns_dict(self, mock_check_all, sftp_backend):
        """Test that get_dependency_status returns a dictionary."""
        mock_check_all.return_value = {
            "ssh": ToolInfo(name="ssh", installed=True, path="/usr/bin/ssh", version="8.9"),
            "ssh-keygen": ToolInfo(
                name="ssh-keygen",
                installed=True,
                path="/usr/bin/ssh-keygen",
                version="8.9"
            ),
        }

        result = sftp_backend.get_dependency_status()

        assert isinstance(result, dict)
        assert all(isinstance(info, ToolInfo) for info in result.values())


class TestConfigureDependencyCheck:
    """Test that configure checks dependencies."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    def test_configure_raises_on_missing_dependencies(
        self, mock_prompt, mock_missing, sftp_backend
    ):
        """Test that configure raises DependencyError when SSH tools are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        with pytest.raises(DependencyError) as exc_info:
            sftp_backend.configure()

        assert "ssh" in str(exc_info.value).lower()
        # Prompt should not be called if dependencies are missing
        mock_prompt.assert_not_called()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    @patch('typer.prompt')
    @patch('typer.confirm')
    def test_configure_proceeds_when_dependencies_present(
        self, mock_confirm, mock_prompt, mock_missing, sftp_backend
    ):
        """Test that configure proceeds when all dependencies are present."""
        mock_missing.return_value = []
        # Mock prompts to avoid interactive input
        mock_prompt.side_effect = ["test-host", "22", "testuser", "/remote/path"]
        mock_confirm.return_value = True

        # Should not raise DependencyError
        try:
            result = sftp_backend.configure()
            # If it gets here, dependencies were checked and passed
            assert mock_missing.called
        except (SystemExit, Exception) as e:
            # Other errors are OK for this test - we just care that DependencyError wasn't raised
            if isinstance(e, DependencyError):
                pytest.fail("DependencyError should not be raised when dependencies are present")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_configure_checks_dependencies_first(self, mock_missing, sftp_backend):
        """Test that configure checks dependencies before any interactive prompts."""
        mock_missing.return_value = ["ssh"]

        with pytest.raises(DependencyError):
            sftp_backend.configure()

        # Verify dependency check was called
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])


# ---------------------------------------------------------------------------
# Plan 0038 (v7.6.1): wizard must emit canonical Kopia SFTP shape and
# persist a [credentials] block. Pre-v7.6.1 the wizard shipped the broken
# ``--path=user@host:path`` form and an invalid ``--sftp-port`` flag —
# same family as the Plan 0029 Tailscale bug.
# ---------------------------------------------------------------------------


def _run_configure(
    backend,
    *,
    user="root",
    host="nas.example.com",
    path="/backup/kopia",
    port="22",
    ssh_key="/root/.ssh/id_ed25519",
    known_hosts_return=None,
):
    """Drive SFTPBackend.configure() with all side effects mocked."""
    prompts = [user, host, path, port, ssh_key]
    with patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing',
               return_value=[]), \
         patch('typer.prompt', side_effect=prompts), \
         patch('kopi_docka.backends.sftp.ensure_known_hosts',
               return_value=known_hosts_return):
        return backend.configure()


@pytest.mark.unit
class TestConfigureCanonicalShape:
    """The wizard's kopia_params must be Kopia-correct (Plan 0038)."""

    def test_kopia_params_uses_separate_flags(self, sftp_backend):
        result = _run_configure(sftp_backend)
        params = result["kopia_params"]

        assert params.startswith("sftp ")
        assert "--path=/backup/kopia" in params
        assert "--host=nas.example.com" in params
        assert "--username=root" in params
        assert "--keyfile=/root/.ssh/id_ed25519" in params

    def test_path_does_not_embed_host(self, sftp_backend):
        """Pre-v7.6.1 regression: the wizard wrote ``--path user@host:path``."""
        result = _run_configure(sftp_backend, host="my-host.example.com")

        for tok in shlex.split(result["kopia_params"]):
            if tok.startswith("--path="):
                assert ":" not in tok.split("=", 1)[1]
                break
        else:
            pytest.fail("No --path= flag found")

    def test_port_22_not_emitted(self, sftp_backend):
        result = _run_configure(sftp_backend, port="22")
        assert "--port" not in result["kopia_params"]

    def test_custom_port_emits_port_flag_not_sftp_port(self, sftp_backend):
        """Pre-v7.6.1 used ``--sftp-port`` — Kopia rejects that flag.
        Verified locally with `kopia repository create sftp --sftp-port=22 ...`
        → ``unknown long flag '--sftp-port'``.
        """
        result = _run_configure(sftp_backend, port="2222")
        assert "--port=2222" in result["kopia_params"]
        assert "--sftp-port" not in result["kopia_params"]

    def test_known_hosts_flag_added_when_keyscan_succeeds(self, sftp_backend):
        from pathlib import Path
        result = _run_configure(
            sftp_backend,
            known_hosts_return=Path("/root/.ssh/known_hosts"),
        )
        assert "--known-hosts=/root/.ssh/known_hosts" in result["kopia_params"]

    def test_known_hosts_flag_omitted_when_keyscan_fails(self, sftp_backend):
        result = _run_configure(sftp_backend, known_hosts_return=None)
        assert "--known-hosts" not in result["kopia_params"]


@pytest.mark.unit
class TestConfigureCredentialsBlock:
    """The wizard must persist a [credentials] block so that
    ``advanced config repair-kopia-params`` can rebuild kopia_params
    later without the user having to re-run the full wizard."""

    def test_credentials_block_present(self, sftp_backend):
        result = _run_configure(sftp_backend)
        assert "credentials" in result
        assert isinstance(result["credentials"], dict)

    def test_credentials_record_all_required_keys(self, sftp_backend):
        from pathlib import Path
        result = _run_configure(
            sftp_backend,
            user="backupuser",
            host="nas.example.com",
            path="/srv/backups",
            ssh_key="/home/me/.ssh/sftp_ed25519",
            known_hosts_return=Path("/home/me/.ssh/known_hosts"),
        )
        creds = result["credentials"]
        assert creds["remote_path"] == "/srv/backups"
        assert creds["host"] == "nas.example.com"
        assert creds["ssh_user"] == "backupuser"
        assert creds["ssh_key"] == "/home/me/.ssh/sftp_ed25519"
        assert creds["known_hosts"] == "/home/me/.ssh/known_hosts"

    def test_credentials_includes_peer_fqdn_alias(self, sftp_backend):
        """``peer_fqdn`` alias keeps SFTP credentials compatible with
        the existing repair-kopia-params fallback chain
        (host → peer_fqdn → peer_hostname)."""
        result = _run_configure(sftp_backend, host="nas.example.com")
        creds = result["credentials"]
        assert creds["peer_fqdn"] == "nas.example.com"


@pytest.mark.unit
class TestRebuildKopiaParams:
    """SFTPBackend.rebuild_kopia_params — used by repair-kopia-params."""

    def test_rebuilds_from_host_key(self, sftp_backend):
        creds = {
            "remote_path": "/backup",
            "host": "nas",
            "ssh_user": "root",
            "ssh_key": "/root/.ssh/id",
        }
        params = sftp_backend.rebuild_kopia_params(creds)
        assert "--path=/backup" in params
        assert "--host=nas" in params

    def test_falls_back_to_peer_fqdn(self, sftp_backend):
        """Tailscale-shaped credentials use peer_fqdn — when repair-kopia-params
        sees ``sftp`` as backend it dispatches to SFTPBackend regardless of
        whether the install was Tailscale-flavoured or direct-SFTP."""
        creds = {
            "remote_path": "/backup",
            "peer_fqdn": "tzero.ts.net",
            "ssh_user": "root",
            "ssh_key": "/root/.ssh/id",
        }
        params = sftp_backend.rebuild_kopia_params(creds)
        assert "--host=tzero.ts.net" in params

    def test_falls_back_to_peer_hostname(self, sftp_backend):
        creds = {
            "remote_path": "/backup",
            "peer_hostname": "legacy-peer",
            "ssh_user": "root",
            "ssh_key": "/root/.ssh/id",
        }
        params = sftp_backend.rebuild_kopia_params(creds)
        assert "--host=legacy-peer" in params

    def test_raises_when_credentials_missing(self, sftp_backend):
        with pytest.raises(MissingCredentialsError) as exc_info:
            sftp_backend.rebuild_kopia_params({"ssh_user": "root"})

        missing = exc_info.value.missing
        assert any("remote_path" in m for m in missing)
        assert any("host" in m or "peer_fqdn" in m for m in missing)
        assert any("ssh_key" in m for m in missing)

    def test_default_ssh_user_is_root(self, sftp_backend):
        creds = {
            "remote_path": "/backup",
            "host": "nas",
            "ssh_key": "/root/.ssh/id",
        }
        params = sftp_backend.rebuild_kopia_params(creds)
        assert "--username=root" in params


@pytest.mark.unit
class TestGetStatusParser:
    """get_status() parses the canonical kopia_params shape."""

    def test_parses_canonical_shape(self, sftp_backend):
        sftp_backend.config = {
            "kopia_params": (
                "sftp --path=/backup --host=nas.example.com "
                "--username=root --keyfile=/root/.ssh/id"
            )
        }
        status = sftp_backend.get_status()
        assert status["details"]["host"] == "nas.example.com"
        assert status["details"]["user"] == "root"
        assert status["details"]["path"] == "/backup"

    def test_parses_legacy_combined_shape(self, sftp_backend):
        """Old SFTP wizard wrote ``--path user@host:path`` — for installs
        that pre-date v7.6.1 the parser should still extract something
        sensible so doctor / status don't crash."""
        sftp_backend.config = {
            "kopia_params": "sftp --path root@nas.example.com:/backup"
        }
        status = sftp_backend.get_status()
        assert status["details"]["host"] == "nas.example.com"
        assert status["details"]["user"] == "root"
        assert status["details"]["path"] == "/backup"

    def test_picks_up_port(self, sftp_backend):
        sftp_backend.config = {
            "kopia_params": (
                "sftp --path=/backup --host=nas --username=root "
                "--keyfile=/root/.ssh/id --port=2222"
            )
        }
        status = sftp_backend.get_status()
        assert status["details"]["port"] == "2222"
