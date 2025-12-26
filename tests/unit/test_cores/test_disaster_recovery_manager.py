"""
Unit tests for DisasterRecoveryManager class.

Tests bundle creation, encryption/decryption, rotation, and recovery script
generation for different backend types (filesystem, S3, B2, Azure, GCS, rclone).
"""

import json
import hashlib
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, call

import pytest

from kopi_docka.cores.disaster_recovery_manager import DisasterRecoveryManager
from kopi_docka.helpers.constants import VERSION


def make_mock_config(
    config_file: str = "/etc/kopi-docka.json",
    kopia_password: str = "test-password",
    kopia_params: str = "filesystem --path /test/repo",
    recovery_bundle_path: str = "/backup/recovery",
    recovery_bundle_retention: int = 3,
) -> Mock:
    """Create a mock Config object for disaster recovery testing."""
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


@pytest.fixture
def mock_repo():
    """Mock KopiaRepository for testing."""
    repo = Mock()
    repo._get_env.return_value = {"KOPIA_PASSWORD": "test-password"}
    repo.list_snapshots.return_value = [
        {"id": "snapshot1", "time": "2025-12-26T10:00:00Z"},
        {"id": "snapshot2", "time": "2025-12-26T11:00:00Z"},
    ]
    return repo


# =============================================================================
# Bundle Creation Tests
# =============================================================================


