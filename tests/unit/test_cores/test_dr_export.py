"""
Unit tests for Disaster Recovery ZIP export (plan_0019).

Tests the new single-file encrypted ZIP export, passphrase generation,
stream mode, and legacy compatibility.
"""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest
import pyzipper

from kopi_docka.cores.disaster_recovery_manager import (
    DisasterRecoveryManager,
    generate_passphrase,
    PASSPHRASE_WORDLIST,
)
from kopi_docka.helpers.constants import VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_config(
    config_file: str = "/etc/kopi-docka.json",
    kopia_password: str = "test-password",
    kopia_params: str = "filesystem --path /test/repo",
    recovery_bundle_path: str = "/backup/recovery",
    recovery_bundle_retention: int = 3,
) -> Mock:
    """Create a mock Config object for DR testing."""
    config = Mock()
    config.config_file = config_file
    config.kopia_password = kopia_password

    def get_side_effect(section, key, fallback=None):
        if section == "kopia" and key == "kopia_params":
            return kopia_params
        if section == "kopia" and key == "encryption":
            return "AES256-GCM-HMAC-SHA256"
        if section == "kopia" and key == "compression":
            return "zstd"
        if section == "kopia" and key == "password_file":
            return fallback
        if section == "backup" and key == "recovery_bundle_path":
            return recovery_bundle_path
        if section == "backup" and key == "recovery_bundle_retention":
            return str(recovery_bundle_retention)
        return fallback

    def getint_side_effect(section, key, fallback=None):
        if section == "backup" and key == "recovery_bundle_retention":
            return recovery_bundle_retention
        return fallback

    config.get.side_effect = get_side_effect
    config.getint.side_effect = getint_side_effect
    return config


def _make_manager(config=None, repo_status=None):
    """Create a DisasterRecoveryManager with mocked dependencies."""
    if config is None:
        config = make_mock_config()

    if repo_status is None:
        repo_status = {
            "storage": {"type": "filesystem", "config": {"path": "/test/repo"}}
        }

    manager = DisasterRecoveryManager.__new__(DisasterRecoveryManager)
    manager.config = config
    manager.repo = Mock()
    manager.repo._get_env.return_value = {"KOPIA_PASSWORD": "test-password"}
    manager.repo.list_snapshots.return_value = [
        {"id": "snap1", "time": "2026-01-30T10:00:00Z"},
    ]

    return manager, repo_status


# =============================================================================
# Passphrase Generation Tests
# =============================================================================


@pytest.mark.unit
class TestPassphraseGeneration:
    """Tests for generate_passphrase()."""

    def test_word_passphrase_default_count(self):
        """Default word passphrase has 5 words separated by hyphens."""
        pp = generate_passphrase()
        parts = pp.split("-")
        assert len(parts) == 5

    def test_word_passphrase_custom_count(self):
        """Word passphrase respects custom word_count."""
        pp = generate_passphrase(word_count=3)
        parts = pp.split("-")
        assert len(parts) == 3

    def test_word_passphrase_title_case(self):
        """Word passphrase words are Title-Cased."""
        pp = generate_passphrase(word_count=6)
        for word in pp.split("-"):
            assert word[0].isupper(), f"Expected Title-Case, got: {word}"

    def test_word_passphrase_uses_wordlist(self):
        """All words come from the PASSPHRASE_WORDLIST."""
        pp = generate_passphrase(word_count=5)
        for word in pp.split("-"):
            assert word.lower() in PASSPHRASE_WORDLIST

    def test_random_passphrase_length(self):
        """Random passphrase is 24 characters."""
        pp = generate_passphrase(style="random")
        assert len(pp) == 24

    def test_random_passphrase_alphanumeric(self):
        """Random passphrase contains only alphanumeric characters."""
        pp = generate_passphrase(style="random")
        assert pp.isalnum()

    def test_passphrases_are_unique(self):
        """Two generated passphrases should (almost certainly) differ."""
        pp1 = generate_passphrase()
        pp2 = generate_passphrase()
        assert pp1 != pp2

    def test_wordlist_has_sufficient_entries(self):
        """Wordlist has enough entries for reasonable entropy."""
        # With 200 words, 5-word passphrase ~= 38 bits entropy
        assert len(PASSPHRASE_WORDLIST) >= 100


