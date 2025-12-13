"""
Unit tests for config helper functions.

Tests the detect_repository_type function and other config utilities.
"""
import pytest
from kopi_docka.helpers.config import detect_repository_type


class TestDetectRepositoryType:
    """Tests for detect_repository_type function."""

    def test_filesystem_type(self):
        """Test detection of filesystem repository type."""
        assert detect_repository_type("filesystem --path /backup/kopia") == "filesystem"
        assert detect_repository_type("filesystem --path=/backup/kopia") == "filesystem"

    def test_rclone_type(self):
        """Test detection of rclone repository type."""
        assert detect_repository_type("rclone --remote-path=gdrive:kopia-backup") == "rclone"
        assert detect_repository_type("rclone --remote-path gdrive:backup --rclone-args='--config=/root/.config/rclone/rclone.conf'") == "rclone"

    def test_s3_type(self):
        """Test detection of S3 repository type."""
        assert detect_repository_type("s3 --bucket my-bucket") == "s3"
        assert detect_repository_type("s3 --bucket my-bucket --prefix kopia/") == "s3"

    def test_b2_type(self):
        """Test detection of Backblaze B2 repository type."""
        assert detect_repository_type("b2 --bucket my-b2-bucket") == "b2"

    def test_azure_type(self):
        """Test detection of Azure Blob repository type."""
        assert detect_repository_type("azure --container my-container") == "azure"

    def test_gcs_type(self):
        """Test detection of Google Cloud Storage repository type."""
        assert detect_repository_type("gcs --bucket my-gcs-bucket") == "gcs"

    def test_sftp_type(self):
        """Test detection of SFTP repository type."""
        assert detect_repository_type("sftp --path user@host:/backup") == "sftp"

    def test_webdav_type(self):
        """Test detection of WebDAV repository type."""
        assert detect_repository_type("webdav --url https://example.com/webdav") == "webdav"

    def test_empty_string(self):
        """Test handling of empty string."""
        assert detect_repository_type("") == "unknown"

    def test_none_value(self):
        """Test handling of None value."""
        assert detect_repository_type(None) == "unknown"

    def test_whitespace_only(self):
        """Test handling of whitespace-only string."""
        assert detect_repository_type("   ") == "unknown"

    def test_unknown_type(self):
        """Test handling of unknown repository type."""
        assert detect_repository_type("somethingelse --path /backup") == "unknown"

    def test_case_insensitive(self):
        """Test that detection is case-insensitive."""
        assert detect_repository_type("FILESYSTEM --path /backup") == "filesystem"
        assert detect_repository_type("Rclone --remote-path=gdrive:backup") == "rclone"
        assert detect_repository_type("S3 --bucket my-bucket") == "s3"

    def test_leading_whitespace(self):
        """Test handling of leading whitespace."""
        assert detect_repository_type("  filesystem --path /backup") == "filesystem"
        assert detect_repository_type("\trclone --remote-path=gdrive:backup") == "rclone"