@pytest.mark.unit
class TestBundleCreation:
    """Tests for complete bundle creation flow."""

    @patch("kopi_docka.cores.disaster_recovery_manager.KopiaRepository")
    @patch("subprocess.run")
    @patch("tarfile.open")
    def test_create_bundle_filesystem_backend(
        self, mock_tarfile, mock_subprocess, mock_kopia_repo_class, tmp_path
    ):
        """Bundle creation succeeds for filesystem backend."""
        config = make_mock_config(
            config_file=str(tmp_path / "config.json"),
            recovery_bundle_path=str(tmp_path / "recovery"),
        )

        # Create config file
        (tmp_path / "config.json").write_text(json.dumps({"test": "config"}))

        # Mock repo status
        repo_status = {
            "storage": {
                "type": "filesystem",
                "config": {"path": "/test/repo"},
            }
        }
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(repo_status),
            stderr="",
        )

        # Mock KopiaRepository
        mock_repo = Mock()
        mock_repo._get_env.return_value = {"KOPIA_PASSWORD": "test-password"}
        mock_repo.list_snapshots.return_value = [{"id": "snap1"}]
        mock_kopia_repo_class.return_value = mock_repo

        # Mock tarfile
        mock_tar = MagicMock()
        mock_tarfile.return_value.__enter__.return_value = mock_tar

        manager = DisasterRecoveryManager(config)

        with patch.object(manager, "_create_encrypted_archive") as mock_encrypt:
            # Mock the encrypted archive file creation
            def create_archive_side_effect(src_dir, out_file):
                out_file.write_text("encrypted content")
                return "test-password-123"

            mock_encrypt.side_effect = create_archive_side_effect

            result = manager.create_recovery_bundle(
                output_dir=tmp_path / "recovery", write_password_file=False
            )

        assert result.exists()
        assert result.name.endswith(".tar.gz.enc")
        assert result.name.startswith("kopi-docka-recovery-")

        # Verify encrypted archive was called
        mock_encrypt.assert_called_once()

    @patch("kopi_docka.cores.disaster_recovery_manager.KopiaRepository")
    @patch("subprocess.run")
    def test_create_bundle_with_password_file(
        self, mock_subprocess, mock_kopia_repo_class, tmp_path
    ):
        """Bundle creation writes password sidecar when requested."""
        config = make_mock_config(
            config_file=str(tmp_path / "config.json"),
            recovery_bundle_path=str(tmp_path / "recovery"),
        )
        (tmp_path / "config.json").write_text(json.dumps({"test": "config"}))

        repo_status = {"storage": {"type": "filesystem", "config": {"path": "/test/repo"}}}
        mock_subprocess.return_value = Mock(
            returncode=0, stdout=json.dumps(repo_status), stderr=""
        )

        mock_repo = Mock()
        mock_repo._get_env.return_value = {"KOPIA_PASSWORD": "test-password"}
        mock_repo.list_snapshots.return_value = []
        mock_kopia_repo_class.return_value = mock_repo

        manager = DisasterRecoveryManager(config)

        with patch.object(manager, "_create_encrypted_archive") as mock_encrypt:
            mock_encrypt.return_value = "supersecret123"

            # Mock the encrypted archive file creation
            def create_archive_side_effect(src_dir, out_file):
                out_file.write_text("encrypted content")
                return "supersecret123"

            mock_encrypt.side_effect = create_archive_side_effect

            result = manager.create_recovery_bundle(
                output_dir=tmp_path / "recovery", write_password_file=True
            )

        # Check password file created
        password_file = Path(str(result) + ".PASSWORD")
        assert password_file.exists()
        assert password_file.read_text().strip() == "supersecret123"
        # Check permissions (should be 0o600)
        assert oct(password_file.stat().st_mode)[-3:] == "600"

    @patch("kopi_docka.cores.disaster_recovery_manager.KopiaRepository")
    @patch("subprocess.run")
    def test_create_bundle_cleanup_on_success(
        self, mock_subprocess, mock_kopia_repo_class, tmp_path
    ):
        """Temporary working directory is cleaned up after bundle creation."""
        config = make_mock_config(
            config_file=str(tmp_path / "config.json"),
            recovery_bundle_path=str(tmp_path / "recovery"),
        )
        (tmp_path / "config.json").write_text(json.dumps({"test": "config"}))

        repo_status = {"storage": {"type": "filesystem", "config": {"path": "/test/repo"}}}
        mock_subprocess.return_value = Mock(
            returncode=0, stdout=json.dumps(repo_status), stderr=""
        )

        mock_repo = Mock()
        mock_repo._get_env.return_value = {"KOPIA_PASSWORD": "test-password"}
        mock_repo.list_snapshots.return_value = []
        mock_kopia_repo_class.return_value = mock_repo

        manager = DisasterRecoveryManager(config)

        with patch.object(manager, "_create_encrypted_archive") as mock_encrypt:
            # Mock the encrypted archive file creation
            def create_archive_side_effect(src_dir, out_file):
                out_file.write_text("encrypted content")
                return "test-password"

            mock_encrypt.side_effect = create_archive_side_effect

            with patch("shutil.rmtree") as mock_rmtree:
                manager.create_recovery_bundle(
                    output_dir=tmp_path / "recovery", write_password_file=False
                )

                # Verify cleanup was called
                mock_rmtree.assert_called()
                # Check that the path contains the bundle name pattern
                cleanup_path = mock_rmtree.call_args[0][0]
                assert "kopi-docka-recovery-" in str(cleanup_path)


# =============================================================================
# Rclone Config Detection Tests
# =============================================================================


@pytest.mark.unit
class TestRcloneConfigDetection:
    """Tests for _find_rclone_config() method."""

    def test_find_rclone_from_kopia_params(self):
        """Rclone config found from kopia_params --rclone-args."""
        config = make_mock_config(
            kopia_params="rclone --remote-path=myremote:backup --rclone-args='--config=/opt/rclone.conf'"
        )
        manager = DisasterRecoveryManager(config)

        with patch("pathlib.Path.exists", return_value=True):
            result = manager._find_rclone_config()

        assert result == Path("/opt/rclone.conf")

    def test_find_rclone_from_fallback_root(self):
        """Rclone config found from /root/.config/rclone/rclone.conf."""
        config = make_mock_config(kopia_params="filesystem --path /test")
        manager = DisasterRecoveryManager(config)

        def exists_side_effect(self):
            return str(self) == "/root/.config/rclone/rclone.conf"

        with patch("pathlib.Path.exists", exists_side_effect):
            result = manager._find_rclone_config()

        assert result == Path("/root/.config/rclone/rclone.conf")

    def test_find_rclone_from_sudo_user(self):
        """Rclone config found from SUDO_USER home directory."""
        config = make_mock_config(kopia_params="filesystem --path /test")
        manager = DisasterRecoveryManager(config)

        def exists_side_effect(self):
            return str(self) == "/home/testuser/.config/rclone/rclone.conf"

        with patch("pathlib.Path.exists", exists_side_effect):
            with patch.dict("os.environ", {"SUDO_USER": "testuser"}):
                result = manager._find_rclone_config()

        assert result == Path("/home/testuser/.config/rclone/rclone.conf")

    def test_find_rclone_not_found(self):
        """Returns None when no rclone config found."""
        config = make_mock_config(kopia_params="filesystem --path /test")
        manager = DisasterRecoveryManager(config)

        with patch("pathlib.Path.exists", return_value=False):
            result = manager._find_rclone_config()

        assert result is None