# =============================================================================
# Encrypted ZIP Creation Tests
# =============================================================================


@pytest.mark.unit
class TestCreateEncryptedZip:
    """Tests for create_encrypted_zip()."""

    @patch("subprocess.run")
    def test_creates_valid_zip_bytes(self, mock_subprocess):
        """create_encrypted_zip returns valid ZIP content as bytes."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            # kopia repository status (for _create_recovery_info)
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            # hostname
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            # kopia repository status (for _get_kopia_status_json)
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            content = manager.create_encrypted_zip("test-passphrase-123")

        assert content is not None
        assert isinstance(content, bytes)
        assert len(content) > 0

        # Verify it's a valid AES-encrypted ZIP
        with pyzipper.AESZipFile(io.BytesIO(content), "r") as zf:
            zf.setpassword(b"test-passphrase-123")
            names = zf.namelist()
            assert "recovery-info.json" in names
            assert "kopia-password.txt" in names
            assert "recover.sh" in names
            assert "RECOVERY-INSTRUCTIONS.txt" in names
            assert "backup-status.json" in names

    @patch("subprocess.run")
    def test_zip_contains_correct_password(self, mock_subprocess):
        """ZIP contains the kopia password."""
        config = make_mock_config(kopia_password="super-secret-kopia-pw")
        manager, repo_status = _make_manager(config=config)

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            content = manager.create_encrypted_zip("my-pp")

        with pyzipper.AESZipFile(io.BytesIO(content), "r") as zf:
            zf.setpassword(b"my-pp")
            pw = zf.read("kopia-password.txt").decode("utf-8")
            assert pw == "super-secret-kopia-pw"

    @patch("subprocess.run")
    def test_zip_recovery_info_has_version(self, mock_subprocess):
        """recovery-info.json includes the kopi-docka version."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            content = manager.create_encrypted_zip("pp")

        with pyzipper.AESZipFile(io.BytesIO(content), "r") as zf:
            zf.setpassword(b"pp")
            info = json.loads(zf.read("recovery-info.json"))
            assert info["kopi_docka_version"] == VERSION

    @patch("subprocess.run")
    def test_zip_writes_to_output_stream(self, mock_subprocess):
        """create_encrypted_zip writes to provided output and returns None."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        buf = io.BytesIO()

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            result = manager.create_encrypted_zip("pp", output=buf)

        assert result is None
        assert buf.tell() > 0  # something was written

    @patch("subprocess.run")
    def test_wrong_passphrase_cannot_read(self, mock_subprocess):
        """ZIP contents cannot be read with wrong passphrase."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            content = manager.create_encrypted_zip("correct-passphrase")

        with pyzipper.AESZipFile(io.BytesIO(content), "r") as zf:
            zf.setpassword(b"wrong-passphrase")
            with pytest.raises(RuntimeError):
                zf.read("recovery-info.json")


# =============================================================================
# Export to File Tests
# =============================================================================


@pytest.mark.unit
class TestExportToFile:
    """Tests for export_to_file()."""

    @patch("subprocess.run")
    def test_export_creates_single_file(self, mock_subprocess, tmp_path):
        """export_to_file creates exactly ONE file."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        output = tmp_path / "recovery.zip"

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            result = manager.export_to_file(output, "test-pp")

        assert result == output
        assert output.exists()

        # Only ONE file created (no .PASSWORD, no .README sidecar)
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "recovery.zip"

    @patch("subprocess.run")
    def test_export_creates_parent_dirs(self, mock_subprocess, tmp_path):
        """export_to_file creates parent directories."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        output = tmp_path / "deep" / "nested" / "recovery.zip"

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            result = manager.export_to_file(output, "test-pp")

        assert result.exists()
        assert result.parent.name == "nested"

    @patch("subprocess.run")
    def test_export_sets_ownership(self, mock_subprocess, tmp_path):
        """export_to_file calls os.chown when SUDO_USER is set."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        output = tmp_path / "recovery.zip"

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            with patch.dict(os.environ, {"SUDO_USER": "testuser"}):
                                with patch("os.chown") as mock_chown:
                                    with patch("pwd.getpwnam") as mock_getpw:
                                        mock_getpw.return_value = Mock(pw_uid=1000, pw_gid=1000)
                                        manager.export_to_file(output, "test-pp")

                                        mock_chown.assert_called_once_with(output, 1000, 1000)

    @patch("subprocess.run")
    def test_export_no_chown_without_sudo(self, mock_subprocess, tmp_path):
        """export_to_file does not chown when not running via sudo."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        output = tmp_path / "recovery.zip"

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            with patch.dict(os.environ, {}, clear=True):
                                with patch("os.chown") as mock_chown:
                                    manager.export_to_file(output, "test-pp")
                                    mock_chown.assert_not_called()


