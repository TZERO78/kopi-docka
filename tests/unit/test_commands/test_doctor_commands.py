"""Unit tests for doctor_commands.py."""

import pytest
from unittest.mock import patch, Mock

from kopi_docka.__main__ import app


@pytest.mark.unit
class TestDoctorCommand:
    @patch("kopi_docka.commands.doctor_commands.DependencyManager")
    def test_doctor_runs_with_config(self, mock_dep_cls, cli_runner, mock_root, tmp_config):
        mock_dep = Mock()
        mock_dep.check_all.return_value = {"kopia": True, "docker": True}
        mock_dep_cls.return_value = mock_dep

        result = cli_runner.invoke(app, ["--config", str(tmp_config), "doctor"])
        assert result.exit_code in (0, 1)

    @patch("kopi_docka.commands.doctor_commands.DependencyManager")
    def test_doctor_with_verbose(self, mock_dep_cls, cli_runner, mock_root, tmp_config):
        mock_dep = Mock()
        mock_dep.check_all.return_value = {"kopia": True, "docker": True}
        mock_dep_cls.return_value = mock_dep

        result = cli_runner.invoke(app, ["--config", str(tmp_config), "doctor", "--verbose"])
        assert result.exit_code in (0, 1)

    def test_doctor_non_root_still_runs(self, cli_runner, mock_non_root, tmp_config):
        # doctor is a safe command, allowed for non-root
        result = cli_runner.invoke(app, ["--config", str(tmp_config), "doctor"])
        assert result.exit_code in (0, 1)

    @patch("kopi_docka.commands.doctor_commands.DependencyManager")
    def test_doctor_produces_output(self, mock_dep_cls, cli_runner, mock_root, tmp_config):
        mock_dep = Mock()
        mock_dep.check_all.return_value = {"kopia": True, "docker": True}
        mock_dep_cls.return_value = mock_dep

        result = cli_runner.invoke(app, ["--config", str(tmp_config), "doctor"])
        assert len(result.output) > 0


@pytest.mark.unit
class TestDoctorModuleFunctions:
    def test_module_importable(self):
        import kopi_docka.commands.doctor_commands as dc
        assert hasattr(dc, "cmd_doctor")

    def test_cmd_doctor_callable(self):
        from kopi_docka.commands.doctor_commands import cmd_doctor
        assert callable(cmd_doctor)


@pytest.mark.unit
class TestKopiaParamsSanity:
    """Plan 0029 / Phase 3 — detect broken kopia_params shapes.

    The legacy Tailscale wizard (v7.0.0–v7.3.13) produced
    ``sftp --path=HOST:PATH --host=HOST`` and forgot ``--username`` /
    ``--keyfile`` entirely. Kopia connects, then snapshots hang on the
    very first run. The sanity check has to flag every one of those
    fingerprints precisely.
    """

    def test_broken_path_with_host_prefix_detected(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = "sftp --path=tzero-server.beetal-vega.ts.net:/backup --host=tzero-server.beetal-vega.ts.net"
        codes = [c for c, *_ in _check_kopia_params_sanity(params)]
        assert "broken_path_with_host_prefix" in codes
        assert "missing_username" in codes
        assert "missing_auth" in codes

    def test_missing_username_detected(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = "sftp --path=/backup --host=peer --keyfile=/root/.ssh/k"
        codes = [c for c, *_ in _check_kopia_params_sanity(params)]
        assert "missing_username" in codes
        assert "broken_path_with_host_prefix" not in codes

    def test_missing_auth_detected(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = "sftp --path=/backup --host=peer --username=root"
        codes = [c for c, *_ in _check_kopia_params_sanity(params)]
        assert "missing_auth" in codes

    def test_correct_form_passes(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = (
            "sftp --path=/backup --host=peer.ts.net "
            "--username=root --keyfile=/root/.ssh/k "
            "--known-hosts=/root/.ssh/known_hosts"
        )
        assert _check_kopia_params_sanity(params) == []

    def test_sftp_password_satisfies_auth(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = "sftp --path=/backup --host=peer --username=root --sftp-password=secret"
        codes = [c for c, *_ in _check_kopia_params_sanity(params)]
        assert "missing_auth" not in codes

    def test_rclone_backend_is_skipped(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        # rclone has no --username/--keyfile concept; the SFTP-only check
        # must not trip on it.
        params = "rclone --remote-path=gdrive:backups"
        assert _check_kopia_params_sanity(params) == []

    def test_filesystem_backend_is_skipped(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        params = "filesystem --path /mnt/backup"
        assert _check_kopia_params_sanity(params) == []

    def test_empty_params_returns_no_issues(self):
        from kopi_docka.commands.doctor_commands import _check_kopia_params_sanity

        assert _check_kopia_params_sanity("") == []
        assert _check_kopia_params_sanity("   ") == []


@pytest.mark.unit
class TestBackendSanityHint:
    """Plan 0029 / v7.5.0 — broken-config user is pointed at the new
    `advanced config repair-kopia-params` command, not a sed line.
    """

    def test_doctor_emits_repair_command_hint(self, cli_runner, mock_root, tmp_path):
        import json

        config_data = {
            "kopia": {
                # Broken pre-v7.4 wizard form: --path=HOST:PATH, no --username/--keyfile
                "kopia_params": "sftp --path=peer.ts.net:/backup --host=peer.ts.net",
                "password": "test-password-123",
                "profile": "test-profile",
            },
            "credentials": {
                "remote_path": "/backup",
                "peer_fqdn": "peer.ts.net",
                "ssh_user": "root",
                "ssh_key": "/root/.ssh/id_ed25519",
            },
            "backup": {"base_path": "/tmp/x"},
            "docker": {"socket": "/var/run/docker.sock"},
            "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 5},
            "logging": {"level": "INFO", "file": "/tmp/x.log"},
        }
        cfg_file = tmp_path / "kopi-docka.json"
        cfg_file.write_text(json.dumps(config_data))

        with patch("kopi_docka.commands.doctor_commands.DependencyManager"):
            result = cli_runner.invoke(app, ["--config", str(cfg_file), "doctor"])

        out = result.output
        assert "advanced config repair-kopia-params" in out, (
            f"Doctor should suggest the repair command, got output:\n{out}"
        )
        # Make sure we no longer dump a sed line at the user.
        assert "sudo sed -i" not in out, "Doctor should no longer emit the sed migration"
