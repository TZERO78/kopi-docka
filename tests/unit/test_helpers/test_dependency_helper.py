"""Unit tests for DependencyHelper utility class."""

import subprocess
from unittest.mock import Mock, patch
import pytest
from kopi_docka.helpers.dependency_helper import DependencyHelper, ToolInfo


class TestDependencyHelperExists:
    """Tests for exists() method."""

    @patch('shutil.which')
    def test_exists_found(self, mock_which):
        """Test that exists() returns True when tool is in PATH."""
        mock_which.return_value = "/usr/bin/docker"

        result = DependencyHelper.exists("docker")

        assert result is True
        mock_which.assert_called_once_with("docker")

    @patch('shutil.which')
    def test_exists_not_found(self, mock_which):
        """Test that exists() returns False when tool is missing."""
        mock_which.return_value = None

        result = DependencyHelper.exists("nonexistent-tool")

        assert result is False
        mock_which.assert_called_once_with("nonexistent-tool")


class TestDependencyHelperGetPath:
    """Tests for get_path() method."""

    @patch('shutil.which')
    def test_get_path_found(self, mock_which):
        """Test that get_path() returns the full path when tool exists."""
        mock_which.return_value = "/usr/bin/kopia"

        result = DependencyHelper.get_path("kopia")

        assert result == "/usr/bin/kopia"
        mock_which.assert_called_once_with("kopia")

    @patch('shutil.which')
    def test_get_path_not_found(self, mock_which):
        """Test that get_path() returns None when tool is missing."""
        mock_which.return_value = None

        result = DependencyHelper.get_path("nonexistent-tool")

        assert result is None
        mock_which.assert_called_once_with("nonexistent-tool")