# =============================================================================
# Recovery Info Creation Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryInfoCreation:
    """Tests for _create_recovery_info() method."""

    @patch("subprocess.run")
    def test_create_recovery_info_success(self, mock_subprocess):
        """Recovery info contains all required fields."""
        repo_status = {
            "storage": {
                "type": "s3",
                "config": {"bucket": "my-backup-bucket"},
            }
        }
        mock_subprocess.side_effect = [
            # kopia repository status
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            # hostname
            Mock(returncode=0, stdout="testhost\n", stderr=""),
        ]

        config = make_mock_config(config_file="/etc/kopi-docka.json")
        manager = DisasterRecoveryManager(config)

        with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
            with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                with patch.object(manager, "_get_python_version", return_value="3.10.12"):
                    info = manager._create_recovery_info()

        assert info["kopi_docka_version"] == VERSION
        assert info["hostname"] == "testhost"
        assert info["repository"]["type"] == "s3"
        assert info["repository"]["connection"]["bucket"] == "my-backup-bucket"
        assert info["repository"]["encryption"] == "AES256-GCM-HMAC-SHA256"
        assert info["repository"]["compression"] == "zstd"
        assert info["kopia_version"] == "0.18.2"
        assert info["docker_version"] == "27.0.0"
        assert info["python_version"] == "3.10.12"

    @patch("subprocess.run")
    def test_create_recovery_info_with_paths(self, mock_subprocess):
        """Recovery info includes config and password file paths."""
        repo_status = {"storage": {"type": "filesystem", "config": {"path": "/test"}}}
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps(repo_status), stderr=""),
            Mock(returncode=0, stdout="testhost\n", stderr=""),
        ]

        config = make_mock_config(
            config_file="/etc/kopi-docka.json", kopia_params="filesystem --path /test"
        )

        # Store original side_effect
        original_get = config.get.side_effect

        def get_with_password(section, key, fallback=None):
            if section == "kopia" and key == "password_file":
                return "/root/kopia-password.txt"
            return original_get(section, key, fallback)

        config.get.side_effect = get_with_password

        manager = DisasterRecoveryManager(config)

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(manager, "_get_kopia_version", return_value="0.18.2"):
                with patch.object(manager, "_get_docker_version", return_value="27.0.0"):
                    with patch.object(manager, "_get_python_version", return_value="3.10.12"):
                        info = manager._create_recovery_info()

        assert "paths" in info
        assert info["paths"]["config"] == "/etc/kopi-docka.json"
        assert info["paths"]["password"] == "/root/kopia-password.txt"

    @patch("subprocess.run")
    def test_create_recovery_info_handles_kopia_failure(self, mock_subprocess):
        """Recovery info creation continues when kopia status fails."""
        mock_subprocess.side_effect = [
            # kopia repository status fails
            Mock(returncode=1, stdout="", stderr="Error"),
            # hostname
            Mock(returncode=0, stdout="testhost\n", stderr=""),
        ]

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        with patch.object(manager, "_get_kopia_version", return_value="unknown"):
            with patch.object(manager, "_get_docker_version", return_value="unknown"):
                with patch.object(manager, "_get_python_version", return_value="3.10.12"):
                    info = manager._create_recovery_info()

        # Should still create info with defaults
        assert info["hostname"] == "testhost"
        assert info["repository"]["type"] == "unknown"


