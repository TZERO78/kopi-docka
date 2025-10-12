"""
Dependency Installation Module

Auto-installs missing dependencies based on detected OS.
Supports: kopia, rclone, tailscale, docker, etc.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

from .os_detect import OSInfo, detect_os, get_package_manager
from ..i18n import _


class DependencyInstaller:
    """Handles automatic installation of system dependencies"""
    
    def __init__(self):
        self.os_info = detect_os()
        self.package_manager = get_package_manager()
    
    def check_installed(self, command: str) -> bool:
        """Check if a command is installed"""
        return shutil.which(command) is not None
    
    def install_kopia(self) -> bool:
        """
        Install Kopia based on detected OS.
        
        Handles Debian 11-13 (including Trixie), Ubuntu 20-24, Arch, etc.
        
        Returns:
            True if successful, False otherwise
        """
        if self.check_installed("kopia"):
            return True
        
        print(_("Installing Kopia..."))
        
        if self.os_info.is_debian_based:
            return self._install_kopia_debian()
        elif self.os_info.is_arch:
            return self._install_kopia_arch()
        elif self.os_info.is_fedora:
            return self._install_kopia_fedora()
        else:
            print(_("Unsupported OS for auto-install. Please install Kopia manually from https://kopia.io"))
            return False
    
    def install_rclone(self) -> bool:
        """Install rclone based on detected OS"""
        if self.check_installed("rclone"):
            return True
        
        print(_("Installing rclone..."))
        
        if self.os_info.is_debian_based:
            return self._run_install_command([
                "sudo", self.package_manager, "update", "&&",
                "sudo", self.package_manager, "install", "-y", "rclone"
            ], shell=True)
        elif self.os_info.is_arch:
            return self._run_install_command([
                "sudo", "pacman", "-S", "--noconfirm", "rclone"
            ])
        elif self.os_info.is_rhel_based:
            return self._run_install_command([
                "sudo", self.package_manager, "install", "-y", "rclone"
            ])
        else:
            # Universal install script
            print(_("Using universal rclone install script..."))
            return self._run_install_command([
                "curl", "https://rclone.org/install.sh", "|", "sudo", "bash"
            ], shell=True)
    
    def install_tailscale(self) -> bool:
        """Install Tailscale based on detected OS"""
        if self.check_installed("tailscale"):
            return True
        
        print(_("Installing Tailscale..."))
        
        # Tailscale provides a universal install script
        return self._run_install_command([
            "curl", "-fsSL", "https://tailscale.com/install.sh", "|", "sh"
        ], shell=True)
    
    def install_docker(self) -> bool:
        """Install Docker based on detected OS"""
        if self.check_installed("docker"):
            return True
        
        print(_("Installing Docker..."))
        
        if self.os_info.is_debian_based:
            # Use Docker's official install script
            return self._run_install_command([
                "curl", "-fsSL", "https://get.docker.com", "|", "sh"
            ], shell=True)
        elif self.os_info.is_arch:
            return self._run_install_command([
                "sudo", "pacman", "-S", "--noconfirm", "docker"
            ])
        elif self.os_info.is_fedora:
            return self._run_install_command([
                "sudo", "dnf", "install", "-y", "docker"
            ])
        else:
            print(_("Please install Docker manually from https://docs.docker.com/engine/install/"))
            return False
    
    # Private installation methods
    
    def _install_kopia_debian(self) -> bool:
        """
        Install Kopia on Debian/Ubuntu.
        
        Supports Debian 11 (Bullseye), 12 (Bookworm), 13 (Trixie)
        and Ubuntu 20.04, 22.04, 24.04
        """
        commands = [
            # Download and install GPG key (new method, not deprecated apt-key)
            [
                "curl", "-fsSL", "https://kopia.io/signing-key",
                "-o", "/tmp/kopia-keyring.gpg"
            ],
            [
                "sudo", "gpg", "--dearmor", "--yes",
                "-o", "/usr/share/keyrings/kopia-keyring.gpg",
                "/tmp/kopia-keyring.gpg"
            ],
            # Add repository
            [
                "echo",
                "deb [signed-by=/usr/share/keyrings/kopia-keyring.gpg] https://packages.kopia.io/apt stable main",
                "|", "sudo", "tee", "/etc/apt/sources.list.d/kopia.list"
            ],
            # Update and install
            ["sudo", self.package_manager, "update"],
            ["sudo", self.package_manager, "install", "-y", "kopia"]
        ]
        
        for cmd in commands:
            if "|" in cmd or ">" in cmd:
                # Shell command
                if not self._run_install_command(cmd, shell=True):
                    return False
            else:
                if not self._run_install_command(cmd):
                    return False
        
        return self.check_installed("kopia")
    
    def _install_kopia_arch(self) -> bool:
        """Install Kopia on Arch Linux"""
        # Kopia is available in AUR
        print(_("Kopia must be installed from AUR. Please use your AUR helper:"))
        print("  yay -S kopia-bin")
        print("  or")
        print("  paru -S kopia-bin")
        return False
    
    def _install_kopia_fedora(self) -> bool:
        """Install Kopia on Fedora/RHEL"""
        commands = [
            # Add Kopia RPM repository
            [
                "sudo", "rpm", "--import", "https://kopia.io/signing-key"
            ],
            [
                "sudo", "tee", "/etc/yum.repos.d/kopia.repo", "<<EOF\n"
                "[kopia]\n"
                "name=Kopia\n"
                "baseurl=https://packages.kopia.io/rpm/stable/\\$basearch/\n"
                "gpgcheck=1\n"
                "enabled=1\n"
                "gpgkey=https://kopia.io/signing-key\n"
                "EOF"
            ],
            # Install
            ["sudo", self.package_manager, "install", "-y", "kopia"]
        ]
        
        for cmd in commands:
            if "<<EOF" in " ".join(cmd):
                # Use shell for heredoc
                if not self._run_install_command(cmd, shell=True):
                    return False
            else:
                if not self._run_install_command(cmd):
                    return False
        
        return self.check_installed("kopia")
    
    def _run_install_command(
        self,
        command: List[str],
        shell: bool = False
    ) -> bool:
        """
        Run installation command.
        
        Args:
            command: Command and arguments
            shell: Whether to run in shell
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if shell:
                # Join command for shell execution
                cmd_str = " ".join(command)
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    text=True,
                    capture_output=True
                )
            else:
                result = subprocess.run(
                    command,
                    text=True,
                    capture_output=True
                )
            
            if result.returncode != 0:
                print(f"Error: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            print(f"Installation failed: {e}")
            return False


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
