################################################################################
# KOPI-DOCKA
#
# @file:        dependency_manager.py
# @module:      kopi_docka.cores
# @description: Simplified dependency manager with Hard/Soft Gate system
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Think Simple Strategy: No distro detection, no automatic installation
# - Users prepare their system manually or use Server-Baukasten
# - Hard Gate: Docker + Kopia (non-skippable)
# - Soft Gate: Command-specific tools (skippable with flag)
################################################################################

"""
Simplified Dependency Manager - Think Simple Strategy

No distro detection, no package managers, no automatic installation.
Users prepare their system manually or use Server-Baukasten.
"""

from enum import Enum
from typing import List, Dict, Optional
import sys
from rich.console import Console

from ..helpers.logging import get_logger

logger = get_logger(__name__)
console = Console()


class DependencyCategory(str, Enum):
    """Dependency category types."""
    MUST_HAVE = "MUST_HAVE"  # Docker, Kopia - not skippable
    SOFT = "SOFT"            # tar, openssl - skippable with flag
    BACKEND = "BACKEND"      # ssh, tailscale, rclone - checked by backends
    OPTIONAL = "OPTIONAL"    # systemctl, hostname, du - only shown in doctor


# Installation URLs for MUST_HAVE dependencies
INSTALLATION_URLS = {
    "docker": "https://docs.docker.com/engine/install/",
    "kopia": "https://kopia.io/docs/installation/",
}

# Server-Baukasten for automated system setup
SERVER_BAUKASTEN_URL = "https://github.com/TZERO78/Server-Baukasten"