# =============================================================================
# Repository Extraction Tests
# =============================================================================


@pytest.mark.unit
class TestRepositoryExtraction:
    """Tests for _extract_repo_from_status() for different backend types."""

    def test_extract_filesystem_backend(self):
        """Extracts filesystem repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {"storage": {"type": "filesystem", "config": {"path": "/backup/repo"}}}

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "filesystem"
        assert connection == {"path": "/backup/repo"}

    def test_extract_s3_backend(self):
        """Extracts S3 repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {"storage": {"type": "s3", "config": {"bucket": "my-s3-bucket"}}}

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "s3"
        assert connection == {"bucket": "my-s3-bucket"}

    def test_extract_b2_backend(self):
        """Extracts B2 repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {"storage": {"type": "b2", "config": {"bucket": "my-b2-bucket"}}}

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "b2"
        assert connection == {"bucket": "my-b2-bucket"}

    def test_extract_azure_backend(self):
        """Extracts Azure repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {"storage": {"type": "azure", "config": {"container": "mycontainer"}}}

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "azure"
        assert connection == {"container": "mycontainer"}

    def test_extract_gcs_backend(self):
        """Extracts GCS repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {"storage": {"type": "gcs", "config": {"bucket": "my-gcs-bucket"}}}

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "gcs"
        assert connection == {"bucket": "my-gcs-bucket"}

    def test_extract_sftp_backend(self):
        """Extracts SFTP repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {
            "storage": {
                "type": "sftp",
                "config": {"host": "backup.example.com", "path": "/backups/kopia"},
            }
        }

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "sftp"
        assert connection == {"host": "backup.example.com", "path": "/backups/kopia"}

    def test_extract_rclone_backend(self):
        """Extracts rclone repository info correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {
            "storage": {"type": "rclone", "config": {"remotePath": "myremote:backup/kopia"}}
        }

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "rclone"
        assert connection == {"remotePath": "myremote:backup/kopia"}

    def test_extract_unknown_backend(self):
        """Handles unknown backend type gracefully."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        repo_status = {
            "storage": {
                "type": "custom-backend",
                "config": {"custom_param": "value"},
            }
        }

        repo_type, connection = manager._extract_repo_from_status(repo_status)

        assert repo_type == "custom-backend"
        assert connection == {"custom_param": "value"}


# =============================================================================
# Kopia Config Export Tests
# =============================================================================


@pytest.mark.unit
class TestKopiaConfigExport:
    """Tests for _export_kopia_config() method."""

    @patch("subprocess.run")
    def test_export_kopia_config_success(self, mock_subprocess, tmp_path):
        """Kopia config and password are exported successfully."""
        repo_status = {"storage": {"type": "filesystem", "config": {"path": "/test"}}}
        mock_subprocess.return_value = Mock(
            returncode=0, stdout=json.dumps(repo_status), stderr=""
        )

        config = make_mock_config(kopia_password="secret123")
        manager = DisasterRecoveryManager(config)

        manager._export_kopia_config(tmp_path)

        # Check kopia-repository.json
        repo_file = tmp_path / "kopia-repository.json"
        assert repo_file.exists()
        assert json.loads(repo_file.read_text()) == repo_status

        # Check kopia-password.txt
        password_file = tmp_path / "kopia-password.txt"
        assert password_file.exists()
        assert password_file.read_text() == "secret123"

    @patch("subprocess.run")
    def test_export_kopia_config_handles_failure(self, mock_subprocess, tmp_path):
        """Export continues when kopia command fails."""
        mock_subprocess.return_value = Mock(returncode=1, stdout="", stderr="Error")

        config = make_mock_config(kopia_password="secret123")
        manager = DisasterRecoveryManager(config)

        # Should not raise exception
        manager._export_kopia_config(tmp_path)

        # Password should still be written
        password_file = tmp_path / "kopia-password.txt"
        assert password_file.exists()
        assert password_file.read_text() == "secret123"


