"""Unit tests for kopi_docka.commands.config_commands."""

import json
import shlex

import pytest
import typer
from unittest.mock import patch

from kopi_docka.__main__ import app


def _write_config(tmp_path, *, kopia_params, credentials=None):
    """Write a kopi-docka config file with the given kopia_params/credentials."""
    config_data = {
        "kopia": {
            "kopia_params": kopia_params,
            "password": "test-password-123",
            "profile": "test-profile",
            "compression": "zstd",
            "encryption": "AES256-GCM-HMAC-SHA256",
            "cache_directory": "/tmp/cache",
        },
        "credentials": credentials or {},
        "backup": {"base_path": "/tmp/x", "parallel_workers": "1"},
        "docker": {"socket": "/var/run/docker.sock"},
        "retention": {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 5},
        "logging": {"level": "INFO", "file": "/tmp/x.log"},
    }
    cfg_file = tmp_path / "kopi-docka.json"
    cfg_file.write_text(json.dumps(config_data, indent=2))
    return cfg_file


@pytest.mark.unit
class TestRepairKopiaParams:
    """advanced config repair-kopia-params — v7.5.0 Plan 0029 follow-up."""

    BROKEN = (
        "sftp --path=tzero-server.beetal-vega.ts.net:/mnt/user/backups "
        "--host=tzero-server.beetal-vega.ts.net"
    )
    CREDENTIALS = {
        "remote_path": "/mnt/user/backups",
        "peer_fqdn": "tzero-server.beetal-vega.ts.net",
        "ssh_user": "root",
        "ssh_key": "/root/.ssh/kopi-docka_ed25519",
        "known_hosts": "/root/.ssh/known_hosts",
    }

    def test_repair_rewrites_broken_config_in_place(
        self, cli_runner, mock_root, tmp_path
    ):
        cfg_file = _write_config(
            tmp_path, kopia_params=self.BROKEN, credentials=self.CREDENTIALS
        )

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        assert result.exit_code == 0, result.output

        updated = json.loads(cfg_file.read_text())
        new_params = updated["kopia"]["kopia_params"]

        tokens = shlex.split(new_params)
        assert tokens[0] == "sftp"
        flags = {tok.split("=", 1)[0]: tok.split("=", 1)[1] for tok in tokens[1:]}
        assert flags["--path"] == "/mnt/user/backups"
        assert ":" not in flags["--path"]
        assert flags["--host"] == "tzero-server.beetal-vega.ts.net"
        assert flags["--username"] == "root"
        assert flags["--keyfile"] == "/root/.ssh/kopi-docka_ed25519"
        assert flags["--known-hosts"] == "/root/.ssh/known_hosts"

    def test_repair_is_idempotent(self, cli_runner, mock_root, tmp_path):
        """Running twice must not double-quote/double-escape paths."""
        cfg_file = _write_config(
            tmp_path, kopia_params=self.BROKEN, credentials=self.CREDENTIALS
        )

        cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        after_first = json.loads(cfg_file.read_text())["kopia"]["kopia_params"]

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        assert result.exit_code == 0
        assert "already in the canonical shape" in result.output

        after_second = json.loads(cfg_file.read_text())["kopia"]["kopia_params"]
        assert after_first == after_second

    def test_dry_run_leaves_config_untouched(
        self, cli_runner, mock_root, tmp_path
    ):
        cfg_file = _write_config(
            tmp_path, kopia_params=self.BROKEN, credentials=self.CREDENTIALS
        )
        before = cfg_file.read_text()

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output
        assert cfg_file.read_text() == before

    def test_missing_credentials_aborts(self, cli_runner, mock_root, tmp_path):
        cfg_file = _write_config(
            tmp_path,
            kopia_params=self.BROKEN,
            credentials={"ssh_user": "root"},  # missing remote_path, peer_fqdn, ssh_key
        )

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        assert result.exit_code != 0
        for missing in ("remote_path", "peer_fqdn", "ssh_key"):
            assert missing in result.output

    def test_non_sftp_backend_refused(self, cli_runner, mock_root, tmp_path):
        cfg_file = _write_config(
            tmp_path,
            kopia_params="rclone --remote-path=gdrive:backups",
            credentials={},
        )

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        assert result.exit_code != 0
        assert "rclone" in result.output.lower()

    def test_peer_hostname_used_when_peer_fqdn_missing(
        self, cli_runner, mock_root, tmp_path
    ):
        """Older wizard runs only stored ``peer_hostname`` — must still work."""
        creds = {
            "remote_path": "/backup",
            "peer_hostname": "legacy-peer",  # no peer_fqdn
            "ssh_user": "root",
            "ssh_key": "/root/.ssh/id",
        }
        cfg_file = _write_config(
            tmp_path, kopia_params=self.BROKEN, credentials=creds
        )

        result = cli_runner.invoke(
            app,
            ["--config", str(cfg_file), "advanced", "config",
             "repair-kopia-params", "--yes"],
        )
        assert result.exit_code == 0, result.output
        new_params = json.loads(cfg_file.read_text())["kopia"]["kopia_params"]
        assert "--host=legacy-peer" in new_params
