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
class TestSftpMigrationCommand:
    """Plan 0029 / Phase 3 — migration command pulls real credentials."""

    def _make_cfg(self, credentials: dict, kopia_params: str = "sftp --path=p:/x"):
        cfg = Mock()
        config_data = {
            "kopia": {"kopia_params": kopia_params},
            "credentials": credentials,
        }

        def _get(section, option, fallback=None):
            return config_data.get(section, {}).get(option, fallback)

        cfg.get.side_effect = _get
        cfg.config_file = "/etc/kopi-docka.json"
        return cfg

    def test_migration_command_uses_concrete_values(self):
        from kopi_docka.commands.doctor_commands import _build_sftp_migration_command

        cfg = self._make_cfg({
            "remote_path": "/mnt/user/backups/kopi-docka",
            "peer_fqdn": "tzero-server.beetal-vega.ts.net",
            "ssh_user": "root",
            "ssh_key": "/root/.ssh/kopi-docka_ed25519",
            "known_hosts": "/root/.ssh/known_hosts",
        })

        cmd = _build_sftp_migration_command(cfg, "/etc/kopi-docka.json")

        assert cmd is not None
        assert "/mnt/user/backups/kopi-docka" in cmd
        assert "tzero-server.beetal-vega.ts.net" in cmd
        assert "--username=root" in cmd
        assert "/root/.ssh/kopi-docka_ed25519" in cmd
        assert "/root/.ssh/known_hosts" in cmd
        assert "/etc/kopi-docka.json" in cmd
        assert cmd.startswith("sudo sed -i")

    def test_migration_command_omits_known_hosts_when_unset(self):
        from kopi_docka.commands.doctor_commands import _build_sftp_migration_command

        cfg = self._make_cfg({
            "remote_path": "/backup",
            "peer_fqdn": "peer.ts.net",
            "ssh_user": "backup",
            "ssh_key": "/home/backup/.ssh/id",
            # no known_hosts
        })

        cmd = _build_sftp_migration_command(cfg, "/etc/kopi-docka.json")
        assert "--known-hosts" not in cmd
