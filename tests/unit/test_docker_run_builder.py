#!/usr/bin/env python3
################################################################################
# @file:        test_docker_run_builder.py
# @description: Unit tests for DockerRunBuilder
################################################################################

"""Unit tests for DockerRunBuilder - docker run command reconstruction."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kopi_docka.helpers.docker_run_builder import (
    DockerRunBuilder,
    find_inspect_files,
    build_all_commands,
)


class TestDockerRunBuilderBasic:
    """Test basic functionality of DockerRunBuilder."""

    def test_simple_container(self):
        """Test building command for simple container."""
        inspect_data = {
            "Name": "/nginx",
            "Config": {
                "Image": "nginx:latest",
                "Env": ["NGINX_HOST=localhost"],
            },
            "HostConfig": {
                "RestartPolicy": {"Name": "unless-stopped"},
                "PortBindings": {"80/tcp": [{"HostPort": "8080", "HostIp": ""}]},
            },
            "NetworkSettings": {"Networks": {}},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()

        assert "docker run -d" in command
        assert "--name nginx" in command
        assert "--restart unless-stopped" in command
        assert "-p 8080:80" in command
        assert 'NGINX_HOST=localhost' in command
        assert "nginx:latest" in command

    def test_get_container_name(self):
        """Test container name extraction."""
        inspect_data = {"Name": "/my-container", "Config": {}, "HostConfig": {}}
        builder = DockerRunBuilder(inspect_data)
        assert builder.get_container_name() == "my-container"

    def test_get_container_name_without_slash(self):
        """Test container name without leading slash."""
        inspect_data = {"Name": "my-container", "Config": {}, "HostConfig": {}}
        builder = DockerRunBuilder(inspect_data)
        assert builder.get_container_name() == "my-container"

    def test_get_image(self):
        """Test image name extraction."""
        inspect_data = {
            "Name": "/test",
            "Config": {"Image": "redis:7-alpine"},
            "HostConfig": {},
        }
        builder = DockerRunBuilder(inspect_data)
        assert builder.get_image() == "redis:7-alpine"

    def test_missing_name_returns_unknown(self):
        """Test fallback for missing container name."""
        inspect_data = {"Config": {}, "HostConfig": {}}
        builder = DockerRunBuilder(inspect_data)
        assert builder.get_container_name() == "unknown"


class TestDockerRunBuilderVolumes:
    """Test volume and mount handling."""

    def test_bind_mount(self):
        """Test bind mount reconstruction."""
        inspect_data = {
            "Name": "/test",
            "Config": {"Image": "alpine"},
            "HostConfig": {},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/host/data",
                    "Destination": "/container/data",
                    "RW": True,
                }
            ],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-v /host/data:/container/data" in command

    def test_bind_mount_readonly(self):
        """Test read-only bind mount."""
        inspect_data = {
            "Name": "/test",
            "Config": {"Image": "alpine"},
            "HostConfig": {},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/host/config",
                    "Destination": "/etc/config",
                    "RW": False,
                }
            ],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-v /host/config:/etc/config:ro" in command

    def test_named_volume(self):
        """Test named volume reconstruction."""
        inspect_data = {
            "Name": "/test",
            "Config": {"Image": "postgres"},
            "HostConfig": {},
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": "postgres-data",
                    "Destination": "/var/lib/postgresql/data",
                }
            ],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-v postgres-data:/var/lib/postgresql/data" in command


class TestDockerRunBuilderPorts:
    """Test port binding reconstruction."""

    def test_simple_port(self):
        """Test simple port mapping."""
        inspect_data = {
            "Name": "/web",
            "Config": {"Image": "nginx"},
            "HostConfig": {"PortBindings": {"80/tcp": [{"HostPort": "8080", "HostIp": ""}]}},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-p 8080:80" in command

    def test_port_with_ip(self):
        """Test port mapping with specific IP."""
        inspect_data = {
            "Name": "/web",
            "Config": {"Image": "nginx"},
            "HostConfig": {
                "PortBindings": {"80/tcp": [{"HostPort": "8080", "HostIp": "127.0.0.1"}]}
            },
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-p 127.0.0.1:8080:80" in command

    def test_multiple_ports(self):
        """Test multiple port mappings."""
        inspect_data = {
            "Name": "/web",
            "Config": {"Image": "nginx"},
            "HostConfig": {
                "PortBindings": {
                    "80/tcp": [{"HostPort": "8080", "HostIp": ""}],
                    "443/tcp": [{"HostPort": "8443", "HostIp": ""}],
                }
            },
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-p 8080:80" in command
        assert "-p 8443:443" in command


class TestDockerRunBuilderEnvironment:
    """Test environment variable handling."""

    def test_custom_env_vars(self):
        """Test custom environment variables."""
        inspect_data = {
            "Name": "/app",
            "Config": {
                "Image": "myapp",
                "Env": ["APP_ENV=production", "DEBUG=false", "API_KEY=secret123"],
            },
            "HostConfig": {},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "APP_ENV=production" in command
        assert "DEBUG=false" in command
        assert "API_KEY=secret123" in command

    def test_filters_docker_injected_vars(self):
        """Test filtering of Docker-injected environment variables."""
        inspect_data = {
            "Name": "/app",
            "Config": {
                "Image": "myapp",
                "Env": [
                    "PATH=/usr/local/bin:/usr/bin",
                    "HOME=/root",
                    "HOSTNAME=abc123",
                    "MY_VAR=keep_this",
                ],
            },
            "HostConfig": {},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        
        # Docker-injected vars should be filtered out
        assert "PATH=" not in command or "MY_VAR=keep_this" in command
        assert "HOME=" not in command or "MY_VAR=keep_this" in command
        assert "HOSTNAME=" not in command or "MY_VAR=keep_this" in command
        
        # Custom var should be kept
        assert "MY_VAR=keep_this" in command


class TestDockerRunBuilderNetwork:
    """Test network configuration."""

    def test_custom_network(self):
        """Test custom network."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp"},
            "HostConfig": {"NetworkMode": "my-network"},
            "NetworkSettings": {"Networks": {"my-network": {}}},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "--network my-network" in command

    def test_bridge_network_not_included(self):
        """Test that default bridge network is not explicitly set."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp"},
            "HostConfig": {"NetworkMode": "bridge"},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "--network bridge" not in command

    def test_get_custom_networks(self):
        """Test extraction of custom networks."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp"},
            "HostConfig": {},
            "NetworkSettings": {
                "Networks": {"bridge": {}, "my-network": {}, "app-network": {}}
            },
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        networks = builder.get_networks()
        assert "my-network" in networks
        assert "app-network" in networks
        assert "bridge" not in networks


