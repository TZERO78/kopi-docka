"""
Operating System Detection Module

Detects Linux distribution and version for dependency installation.
Supports: Debian 11-13 (including Trixie), Ubuntu 20-24, Arch, Fedora, etc.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .ui_utils import run_command


@dataclass
class OSInfo:
    """Operating system information"""

    id: str  # e.g., "debian", "ubuntu", "arch"
    version: str  # e.g., "13", "24.04"
    version_codename: str  # e.g., "trixie", "noble"
    name: str  # e.g., "Debian GNU/Linux"
    pretty_name: str  # e.g., "Debian GNU/Linux 13 (trixie)"
    architecture: str  # e.g., "x86_64", "aarch64"

    @property
    def is_debian(self) -> bool:
        """Check if Debian-based"""
        return self.id == "debian"

    @property
    def is_ubuntu(self) -> bool:
        """Check if Ubuntu-based"""
        return self.id == "ubuntu"

    @property
    def is_debian_based(self) -> bool:
        """Check if Debian or Ubuntu"""
        return self.id in ("debian", "ubuntu")

    @property
    def is_arch(self) -> bool:
        """Check if Arch Linux"""
        return self.id == "arch"

    @property
    def is_fedora(self) -> bool:
        """Check if Fedora"""
        return self.id == "fedora"

    @property
    def is_rhel_based(self) -> bool:
        """Check if RHEL-based (Fedora, CentOS, Rocky, Alma)"""
        return self.id in ("fedora", "rhel", "centos", "rocky", "almalinux")

    @property
    def debian_version_major(self) -> Optional[int]:
        """Get Debian major version (11, 12, 13, etc.)"""
        if self.is_debian and self.version:
            try:
                return int(self.version.split(".")[0])
            except (ValueError, IndexError):
                return None
        return None

    @property
    def ubuntu_version(self) -> Optional[str]:
        """Get Ubuntu version (20.04, 22.04, 24.04, etc.)"""
        if self.is_ubuntu:
            return self.version
        return None

    def __str__(self) -> str:
        return f"{self.pretty_name} ({self.architecture})"


def detect_os() -> OSInfo:
    """
    Detect Linux distribution and version.

    Reads from /etc/os-release (standard since systemd).
    Falls back to platform module if file not available.

    Returns:
        OSInfo object with distribution details

    Example:
        >>> os_info = detect_os()
        >>> print(os_info.id, os_info.version, os_info.version_codename)
        debian 13 trixie
    """
    os_release_path = Path("/etc/os-release")

    if os_release_path.exists():
        return _parse_os_release(os_release_path)
    else:
        # Fallback for non-systemd systems
        return _fallback_detection()


def _parse_os_release(path: Path) -> OSInfo:
    """Parse /etc/os-release file"""
    info = {}

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                # Remove quotes
                value = value.strip('"').strip("'")
                info[key] = value
    except Exception:
        return _fallback_detection()

    return OSInfo(
        id=info.get("ID", "unknown").lower(),
        version=info.get("VERSION_ID", ""),
        version_codename=info.get("VERSION_CODENAME", ""),
        name=info.get("NAME", "Unknown Linux"),
        pretty_name=info.get("PRETTY_NAME", info.get("NAME", "Unknown Linux")),
        architecture=platform.machine(),
    )


def _fallback_detection() -> OSInfo:
    """Fallback detection using platform module"""
    system = platform.system()

    if system == "Linux":
        # Try to get more info
        try:
            distro = platform.freedesktop_os_release()
            return OSInfo(
                id=distro.get("ID", "unknown").lower(),
                version=distro.get("VERSION_ID", ""),
                version_codename=distro.get("VERSION_CODENAME", ""),
                name=distro.get("NAME", "Unknown Linux"),
                pretty_name=distro.get("PRETTY_NAME", "Unknown Linux"),
                architecture=platform.machine(),
            )
        except Exception:
            pass

    # Ultimate fallback
    return OSInfo(
        id="unknown",
        version="",
        version_codename="",
        name=system,
        pretty_name=f"{system} {platform.release()}",
        architecture=platform.machine(),
    )


def get_package_manager() -> Optional[str]:
    """
    Detect available package manager.

    Returns:
        Package manager command (e.g., "apt", "dnf", "pacman") or None
    """
    os_info = detect_os()

    # Debian/Ubuntu
    if os_info.is_debian_based:
        return "apt" if _command_exists("apt") else "apt-get"

    # Arch
    if os_info.is_arch:
        return "pacman"

    # Fedora/RHEL
    if os_info.is_rhel_based:
        if _command_exists("dnf"):
            return "dnf"
        elif _command_exists("yum"):
            return "yum"

    # Try to detect by checking which commands exist
    for pm in ["apt", "dnf", "yum", "pacman", "zypper", "apk"]:
        if _command_exists(pm):
            return pm

    return None


def _command_exists(command: str) -> bool:
    """Check if a command exists in PATH"""
    try:
        result = run_command(
            ["which", command],
            f"Checking for {command}",
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


# Alias for backwards compatibility
detect_os_info = detect_os

# Convenience exports
__all__ = [
    "OSInfo",
    "detect_os",
    "detect_os_info",
    "get_package_manager",
]


if __name__ == "__main__":
    # Test detection
    os_info = detect_os()
    print(f"OS: {os_info}")
    print(f"ID: {os_info.id}")
    print(f"Version: {os_info.version}")
    print(f"Codename: {os_info.version_codename}")
    print(f"Architecture: {os_info.architecture}")
    print(f"Package Manager: {get_package_manager()}")

    if os_info.is_debian:
        print(f"Debian Version: {os_info.debian_version_major}")
    elif os_info.is_ubuntu:
        print(f"Ubuntu Version: {os_info.ubuntu_version}")
