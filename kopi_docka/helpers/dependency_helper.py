"""Lightweight CLI tool detection utility."""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ToolInfo:
    """Information about a CLI tool."""
    name: str
    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None


class DependencyHelper:
    """Helper class for checking CLI tool availability and versions."""

    # Known version commands for common tools
    VERSION_COMMANDS = {
        "docker": ["docker", "version", "--format", "{{.Server.Version}}"],
        "kopia": ["kopia", "--version"],
        "tailscale": ["tailscale", "version"],
        "rclone": ["rclone", "version"],
        "ssh": ["ssh", "-V"],
        "ssh-keygen": ["ssh-keygen", "-V"],
        "ssh-copy-id": ["ssh-copy-id", "-h"],  # No --version, only -h
        "openssl": ["openssl", "version"],
        "tar": ["tar", "--version"],
        "curl": ["curl", "--version"],
        "systemctl": ["systemctl", "--version"],
        "journalctl": ["journalctl", "--version"],
    }

    @staticmethod
    def exists(name: str) -> bool:
        """Check if a tool exists in PATH."""
        return shutil.which(name) is not None

    @staticmethod
    def get_path(name: str) -> Optional[str]:
        """Get the full path to a tool."""
        return shutil.which(name)

    @staticmethod
    def get_version(name: str, version_cmd: Optional[List[str]] = None) -> Optional[str]:
        """
        Get the version of a tool with robust parsing.

        Handles various edge cases:
        - Version output in stderr (ssh, ssh-keygen)
        - Prefixes like "v1.2.3", "version 1.2.3"
        - Suffixes like "1.2.3-alpha", "1.2.3-rc1"
        - Multi-line output (takes first match)
        - Command failures (returns None)

        Args:
            name: Tool name
            version_cmd: Custom version command (default: use VERSION_COMMANDS)

        Returns:
            Version string (e.g., "1.2.3", "1.2.3-alpha") or None if unable to determine
        """
        if not DependencyHelper.exists(name):
            return None

        cmd = version_cmd or DependencyHelper.VERSION_COMMANDS.get(name)
        if not cmd:
            return None

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )

            # Try stdout first, fallback to stderr (ssh outputs to stderr)
            output = result.stdout.strip() or result.stderr.strip()

            if not output:
                return None

            # Extract version with robust regex patterns
            import re

            # Pattern 1: Semantic versioning with optional prefix/suffix
            # Matches: v1.2.3, 1.2.3-alpha, 1.2.3-rc1, version 1.2.3
            patterns = [
                # Full semver with suffix: 1.2.3-alpha1, 2.0.0-rc.1
                r'v?(\d+\.\d+\.\d+(?:-[a-zA-Z0-9._-]+)?)',
                # Partial version with suffix: 1.2-beta
                r'v?(\d+\.\d+(?:-[a-zA-Z0-9._-]+)?)',
                # Just numbers: 1.2.3, 1.2
                r'(\d+\.\d+(?:\.\d+)?)',
            ]

            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    version = match.group(1)
                    # Clean up: remove leading 'v' if present
                    return version.lstrip('v')

            # Fallback: return first 50 chars if no version pattern found
            # This handles tools with non-standard version output
            return output.split('\n')[0][:50].strip()

        except subprocess.TimeoutExpired:
            # Tool exists but version command hangs - return special marker
            return "timeout"
        except FileNotFoundError:
            # Tool doesn't exist (shouldn't happen due to exists() check)
            return None
        except Exception:
            # Log error but don't crash
            return None

    @staticmethod
    def check(name: str, version_cmd: Optional[List[str]] = None) -> ToolInfo:
        """
        Get complete information about a tool.

        Args:
            name: Tool name
            version_cmd: Custom version command

        Returns:
            ToolInfo with all available information
        """
        installed = DependencyHelper.exists(name)
        return ToolInfo(
            name=name,
            installed=installed,
            path=DependencyHelper.get_path(name) if installed else None,
            version=DependencyHelper.get_version(name, version_cmd) if installed else None
        )

    @staticmethod
    def check_all(names: List[str]) -> Dict[str, ToolInfo]:
        """
        Check multiple tools at once.

        Args:
            names: List of tool names

        Returns:
            Dict mapping tool name to ToolInfo
        """
        return {name: DependencyHelper.check(name) for name in names}

    @staticmethod
    def missing(names: List[str]) -> List[str]:
        """
        Get list of missing tools.

        Args:
            names: List of tool names to check

        Returns:
            List of tool names that are not installed
        """
        return [name for name in names if not DependencyHelper.exists(name)]