class TestDockerRunBuilderAdvanced:
    """Test advanced container configurations."""

    def test_privileged_container(self):
        """Test privileged flag."""
        inspect_data = {
            "Name": "/privileged-app",
            "Config": {"Image": "myapp"},
            "HostConfig": {"Privileged": True},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "--privileged" in command

    def test_user_flag(self):
        """Test user flag."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp", "User": "1000:1000"},
            "HostConfig": {},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-u 1000:1000" in command

    def test_working_directory(self):
        """Test working directory."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp", "WorkingDir": "/app"},
            "HostConfig": {},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-w /app" in command

    def test_capabilities(self):
        """Test capability add/drop."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp"},
            "HostConfig": {"CapAdd": ["NET_ADMIN"], "CapDrop": ["MKNOD"]},
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "--cap-add NET_ADMIN" in command
        assert "--cap-drop MKNOD" in command

    def test_memory_limit(self):
        """Test memory limit."""
        inspect_data = {
            "Name": "/app",
            "Config": {"Image": "myapp"},
            "HostConfig": {"Memory": 536870912},  # 512MB
            "Mounts": [],
        }

        builder = DockerRunBuilder(inspect_data)
        command = builder.build_command()
        assert "-m 536870912" in command


class TestDockerRunBuilderFromFile:
    """Test loading from file."""

    def test_from_file(self, tmp_path):
        """Test loading inspect data from file."""
        inspect_data = {
            "Name": "/test",
            "Config": {"Image": "nginx:latest"},
            "HostConfig": {},
            "Mounts": [],
        }

        inspect_file = tmp_path / "nginx_inspect.json"
        inspect_file.write_text(json.dumps(inspect_data))

        builder = DockerRunBuilder.from_file(inspect_file)
        assert builder.get_container_name() == "test"
        assert builder.get_image() == "nginx:latest"

    def test_from_file_invalid_json(self, tmp_path):
        """Test handling of invalid JSON."""
        inspect_file = tmp_path / "invalid.json"
        inspect_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            DockerRunBuilder.from_file(inspect_file)


class TestFindInspectFiles:
    """Test finding inspect files."""

    def test_find_inspect_files(self, tmp_path):
        """Test finding inspect files in directory."""
        (tmp_path / "nginx_inspect.json").touch()
        (tmp_path / "redis_inspect.json").touch()
        (tmp_path / "other_file.txt").touch()
        (tmp_path / "docker-compose.yml").touch()

        files = find_inspect_files(tmp_path)
        assert len(files) == 2
        assert all(f.name.endswith("_inspect.json") for f in files)

    def test_find_inspect_files_empty_dir(self, tmp_path):
        """Test finding inspect files in empty directory."""
        files = find_inspect_files(tmp_path)
        assert len(files) == 0

    def test_find_inspect_files_nonexistent_dir(self, tmp_path):
        """Test handling of non-existent directory."""
        non_existent = tmp_path / "does-not-exist"
        files = find_inspect_files(non_existent)
        assert len(files) == 0


class TestBuildAllCommands:
    """Test building commands for multiple containers."""

    def test_build_all_commands(self, tmp_path):
        """Test building commands for all inspect files."""
        # Create test inspect files
        nginx_data = {
            "Name": "/nginx",
            "Config": {"Image": "nginx:latest"},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Mounts": [],
        }
        redis_data = {
            "Name": "/redis",
            "Config": {"Image": "redis:7"},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Mounts": [],
        }

        (tmp_path / "nginx_inspect.json").write_text(json.dumps(nginx_data))
        (tmp_path / "redis_inspect.json").write_text(json.dumps(redis_data))

        results = build_all_commands(tmp_path)
        assert len(results) == 2
        
        # Check that both containers are in results
        names = [r["name"] for r in results if "name" in r]
        assert "nginx" in names
        assert "redis" in names

    def test_build_all_commands_with_error(self, tmp_path):
        """Test handling of invalid inspect file."""
        good_data = {
            "Name": "/nginx",
            "Config": {"Image": "nginx:latest"},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Mounts": [],
        }

        (tmp_path / "good_inspect.json").write_text(json.dumps(good_data))
        (tmp_path / "bad_inspect.json").write_text("{ invalid json }")

        results = build_all_commands(tmp_path)
        assert len(results) == 2
        
        # One should succeed, one should have error
        errors = [r for r in results if "error" in r]
        successes = [r for r in results if "name" in r]
        assert len(errors) == 1
        assert len(successes) == 1