class DependencyManager:
    """Simplified dependency manager without automatic installation."""

    def __init__(self, config=None):
        """
        Initialize dependency manager.

        Args:
            config: Optional config object (for backward compatibility)
        """
        self.config = config
        self._init_dependencies()

    def _init_dependencies(self):
        """Initialize the dependency definitions with categories."""
        self.dependencies = {
            "docker": {
                "check_method": self.check_docker,
                "required": True,
                "category": DependencyCategory.MUST_HAVE,
                "description": "Container runtime for Kopi-Docka",
            },
            "kopia": {
                "check_method": self.check_kopia,
                "required": True,
                "category": DependencyCategory.MUST_HAVE,
                "description": "Backup engine",
            },
            "tar": {
                "check_method": self.check_tar,
                "required": False,
                "category": DependencyCategory.SOFT,
                "description": "Archive creation for disaster recovery",
            },
            "openssl": {
                "check_method": self.check_openssl,
                "required": False,
                "category": DependencyCategory.SOFT,
                "description": "Encryption for disaster recovery bundles",
            },
            "openssh": {
                "check_method": self.check_openssh,
                "required": False,
                "category": DependencyCategory.BACKEND,
                "description": "SSH client for Tailscale/SFTP backends",
            },
            "systemctl": {
                "check_method": self.check_systemctl,
                "required": False,
                "category": DependencyCategory.OPTIONAL,
                "description": "Systemd service management",
            },
            "hostname": {
                "check_method": self.check_hostname,
                "required": False,
                "category": DependencyCategory.OPTIONAL,
                "description": "System hostname utility",
            },
        }

    def check_docker(self) -> bool:
        """Check if Docker is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("docker")

    def check_kopia(self) -> bool:
        """Check if Kopia is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("kopia")

    def check_tar(self) -> bool:
        """Check if tar is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("tar")

    def check_openssl(self) -> bool:
        """Check if openssl is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("openssl")

    def check_openssh(self) -> bool:
        """Check if SSH client tools are available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        required_tools = ["ssh", "ssh-keygen"]
        missing = DependencyHelper.missing(required_tools)
        return len(missing) == 0

    def check_systemctl(self) -> bool:
        """Check if systemctl is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("systemctl")

    def check_hostname(self) -> bool:
        """Check if hostname is available."""
        from kopi_docka.helpers.dependency_helper import DependencyHelper
        return DependencyHelper.exists("hostname")

    def check_hard_gate(self) -> None:
        """
        Check MUST_HAVE dependencies (docker, kopia).

        These dependencies CANNOT be skipped, even with --skip-dependency-check.

        Raises:
            SystemExit: If any MUST_HAVE dependency is missing
        """
        from kopi_docka.helpers.dependency_helper import DependencyHelper

        must_have_deps = {
            name: info for name, info in self.dependencies.items()
            if info.get("category") == DependencyCategory.MUST_HAVE
        }

        missing = []
        for name, info in must_have_deps.items():
            if not DependencyHelper.exists(name):
                missing.append(name)

        if missing:
            error_msg = [
                "",
                "━" * 60,
                "✗ Cannot proceed - required dependencies missing",
                "━" * 60,
                "",
                f"  Missing: {', '.join(missing)}",
                "",
                "Kopi-Docka requires Docker and Kopia to function.",
                "",
                "Installation:",
            ]

            for dep in missing:
                if dep in INSTALLATION_URLS:
                    error_msg.append(f"  • {dep.capitalize()}: {INSTALLATION_URLS[dep]}")

            error_msg.extend([
                "",
                "Automated Setup:",
                "  Use Server-Baukasten for automated system preparation:",
                f"  {SERVER_BAUKASTEN_URL}",
                "",
                "After installation, verify with:",
                "  kopi-docka doctor",
                "",
                "Note: --skip-dependency-check does NOT apply to Docker/Kopia.",
                ""
            ])

            console.print("\n".join(error_msg), style="red")
            sys.exit(1)

    def check_soft_gate(self, required_tools: List[str], skip: bool = False) -> None:
        """
        Check SOFT dependencies (command-specific tools).

        These can be skipped with --skip-dependency-check flag.

        Args:
            required_tools: List of tool names to check (e.g., ["tar", "openssl"])
            skip: If True, show warning and continue. If False, raise error.

        Raises:
            SystemExit: If any required tool is missing and skip=False
        """
        from kopi_docka.helpers.dependency_helper import DependencyHelper

        missing = DependencyHelper.missing(required_tools)

        if not missing:
            return  # All tools present

        if skip:
            # Show warning and continue
            console.print(f"\n[yellow]⚠️ Skipping dependency check for: {', '.join(missing)}[/yellow]")
            console.print("[yellow]   Some features may not work correctly.[/yellow]\n")
            return

        # Build simple error message
        error_msg = [
            "",
            f"✗ Missing optional dependencies: {', '.join(missing)}",
            "",
            "Please install manually.",
            "",
            "Automated Setup:",
            "  Use Server-Baukasten for automated system preparation:",
            f"  {SERVER_BAUKASTEN_URL}",
            "",
            "Or run with --skip-dependency-check (not recommended):",
        ]

        # Get current command name from sys.argv
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            error_msg.append(f"  kopi-docka {cmd} --skip-dependency-check")
        else:
            error_msg.append("  kopi-docka <command> --skip-dependency-check")

        error_msg.append("")

        console.print("\n".join(error_msg), style="yellow")
        sys.exit(1)

    def check_dependency(self, name: str) -> bool:
        """
        Check if a specific dependency is installed.

        Args:
            name: Dependency name

        Returns:
            True if installed, False otherwise
        """
        dep = self.dependencies.get(name)
        if not dep:
            return False

        # Use specific check method
        method = dep.get("check_method")
        if method:
            return method()

        return False

    def check_all(self, include_optional: bool = False) -> Dict[str, bool]:
        """
        Check all dependencies.

        Args:
            include_optional: Include optional dependencies in check

        Returns:
            Dictionary mapping dependency name to installation status
        """
        results = {}
        for name, dep in self.dependencies.items():
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
        for name, dep in self.dependencies.items():
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
        from kopi_docka.helpers.dependency_helper import DependencyHelper

        if not self.check_dependency(name):
            return None

        return DependencyHelper.get_version(name)

    def print_status(self, verbose: bool = False):
        """
        Print dependency status report (legacy compatibility).

        Args:
            verbose: Show detailed information including versions
        """
        from kopi_docka.helpers.dependency_helper import DependencyHelper

        print("\n" + "=" * 60)
        print("KOPI-DOCKA DEPENDENCY STATUS")
        print("=" * 60)

        results = self.check_all(include_optional=True)

        required_deps = []
        optional_deps = []

        for name, installed in results.items():
            dep = self.dependencies[name]
            dep_info = {
                "name": name,
                "installed": installed,
                "description": dep["description"],
                "required": dep["required"],
                "category": dep.get("category", "UNKNOWN"),
            }

            if verbose and installed:
                version = DependencyHelper.get_version(name)
                if version:
                    dep_info["version"] = version

            if dep["required"]:
                required_deps.append(dep_info)
            else:
                optional_deps.append(dep_info)

        # Print required dependencies
        print("\n🔒 Required Dependencies:")
        print("-" * 40)
        all_required_ok = True

        for dep in required_deps:
            status = "✓" if dep["installed"] else "✗"
            category = f"[{dep['category']}]"
            version = (
                f" (v{dep.get('version', 'unknown')})" if verbose and dep.get("version") else ""
            )
            print(f"{status} {dep['name']:<15} {category:<15} : {dep['description']}{version}")

            if not dep["installed"]:
                all_required_ok = False

        # Print optional dependencies
        print("\n📎 Optional Dependencies:")
        print("-" * 40)

        for dep in optional_deps:
            status = "✓" if dep["installed"] else "○"
            category = f"[{dep['category']}]"
            version = (
                f" (v{dep.get('version', 'unknown')})" if verbose and dep.get("version") else ""
            )
            print(f"{status} {dep['name']:<15} {category:<15} : {dep['description']}{version}")

        print("=" * 60)

        if not all_required_ok:
            print("\n⚠ Missing required dependencies detected!")
            print(f"Install manually or use: {SERVER_BAUKASTEN_URL}")
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
            "dependencies": self.dependencies,
            "status": self.check_all(include_optional=True),
            "missing": self.get_missing(required_only=False),
        }
