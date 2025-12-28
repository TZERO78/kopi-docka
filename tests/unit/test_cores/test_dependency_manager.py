"""Unit tests for DependencyManager with Hard/Soft Gate system."""

import sys
from unittest.mock import Mock, patch, call
import pytest

from kopi_docka.cores.dependency_manager import (
    DependencyManager,
    DependencyCategory,
    INSTALLATION_URLS,
    SERVER_BAUKASTEN_URL,
)


@pytest.fixture
def dep_manager():
    """Create DependencyManager instance for testing."""
    return DependencyManager()


class TestDependencyManagerInit:
    """Test DependencyManager initialization."""

    def test_init_without_config(self):
        """Test initialization without config."""
        manager = DependencyManager()
        assert manager.config is None
        assert manager.dependencies is not None
        assert "docker" in manager.dependencies
        assert "kopia" in manager.dependencies

    def test_init_with_config(self):
        """Test initialization with config object."""
        mock_config = Mock()
        manager = DependencyManager(config=mock_config)
        assert manager.config == mock_config

    def test_dependencies_structure(self, dep_manager):
        """Test that dependencies are properly structured."""
        # Check MUST_HAVE dependencies
        assert dep_manager.dependencies["docker"]["category"] == DependencyCategory.MUST_HAVE
        assert dep_manager.dependencies["kopia"]["category"] == DependencyCategory.MUST_HAVE
        assert dep_manager.dependencies["docker"]["required"] is True
        assert dep_manager.dependencies["kopia"]["required"] is True

        # Check SOFT dependencies
        assert dep_manager.dependencies["tar"]["category"] == DependencyCategory.SOFT
        assert dep_manager.dependencies["openssl"]["category"] == DependencyCategory.SOFT
        assert dep_manager.dependencies["tar"]["required"] is False

        # Check BACKEND dependencies
        assert dep_manager.dependencies["openssh"]["category"] == DependencyCategory.BACKEND

        # Check OPTIONAL dependencies
        assert dep_manager.dependencies["systemctl"]["category"] == DependencyCategory.OPTIONAL
        assert dep_manager.dependencies["hostname"]["category"] == DependencyCategory.OPTIONAL


