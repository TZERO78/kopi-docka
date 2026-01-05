"""Unit tests for system_utils module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from kopi_docka.helpers.system_utils import _disk_probe_base, _is_remote_path, SystemUtils


class TestDiskProbeBase:
    """Tests for _disk_probe_base() function."""

    def test_remote_url_returns_root(self):
        """Test that remote URLs return '/' to avoid probing."""
        assert _disk_probe_base("s3://bucket/path") == "/"
        assert _disk_probe_base("b2://bucket/path") == "/"
        assert _disk_probe_base("sftp://user@host:/path") == "/"
        assert _disk_probe_base("azure://container/path") == "/"
        assert _disk_probe_base("gcs://bucket/path") == "/"

    def test_existing_path_returns_as_is(self, tmp_path):
        """Test that existing paths are returned unchanged."""
        result = _disk_probe_base(str(tmp_path))
        assert result == str(tmp_path)
        assert Path(result).exists()

    def test_nonexistent_path_walks_up_to_parent(self, tmp_path):
        """Test that non-existent paths walk up to nearest existing parent."""
        nonexistent = tmp_path / "does" / "not" / "exist"
        result = _disk_probe_base(str(nonexistent))
        
        # Should return tmp_path (the first existing parent)
        assert result == str(tmp_path)
        assert Path(result).exists()

    def test_deeply_nested_nonexistent_path(self, tmp_path):
        """Test handling of deeply nested non-existent paths."""
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        result = _disk_probe_base(str(deep_path))
        
        assert result == str(tmp_path)
        assert Path(result).exists()

    def test_parent_also_nonexistent(self, tmp_path):
        """Test when parent directory also doesn't exist."""
        nonexistent_base = tmp_path / "nonexistent_base"
        nonexistent_child = nonexistent_base / "child" / "grandchild"
        
        result = _disk_probe_base(str(nonexistent_child))
        
        # Should walk up to tmp_path
        assert result == str(tmp_path)
        assert Path(result).exists()

    def test_root_path_returns_root(self):
        """Test that root path '/' is handled correctly."""
        result = _disk_probe_base("/")
        assert result == "/"

    def test_exception_handling_returns_root(self):
        """Test that exceptions are caught and return '/'."""
        # Mock Path to raise exception
        with patch("kopi_docka.helpers.system_utils.Path") as mock_path:
            mock_path.side_effect = Exception("Test exception")
            result = _disk_probe_base("/some/path")
            assert result == "/"

    def test_relative_path_resolution(self):
        """Test that relative paths are handled correctly."""
        # Current directory should exist
        result = _disk_probe_base(".")
        assert Path(result).exists()

    def test_home_directory_path(self):
        """Test that home directory paths work."""
        result = _disk_probe_base(str(Path.home()))
        assert result == str(Path.home())
        assert Path(result).exists()


class TestIsRemotePath:
    """Tests for _is_remote_path() helper function."""

    def test_detects_remote_urls(self):
        """Test that remote URLs are correctly identified."""
        assert _is_remote_path("s3://bucket/path") is True
        assert _is_remote_path("b2://bucket") is True
        assert _is_remote_path("sftp://host/path") is True
        assert _is_remote_path("azure://container") is True
        assert _is_remote_path("gcs://bucket") is True
        assert _is_remote_path("rclone://remote:path") is True

    def test_detects_local_paths(self):
        """Test that local paths are correctly identified."""
        assert _is_remote_path("/var/lib/kopi-docka") is False
        assert _is_remote_path("/backup/kopia") is False
        assert _is_remote_path("relative/path") is False
        assert _is_remote_path(".") is False
        assert _is_remote_path("~/backup") is False

    def test_edge_cases(self):
        """Test edge cases for URL detection."""
        # File URLs (still considered remote-ish)
        assert _is_remote_path("file:///path/to/file") is True
        
        # HTTP/HTTPS (though unlikely in this context)
        assert _is_remote_path("https://example.com/path") is True
        
        # Windows paths with colon (edge case)
        # In Linux context, C:/path would be treated as remote due to ://
        # This is acceptable since we're Linux-focused


class TestSystemUtilsDiskSpace:
    """Integration tests for SystemUtils disk space methods."""

    def test_get_available_disk_space_with_existing_path(self, tmp_path):
        """Test getting disk space for existing path."""
        utils = SystemUtils()
        space = utils.get_available_disk_space(str(tmp_path))
        
        # Should return a positive number (GB)
        assert space > 0
        assert isinstance(space, float)

    def test_get_available_disk_space_with_nonexistent_path(self, tmp_path):
        """Test getting disk space for non-existent path (uses parent)."""
        utils = SystemUtils()
        nonexistent = tmp_path / "does_not_exist"
        
        # Should not crash, should return space from parent
        space = utils.get_available_disk_space(str(nonexistent))
        assert space >= 0  # Should work or return 0 (error case)

    def test_get_available_disk_space_with_remote_url(self):
        """Test that remote URLs don't crash."""
        utils = SystemUtils()
        
        # Should probe '/' instead and not crash
        space = utils.get_available_disk_space("s3://bucket/path")
        assert space >= 0

    def test_get_total_disk_space(self, tmp_path):
        """Test getting total disk space."""
        utils = SystemUtils()
        total = utils.get_total_disk_space(str(tmp_path))
        
        assert total > 0
        assert isinstance(total, float)

    def test_get_disk_usage_percent(self, tmp_path):
        """Test getting disk usage percentage."""
        utils = SystemUtils()
        usage = utils.get_disk_usage_percent(str(tmp_path))
        
        assert 0 <= usage <= 100
        assert isinstance(usage, float)
