"""
Dependency Installation Module

Auto-installs missing dependencies based on detected OS.
Supports: kopia, rclone, tailscale, docker, etc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from .os_detect import OSInfo, detect_os, get_package_manager
from ..i18n import _


class InstallStatus(Enum):
    """Status of an installation operation"""

    SUCCESS = "success"
    FAILED = "failed"
    ALREADY_INSTALLED = "already_installed"
    UNSUPPORTED_OS = "unsupported_os"
    NETWORK_ERROR = "network_error"
    PERMISSION_ERROR = "permission_error"
    TIMEOUT = "timeout"


@dataclass
class InstallResult:
    """Rich result with detailed installation information"""

    status: InstallStatus
    dependency: str
    message: str
    error_details: Optional[str] = None
    command_output: Optional[str] = None


class DependencyInstaller:
    """Handles automatic installation of system dependencies"""

    def __init__(self, debug: bool = False, logger=None):
        self.os_info = detect_os()
        self.package_manager = get_package_manager()
        self.debug = debug
        self.logger = logger  # Callback function for logging

        if self.debug:
            self._log(f"[cyan]DependencyInstaller initialized[/]")
            self._log(f"OS: {self.os_info}")
            self._log(f"Package Manager: {self.package_manager}")
            self._log(f"PATH: {os.environ.get('PATH', 'N/A')[:100]}...")

    def _log(self, message: str) -> None:
        """Log a message using the logger callback or print."""
        if self.logger:
            self.logger(message)
        elif self.debug:
            print(f"[DEBUG] {message}")

    def check_installed(self, command: str) -> bool:
        """Check if a command is installed"""
        # 1. First try via PATH
        result = shutil.which(command)

        if result:
            if self.debug:
                self._log(f"[green]✓[/] Found '{command}' at: [cyan]{result}[/]")
            return True

        # 2. If not found in PATH, check alternative common paths
        alt_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "/opt/bin",
            "/snap/bin",
            "/home/linuxbrew/.linuxbrew/bin",
        ]

        for alt_path in alt_paths:
            full_path = os.path.join(alt_path, command)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                if self.debug:
                    self._log(f"[green]✓[/] Found '{command}' at: [cyan]{full_path}[/]")
                return True

        # 3. Not found anywhere
        if self.debug:
            self._log(f"[red]✗[/] Command '{command}' not found in PATH or common directories")

        return False

    def install(self, dep: str) -> InstallResult:
        """
        Install a dependency by name.

        Args:
            dep: Dependency name (e.g., 'kopia', 'rclone', 'docker', 'tailscale')

        Returns:
            InstallResult with detailed information
        """
        # Pre-check: already installed?
        if self.check_installed(dep):
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                dependency=dep,
                message=f"{dep} is already installed",
            )

        install_methods = {
            "kopia": self.install_kopia,
            "rclone": self.install_rclone,
            "tailscale": self.install_tailscale,
            "docker": self.install_docker,
        }

        if dep in install_methods:
            return install_methods[dep]()
        else:
            return InstallResult(
                status=InstallStatus.FAILED,
                dependency=dep,
                message=f"Unknown dependency: {dep}",
                error_details="No installation method defined for this dependency",
            )

    def install_kopia(self) -> InstallResult:
        """
        Install Kopia based on detected OS.

        Handles Debian 11-13 (including Trixie), Ubuntu 20-24, Arch, etc.

        Returns:
            InstallResult with details
        """
        if self.check_installed("kopia"):
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                dependency="kopia",
                message="Kopia is already installed",
            )

        print(_("Installing Kopia..."))

        if self.os_info.is_debian_based:
            return self._install_kopia_debian()
        elif self.os_info.is_arch:
            return self._install_kopia_arch()
        elif self.os_info.is_fedora:
            return self._install_kopia_fedora()
        else:
            return InstallResult(
                status=InstallStatus.UNSUPPORTED_OS,
                dependency="kopia",
                message="Unsupported OS for automatic installation",
                error_details=f"OS: {self.os_info.name} {self.os_info.version}. Please install manually from https://kopia.io",
            )

    def install_rclone(self) -> InstallResult:
        """Install rclone based on detected OS"""
        if self.check_installed("rclone"):
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                dependency="rclone",
                message="Rclone is already installed",
            )

        print(_("Installing rclone..."))

        if self.os_info.is_debian_based:
            result = self._run_install_command(
                [
                    "sudo",
                    self.package_manager,
                    "update",
                    "&&",
                    "sudo",
                    self.package_manager,
                    "install",
                    "-y",
                    "rclone",
                ],
                shell=True,
                dep_name="rclone",
            )
        elif self.os_info.is_arch:
            result = self._run_install_command(
                ["sudo", "pacman", "-S", "--noconfirm", "rclone"], dep_name="rclone"
            )
        elif self.os_info.is_rhel_based:
            result = self._run_install_command(
                ["sudo", self.package_manager, "install", "-y", "rclone"], dep_name="rclone"
            )
        else:
            # Universal install script
            print(_("Using universal rclone install script..."))
            result = self._run_install_command(
                ["curl", "https://rclone.org/install.sh", "|", "sudo", "bash"],
                shell=True,
                dep_name="rclone",
            )

        return result

    def install_tailscale(self) -> InstallResult:
        """Install Tailscale based on detected OS"""
        if self.check_installed("tailscale"):
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                dependency="tailscale",
                message="Tailscale is already installed",
            )

        print(_("Installing Tailscale..."))

        # Tailscale provides a universal install script
        return self._run_install_command(
            ["curl", "-fsSL", "https://tailscale.com/install.sh", "|", "sh"],
            shell=True,
            dep_name="tailscale",
        )

    def install_docker(self) -> InstallResult:
        """Install Docker based on detected OS"""
        if self.check_installed("docker"):
            return InstallResult(
                status=InstallStatus.ALREADY_INSTALLED,
                dependency="docker",
                message="Docker is already installed",
            )

        print(_("Installing Docker..."))

        if self.os_info.is_debian_based:
            # Use Docker's official install script
            result = self._run_install_command(
                ["curl", "-fsSL", "https://get.docker.com", "|", "sh"],
                shell=True,
                dep_name="docker",
            )
        elif self.os_info.is_arch:
            result = self._run_install_command(
                ["sudo", "pacman", "-S", "--noconfirm", "docker"], dep_name="docker"
            )
        elif self.os_info.is_fedora:
            result = self._run_install_command(
                ["sudo", "dnf", "install", "-y", "docker"], dep_name="docker"
            )
        else:
            return InstallResult(
                status=InstallStatus.UNSUPPORTED_OS,
                dependency="docker",
                message="Unsupported OS for automatic installation",
                error_details="Please install Docker manually from https://docs.docker.com/engine/install/",
            )

        return result

    # Private installation methods

    def _install_kopia_debian(self) -> InstallResult:
        """
        Install Kopia on Debian/Ubuntu.

        Supports Debian 11 (Bullseye), 12 (Bookworm), 13 (Trixie)
        and Ubuntu 20.04, 22.04, 24.04
        """
        commands = [
            # Download and install GPG key (new method, not deprecated apt-key)
            ["curl", "-fsSL", "https://kopia.io/signing-key", "-o", "/tmp/kopia-keyring.gpg"],
            [
                "sudo",
                "gpg",
                "--dearmor",
                "--yes",
                "-o",
                "/usr/share/keyrings/kopia-keyring.gpg",
                "/tmp/kopia-keyring.gpg",
            ],
            # Add repository
            [
                "echo",
                "deb [signed-by=/usr/share/keyrings/kopia-keyring.gpg] https://packages.kopia.io/apt stable main",
                "|",
                "sudo",
                "tee",
                "/etc/apt/sources.list.d/kopia.list",
            ],
            # Update and install
            ["sudo", self.package_manager, "update"],
            ["sudo", self.package_manager, "install", "-y", "kopia"],
        ]

        for cmd in commands:
            if "|" in cmd or ">" in cmd:
                # Shell command
                result = self._run_install_command(cmd, shell=True, dep_name="kopia")
            else:
                result = self._run_install_command(cmd, dep_name="kopia")

            if result.status != InstallStatus.SUCCESS:
                return result

        # Verify installation
        if self.check_installed("kopia"):
            return InstallResult(
                status=InstallStatus.SUCCESS,
                dependency="kopia",
                message="Kopia installed and verified successfully",
            )
        else:
            return InstallResult(
                status=InstallStatus.FAILED,
                dependency="kopia",
                message="Installation completed but verification failed",
                error_details="Command 'kopia' not found after installation. Check PATH.",
            )

    def _install_kopia_arch(self) -> InstallResult:
        """Install Kopia on Arch Linux"""
        # Kopia is available in AUR
        return InstallResult(
            status=InstallStatus.UNSUPPORTED_OS,
            dependency="kopia",
            message="Kopia must be installed manually from AUR",
            error_details="Use your AUR helper: 'yay -S kopia-bin' or 'paru -S kopia-bin'",
        )

    def _install_kopia_fedora(self) -> InstallResult:
        """Install Kopia on Fedora/RHEL"""
        commands = [
            # Add Kopia RPM repository
            ["sudo", "rpm", "--import", "https://kopia.io/signing-key"],
            [
                "sudo",
                "tee",
                "/etc/yum.repos.d/kopia.repo",
                "<<EOF\n"
                "[kopia]\n"
                "name=Kopia\n"
                "baseurl=https://packages.kopia.io/rpm/stable/\\$basearch/\n"
                "gpgcheck=1\n"
                "enabled=1\n"
                "gpgkey=https://kopia.io/signing-key\n"
                "EOF",
            ],
            # Install
            ["sudo", self.package_manager, "install", "-y", "kopia"],
        ]

        for cmd in commands:
            if "<<EOF" in " ".join(cmd):
                # Use shell for heredoc
                result = self._run_install_command(cmd, shell=True, dep_name="kopia")
            else:
                result = self._run_install_command(cmd, dep_name="kopia")

            if result.status != InstallStatus.SUCCESS:
                return result

        # Verify installation
        if self.check_installed("kopia"):
            return InstallResult(
                status=InstallStatus.SUCCESS,
                dependency="kopia",
                message="Kopia installed and verified successfully",
            )
        else:
            return InstallResult(
                status=InstallStatus.FAILED,
                dependency="kopia",
                message="Installation completed but verification failed",
                error_details="Command 'kopia' not found after installation. Check PATH.",
            )

    def _run_install_command(
        self, command: List[str], shell: bool = False, dep_name: str = "unknown"
    ) -> InstallResult:
        """
        Run installation command with detailed result.

        Args:
            command: Command and arguments
            shell: Whether to run in shell
            dep_name: Name of the dependency being installed

        Returns:
            InstallResult with detailed information
        """
        try:
            if shell:
                # Join command for shell execution
                cmd_str = " ".join(command)
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    text=True,
                    capture_output=True,
                    timeout=300,  # 5 minute timeout
                )
            else:
                result = subprocess.run(command, text=True, capture_output=True, timeout=300)

            if result.returncode != 0:
                return InstallResult(
                    status=InstallStatus.FAILED,
                    dependency=dep_name,
                    message="Installation command failed",
                    error_details=result.stderr,
                    command_output=result.stdout,
                )

            return InstallResult(
                status=InstallStatus.SUCCESS,
                dependency=dep_name,
                message=f"{dep_name} installed successfully",
                command_output=result.stdout,
            )

        except subprocess.TimeoutExpired:
            return InstallResult(
                status=InstallStatus.TIMEOUT,
                dependency=dep_name,
                message="Installation timed out (>5 minutes)",
                error_details="Command took too long. Possible network issues or slow mirrors.",
            )
        except PermissionError as e:
            return InstallResult(
                status=InstallStatus.PERMISSION_ERROR,
                dependency=dep_name,
                message="Permission denied",
                error_details=f"{str(e)}. Try running with sudo.",
            )
        except Exception as e:
            return InstallResult(
                status=InstallStatus.FAILED,
                dependency=dep_name,
                message="Installation failed with exception",
                error_details=str(e),
            )


def install_missing_dependencies(required: List[str]) -> bool:
    """
    Install all missing dependencies.

    Args:
        required: List of required commands (e.g., ["kopia", "docker", "rclone"])

    Returns:
        True if all dependencies installed successfully
    """
    installer = DependencyInstaller()

    install_methods = {
        "kopia": installer.install_kopia,
        "rclone": installer.install_rclone,
        "tailscale": installer.install_tailscale,
        "docker": installer.install_docker,
    }

    success = True
    for dep in required:
        if not installer.check_installed(dep):
            print(f"\n{_('Installing')} {dep}...")

            if dep in install_methods:
                if not install_methods[dep]():
                    print(f"✗ {_('Failed to install')} {dep}")
                    success = False
                else:
                    print(f"✓ {dep} {_('installed successfully')}")
            else:
                print(f"✗ {_('Unknown dependency')}: {dep}")
                success = False

    return success


# Convenience exports
__all__ = [
    "DependencyInstaller",
    "InstallStatus",
    "InstallResult",
    "install_missing_dependencies",
]


if __name__ == "__main__":
    # Test installation
    installer = DependencyInstaller()
    print(f"OS: {installer.os_info}")
    print(f"Package Manager: {installer.package_manager}")
    print(f"\nKopia installed: {installer.check_installed('kopia')}")
    print(f"Docker installed: {installer.check_installed('docker')}")
    print(f"Rclone installed: {installer.check_installed('rclone')}")
    print(f"Tailscale installed: {installer.check_installed('tailscale')}")
