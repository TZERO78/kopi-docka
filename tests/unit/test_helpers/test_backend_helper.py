"""Unit tests for kopi_docka.helpers.backend_helper.

Plan 0038 — single source of truth for the canonical Kopia SFTP shape.
The SFTP wizard, the Tailscale wizard, and ``rebuild_kopia_params``
all build their params through ``build_sftp_kopia_params``; broken-
once = broken-everywhere, fixed-once = fixed-everywhere.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kopi_docka.helpers.backend_helper import (
    build_sftp_kopia_params,
    ensure_known_hosts,
)


@pytest.mark.unit
class TestBuildSftpKopiaParams:
    """build_sftp_kopia_params() — canonical Kopia SFTP shape."""

    def test_minimum_required_flags_emitted(self):
        params = build_sftp_kopia_params(
            remote_path="/backup/kopia",
            host="nas.example.com",
            ssh_user="root",
            ssh_key="/root/.ssh/id_ed25519",
        )

        assert params.startswith("sftp ")
        assert "--path=/backup/kopia" in params
        assert "--host=nas.example.com" in params
        assert "--username=root" in params
        assert "--keyfile=/root/.ssh/id_ed25519" in params

    def test_path_is_not_combined_with_host(self):
        """Regression for Plan 0029 / Plan 0038 — the legacy wizards shipped
        ``--path=user@host:path``; Kopia accepts it at connect but every
        subsequent snapshot hangs. The helper must NEVER produce that form."""
        params = build_sftp_kopia_params(
            remote_path="/mnt/user/backups",
            host="tzero-server.beetal-vega.ts.net",
            ssh_user="root",
            ssh_key="/root/.ssh/id_ed25519",
        )

        # Find the --path= value
        for tok in params.split():
            if tok.startswith("--path="):
                path_value = tok.split("=", 1)[1]
                break
        else:
            pytest.fail(f"No --path= in output: {params!r}")

        assert ":" not in path_value, (
            f"--path={path_value!r} still embeds host:port — exact "
            f"wizard-bug shape Plan 0038 fixes."
        )

    def test_known_hosts_emitted_when_provided(self):
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            known_hosts="/root/.ssh/known_hosts",
        )
        assert "--known-hosts=/root/.ssh/known_hosts" in params

    def test_known_hosts_omitted_when_none(self):
        """When ssh-keyscan fails the wizard passes ``None`` — must NOT
        emit ``--known-hosts=`` (Kopia would reject an empty flag value).
        """
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            known_hosts=None,
        )
        assert "--known-hosts" not in params

    def test_port_omitted_when_default_22(self):
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            port="22",
        )
        assert "--port" not in params

    def test_port_emitted_when_non_default(self):
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            port="2222",
        )
        assert "--port=2222" in params

    def test_port_accepts_int(self):
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            port=2222,
        )
        assert "--port=2222" in params

    def test_uses_port_flag_not_sftp_port(self):
        """Pre-v7.6.1 the SFTP wizard wrote ``--sftp-port`` which Kopia
        does not accept (verified with ``kopia repository create sftp
        --sftp-port=22 ...`` → ``unknown long flag``). Must be ``--port``.
        """
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
            port="2222",
        )
        assert "--sftp-port" not in params
        assert "--port=2222" in params

    def test_path_with_spaces_is_quoted(self):
        params = build_sftp_kopia_params(
            remote_path="/path with spaces/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
        )
        # shlex.quote wraps in single quotes
        assert "'/path with spaces/backup'" in params

    def test_first_token_is_sftp(self):
        """The detect_repository_type helper splits on the first whitespace
        and expects the backend name as the leading token."""
        params = build_sftp_kopia_params(
            remote_path="/backup",
            host="peer",
            ssh_user="root",
            ssh_key="/root/.ssh/id",
        )
        assert params.split(None, 1)[0] == "sftp"


@pytest.mark.unit
class TestEnsureKnownHosts:
    """ensure_known_hosts() — pre-populate known_hosts via ssh-keyscan.

    Migrated from TailscaleBackend._ensure_known_hosts; the implementation
    lives in backend_helper.py since v7.6.1 so the direct SFTP wizard can
    use it too.
    """

    def test_returns_existing_path_when_host_already_trusted(self, tmp_path):
        kh = tmp_path / ".ssh" / "known_hosts"
        kh.parent.mkdir(parents=True)
        kh.write_text("peer.example.com ssh-ed25519 AAAA...\n")

        with patch.object(Path, "home", return_value=tmp_path):
            result = ensure_known_hosts("peer.example.com")

        assert result == kh

    def test_runs_keyscan_and_appends_when_not_trusted(self, tmp_path):
        kh = tmp_path / ".ssh" / "known_hosts"

        fake_scan = Mock()
        fake_scan.returncode = 0
        fake_scan.stdout = "peer.example.com ssh-ed25519 AAAAFAKE\n"

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("kopi_docka.helpers.backend_helper.run_command", return_value=fake_scan):
            result = ensure_known_hosts("peer.example.com")

        assert result == kh
        assert "AAAAFAKE" in kh.read_text()

    def test_returns_none_when_keyscan_returns_empty(self, tmp_path):
        fake_scan = Mock()
        fake_scan.returncode = 1
        fake_scan.stdout = ""

        with patch.object(Path, "home", return_value=tmp_path), \
             patch("kopi_docka.helpers.backend_helper.run_command", return_value=fake_scan):
            result = ensure_known_hosts("peer.example.com")

        assert result is None