# =============================================================================
# Recovery Script Generation Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryScriptGeneration:
    """Tests for _create_recovery_script() for different backend types."""

    def test_create_recovery_script_filesystem(self, tmp_path):
        """Recovery script for filesystem backend is correct."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "filesystem",
                "connection": {"path": "/backup/repo"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        assert script_file.exists()
        script_content = script_file.read_text()

        # Check essential elements
        assert "#!/bin/bash" in script_content
        assert "Kopi-Docka Disaster Recovery Script" in script_content
        assert 'kopia repository connect filesystem --path="/backup/repo"' in script_content
        assert "kopia repository status" in script_content

        # Check executable
        assert script_file.stat().st_mode & 0o111  # Has execute permission

    def test_create_recovery_script_s3(self, tmp_path):
        """Recovery script for S3 backend includes credential prompts."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "s3",
                "connection": {"bucket": "my-s3-bucket"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert 'read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID' in script_content
        assert 'read -s -p "AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY' in script_content
        assert 'kopia repository connect s3 --bucket="my-s3-bucket"' in script_content

    def test_create_recovery_script_b2(self, tmp_path):
        """Recovery script for B2 backend includes credential prompts."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "b2",
                "connection": {"bucket": "my-b2-bucket"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert 'read -p "B2 Account ID: " B2_ACCOUNT_ID' in script_content
        assert 'read -s -p "B2 Account Key: " B2_ACCOUNT_KEY' in script_content
        assert 'kopia repository connect b2 --bucket="my-b2-bucket"' in script_content

    def test_create_recovery_script_azure(self, tmp_path):
        """Recovery script for Azure backend includes credential prompts."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "azure",
                "connection": {"container": "mycontainer"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert 'read -p "Azure Storage Account: " AZURE_ACCOUNT' in script_content
        assert 'read -s -p "Azure Storage Key: " AZURE_KEY' in script_content
        assert 'kopia repository connect azure --container="mycontainer"' in script_content

    def test_create_recovery_script_gcs(self, tmp_path):
        """Recovery script for GCS backend includes service account setup."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "gcs",
                "connection": {"bucket": "my-gcs-bucket"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert "GOOGLE_APPLICATION_CREDENTIALS" in script_content
        assert "/root/gcp-sa.json" in script_content
        assert 'kopia repository connect gcs --bucket="$GCS_BUCKET"' in script_content

    def test_create_recovery_script_rclone(self, tmp_path):
        """Recovery script for rclone backend includes rclone.conf note."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "rclone",
                "connection": {"remotePath": "myremote:backup/kopia"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert "Ensure rclone.conf is restored" in script_content
        assert 'kopia repository connect rclone --remote-path="myremote:backup/kopia"' in script_content

    def test_create_recovery_script_unknown_backend(self, tmp_path):
        """Recovery script for unknown backend shows manual connect message."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "repository": {
                "type": "custom-backend",
                "connection": {"custom_param": "value"},
            },
        }

        manager._create_recovery_script(tmp_path, info)

        script_file = tmp_path / "recover.sh"
        script_content = script_file.read_text()

        assert "Unsupported auto-connect" in script_content
        assert "custom-backend" in script_content
        assert "exit 1" in script_content


# =============================================================================
# Recovery Instructions Tests
# =============================================================================


@pytest.mark.unit
class TestRecoveryInstructions:
    """Tests for _create_recovery_instructions() method."""

    def test_create_recovery_instructions(self, tmp_path):
        """Recovery instructions file is created with correct content."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        info = {
            "created_at": "2025-12-26T10:00:00",
            "hostname": "testhost",
            "repository": {
                "type": "s3",
                "connection": {"bucket": "my-bucket"},
                "encryption": "AES256-GCM-HMAC-SHA256",
                "compression": "zstd",
            },
        }

        manager._create_recovery_instructions(tmp_path, info)

        instructions_file = tmp_path / "RECOVERY-INSTRUCTIONS.txt"
        assert instructions_file.exists()

        content = instructions_file.read_text()
        assert "KOPI-DOCKA DISASTER RECOVERY INSTRUCTIONS" in content
        assert "Created: 2025-12-26T10:00:00" in content
        assert "System:  testhost" in content
        assert "Type:   s3" in content
        assert "Enc:    AES256-GCM-HMAC-SHA256" in content
        assert "Comp:   zstd" in content
        assert "sudo ./recover.sh" in content


# =============================================================================
# Backup Status Tests
# =============================================================================


@pytest.mark.unit
class TestBackupStatus:
    """Tests for _get_backup_status() method."""

    def test_get_backup_status_success(self, mock_repo):
        """Backup status retrieves recent snapshots."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)
        manager.repo = mock_repo

        status = manager._get_backup_status()

        assert "timestamp" in status
        assert "snapshots" in status
        assert len(status["snapshots"]) == 2
        assert status["snapshots"][0]["id"] == "snapshot1"

    def test_get_backup_status_limits_to_10(self, mock_repo):
        """Backup status limits to 10 most recent snapshots."""
        mock_repo.list_snapshots.return_value = [{"id": f"snap{i}"} for i in range(20)]

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)
        manager.repo = mock_repo

        status = manager._get_backup_status()

        assert len(status["snapshots"]) == 10

    def test_get_backup_status_handles_failure(self, mock_repo):
        """Backup status returns empty list on failure."""
        mock_repo.list_snapshots.side_effect = Exception("Failed to list snapshots")

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)
        manager.repo = mock_repo

        status = manager._get_backup_status()

        assert status["snapshots"] == []


# =============================================================================
# Encrypted Archive Tests
# =============================================================================


@pytest.mark.unit
class TestEncryptedArchive:
    """Tests for _create_encrypted_archive() method."""

    @patch("tarfile.open")
    @patch("subprocess.run")
    def test_create_encrypted_archive_success(self, mock_subprocess, mock_tarfile, tmp_path):
        """Encrypted archive is created with tar.gz + openssl."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        src_dir = tmp_path / "bundle"
        src_dir.mkdir()
        (src_dir / "test.txt").write_text("test content")

        out_file = tmp_path / "bundle.tar.gz.enc"

        # Mock tarfile
        mock_tar = MagicMock()
        mock_tarfile.return_value.__enter__.return_value = mock_tar

        # Mock openssl subprocess
        mock_subprocess.return_value = Mock(returncode=0)

        password = manager._create_encrypted_archive(src_dir, out_file)

        # Check password is strong (48 characters)
        assert len(password) == 48
        assert all(c.isalnum() or c in "_-" for c in password)

        # Check tarfile was created
        mock_tarfile.assert_called_once()
        call_args = mock_tarfile.call_args
        assert call_args[0][1] == "w:gz"

        # Check openssl was called
        mock_subprocess.assert_called_once()
        openssl_call = mock_subprocess.call_args[0][0]
        assert openssl_call[0] == "openssl"
        assert openssl_call[1] == "enc"
        assert openssl_call[2] == "-aes-256-cbc"
        assert openssl_call[3] == "-salt"
        assert openssl_call[4] == "-pbkdf2"
        assert f"pass:{password}" in openssl_call

    @patch("tarfile.open")
    @patch("subprocess.run")
    def test_create_encrypted_archive_cleanup_tar(self, mock_subprocess, mock_tarfile, tmp_path):
        """Unencrypted tar.gz is removed after encryption."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        src_dir = tmp_path / "bundle"
        src_dir.mkdir()
        out_file = tmp_path / "bundle.tar.gz.enc"

        # Create the tar file that should be cleaned up
        tar_path = out_file.with_suffix("")  # bundle.tar.gz
        tar_path.touch()

        mock_tar = MagicMock()
        mock_tarfile.return_value.__enter__.return_value = mock_tar
        mock_subprocess.return_value = Mock(returncode=0)

        manager._create_encrypted_archive(src_dir, out_file)

        # Check tar file is removed
        assert not tar_path.exists()


# =============================================================================
# Companion Files Tests
# =============================================================================


@pytest.mark.unit
class TestCompanionFiles:
    """Tests for _create_companion_files() method."""

    def test_create_companion_files_with_password(self, tmp_path):
        """Companion files (README + PASSWORD) are created."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        archive_path = tmp_path / "bundle.tar.gz.enc"
        archive_path.write_text("encrypted data")

        info = {
            "repository": {
                "type": "s3",
                "connection": {"bucket": "my-bucket"},
            }
        }

        manager._create_companion_files(
            archive_path, password="supersecret123", info=info, write_password_file=True
        )

        # Check README
        readme_file = tmp_path / "bundle.tar.gz.enc.README"
        assert readme_file.exists()
        readme_content = readme_file.read_text()
        assert "KOPI-DOCKA DISASTER RECOVERY BUNDLE" in readme_content
        assert "openssl enc -aes-256-cbc" in readme_content
        assert "Repo Type: s3" in readme_content

        # Check PASSWORD
        password_file = tmp_path / "bundle.tar.gz.enc.PASSWORD"
        assert password_file.exists()
        assert password_file.read_text().strip() == "supersecret123"
        assert oct(password_file.stat().st_mode)[-3:] == "600"

    def test_create_companion_files_without_password(self, tmp_path):
        """README is created but PASSWORD file is not when write_password_file=False."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        archive_path = tmp_path / "bundle.tar.gz.enc"
        archive_path.write_text("encrypted data")

        info = {"repository": {"type": "filesystem", "connection": {"path": "/test"}}}

        manager._create_companion_files(
            archive_path, password="supersecret123", info=info, write_password_file=False
        )

        # Check README exists
        readme_file = tmp_path / "bundle.tar.gz.enc.README"
        assert readme_file.exists()

        # Check PASSWORD does not exist
        password_file = tmp_path / "bundle.tar.gz.enc.PASSWORD"
        assert not password_file.exists()

    def test_create_companion_files_includes_sha256(self, tmp_path):
        """README includes SHA256 checksum of archive."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        archive_path = tmp_path / "bundle.tar.gz.enc"
        archive_content = b"encrypted data"
        archive_path.write_bytes(archive_content)

        # Calculate expected checksum
        expected_checksum = hashlib.sha256(archive_content).hexdigest()

        info = {"repository": {"type": "filesystem", "connection": {"path": "/test"}}}

        manager._create_companion_files(
            archive_path, password="test", info=info, write_password_file=False
        )

        readme_file = tmp_path / "bundle.tar.gz.enc.README"
        readme_content = readme_file.read_text()
        assert f"SHA256:   {expected_checksum}" in readme_content


# =============================================================================
# Bundle Rotation Tests
# =============================================================================


@pytest.mark.unit
class TestBundleRotation:
    """Tests for _rotate_bundles() method."""

    def test_rotate_bundles_keeps_n_newest(self, tmp_path):
        """Bundle rotation keeps only N newest bundles."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        # Create 5 bundles
        bundles = []
        for i in range(5):
            bundle = tmp_path / f"kopi-docka-recovery-202512260{i}0000.tar.gz.enc"
            bundle.write_text(f"bundle {i}")
            bundles.append(bundle)

        manager._rotate_bundles(tmp_path, keep=3)

        # Check only 3 newest remain (last 3)
        assert not bundles[0].exists()  # oldest removed
        assert not bundles[1].exists()  # second oldest removed
        assert bundles[2].exists()  # kept
        assert bundles[3].exists()  # kept
        assert bundles[4].exists()  # newest kept

    def test_rotate_bundles_removes_sidecars(self, tmp_path):
        """Bundle rotation removes README and PASSWORD sidecars."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        # Create old bundle with sidecars
        old_bundle = tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc"
        old_bundle.write_text("old bundle")
        (tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc.README").write_text("readme")
        (tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc.PASSWORD").write_text("pass")

        # Create newer bundle
        new_bundle = tmp_path / "kopi-docka-recovery-20251226120000.tar.gz.enc"
        new_bundle.write_text("new bundle")

        manager._rotate_bundles(tmp_path, keep=1)

        # Check old bundle and sidecars removed
        assert not old_bundle.exists()
        assert not (tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc.README").exists()
        assert not (tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc.PASSWORD").exists()

        # Check new bundle remains
        assert new_bundle.exists()

    def test_rotate_bundles_disabled_when_keep_zero(self, tmp_path):
        """Bundle rotation disabled when keep=0."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        # Create 3 bundles
        for i in range(3):
            bundle = tmp_path / f"kopi-docka-recovery-202512260{i}0000.tar.gz.enc"
            bundle.write_text(f"bundle {i}")

        manager._rotate_bundles(tmp_path, keep=0)

        # All bundles should still exist (rotation disabled)
        assert len(list(tmp_path.glob("kopi-docka-recovery-*.tar.gz.enc"))) == 3

    def test_rotate_bundles_handles_missing_sidecars(self, tmp_path):
        """Bundle rotation continues when sidecars don't exist."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        # Create old bundle without sidecars
        old_bundle = tmp_path / "kopi-docka-recovery-20251225120000.tar.gz.enc"
        old_bundle.write_text("old bundle")

        # Create newer bundle
        new_bundle = tmp_path / "kopi-docka-recovery-20251226120000.tar.gz.enc"
        new_bundle.write_text("new bundle")

        # Should not raise exception
        manager._rotate_bundles(tmp_path, keep=1)

        assert not old_bundle.exists()
        assert new_bundle.exists()


# =============================================================================
# Helper Methods Tests
# =============================================================================


@pytest.mark.unit
class TestHelperMethods:
    """Tests for utility helper methods."""

    def test_sha256_checksum(self, tmp_path):
        """SHA256 checksum is calculated correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        test_file = tmp_path / "test.txt"
        test_content = b"test content for checksum"
        test_file.write_bytes(test_content)

        expected = hashlib.sha256(test_content).hexdigest()
        result = manager._sha256(test_file)

        assert result == expected

    def test_sha256_large_file(self, tmp_path):
        """SHA256 handles large files (>1MB chunks)."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        test_file = tmp_path / "large.bin"
        # Create 2MB file
        test_content = b"x" * (2 * 1024 * 1024)
        test_file.write_bytes(test_content)

        expected = hashlib.sha256(test_content).hexdigest()
        result = manager._sha256(test_file)

        assert result == expected

    @patch("kopi_docka.cores.disaster_recovery_manager.run_command")
    def test_get_kopia_version(self, mock_run_command):
        """Kopia version is extracted correctly."""
        mock_run_command.return_value = Mock(
            returncode=0, stdout="0.18.2 build: abc123\nother output\n", stderr=""
        )

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        version = manager._get_kopia_version()

        assert version == "0.18.2 build: abc123"

    @patch("kopi_docka.cores.disaster_recovery_manager.run_command")
    def test_get_kopia_version_handles_failure(self, mock_run_command):
        """Kopia version returns 'unknown' on failure."""
        mock_run_command.side_effect = Exception("Command failed")

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        version = manager._get_kopia_version()

        assert version == "unknown"

    @patch("kopi_docka.cores.disaster_recovery_manager.run_command")
    def test_get_docker_version(self, mock_run_command):
        """Docker version is extracted correctly."""
        mock_run_command.return_value = Mock(returncode=0, stdout="27.0.3\n", stderr="")

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        version = manager._get_docker_version()

        assert version == "27.0.3"

    @patch("kopi_docka.cores.disaster_recovery_manager.run_command")
    def test_get_docker_version_handles_failure(self, mock_run_command):
        """Docker version returns 'unknown' on failure."""
        mock_run_command.side_effect = Exception("Command failed")

        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        version = manager._get_docker_version()

        assert version == "unknown"

    def test_get_python_version(self):
        """Python version is extracted correctly."""
        config = make_mock_config()
        manager = DisasterRecoveryManager(config)

        version = manager._get_python_version()

        # Check format: major.minor.micro
        parts = version.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)