class TestDependencyHelperGetVersion:
    """Tests for get_version() method."""

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_standard(self, mock_which, mock_run):
        """Test version extraction for standard format (1.2.3)."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.return_value = Mock(
            stdout="1.2.3\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version == "1.2.3"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_with_v_prefix(self, mock_which, mock_run):
        """Test version extraction with 'v' prefix (v1.2.3 → 1.2.3)."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.return_value = Mock(
            stdout="v1.2.3\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version == "1.2.3"  # 'v' should be stripped

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_with_suffix(self, mock_which, mock_run):
        """Test version extraction with suffix (1.2.3-alpha, 1.2.3-rc1)."""
        mock_which.return_value = "/usr/bin/kopia"
        mock_run.return_value = Mock(
            stdout="kopia 1.2.3-alpha1 build xyz\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("kopia", ["kopia", "--version"])

        assert version == "1.2.3-alpha1"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_stderr(self, mock_which, mock_run):
        """Test version extraction from stderr (ssh, ssh-keygen)."""
        mock_which.return_value = "/usr/bin/ssh"
        mock_run.return_value = Mock(
            stdout="",  # ssh outputs to stderr!
            stderr="OpenSSH_8.9p1 Ubuntu-3ubuntu0.1, OpenSSL 3.0.2 15 Mar 2022\n",
            returncode=0
        )

        version = DependencyHelper.get_version("ssh", ["ssh", "-V"])

        # Should extract first full semver from stderr (3.0.2 comes before partial 8.9)
        assert version == "3.0.2"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_multiline(self, mock_which, mock_run):
        """Test version extraction from multiline output (takes first match)."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.return_value = Mock(
            stdout="Tool Version 2.5.1\nBuild: 12345\nDate: 2025-01-01\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version == "2.5.1"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_timeout(self, mock_which, mock_run):
        """Test version command timeout returns 'timeout'."""
        mock_which.return_value = "/usr/bin/slow-tool"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["slow-tool", "--version"], timeout=2)

        version = DependencyHelper.get_version("slow-tool", ["slow-tool", "--version"])

        assert version == "timeout"

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_empty_output(self, mock_which, mock_run):
        """Test empty output returns None."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.return_value = Mock(
            stdout="",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version is None

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_weird_format(self, mock_which, mock_run):
        """Test weird format falls back to first 50 chars."""
        mock_which.return_value = "/usr/bin/weird-tool"
        mock_run.return_value = Mock(
            stdout="This tool has a very weird version format without numbers that can be parsed easily" * 5,
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("weird-tool", ["weird-tool", "--version"])

        # Should return first 50 chars of first line
        assert version is not None
        assert len(version) <= 50

    @patch('shutil.which')
    def test_get_version_tool_not_exists(self, mock_which):
        """Test get_version returns None when tool doesn't exist."""
        mock_which.return_value = None

        version = DependencyHelper.get_version("nonexistent-tool", ["nonexistent-tool", "--version"])

        assert version is None

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_command_fails(self, mock_which, mock_run):
        """Test get_version handles command failures gracefully."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.side_effect = Exception("Command failed")

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version is None

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_uses_known_commands(self, mock_which, mock_run):
        """Test get_version uses VERSION_COMMANDS when no custom command provided."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(
            stdout="20.10.23\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("docker")  # No version_cmd provided

        # Should use VERSION_COMMANDS["docker"]
        expected_cmd = ["docker", "version", "--format", "{{.Server.Version}}"]
        mock_run.assert_called_once()
        actual_cmd = mock_run.call_args[0][0]
        assert actual_cmd == expected_cmd

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_get_version_partial_semver(self, mock_which, mock_run):
        """Test version extraction for partial semver (1.2)."""
        mock_which.return_value = "/usr/bin/test-tool"
        mock_run.return_value = Mock(
            stdout="version 1.2\n",
            stderr="",
            returncode=0
        )

        version = DependencyHelper.get_version("test-tool", ["test-tool", "--version"])

        assert version == "1.2"


class TestDependencyHelperCheck:
    """Tests for check() method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_version')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_path')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_returns_toolinfo_installed(self, mock_exists, mock_get_path, mock_get_version):
        """Test check() returns complete ToolInfo for installed tool."""
        mock_exists.return_value = True
        mock_get_path.return_value = "/usr/bin/docker"
        mock_get_version.return_value = "20.10.23"

        result = DependencyHelper.check("docker")

        assert isinstance(result, ToolInfo)
        assert result.name == "docker"
        assert result.installed is True
        assert result.path == "/usr/bin/docker"
        assert result.version == "20.10.23"

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_version')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_path')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_returns_toolinfo_not_installed(self, mock_exists, mock_get_path, mock_get_version):
        """Test check() returns ToolInfo with installed=False for missing tool."""
        mock_exists.return_value = False

        result = DependencyHelper.check("nonexistent-tool")

        assert isinstance(result, ToolInfo)
        assert result.name == "nonexistent-tool"
        assert result.installed is False
        assert result.path is None
        assert result.version is None
        # get_path and get_version should not be called for non-existent tools
        mock_get_path.assert_not_called()
        mock_get_version.assert_not_called()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_version')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.get_path')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_with_custom_version_cmd(self, mock_exists, mock_get_path, mock_get_version):
        """Test check() passes custom version command to get_version()."""
        mock_exists.return_value = True
        mock_get_path.return_value = "/usr/bin/custom-tool"
        mock_get_version.return_value = "3.0.0"

        custom_cmd = ["custom-tool", "-v"]
        result = DependencyHelper.check("custom-tool", version_cmd=custom_cmd)

        assert result.version == "3.0.0"
        mock_get_version.assert_called_once_with("custom-tool", custom_cmd)


class TestDependencyHelperCheckAll:
    """Tests for check_all() method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check')
    def test_check_all_multiple_tools(self, mock_check):
        """Test check_all() checks multiple tools and returns dict."""
        mock_check.side_effect = [
            ToolInfo(name="docker", installed=True, path="/usr/bin/docker", version="20.10.23"),
            ToolInfo(name="kopia", installed=True, path="/usr/bin/kopia", version="0.15.0"),
            ToolInfo(name="missing-tool", installed=False, path=None, version=None),
        ]

        result = DependencyHelper.check_all(["docker", "kopia", "missing-tool"])

        assert isinstance(result, dict)
        assert len(result) == 3
        assert "docker" in result
        assert "kopia" in result
        assert "missing-tool" in result
        assert result["docker"].installed is True
        assert result["kopia"].installed is True
        assert result["missing-tool"].installed is False

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.check')
    def test_check_all_empty_list(self, mock_check):
        """Test check_all() with empty list returns empty dict."""
        result = DependencyHelper.check_all([])

        assert isinstance(result, dict)
        assert len(result) == 0
        mock_check.assert_not_called()


class TestDependencyHelperMissing:
    """Tests for missing() method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_missing_returns_only_missing_tools(self, mock_exists):
        """Test missing() returns only tools that are not installed."""
        # docker and kopia installed, tar and openssl missing
        mock_exists.side_effect = lambda name: name in ["docker", "kopia"]

        result = DependencyHelper.missing(["docker", "kopia", "tar", "openssl"])

        assert isinstance(result, list)
        assert len(result) == 2
        assert "tar" in result
        assert "openssl" in result
        assert "docker" not in result
        assert "kopia" not in result

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_missing_all_installed(self, mock_exists):
        """Test missing() returns empty list when all tools are installed."""
        mock_exists.return_value = True

        result = DependencyHelper.missing(["docker", "kopia"])

        assert isinstance(result, list)
        assert len(result) == 0

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_missing_all_missing(self, mock_exists):
        """Test missing() returns all tools when none are installed."""
        mock_exists.return_value = False

        result = DependencyHelper.missing(["tool1", "tool2", "tool3"])

        assert isinstance(result, list)
        assert len(result) == 3
        assert "tool1" in result
        assert "tool2" in result
        assert "tool3" in result

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_missing_empty_list(self, mock_exists):
        """Test missing() with empty list returns empty list."""
        result = DependencyHelper.missing([])

        assert isinstance(result, list)
        assert len(result) == 0
        mock_exists.assert_not_called()


class TestToolInfo:
    """Tests for ToolInfo dataclass."""

    def test_toolinfo_creation_all_fields(self):
        """Test creating ToolInfo with all fields."""
        info = ToolInfo(
            name="docker",
            installed=True,
            path="/usr/bin/docker",
            version="20.10.23"
        )

        assert info.name == "docker"
        assert info.installed is True
        assert info.path == "/usr/bin/docker"
        assert info.version == "20.10.23"

    def test_toolinfo_creation_minimal(self):
        """Test creating ToolInfo with minimal fields (defaults)."""
        info = ToolInfo(name="test-tool", installed=False)

        assert info.name == "test-tool"
        assert info.installed is False
        assert info.path is None
        assert info.version is None
