################################################################################
# KOPI-DOCKA
#
# @file:        dependency_manager.py
# @module:      kopi_docka.cores
# @description: Checks, reports, and installs system dependencies required by Kopi-Docka.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.2
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - DEPENDENCIES map captures check commands, packages, and metadata
# - Detects distro family to assemble install commands dynamically
# - get_missing separates required versus optional components
################################################################################

"""
Dependency management for Kopi-Docka.

This module handles checking and installing system dependencies.
"""

import os
import re
import shutil
import subprocess
from typing import List, Dict, Tuple, Optional
from pathlib import Path

from ..helpers.logging import get_logger

logger = get_logger(__name__)


class DependencyManager:
    """Manages system dependencies for Kopi-Docka."""

    # Define all dependencies with metadata
    DEPENDENCIES = {
        "docker": {
            "check_command": "docker",
            "check_method": "check_docker",
            "packages": {
                "debian": "docker.io",
                "redhat": "docker",
                "arch": "docker",
                "alpine": "docker",
            },
            "required": True,
            "description": "Docker container runtime",
            "install_notes": "May require adding user to docker group",
        },
        "python3-systemd": {
            "check_command": None,
            "check_method": "check_python_systemd",
            "packages": {
                "debian": "python3-systemd",
                "redhat": "python3-systemd",
                "arch": "python-systemd",
                "alpine": None,  # Not available in Alpine
            },
            "required": False,
            "description": "Structured logging for systemd journal",
            "install_notes": "Enhances logging when running under systemd",
        },
        "kopia": {
            "check_command": "kopia",
            "check_method": "check_kopia",
            "packages": {
                "debian": None,  # Special installation
                "redhat": None,  # Special installation
                "arch": "kopia",  # AUR
                "alpine": None,  # Not available
            },
            "required": True,
            "description": "Kopia backup tool",
            "special_install": True,
            "version_command": ["kopia", "version"],
        },
        "tar": {
            "check_command": "tar",
            "check_method": "check_tar",
            "packages": {
                "debian": "tar",
                "redhat": "tar",
                "arch": "tar",
                "alpine": "tar",
            },
            "required": True,
            "description": "Archive tool for volume backups",
        },
        "openssl": {
            "check_command": "openssl",
            "check_method": "check_openssl",
            "packages": {
                "debian": "openssl",
                "redhat": "openssl",
                "arch": "openssl",
                "alpine": "openssl",
            },
            "required": True,
            "description": "Encryption for disaster recovery bundles",
        },
        "hostname": {
            "check_command": "hostname",
            "check_method": "check_hostname",
            "packages": {
                "debian": "hostname",
                "redhat": "hostname",
                "arch": "inetutils",
                "alpine": "hostname",
            },
            "required": False,
            "description": "System hostname for reporting",
        },
        "du": {
            "check_command": "du",
            "check_method": "check_du",
            "packages": {
                "debian": "coreutils",
                "redhat": "coreutils",
                "arch": "coreutils",
                "alpine": "coreutils",
            },
            "required": False,
            "description": "Disk usage calculation for volume analysis",
        },
    }

    def __init__(self):
        """Initialize dependency manager."""
        self.distro = self._detect_distro()
        logger.debug(f"Detected distribution: {self.distro}")

    def _detect_distro(self) -> str:
        """
        Detect Linux distribution type.

        Returns:
            Distribution type (debian, redhat, arch, alpine, unknown)
        """
        if os.path.exists("/etc/debian_version"):
            return "debian"
        elif os.path.exists("/etc/redhat-release"):
            return "redhat"
        elif os.path.exists("/etc/arch-release"):
            return "arch"
        elif os.path.exists("/etc/alpine-release"):
            return "alpine"
        else:
            return "unknown"

    def _get_package_manager(self) -> Optional[Tuple[str, List[str]]]:
        """
        Get package manager for current distro.

        Returns:
            Tuple of (manager_name, install_command) or None
        """
        managers = {
            "debian": ("apt", ["apt-get", "install", "-y"]),
            "redhat": ("yum", ["yum", "install", "-y"]),
            "arch": ("pacman", ["pacman", "-S", "--noconfirm"]),
            "alpine": ("apk", ["apk", "add", "--no-cache"]),
        }
        return managers.get(self.distro)

    def check_python_systemd(self) -> bool:
        """Check if python-systemd module is installed."""
        try:
            import systemd.journal

            return True
        except ImportError:
            return False

    def check_docker(self) -> bool:
        """Check if Docker is installed and running."""
        if not shutil.which("docker"):
            return False

        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            if result.returncode != 0:
                logger.debug("Docker installed but not accessible (user not in docker group?)")
                return False
            return True
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Error checking Docker: {e}")
            return False

    def check_kopia(self) -> bool:
        """Check if Kopia is installed."""
        return shutil.which("kopia") is not None

    def check_tar(self) -> bool:
        """Check if tar is installed."""
        return shutil.which("tar") is not None

    def check_openssl(self) -> bool:
        """Check if openssl is installed."""
        return shutil.which("openssl") is not None

    def check_hostname(self) -> bool:
        """Check if hostname command is available."""
        return shutil.which("hostname") is not None

    def check_du(self) -> bool:
        """Check if du command is available."""
        return shutil.which("du") is not None

    def check_dependency(self, name: str) -> bool:
        """
        Check if a specific dependency is installed.

        Args:
            name: Dependency name

        Returns:
            True if installed, False otherwise
        """
        dep = self.DEPENDENCIES.get(name)
        if not dep:
            return False

        # Use specific check method if available
        if "check_method" in dep:
            method = getattr(self, dep["check_method"], None)
            if method:
                return method()

        # Fallback to command check
        return shutil.which(dep["check_command"]) is not None

    def check_all(self, include_optional: bool = False) -> Dict[str, bool]:
        """
        Check all dependencies.

        Args:
            include_optional: Include optional dependencies in check

        Returns:
            Dictionary mapping dependency name to installation status
        """
        results = {}
        for name, dep in self.DEPENDENCIES.items():
            if not include_optional and not dep["required"]:
                continue
            results[name] = self.check_dependency(name)
        return results

    def get_missing(self, required_only: bool = True) -> List[str]:
        """
        Get list of missing dependencies.

        Args:
            required_only: Only check required dependencies

        Returns:
            List of missing dependency names
        """
        missing = []
        for name, dep in self.DEPENDENCIES.items():
            if required_only and not dep["required"]:
                continue
            if not self.check_dependency(name):
                missing.append(name)
        return missing

    def get_version(self, name: str) -> Optional[str]:
        """
        Get version of installed dependency.

        Args:
            name: Dependency name

        Returns:
            Version string or None if not available
        """
        dep = self.DEPENDENCIES.get(name)
        if not dep or not self.check_dependency(name):
            return None

        if name == "docker":
            try:
                result = subprocess.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass

        elif name == "kopia":
            try:
                result = subprocess.run(
                    ["kopia", "version"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line.strip():
                            return line.strip().split()[0]
            except Exception:
                pass

        elif "version_command" in dep:
            try:
                result = subprocess.run(
                    dep["version_command"] + ["--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass

        return None

    def get_install_commands(self) -> List[str]:
        """
        Get installation commands for current distro.

        Returns:
            List of shell commands to install missing dependencies
        """
        commands = []
        missing = self.get_missing()

        if not missing:
            return commands

        manager_info = self._get_package_manager()
        if not manager_info:
            logger.warning(f"Unknown distribution: {self.distro}")
            return commands

        manager_name, base_cmd = manager_info

        # Group packages for installation
        regular_packages = []
        special_installs = []

        for dep_name in missing:
            dep = self.DEPENDENCIES[dep_name]
            package = dep["packages"].get(self.distro)

            if package is None:
                # Special installation required
                special_installs.append(dep_name)
            else:
                regular_packages.append(package)

        # Create install command for regular packages
        if regular_packages:
            cmd = base_cmd + regular_packages
            commands.append(" ".join(cmd))

        # Add special installation instructions
        for dep_name in special_installs:
            if dep_name == "kopia":
                if self.distro == "debian":
                    commands.extend(
                        [
                            # Sicherstellen, dass gnupg installiert ist
                            "command -v gpg >/dev/null 2>&1 || apt-get install -y gnupg",
                            # Keyring-Verzeichnis erstellen (falls nicht vorhanden)
                            "install -d -m 0755 /etc/apt/keyrings",
                            # Key herunterladen & im Keyring speichern
                            "curl -fsSL https://kopia.io/signing-key | gpg --dearmor -o /etc/apt/keyrings/kopia.gpg",
                            # Berechtigungen setzen
                            "chmod 0644 /etc/apt/keyrings/kopia.gpg",
                            # APT-Source mit signed-by eintragen (https statt http!)
                            'echo "deb [signed-by=/etc/apt/keyrings/kopia.gpg] https://packages.kopia.io/apt/ stable main" > /etc/apt/sources.list.d/kopia.list',
                            "apt update",
                            "apt install -y kopia",
                        ]
                    )
                elif self.distro == "redhat":
                    commands.extend(
                        [
                            "rpm --import https://kopia.io/signing-key",
                            r"""cat > /etc/yum.repos.d/kopia.repo <<EOF
[kopia]
name=Kopia
baseurl=http://packages.kopia.io/rpm/stable/\$basearch/
enabled=1
gpgcheck=1
gpgkey=https://kopia.io/signing-key
EOF""",
                            "yum install -y kopia",
                        ]
                    )
        # Add Docker group command if Docker is missing
        if "docker" in missing:
            commands.append("usermod -aG docker $USER")

        return commands

    def install_missing(self, dry_run: bool = False) -> bool:
        """
        Attempt to install missing dependencies.

        Args:
            dry_run: Only show what would be installed

        Returns:
            True if successful, False otherwise
        """
        missing = self.get_missing()

        if not missing:
            logger.info("All required dependencies are already installed")
            return True

        logger.info(f"Missing dependencies: {', '.join(missing)}")

        if os.geteuid() != 0:
            logger.error("Root privileges required to install dependencies")
            logger.info("Run: sudo kopi-docka install-deps")
            return False

        commands = self.get_install_commands()

        if not commands:
            logger.error("Cannot determine installation commands for this system")
            return False

        if dry_run:
            logger.info("Would execute the following commands:")
            for cmd in commands:
                logger.info(f"  {cmd}")
            return True

        # Execute installation commands
        for cmd in commands:
            logger.info(f"Executing: {cmd}")
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Command failed: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"Error executing command: {e}")
                return False

        # Check if installation was successful
        still_missing = self.get_missing()
        if still_missing:
            logger.warning(
                f"Some dependencies still missing after installation: {', '.join(still_missing)}"
            )
            return False

        logger.info("All dependencies successfully installed")
        return True

    def print_install_guide(self):
        """Print installation guide for missing dependencies."""
        missing = self.get_missing(required_only=False)

        if not missing:
            print("✅ All dependencies are installed!")
            return

        print("\n" + "=" * 60)
        print("DEPENDENCY INSTALLATION GUIDE")
        print("=" * 60)

        required_missing = []
        optional_missing = []

        for dep_name in missing:
            dep = self.DEPENDENCIES[dep_name]
            if dep["required"]:
                required_missing.append(dep_name)
            else:
                optional_missing.append(dep_name)

        if required_missing:
            print("\n🚨 REQUIRED Dependencies Missing:")
            for dep_name in required_missing:
                dep = self.DEPENDENCIES[dep_name]
                print(f"\n  📦 {dep_name}")
                print(f"     {dep['description']}")
                if "install_notes" in dep:
                    print(f"     Note: {dep['install_notes']}")

        if optional_missing:
            print("\n📎 Optional Dependencies Missing:")
            for dep_name in optional_missing:
                dep = self.DEPENDENCIES[dep_name]
                print(f"\n  📦 {dep_name}")
                print(f"     {dep['description']}")
                if "install_notes" in dep:
                    print(f"     Note: {dep['install_notes']}")

        # Show installation commands
        commands = self.get_install_commands()
        if commands:
            print("\n" + "-" * 60)
            print("Installation Commands:")
            print("-" * 60)

            if os.geteuid() != 0:
                print("\n⚠ Run as root or with sudo:")

            for cmd in commands:
                print(f"\n  $ {cmd}")

        # Special instructions
        if "docker" in missing:
            print("\n" + "-" * 60)
            print("📌 Docker Post-Installation:")
            print("-" * 60)
            print("  After installing Docker:")
            print("  1. Add your user to the docker group:")
            print("     $ sudo usermod -aG docker $USER")
            print("  2. Log out and back in for group changes to take effect")
            print("  3. Verify with: docker run hello-world")

        if "kopia" in missing and self.distro == "arch":
            print("\n" + "-" * 60)
            print("📌 Kopia on Arch Linux:")
            print("-" * 60)
            print("  Install from AUR:")
            print("  $ yay -S kopia-bin")
            print("  OR")
            print("  $ paru -S kopia-bin")

        print("\n" + "=" * 60)

        # Automated installation option
        if required_missing:
            print("\n💡 For automated installation (requires root):")
            print("   $ sudo kopi-docka install-deps")
        else:
            print("\n✅ All required dependencies are installed!")
            print("   Optional dependencies can enhance functionality.")

    def auto_install(self, force: bool = False) -> bool:
        """
        Auto-install missing dependencies with confirmation.

        Args:
            force: Skip confirmation prompt

        Returns:
            True if successful, False otherwise
        """
        missing = self.get_missing()

        if not missing:
            print("✅ All required dependencies are already installed!")
            return True

        print("\n🔍 Checking system dependencies...")
        print(f"Distribution: {self.distro.capitalize()}")
        print(f"Missing: {', '.join(missing)}")

        commands = self.get_install_commands()

        if not commands:
            print("\n❌ Cannot determine installation commands for this system")
            print("Please install dependencies manually:")
            self.print_install_guide()
            return False

        print("\n📋 The following commands will be executed:")
        for cmd in commands:
            print(f"  $ {cmd}")

        if not force:
            response = input("\n⚠ Proceed with installation? [y/N]: ")
            if response.lower() != "y":
                return False

        print("\n📦 Installing dependencies...")

        for cmd in commands:
            print(f"\n→ {cmd}")
            try:
                result = subprocess.run(cmd, shell=True, text=True)
                if result.returncode != 0:
                    print(f"❌ Command failed with exit code {result.returncode}")
                    return False
            except Exception as e:
                print(f"❌ Error: {e}")
                return False

        # Post-installation checks
        if "docker" in missing:
            print("\n⚠ Docker installed. You may need to:")
            print("  1. Log out and back in for group membership")
            print("  2. Or run: newgrp docker")

        # Verify installation
        print("\n🔍 Verifying installation...")
        still_missing = self.get_missing()

        if not still_missing:
            print("\n✅ All dependencies successfully installed!")
            return True
        else:
            print("\n⚠ Some dependencies are still missing:")
            for dep in still_missing:
                print(f"  - {dep}")
            print("\nYou may need to:")
            print("  1. Restart your shell/terminal")
            print("  2. Log out and back in (for Docker group)")
            print("  3. Install these manually")
            return False

    def print_status(self, verbose: bool = False):
        """
        Print dependency status report.

        Args:
            verbose: Show detailed information including versions
        """
        print("\n" + "=" * 60)
        print("KOPI-DOCKA DEPENDENCY STATUS")
        print("=" * 60)

        print(
            f"\n📦 System: {self.distro.capitalize() if self.distro != 'unknown' else 'Unknown'} Linux"
        )

        results = self.check_all(include_optional=True)

        required_deps = []
        optional_deps = []

        for name, installed in results.items():
            dep = self.DEPENDENCIES[name]
            dep_info = {
                "name": name,
                "installed": installed,
                "description": dep["description"],
                "required": dep["required"],
            }

            if verbose and installed:
                version = self.get_version(name)
                if version:
                    dep_info["version"] = version

            if dep["required"]:
                required_deps.append(dep_info)
            else:
                optional_deps.append(dep_info)

        # Print required dependencies
        print("\n� Required Dependencies:")
        print("-" * 40)
        all_required_ok = True

        for dep in required_deps:
            status = "✓" if dep["installed"] else "✗"
            version = (
                f" (v{dep.get('version', 'unknown')})" if verbose and dep.get("version") else ""
            )
            print(f"{status} {dep['name']:<15} : {dep['description']}{version}")

            if not dep["installed"]:
                all_required_ok = False

        # Print optional dependencies
        print("\n📎 Optional Dependencies:")
        print("-" * 40)

        for dep in optional_deps:
            status = "✓" if dep["installed"] else "○"
            version = (
                f" (v{dep.get('version', 'unknown')})" if verbose and dep.get("version") else ""
            )
            print(f"{status} {dep['name']:<15} : {dep['description']}{version}")

        print("=" * 60)

        if not all_required_ok:
            print("\n⚠ Missing required dependencies detected!")
            print("Run: kopi-docka install-deps")
        else:
            print("\n✅ All required dependencies are installed!")
            print("Ready to backup! Run: kopi-docka backup --dry-run")

        print()

    def export_requirements(self) -> Dict[str, any]:
        """
        Export dependency requirements for documentation.

        Returns:
            Dictionary with all dependency requirements
        """
        return {
            "system": self.distro,
            "dependencies": self.DEPENDENCIES,
            "status": self.check_all(include_optional=True),
            "missing": self.get_missing(required_only=False),
        }
