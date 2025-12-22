#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        rclone.py
# @module:      kopi_docka.backends
# @description: Rclone backend implementation for Kopia
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Rclone backend for Kopia.

Uses Kopia's built-in rclone support to connect to any cloud storage
that rclone supports (OneDrive, Dropbox, Google Drive, etc.).
"""

import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import typer

from .base import BackendBase


def get_default_remote_path() -> str:
    """
    Generate a hostname-based default remote path.

    Returns:
        String like "kopia-backup_HOSTNAME" with sanitized hostname.
    """
    hostname = socket.gethostname()
    # Sanitize hostname: remove special chars, replace . and - with _, uppercase
    clean_hostname = re.sub(r'[^a-zA-Z0-9_]', '_', hostname.replace('.', '_').replace('-', '_'))
    clean_hostname = re.sub(r'_+', '_', clean_hostname).strip('_').upper()
    # Fallback if hostname is empty after sanitization
    if not clean_hostname:
        clean_hostname = "DEFAULT"
    return f"kopia-backup_{clean_hostname}"


class RcloneBackend(BackendBase):
    """
    Rclone backend implementation.
    
    Leverages Kopia's native rclone support to connect to any
    cloud storage provider supported by rclone.
    """

    @property
    def name(self) -> str:
        return "rclone"

    @property
    def display_name(self) -> str:
        return "Rclone (Universal Cloud Storage)"

    @property
    def description(self) -> str:
        return "Use rclone to connect to any cloud storage (OneDrive, Dropbox, Google Drive, etc.)"

    def _get_config_candidates(self) -> tuple[Optional[Path], Optional[Path], Optional[str]]:
        """
        Find rclone config file candidates with PermissionError handling.
        
        Returns:
            Tuple of (root_config_path, user_config_path, sudo_user_name)
            - root_config_path: Path object for root config (or None if not accessible)
            - user_config_path: Path object for user config (or None if not available)
            - sudo_user_name: Name of the SUDO_USER (or None)
        """
        root_config = Path("/root/.config/rclone/rclone.conf")
        sudo_user = os.environ.get('SUDO_USER')
        user_config = Path(f"/home/{sudo_user}/.config/rclone/rclone.conf") if sudo_user else None
        
        # Check root config with PermissionError handling
        root_config_accessible = None
        try:
            if root_config.exists():
                root_config_accessible = root_config
        except PermissionError:
            pass
        
        # Check user config with PermissionError handling
        user_config_accessible = None
        if user_config:
            try:
                if user_config.exists():
                    user_config_accessible = user_config
            except PermissionError:
                pass
        
        return (root_config_accessible, user_config_accessible, sudo_user)

    def _find_rclone_config(self) -> Optional[str]:
        """
        Find rclone config file with sudo-awareness (legacy method).
        
        Uses _get_config_candidates() internally. Kept for backward compatibility.

        Returns:
            Path to config file if found, None otherwise
        """
        root_config, user_config, _ = self._get_config_candidates()
        
        if root_config:
            return str(root_config)
        if user_config:
            return str(user_config)
        
        return None

    def _test_rclone_connection(self, remote: str, path: str, config_path: Optional[str] = None) -> tuple:
        """
        Test rclone connection by listing directories.

        Args:
            remote: Rclone remote name
            path: Path on the remote
            config_path: Optional path to rclone config file

        Returns:
            Tuple of (success: bool, stderr: str)
        """
        cmd = ["rclone", "lsd", f"{remote}:{path}"]
        if config_path:
            cmd.extend(["--config", config_path])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return (result.returncode == 0, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "Connection timed out after 30 seconds")
        except Exception as e:
            return (False, str(e))

    def _check_remote_path_exists(
        self, remote: str, path: str, config_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Check if a remote path exists using rclone lsd on the parent directory.

        Args:
            remote: Rclone remote name
            path: Path on the remote to check
            config_path: Optional path to rclone config file

        Returns:
            Tuple of (exists: bool, error_message: str)
        """
        # For root-level folder, we need to check if it exists in the remote root
        # Use lsd to list directories at the parent level
        if '/' in path:
            parent = '/'.join(path.split('/')[:-1])
            folder_name = path.split('/')[-1]
        else:
            parent = ''
            folder_name = path

        cmd = ["rclone", "lsd", f"{remote}:{parent}"]
        if config_path:
            cmd.extend(["--config", config_path])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            # Check if the folder name appears in the output
            if result.returncode == 0:
                # Parse lsd output - each line contains folder info
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and folder_name in line:
                        # lsd format: "          -1 2024-01-01 00:00:00        -1 foldername"
                        # The folder name is at the end
                        parts = line.split()
                        if parts and parts[-1] == folder_name:
                            return (True, "")
                return (False, f"Folder '{path}' not found")
            else:
                return (False, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "Connection timed out after 30 seconds")
        except Exception as e:
            return (False, str(e))

    def _rclone_mkdir(
        self, remote: str, path: str, config_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Create a directory on the remote using rclone mkdir.

        Args:
            remote: Rclone remote name
            path: Path to create on the remote
            config_path: Optional path to rclone config file

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        cmd = ["rclone", "mkdir", f"{remote}:{path}"]
        if config_path:
            cmd.extend(["--config", config_path])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return (True, "")
            else:
                return (False, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "Operation timed out after 60 seconds")
        except Exception as e:
            return (False, str(e))

    def configure(self) -> dict:
        """
        Configure Rclone backend with sudo-aware config detection and connection testing.

        Returns:
            Configuration dictionary with kopia_params
        """
        typer.echo("=" * 60)
        typer.echo("Rclone Repository Configuration")
        typer.echo("=" * 60)
        typer.echo("")

        # Step 1: Check if rclone is installed
        if not shutil.which("rclone"):
            typer.secho("ERROR: rclone is not installed!", fg=typer.colors.RED, bold=True)
            typer.echo("")
            typer.echo("Please install rclone first:")
            typer.echo("  curl https://rclone.org/install.sh | sudo bash")
            typer.echo("")
            typer.echo("Or visit: https://rclone.org/install/")
            raise SystemExit(1)

        typer.secho("✓ rclone is installed", fg=typer.colors.GREEN)
        typer.echo("")

        # Step 2: Sudo-aware config detection
        root_config, user_config, sudo_user = self._get_config_candidates()
        rclone_config: Optional[str] = None

        typer.echo("Looking for rclone configuration...")

        if root_config:
            typer.secho(f"✓ Found config: {root_config}", fg=typer.colors.GREEN)
            rclone_config = str(root_config)
        elif user_config:
            typer.secho(f"Found config in user home: {user_config}", fg=typer.colors.YELLOW)
            typer.echo(f"  (You're running as root via sudo, but rclone was configured as '{sudo_user}')")
            typer.echo("")
            if typer.confirm(f"Use config from /home/{sudo_user}?", default=True):
                rclone_config = str(user_config)
                typer.secho(f"✓ Using: {rclone_config}", fg=typer.colors.GREEN)
        
        # If no config was selected, create one
        if not rclone_config:
            typer.secho("No rclone configuration found!", fg=typer.colors.YELLOW)
            typer.echo("")
            typer.echo("Checked locations:")
            typer.echo("  - /root/.config/rclone/rclone.conf")
            if sudo_user:
                typer.echo(f"  - /home/{sudo_user}/.config/rclone/rclone.conf")
            typer.echo("")

            if typer.confirm("Run 'rclone config' to create a new configuration?", default=True):
                typer.echo("")
                typer.echo("Starting rclone configuration wizard...")
                typer.echo("(This will create a config in /root/.config/rclone/)")
                typer.echo("")

                try:
                    subprocess.run(["rclone", "config"], check=True)
                    # Re-check for config after creation
                    root_config_new = Path("/root/.config/rclone/rclone.conf")
                    try:
                        if root_config_new.exists():
                            rclone_config = str(root_config_new)
                    except PermissionError:
                        pass
                except subprocess.CalledProcessError:
                    typer.secho("rclone config failed!", fg=typer.colors.RED)
                    raise SystemExit(1)
            else:
                typer.secho("Cannot proceed without rclone configuration.", fg=typer.colors.RED)
                raise SystemExit(1)

        typer.echo("")

        # Step 3: Get rclone remote name
        typer.echo("Available remotes (from your rclone config):")
        list_cmd = ["rclone", "listremotes"]
        if rclone_config:
            list_cmd.extend(["--config", rclone_config])

        try:
            result = subprocess.run(list_cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                for remote_line in result.stdout.strip().split('\n'):
                    typer.echo(f"  - {remote_line}")
            else:
                typer.secho("  (No remotes configured)", fg=typer.colors.YELLOW)
        except Exception:
            pass

        typer.echo("")
        remote = typer.prompt(
            "Rclone remote name",
            type=str
        ).strip().rstrip(':')  # Remove trailing colon if user added it

        if not remote:
            typer.secho("Remote name cannot be empty!", fg=typer.colors.RED)
            raise SystemExit(1)

        # Get remote path with hostname-based default
        default_remote_path = get_default_remote_path()
        remote_path = typer.prompt(
            "Remote path (folder for backups)",
            default=default_remote_path,
            type=str
        ).strip().lstrip('/')  # Remove leading slash if present

        # Use default if user provides empty string
        if not remote_path:
            remote_path = default_remote_path

        typer.echo("")

        # Step 4: Check if folder exists and offer to create it
        typer.echo("Checking if folder exists...")
        full_remote_path = f"{remote}:{remote_path}"

        exists, check_error = self._check_remote_path_exists(remote, remote_path, rclone_config)

        if exists:
            typer.secho(f"✓ Folder '{remote_path}' exists on {remote}:", fg=typer.colors.GREEN)
        else:
            typer.secho(f"✗ Folder '{remote_path}' not found in {remote}:", fg=typer.colors.YELLOW)
            typer.echo("")

            if typer.confirm("  Create it now?", default=True):
                typer.echo("  Creating folder...")
                create_success, create_error = self._rclone_mkdir(remote, remote_path, rclone_config)

                if create_success:
                    typer.secho(f"✓ Created: {full_remote_path}", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"✗ Failed to create folder: {create_error}", fg=typer.colors.RED)
                    typer.echo("")
                    if not typer.confirm("Continue anyway? (You may need to create the folder manually)", default=False):
                        typer.secho("Configuration cancelled.", fg=typer.colors.YELLOW)
                        raise SystemExit(1)
                    typer.secho("Proceeding without folder creation", fg=typer.colors.YELLOW)
            else:
                typer.secho("⚠ Folder not created. You may need to create it manually.", fg=typer.colors.YELLOW)
                if not typer.confirm("Continue anyway?", default=False):
                    typer.secho("Configuration cancelled.", fg=typer.colors.YELLOW)
                    raise SystemExit(1)

        typer.echo("")

        # Step 5: Live connection test
        typer.echo("Testing connection...")

        success, stderr = self._test_rclone_connection(remote, remote_path, rclone_config)

        if success:
            typer.secho(f"✓ Connection successful to {full_remote_path}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"✗ Connection failed to {full_remote_path}", fg=typer.colors.RED)
            if stderr:
                typer.echo("")
                typer.echo("Error details:")
                for line in stderr.strip().split('\n'):
                    typer.secho(f"  {line}", fg=typer.colors.RED)
            typer.echo("")

            if not typer.confirm("Proceed anyway despite the connection error?", default=False):
                typer.secho("Configuration cancelled.", fg=typer.colors.YELLOW)
                raise SystemExit(1)
            typer.secho("Proceeding with configuration (connection issues may need to be resolved later)", fg=typer.colors.YELLOW)

        typer.echo("")

        # Build kopia_params
        kopia_params = f"rclone --remote-path={full_remote_path}"

        # Always include config path if we're using a specific file
        if rclone_config:
            kopia_params += f" --rclone-args='--config={rclone_config}'"

        # Build instructions
        config_note = f"\n  Config File: {rclone_config}" if rclone_config else ""
        instructions = f"""
Rclone Repository Setup Complete
{'=' * 60}

Remote Configuration:
  Remote Name: {remote}
  Remote Path: {remote_path}
  Full Path:   {full_remote_path}{config_note}

Next Steps:
  1. Initialize repository:
     sudo kopi-docka init

  2. Verify backups:
     rclone tree {remote}:{remote_path}

Useful Commands:
  - List files:    rclone ls {remote}: --config {rclone_config or '~/.config/rclone/rclone.conf'}
  - Check config:  rclone config show {remote}
  - Test speed:    rclone test speed {remote}:

Documentation:
  - Rclone docs: https://rclone.org/docs/
  - Kopia rclone: https://kopia.io/docs/repositories/#rclone
"""

        # Configuration summary
        typer.echo("=" * 60)
        typer.echo("Configuration Summary")
        typer.echo("=" * 60)
        typer.echo(f"  Remote:      {remote}")
        typer.echo(f"  Path:        {remote_path}")
        typer.echo(f"  Full Path:   {full_remote_path}")
        if rclone_config:
            typer.echo(f"  Config File: {rclone_config}")
        typer.echo("")
        typer.secho("✓ Configuration complete!", fg=typer.colors.GREEN)
        typer.echo("")

        return {
            'kopia_params': kopia_params,
            'instructions': instructions
        }
    
    # Abstract method implementations (required by BackendBase)
    # These are stubs since the new architecture uses configure() instead
    
    def check_dependencies(self) -> list:
        """Check if rclone is installed."""
        import shutil
        missing = []
        if not shutil.which("rclone"):
            missing.append("rclone")
        return missing
    
    def install_dependencies(self) -> bool:
        """Rclone must be installed manually."""
        return False
    
    def setup_interactive(self) -> dict:
        """Use configure() instead."""
        return self.configure()
    
    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])
    
    def test_connection(self) -> bool:
        """Test connection (not implemented)."""
        return True
    
    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex
        kopia_params = self.config.get('kopia_params', '')
        return shlex.split(kopia_params) if kopia_params else []

    def get_status(self) -> dict:
        """Get Rclone storage status."""
        import shlex
        import re

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "remote_path": None,
                "remote_name": None,
                "config_file": None,
            }
        }

        kopia_params = self.config.get('kopia_params', '')
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            # Parse --remote-path
            for part in parts:
                if part.startswith('--remote-path='):
                    remote_path = part.split('=', 1)[1]
                    status["details"]["remote_path"] = remote_path
                    # Extract remote name (before the colon)
                    if ':' in remote_path:
                        status["details"]["remote_name"] = remote_path.split(':')[0]

            # Parse --rclone-args for config file
            for part in parts:
                if part.startswith('--rclone-args='):
                    rclone_args = part.split('=', 1)[1].strip("'\"")
                    # Extract --config from rclone args
                    if '--config=' in rclone_args:
                        config_file = rclone_args.split('--config=', 1)[1].strip()
                        status["details"]["config_file"] = config_file

            if status["details"]["remote_path"]:
                status["configured"] = True
                status["available"] = True
        except Exception:
            pass

        return status