class TestHardGate:
    """Test Hard Gate functionality (non-skippable dependencies)."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_hard_gate_all_present(self, mock_exists, dep_manager):
        """Test hard gate when all MUST_HAVE dependencies are present."""
        mock_exists.return_value = True

        # Should not raise any exception
        dep_manager.check_hard_gate()

        # Verify that docker and kopia were checked
        calls = mock_exists.call_args_list
        checked_tools = [call[0][0] for call in calls]
        assert "docker" in checked_tools
        assert "kopia" in checked_tools

    @patch('rich.console.Console.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_hard_gate_docker_missing(self, mock_exists, mock_print, dep_manager):
        """Test hard gate raises SystemExit when Docker is missing."""
        # Docker missing, Kopia present
        mock_exists.side_effect = lambda name: name != "docker"

        with pytest.raises(SystemExit) as exc_info:
            dep_manager.check_hard_gate()

        assert exc_info.value.code == 1

        # Verify error message was printed
        assert mock_print.called
        error_message = mock_print.call_args[0][0]
        assert "docker" in error_message.lower()
        assert "required dependencies missing" in error_message.lower()
        assert INSTALLATION_URLS["docker"] in error_message
        assert SERVER_BAUKASTEN_URL in error_message
        assert "--skip-dependency-check does NOT apply" in error_message

    @patch('rich.console.Console.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_hard_gate_kopia_missing(self, mock_exists, mock_print, dep_manager):
        """Test hard gate raises SystemExit when Kopia is missing."""
        # Kopia missing, Docker present
        mock_exists.side_effect = lambda name: name != "kopia"

        with pytest.raises(SystemExit) as exc_info:
            dep_manager.check_hard_gate()

        assert exc_info.value.code == 1

        # Verify error message was printed
        assert mock_print.called
        error_message = mock_print.call_args[0][0]
        assert "kopia" in error_message.lower()
        assert INSTALLATION_URLS["kopia"] in error_message
        assert SERVER_BAUKASTEN_URL in error_message

    @patch('rich.console.Console.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_hard_gate_both_missing(self, mock_exists, mock_print, dep_manager):
        """Test hard gate when both Docker and Kopia are missing."""
        mock_exists.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            dep_manager.check_hard_gate()

        assert exc_info.value.code == 1

        # Verify error message includes both
        error_message = mock_print.call_args[0][0]
        assert "docker" in error_message.lower()
        assert "kopia" in error_message.lower()


class TestSoftGate:
    """Test Soft Gate functionality (skippable dependencies)."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_soft_gate_all_present(self, mock_missing, dep_manager):
        """Test soft gate when all required tools are present."""
        mock_missing.return_value = []

        # Should not raise any exception
        dep_manager.check_soft_gate(["tar", "openssl"], skip=False)

        mock_missing.assert_called_once_with(["tar", "openssl"])

    @patch('rich.console.Console.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_soft_gate_without_skip(self, mock_missing, mock_print, dep_manager):
        """Test soft gate raises SystemExit when tools missing and skip=False."""
        mock_missing.return_value = ["tar"]

        with pytest.raises(SystemExit) as exc_info:
            dep_manager.check_soft_gate(["tar", "openssl"], skip=False)

        assert exc_info.value.code == 1

        # Verify error message
        assert mock_print.called
        error_message = mock_print.call_args[0][0]
        assert "Missing optional dependencies" in error_message
        assert "tar" in error_message
        assert SERVER_BAUKASTEN_URL in error_message
        assert "--skip-dependency-check" in error_message

    @patch('rich.console.Console.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_soft_gate_with_skip(self, mock_missing, mock_print, dep_manager):
        """Test soft gate shows warning and continues when skip=True."""
        mock_missing.return_value = ["tar", "openssl"]

        # Should not raise - just print warning
        dep_manager.check_soft_gate(["tar", "openssl"], skip=True)

        # Verify warning was printed
        assert mock_print.called
        # Should be called twice - once for main warning, once for detail
        assert mock_print.call_count >= 1

        warning_calls = [str(call) for call in mock_print.call_args_list]
        combined_warnings = " ".join(warning_calls)
        assert "skipping dependency check" in combined_warnings.lower()
        assert "tar" in combined_warnings.lower()
        assert "openssl" in combined_warnings.lower()

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_soft_gate_empty_list(self, mock_missing, dep_manager):
        """Test soft gate with empty required tools list."""
        mock_missing.return_value = []

        # Should not raise
        dep_manager.check_soft_gate([], skip=False)

        mock_missing.assert_called_once_with([])


class TestOpenSSHCheck:
    """Test OpenSSH dependency checking (ssh + ssh-keygen)."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_openssh_both_present(self, mock_missing, dep_manager):
        """Test check_openssh returns True when both ssh and ssh-keygen are present."""
        mock_missing.return_value = []

        result = dep_manager.check_openssh()

        assert result is True
        mock_missing.assert_called_once_with(["ssh", "ssh-keygen"])

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_openssh_partial(self, mock_missing, dep_manager):
        """Test check_openssh returns False when only ssh is present."""
        # ssh-keygen is missing
        mock_missing.return_value = ["ssh-keygen"]

        result = dep_manager.check_openssh()

        assert result is False

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.missing')
    def test_check_openssh_both_missing(self, mock_missing, dep_manager):
        """Test check_openssh returns False when both are missing."""
        mock_missing.return_value = ["ssh", "ssh-keygen"]

        result = dep_manager.check_openssh()

        assert result is False


class TestBasicChecks:
    """Test basic dependency checking methods."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_docker(self, mock_exists, dep_manager):
        """Test check_docker method."""
        mock_exists.return_value = True

        result = dep_manager.check_docker()

        assert result is True
        mock_exists.assert_called_once_with("docker")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_kopia(self, mock_exists, dep_manager):
        """Test check_kopia method."""
        mock_exists.return_value = True

        result = dep_manager.check_kopia()

        assert result is True
        mock_exists.assert_called_once_with("kopia")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_tar(self, mock_exists, dep_manager):
        """Test check_tar method."""
        mock_exists.return_value = True

        result = dep_manager.check_tar()

        assert result is True
        mock_exists.assert_called_once_with("tar")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_openssl(self, mock_exists, dep_manager):
        """Test check_openssl method."""
        mock_exists.return_value = True

        result = dep_manager.check_openssl()

        assert result is True
        mock_exists.assert_called_once_with("openssl")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_systemctl(self, mock_exists, dep_manager):
        """Test check_systemctl method."""
        mock_exists.return_value = True

        result = dep_manager.check_systemctl()

        assert result is True
        mock_exists.assert_called_once_with("systemctl")

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_hostname(self, mock_exists, dep_manager):
        """Test check_hostname method."""
        mock_exists.return_value = True

        result = dep_manager.check_hostname()

        assert result is True
        mock_exists.assert_called_once_with("hostname")


class TestCheckDependency:
    """Test check_dependency method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_dependency_exists(self, mock_exists, dep_manager):
        """Test check_dependency for existing tool."""
        mock_exists.return_value = True

        result = dep_manager.check_dependency("docker")

        assert result is True

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_dependency_missing(self, mock_exists, dep_manager):
        """Test check_dependency for missing tool."""
        mock_exists.return_value = False

        result = dep_manager.check_dependency("docker")

        assert result is False

    def test_check_dependency_unknown(self, dep_manager):
        """Test check_dependency for unknown dependency."""
        result = dep_manager.check_dependency("nonexistent-tool")

        assert result is False


class TestCheckAll:
    """Test check_all method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_all_required_only(self, mock_exists, dep_manager):
        """Test check_all returns only required dependencies by default."""
        mock_exists.return_value = True

        results = dep_manager.check_all(include_optional=False)

        # Should include only required dependencies (docker, kopia)
        assert "docker" in results
        assert "kopia" in results
        assert results["docker"] is True
        assert results["kopia"] is True

        # Optional dependencies should not be included
        assert "systemctl" not in results
        assert "hostname" not in results

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_all_include_optional(self, mock_exists, dep_manager):
        """Test check_all includes optional dependencies when requested."""
        mock_exists.return_value = True

        results = dep_manager.check_all(include_optional=True)

        # Should include all dependencies
        assert "docker" in results
        assert "kopia" in results
        assert "tar" in results
        assert "openssl" in results
        assert "openssh" in results
        assert "systemctl" in results
        assert "hostname" in results

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_check_all_mixed_results(self, mock_exists, dep_manager):
        """Test check_all with some tools present and some missing."""
        # Docker present, Kopia missing
        mock_exists.side_effect = lambda name: name == "docker"

        results = dep_manager.check_all(include_optional=False)

        assert results["docker"] is True
        assert results["kopia"] is False


class TestGetMissing:
    """Test get_missing method."""

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_get_missing_none(self, mock_exists, dep_manager):
        """Test get_missing when all dependencies are present."""
        mock_exists.return_value = True

        missing = dep_manager.get_missing()

        assert missing == []

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_get_missing_some(self, mock_exists, dep_manager):
        """Test get_missing when some dependencies are missing."""
        # Only docker is missing
        mock_exists.side_effect = lambda name: name != "docker"

        missing = dep_manager.get_missing()

        assert "docker" in missing
        assert "kopia" not in missing

    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_get_missing_all(self, mock_exists, dep_manager):
        """Test get_missing when all required dependencies are missing."""
        mock_exists.return_value = False

        missing = dep_manager.get_missing()

        assert "docker" in missing
        assert "kopia" in missing


class TestPrintStatus:
    """Test print_status method."""

    @patch('builtins.print')
    @patch('kopi_docka.helpers.dependency_helper.DependencyHelper.exists')
    def test_print_status(self, mock_exists, mock_print, dep_manager):
        """Test print_status displays dependency information."""
        mock_exists.return_value = True

        dep_manager.print_status()

        # Verify that print was called
        assert mock_print.called
        # Should print multiple lines (header, dependencies, etc.)
        assert mock_print.call_count > 1

        # Verify expected content was printed
        printed_output = " ".join([str(call[0]) for call in mock_print.call_args_list])
        assert "DEPENDENCY STATUS" in printed_output or "dependency" in printed_output.lower()


class TestNoDistroDetection:
    """Verify that distro detection has been removed."""

    def test_no_distro_attribute(self, dep_manager):
        """Test that DependencyManager has no distro attribute."""
        assert not hasattr(dep_manager, 'distro')
        assert not hasattr(dep_manager, 'package_manager')

    def test_no_detect_distro_method(self, dep_manager):
        """Test that _detect_distro method does not exist."""
        assert not hasattr(dep_manager, '_detect_distro')

    def test_no_get_package_manager_method(self, dep_manager):
        """Test that _get_package_manager method does not exist."""
        assert not hasattr(dep_manager, '_get_package_manager')

    def test_no_install_methods(self, dep_manager):
        """Test that installation methods do not exist."""
        assert not hasattr(dep_manager, 'install_dependencies')
        assert not hasattr(dep_manager, 'install_missing')
        assert not hasattr(dep_manager, 'auto_install')
        assert not hasattr(dep_manager, 'get_install_commands')