# =============================================================================
# Export to Stream Tests
# =============================================================================


@pytest.mark.unit
class TestExportToStream:
    """Tests for export_to_stream()."""

    @patch("subprocess.run")
    def test_stream_writes_to_stdout(self, mock_subprocess):
        """export_to_stream writes ZIP content to stdout.buffer."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        fake_stdout = io.BytesIO()

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            with patch("sys.stdout") as mock_stdout:
                                mock_stdout.buffer = fake_stdout
                                manager.export_to_stream("stream-pp")

        # Verify content was written
        assert fake_stdout.tell() > 0

        # Verify it's a valid ZIP
        fake_stdout.seek(0)
        with pyzipper.AESZipFile(fake_stdout, "r") as zf:
            zf.setpassword(b"stream-pp")
            assert "recovery-info.json" in zf.namelist()

    @patch("subprocess.run")
    def test_stream_no_disk_writes(self, mock_subprocess, tmp_path):
        """Stream mode does not create any files on disk."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        fake_stdout = io.BytesIO()

        # Use tmp_path as a monitored directory – nothing should appear there
        initial_files = set(tmp_path.iterdir())

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            with patch("sys.stdout") as mock_stdout:
                                mock_stdout.buffer = fake_stdout
                                manager.export_to_stream("pp")

        # No new files
        assert set(tmp_path.iterdir()) == initial_files


# =============================================================================
# Instructions Content Tests
# =============================================================================


@pytest.mark.unit
class TestInstructionsContent:
    """Tests for _generate_instructions_content()."""

    def test_instructions_mention_zip_format(self):
        """Instructions mention the ZIP format."""
        manager, _ = _make_manager()

        info = {
            "created_at": "2026-01-31T12:00:00",
            "hostname": "testhost",
            "repository": {
                "type": "s3",
                "connection": {"bucket": "test-bucket"},
                "encryption": "AES256-GCM-HMAC-SHA256",
                "compression": "zstd",
            },
        }

        content = manager._generate_instructions_content(info)

        assert "AES-256 encrypted ZIP" in content
        assert "7-Zip" in content
        assert "testhost" in content
        assert "s3" in content
        assert VERSION in content

    def test_instructions_mention_passphrase(self):
        """Instructions mention the passphrase requirement."""
        manager, _ = _make_manager()

        info = {
            "created_at": "2026-01-31T12:00:00",
            "hostname": "testhost",
            "repository": {
                "type": "filesystem",
                "connection": {"path": "/test"},
                "encryption": "AES256-GCM-HMAC-SHA256",
                "compression": "zstd",
            },
        }

        content = manager._generate_instructions_content(info)

        assert "passphrase" in content.lower()


# =============================================================================
# Kopia Status JSON Tests
# =============================================================================


