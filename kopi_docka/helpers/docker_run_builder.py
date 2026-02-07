################################################################################
# KOPI-DOCKA
#
# @file:        docker_run_builder.py
# @module:      kopi_docka.helpers
# @description: Reconstruct docker run commands from container inspect JSON
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     6.1.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025-2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Reconstruct docker run commands from container inspect JSON files.

This module provides functionality to automatically reconstruct `docker run`
commands from `*_inspect.json` files created during backup. This eliminates
the need for manual container recreation in standalone (non-compose) setups.

Features:
- Parse Docker inspect.json files
- Build complete docker run commands
- Handle all common container parameters (ports, volumes, env, etc.)
- Interactive or automated container restart
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .logging import get_logger

logger = get_logger(__name__)


class DockerRunBuilder:
    """
    Build docker run command from container inspect.json data.
    
    Parses Docker container inspection data and reconstructs an equivalent
    `docker run` command that can be used to recreate the container with
    the same configuration.
    
    Example:
        >>> builder = DockerRunBuilder.from_file(Path("nginx_inspect.json"))
        >>> command = builder.build_command()
        >>> print(command)
        docker run -d \\
          --name nginx \\
          --restart unless-stopped \\
          -p 80:80 \\
          -v /data:/usr/share/nginx/html \\
          nginx:latest
    """

    def __init__(self, inspect_data: Dict[str, Any]):
        """
        Initialize builder with inspect data.
        
        Args:
            inspect_data: Dictionary containing Docker inspect output
        """
        self.data = inspect_data
        self.config = inspect_data.get("Config", {})
        self.host_config = inspect_data.get("HostConfig", {})
        self.network_settings = inspect_data.get("NetworkSettings", {})
        self.mounts = inspect_data.get("Mounts", [])

    @classmethod
    def from_file(cls, path: Path) -> "DockerRunBuilder":
        """
        Load inspect data from JSON file.
        
        Args:
            path: Path to *_inspect.json file
            
        Returns:
            DockerRunBuilder instance
            
        Raises:
            json.JSONDecodeError: If file contains invalid JSON
            FileNotFoundError: If file doesn't exist
        """
        logger.debug(f"Loading inspect data from: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    def build_command(self) -> str:
        """
        Build complete docker run command.
        
        Constructs a docker run command with all relevant parameters from
        the inspect data. The command is formatted for readability with
        line continuations.
        
        Returns:
            Multi-line docker run command string
        """
        parts = ["docker run -d"]

        # Container name
        name = self.get_container_name()
        if name and name != "unknown":
            parts.append(f"--name {self._quote_if_needed(name)}")

        # Restart policy
        restart = self.host_config.get("RestartPolicy", {}).get("Name")
        if restart and restart != "no":
            parts.append(f"--restart {restart}")

        # Network
        network = self.host_config.get("NetworkMode", "")
        if network and network not in ("default", "bridge"):
            parts.append(f"--network {network}")

        # Hostname
        hostname = self.config.get("Hostname")
        if hostname:
            parts.append(f"--hostname {hostname}")

        # Ports
        port_bindings = self.host_config.get("PortBindings", {})
        for container_port, bindings in port_bindings.items():
            if bindings:
                for binding in bindings:
                    host_port = binding.get("HostPort", "")
                    host_ip = binding.get("HostIp", "")
                    container_port_num = container_port.split("/")[0]
                    
                    if host_ip:
                        port_spec = f"{host_ip}:{host_port}:{container_port_num}"
                    elif host_port:
                        port_spec = f"{host_port}:{container_port_num}"
                    else:
                        port_spec = container_port_num
                    
                    parts.append(f"-p {port_spec}")

        # Volumes/Mounts
        for mount in self.mounts:
            mount_type = mount.get("Type", "bind")
            dest = mount.get("Destination", "")

            if mount_type == "bind":
                src = mount.get("Source", "")
                rw = mount.get("RW", True)
                mode = "" if rw else ":ro"
                vol_spec = f"{src}:{dest}{mode}"
                parts.append(f"-v {self._quote_if_needed(vol_spec)}")
            elif mount_type == "volume":
                vol_name = mount.get("Name", "")
                if vol_name:
                    parts.append(f"-v {vol_name}:{dest}")

        # Environment variables (filter out Docker-injected vars)
        for env in self.config.get("Env", []):
            if not self._is_docker_injected_env(env):
                parts.append(f"-e {self._quote_if_needed(env)}")

        # User
        user = self.config.get("User")
        if user:
            parts.append(f"-u {user}")

        # Working directory
        workdir = self.config.get("WorkingDir")
        if workdir and workdir != "/":
            parts.append(f"-w {self._quote_if_needed(workdir)}")

        # Privileged
        if self.host_config.get("Privileged"):
            parts.append("--privileged")

        # Capabilities
        for cap in self.host_config.get("CapAdd", []):
            parts.append(f"--cap-add {cap}")
        for cap in self.host_config.get("CapDrop", []):
            parts.append(f"--cap-drop {cap}")

        # Memory limit
        memory = self.host_config.get("Memory", 0)
        if memory and memory > 0:
            parts.append(f"-m {memory}")

        # CPU shares
        cpu_shares = self.host_config.get("CpuShares", 0)
        if cpu_shares and cpu_shares != 0 and cpu_shares != 1024:
            parts.append(f"--cpu-shares {cpu_shares}")

        # Labels (skip docker-compose internal labels)
        labels = self.config.get("Labels", {})
        for key, value in labels.items():
            if not key.startswith("com.docker.compose"):
                parts.append(f"-l {self._quote_if_needed(f'{key}={value}')}")

        # Entrypoint (only if custom)
        entrypoint = self.config.get("Entrypoint")
        if entrypoint and entrypoint != ["/docker-entrypoint.sh"]:
            ep_str = " ".join(entrypoint) if isinstance(entrypoint, list) else entrypoint
            parts.append(f"--entrypoint {self._quote_if_needed(ep_str)}")

        # Image (must be last before CMD)
        image = self.get_image()
        parts.append(image)

        # CMD (only if custom and not empty)
        cmd = self.config.get("Cmd")
        if cmd:
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if cmd_str.strip():
                parts.append(self._quote_if_needed(cmd_str))

        # Format with line continuations for readability
        return " \\\n  ".join(parts)

    def get_container_name(self) -> str:
        """
        Get container name without leading slash.
        
        Returns:
            Container name or "unknown" if not found
        """
        name = self.data.get("Name", "")
        return name.lstrip("/") if name else "unknown"

    def get_image(self) -> str:
        """
        Get image name.
        
        Returns:
            Image name or "unknown" if not found
        """
        return self.config.get("Image", "unknown")

    def get_networks(self) -> List[str]:
        """
        Get list of custom networks the container is connected to.
        
        Returns:
            List of network names (excluding 'bridge' and 'host')
        """
        networks = self.network_settings.get("Networks", {})
        return [
            name
            for name in networks.keys()
            if name not in ("bridge", "host", "none")
        ]

    def _quote_if_needed(self, value: str) -> str:
        """
        Quote value if it contains spaces or special characters.
        
        Args:
            value: String to potentially quote
            
        Returns:
            Quoted or unquoted string
        """
        if " " in value or any(c in value for c in ["$", "!", "*", "?"]):
            # Escape existing quotes
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'
        return value

    def _is_docker_injected_env(self, env: str) -> bool:
        """
        Check if environment variable is Docker-injected.
        
        Args:
            env: Environment variable string (KEY=value)
            
        Returns:
            True if variable should be filtered out
        """
        # Common Docker-injected variables that shouldn't be replicated
        skip_prefixes = (
            "PATH=",
            "HOME=",
            "HOSTNAME=",
            "TERM=",
            "container=",
        )
        return env.startswith(skip_prefixes)


def find_inspect_files(restore_path: Path) -> List[Path]:
    """
    Find all *_inspect.json files in restore path.
    
    Args:
        restore_path: Directory to search for inspect files
        
    Returns:
        List of Path objects for found inspect files
    """
    if not restore_path.exists():
        logger.warning(f"Restore path does not exist: {restore_path}")
        return []

    files = sorted(restore_path.glob("*_inspect.json"))
    logger.debug(f"Found {len(files)} inspect files in {restore_path}")
    return files


def build_all_commands(restore_path: Path) -> List[Dict[str, Any]]:
    """
    Build docker run commands for all found inspect files.
    
    Args:
        restore_path: Directory containing inspect files
        
    Returns:
        List of dictionaries with container info and commands:
        - file: Path to inspect file
        - name: Container name
        - image: Image name
        - command: Reconstructed docker run command
        - networks: List of custom networks
        Or on error:
        - file: Path to inspect file
        - error: Error message
    """
    results = []
    inspect_files = find_inspect_files(restore_path)

    for inspect_file in inspect_files:
        try:
            builder = DockerRunBuilder.from_file(inspect_file)
            results.append(
                {
                    "file": str(inspect_file),
                    "name": builder.get_container_name(),
                    "image": builder.get_image(),
                    "command": builder.build_command(),
                    "networks": builder.get_networks(),
                }
            )
            logger.debug(f"Successfully built command for {builder.get_container_name()}")
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.error(f"Failed to parse {inspect_file}: {e}")
            results.append({"file": str(inspect_file), "error": str(e)})

    return results