@pytest.mark.unit
class TestKopiaStatusJson:
    """Tests for _get_kopia_status_json()."""

    @patch("subprocess.run")
    def test_returns_json_string(self, mock_subprocess):
        """Returns raw JSON string from kopia status."""
        manager, repo_status = _make_manager()

        mock_subprocess.return_value = Mock(
            returncode=0, stdout=json.dumps(repo_status), stderr=""
        )

        result = manager._get_kopia_status_json()

        assert result is not None
        parsed = json.loads(result)
        assert parsed["storage"]["type"] == "filesystem"

    @patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_subprocess):
        """Returns None when kopia command fails."""
        manager, _ = _make_manager()

        mock_subprocess.return_value = Mock(returncode=1, stdout="", stderr="Error")

        result = manager._get_kopia_status_json()

        assert result is None

    @patch("subprocess.run")
    def test_returns_none_on_exception(self, mock_subprocess):
        """Returns None when subprocess raises exception."""
        manager, _ = _make_manager()

        mock_subprocess.side_effect = FileNotFoundError("kopia not found")

        result = manager._get_kopia_status_json()

        assert result is None


# =============================================================================
# No External Dependencies Tests
# =============================================================================


@pytest.mark.unit
class TestNoExternalDependencies:
    """Tests verifying the ZIP export does NOT use tar/openssl."""

    @patch("subprocess.run")
    def test_export_does_not_call_tar(self, mock_subprocess, tmp_path):
        """ZIP export never invokes 'tar'."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            manager.export_to_file(tmp_path / "dr.zip", "pp")

        # Check no subprocess call uses 'tar'
        for c in mock_subprocess.call_args_list:
            cmd = c[0][0] if c[0] else c[1].get("args", [])
            if isinstance(cmd, list) and cmd:
                assert cmd[0] != "tar", "ZIP export should not call 'tar'"

    @patch("subprocess.run")
    def test_export_does_not_call_openssl(self, mock_subprocess, tmp_path):
        """ZIP export never invokes 'openssl'."""
        manager, repo_status = _make_manager()

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        with patch("pathlib.Path.exists", return_value=False):
                            manager.export_to_file(tmp_path / "dr.zip", "pp")

        for c in mock_subprocess.call_args_list:
            cmd = c[0][0] if c[0] else c[1].get("args", [])
            if isinstance(cmd, list) and cmd:
                assert cmd[0] != "openssl", "ZIP export should not call 'openssl'"


# =============================================================================
# ZIP Content Integration Test
# =============================================================================


@pytest.mark.unit
class TestZipContentIntegration:
    """Full round-trip test: create ZIP, extract, verify all files."""

    @patch("subprocess.run")
    def test_full_roundtrip(self, mock_subprocess, tmp_path):
        """Create a ZIP, write to file, extract, and verify all contents."""
        config = make_mock_config(
            config_file=str(tmp_path / "kopi-docka.conf"),
            kopia_password="roundtrip-password-42",
        )
        # Create a real config file
        (tmp_path / "kopi-docka.conf").write_text("[kopia]\npassword=test\n")

        manager, repo_status = _make_manager(config=config)

        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="roundtrip-host\n", stderr=""),
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
        ]

        output = tmp_path / "output" / "recovery.zip"
        passphrase = "Tiger-Summit-Crystal-Noble-Zenith"

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.12.3"):
                    with patch.object(manager, "_find_rclone_config", return_value=None):
                        result = manager.export_to_file(output, passphrase)

        assert result.exists()

        # Extract and verify
        with pyzipper.AESZipFile(str(result), "r") as zf:
            zf.setpassword(passphrase.encode("utf-8"))
            names = zf.namelist()

            # All expected files present
            assert "recovery-info.json" in names
            assert "kopia-password.txt" in names
            assert "kopi-docka.conf" in names
            assert "recover.sh" in names
            assert "RECOVERY-INSTRUCTIONS.txt" in names
            assert "backup-status.json" in names

            # Verify password content
            pw = zf.read("kopia-password.txt").decode("utf-8")
            assert pw == "roundtrip-password-42"

            # Verify recovery info
            info = json.loads(zf.read("recovery-info.json"))
            assert info["hostname"] == "roundtrip-host"
            assert info["kopi_docka_version"] == VERSION

            # Verify recover.sh is a shell script
            script = zf.read("recover.sh").decode("utf-8")
            assert script.startswith("#!/bin/bash")

            # Verify instructions mention ZIP format
            instructions = zf.read("RECOVERY-INSTRUCTIONS.txt").decode("utf-8")
            assert "AES-256 encrypted ZIP" in instructions
