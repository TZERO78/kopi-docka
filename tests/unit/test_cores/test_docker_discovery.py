"""
Unit tests for DockerDiscovery class.

Tests the business logic of container/volume discovery and unit grouping,
with external Docker CLI calls mocked.
"""

import json
import pytest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch, Mock

from kopi_docka.cores.docker_discovery import DockerDiscovery
from kopi_docka.types import ContainerInfo, VolumeInfo, BackupUnit
from kopi_docka.helpers.constants import (
    DOCKER_COMPOSE_PROJECT_LABEL,
    DOCKER_COMPOSE_CONFIG_LABEL,
)


def make_discovery() -> DockerDiscovery:
    """Create a DockerDiscovery instance without running __init__ validation."""
    discovery = DockerDiscovery.__new__(DockerDiscovery)
    discovery.docker_socket = "/var/run/docker.sock"
    return discovery


# =============================================================================
# Database Type Detection Tests
# =============================================================================


@pytest.mark.unit
class TestDetectDatabaseType:
    """Tests for _detect_database_type method."""

    def test_detect_postgres(self):
        """postgres:15 image should be detected as postgres."""
        discovery = make_discovery()
        assert discovery._detect_database_type("postgres:15") == "postgres"

    def test_detect_postgres_with_registry(self):
        """registry/postgres:latest should be detected as postgres."""
        discovery = make_discovery()
        assert discovery._detect_database_type("myregistry.io/postgres:15") == "postgres"

    def test_detect_postgresql(self):
        """postgresql:14 image should be detected as postgres."""
        discovery = make_discovery()
        assert discovery._detect_database_type("postgresql:14") == "postgres"

    def test_detect_postgis(self):
        """postgis/postgis:15 image should be detected as postgres."""
        discovery = make_discovery()
        assert discovery._detect_database_type("postgis/postgis:15") == "postgres"

    def test_detect_mysql(self):
        """mysql:8 image should be detected as mysql."""
        discovery = make_discovery()
        assert discovery._detect_database_type("mysql:8") == "mysql"

    def test_detect_percona(self):
        """percona:8 image should be detected as mysql."""
        discovery = make_discovery()
        assert discovery._detect_database_type("percona:8") == "mysql"

    def test_detect_mariadb(self):
        """mariadb:10 image should be detected as mariadb."""
        discovery = make_discovery()
        assert discovery._detect_database_type("mariadb:10") == "mariadb"

    def test_detect_mongodb(self):
        """mongo:5 image should be detected as mongodb."""
        discovery = make_discovery()
        assert discovery._detect_database_type("mongo:5") == "mongodb"

    def test_detect_redis(self):
        """redis:7 image should be detected as redis."""
        discovery = make_discovery()
        assert discovery._detect_database_type("redis:7") == "redis"

    def test_detect_none_for_nginx(self):
        """nginx:latest should return None (not a database)."""
        discovery = make_discovery()
        assert discovery._detect_database_type("nginx:latest") is None

    def test_detect_none_for_python(self):
        """python:3.12 should return None (not a database)."""
        discovery = make_discovery()
        assert discovery._detect_database_type("python:3.12") is None

    def test_detect_case_insensitive(self):
        """Detection should be case-insensitive."""
        discovery = make_discovery()
        assert discovery._detect_database_type("POSTGRES:15") == "postgres"
        assert discovery._detect_database_type("MySQL:8") == "mysql"

    def test_detect_empty_string(self):
        """Empty string should return None."""
        discovery = make_discovery()
        assert discovery._detect_database_type("") is None

    def test_detect_none_input(self):
        """None input should return None."""
        discovery = make_discovery()
        assert discovery._detect_database_type(None) is None


# =============================================================================
# Container Info Parsing Tests
# =============================================================================


@pytest.mark.unit
class TestParseContainerInfo:
    """Tests for _parse_container_info method."""

    def test_parse_basic_container(self):
        """Basic container info should be parsed correctly."""
        discovery = make_discovery()
        data = {
            "Id": "abc123def456",
            "Name": "/mycontainer",
            "Config": {
                "Image": "nginx:latest",
                "Labels": {},
                "Env": ["PATH=/usr/bin", "MY_VAR=value"],
            },
            "State": {"Status": "running"},
            "Mounts": [],
        }

        result = discovery._parse_container_info(data)

        assert result.id == "abc123def456"
        assert result.name == "mycontainer"  # Leading slash removed
        assert result.image == "nginx:latest"
        assert result.status == "running"
        assert result.environment == {"PATH": "/usr/bin", "MY_VAR": "value"}
        assert result.database_type is None

    def test_parse_container_with_volumes(self):
        """Container with named volumes should extract volume names."""
        discovery = make_discovery()
        data = {
            "Id": "abc123",
            "Name": "/db",
            "Config": {"Image": "postgres:15", "Labels": {}, "Env": []},
            "State": {"Status": "running"},
            "Mounts": [
                {"Type": "volume", "Name": "pgdata"},
                {"Type": "bind", "Source": "/host/path"},  # Ignored (bind mount)
                {"Type": "volume", "Name": "pgconfig"},
            ],
        }

        result = discovery._parse_container_info(data)

        assert result.volumes == ["pgdata", "pgconfig"]
        assert result.database_type == "postgres"

    def test_parse_container_with_compose_labels(self):
        """Container with compose labels should extract project and config files."""
        discovery = make_discovery()
        data = {
            "Id": "abc123",
            "Name": "/mystack_web_1",
            "Config": {
                "Image": "nginx:latest",
                "Labels": {
                    DOCKER_COMPOSE_PROJECT_LABEL: "mystack",
                    DOCKER_COMPOSE_CONFIG_LABEL: "/home/user/mystack/docker-compose.yml,/home/user/mystack/docker-compose.override.yml",
                },
                "Env": [],
            },
            "State": {"Status": "running"},
            "Mounts": [],
        }

        result = discovery._parse_container_info(data)

        assert result.labels.get(DOCKER_COMPOSE_PROJECT_LABEL) == "mystack"
        assert len(result.compose_files) == 2
        assert result.compose_files[0] == Path("/home/user/mystack/docker-compose.yml")
        assert result.compose_files[1] == Path(
            "/home/user/mystack/docker-compose.override.yml"
        )

    def test_parse_container_with_empty_labels(self):
        """Container with null/empty labels should not raise."""
        discovery = make_discovery()
        data = {
            "Id": "abc123",
            "Name": "/test",
            "Config": {"Image": "alpine", "Labels": None, "Env": None},
            "State": {"Status": "exited"},
            "Mounts": None,
        }

        result = discovery._parse_container_info(data)

        assert result.labels == {}
        assert result.environment == {}
        assert result.volumes == []


# =============================================================================
# Container Discovery Tests
# =============================================================================


@pytest.mark.unit
class TestDiscoverContainers:
    """Tests for _discover_containers method."""

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_containers_parses_output(self, mock_run):
        """Should discover containers and parse inspect JSON."""
        discovery = make_discovery()

        # Mock docker ps -q
        mock_run.side_effect = [
            CompletedProcess([], 0, stdout="abc123\nxyz789\n", stderr=""),
            # docker inspect abc123
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "abc123",
                            "Name": "/web",
                            "Config": {"Image": "nginx:latest", "Labels": {}, "Env": []},
                            "State": {"Status": "running"},
                            "Mounts": [],
                        }
                    ]
                ),
                stderr="",
            ),
            # docker inspect xyz789
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "xyz789",
                            "Name": "/db",
                            "Config": {"Image": "postgres:15", "Labels": {}, "Env": []},
                            "State": {"Status": "running"},
                            "Mounts": [{"Type": "volume", "Name": "pgdata"}],
                        }
                    ]
                ),
                stderr="",
            ),
        ]

        containers = discovery._discover_containers()

        assert len(containers) == 2
        assert containers[0].name == "web"
        assert containers[0].database_type is None
        assert containers[1].name == "db"
        assert containers[1].database_type == "postgres"
        assert containers[1].volumes == ["pgdata"]

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_containers_empty_result(self, mock_run):
        """Should return empty list when no containers running."""
        discovery = make_discovery()
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        containers = discovery._discover_containers()

        assert containers == []

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_containers_handles_inspect_failure(self, mock_run):
        """Should skip containers that fail to inspect."""
        discovery = make_discovery()

        mock_run.side_effect = [
            CompletedProcess([], 0, stdout="abc123\nxyz789\n", stderr=""),
            # First inspect fails
            Exception("Container not found"),
            # Second inspect succeeds
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "xyz789",
                            "Name": "/db",
                            "Config": {"Image": "postgres:15", "Labels": {}, "Env": []},
                            "State": {"Status": "running"},
                            "Mounts": [],
                        }
                    ]
                ),
                stderr="",
            ),
        ]

        containers = discovery._discover_containers()

        assert len(containers) == 1
        assert containers[0].name == "db"


# =============================================================================
# Volume Discovery Tests
# =============================================================================


@pytest.mark.unit
class TestDiscoverVolumes:
    """Tests for _discover_volumes method."""

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_volumes_parses_output(self, mock_run):
        """Should discover volumes and parse inspect JSON."""
        discovery = make_discovery()

        mock_run.side_effect = [
            # docker volume ls
            CompletedProcess(
                [],
                0,
                stdout='{"Name": "pgdata"}\n{"Name": "appdata"}\n',
                stderr="",
            ),
            # docker volume inspect pgdata
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Name": "pgdata",
                            "Driver": "local",
                            "Mountpoint": "/var/lib/docker/volumes/pgdata/_data",
                            "Labels": {},
                        }
                    ]
                ),
                stderr="",
            ),
            # du -sb for pgdata
            CompletedProcess([], 0, stdout="1048576\t/var/lib/docker/volumes/pgdata/_data", stderr=""),
            # docker volume inspect appdata
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Name": "appdata",
                            "Driver": "local",
                            "Mountpoint": "/var/lib/docker/volumes/appdata/_data",
                            "Labels": {"backup": "true"},
                        }
                    ]
                ),
                stderr="",
            ),
            # du -sb for appdata
            CompletedProcess([], 0, stdout="2097152\t/var/lib/docker/volumes/appdata/_data", stderr=""),
        ]

        volumes = discovery._discover_volumes()

        assert len(volumes) == 2
        assert volumes[0].name == "pgdata"
        assert volumes[0].driver == "local"
        assert volumes[0].size_bytes == 1048576
        assert volumes[1].name == "appdata"
        assert volumes[1].labels == {"backup": "true"}
        assert volumes[1].size_bytes == 2097152

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_volumes_empty_result(self, mock_run):
        """Should return empty list when no volumes exist."""
        discovery = make_discovery()
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        volumes = discovery._discover_volumes()

        assert volumes == []


# =============================================================================
# Unit Grouping Tests
# =============================================================================


@pytest.mark.unit
class TestGroupIntoUnits:
    """Tests for _group_into_units method."""

    def test_group_compose_stack(self):
        """Containers with same compose project should be grouped into one unit."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="mystack_web_1",
                image="nginx:latest",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "mystack"},
            ),
            ContainerInfo(
                id="c2",
                name="mystack_db_1",
                image="postgres:15",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "mystack"},
                database_type="postgres",
                volumes=["pgdata"],
            ),
        ]
        volumes = [
            VolumeInfo(
                name="pgdata",
                driver="local",
                mountpoint="/var/lib/docker/volumes/pgdata/_data",
            )
        ]

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 1
        assert units[0].name == "mystack"
        assert units[0].type == "stack"
        assert len(units[0].containers) == 2
        assert len(units[0].volumes) == 1
        assert units[0].volumes[0].name == "pgdata"

    def test_group_standalone_container(self):
        """Container without compose label should be standalone unit."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="lonely_nginx",
                image="nginx:latest",
                status="running",
                labels={},
                volumes=["webdata"],
            )
        ]
        volumes = [
            VolumeInfo(
                name="webdata",
                driver="local",
                mountpoint="/var/lib/docker/volumes/webdata/_data",
            )
        ]

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 1
        assert units[0].name == "lonely_nginx"
        assert units[0].type == "standalone"
        assert len(units[0].containers) == 1
        assert len(units[0].volumes) == 1

    def test_group_mixed_compose_and_standalone(self):
        """Mixed containers should create separate units."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="app_web_1",
                image="nginx:latest",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "app"},
            ),
            ContainerInfo(
                id="c2",
                name="standalone_redis",
                image="redis:7",
                status="running",
                labels={},
                database_type="redis",
            ),
        ]
        volumes = []

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 2
        # DB units come first
        assert units[0].name == "standalone_redis"
        assert units[0].type == "standalone"
        assert units[1].name == "app"
        assert units[1].type == "stack"

    def test_group_sorts_databases_first(self):
        """Units with databases should be sorted before non-database units."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="app",
                image="nginx:latest",
                status="running",
                labels={},
            ),
            ContainerInfo(
                id="c2",
                name="cache",
                image="redis:7",
                status="running",
                labels={},
                database_type="redis",
            ),
            ContainerInfo(
                id="c3",
                name="db",
                image="postgres:15",
                status="running",
                labels={},
                database_type="postgres",
            ),
        ]
        volumes = []

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 3
        # Database containers should come first (sorted alphabetically among DBs)
        assert units[0].has_databases is True
        assert units[1].has_databases is True
        # Non-database last
        assert units[2].name == "app"
        assert units[2].has_databases is False

    def test_group_volume_container_mapping(self):
        """Volumes should have container_ids populated correctly."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="mystack_web_1",
                image="nginx:latest",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "mystack"},
                volumes=["shared_data"],
            ),
            ContainerInfo(
                id="c2",
                name="mystack_worker_1",
                image="python:3.12",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "mystack"},
                volumes=["shared_data"],  # Same volume
            ),
        ]
        volumes = [
            VolumeInfo(
                name="shared_data",
                driver="local",
                mountpoint="/var/lib/docker/volumes/shared_data/_data",
            )
        ]

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 1
        assert len(units[0].volumes) == 1
        # Both containers use this volume
        assert set(units[0].volumes[0].container_ids) == {"c1", "c2"}

    def test_group_compose_files_from_container(self):
        """Compose files should be extracted from container labels."""
        discovery = make_discovery()

        containers = [
            ContainerInfo(
                id="c1",
                name="mystack_web_1",
                image="nginx:latest",
                status="running",
                labels={DOCKER_COMPOSE_PROJECT_LABEL: "mystack"},
                compose_files=[Path("/app/docker-compose.yml")],
            )
        ]
        volumes = []

        units = discovery._group_into_units(containers, volumes)

        assert len(units) == 1
        assert units[0].compose_files == [Path("/app/docker-compose.yml")]


# =============================================================================
# Full Discovery Flow Tests
# =============================================================================


@pytest.mark.unit
class TestDiscoverBackupUnits:
    """Tests for the full discover_backup_units flow."""

    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_discover_backup_units_full_flow(self, mock_run):
        """Full discovery should return correctly grouped BackupUnits."""
        discovery = make_discovery()

        # Setup mock responses
        mock_run.side_effect = [
            # docker ps -q
            CompletedProcess([], 0, stdout="c1\nc2\n", stderr=""),
            # docker inspect c1
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "c1",
                            "Name": "/myapp_web_1",
                            "Config": {
                                "Image": "nginx:latest",
                                "Labels": {DOCKER_COMPOSE_PROJECT_LABEL: "myapp"},
                                "Env": [],
                            },
                            "State": {"Status": "running"},
                            "Mounts": [{"Type": "volume", "Name": "webdata"}],
                        }
                    ]
                ),
                stderr="",
            ),
            # docker inspect c2
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": "c2",
                            "Name": "/myapp_db_1",
                            "Config": {
                                "Image": "postgres:15",
                                "Labels": {DOCKER_COMPOSE_PROJECT_LABEL: "myapp"},
                                "Env": [],
                            },
                            "State": {"Status": "running"},
                            "Mounts": [{"Type": "volume", "Name": "pgdata"}],
                        }
                    ]
                ),
                stderr="",
            ),
            # docker volume ls
            CompletedProcess(
                [],
                0,
                stdout='{"Name": "webdata"}\n{"Name": "pgdata"}\n',
                stderr="",
            ),
            # docker volume inspect webdata
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Name": "webdata",
                            "Driver": "local",
                            "Mountpoint": "/var/lib/docker/volumes/webdata/_data",
                            "Labels": {},
                        }
                    ]
                ),
                stderr="",
            ),
            # du for webdata
            CompletedProcess([], 0, stdout="1024\t/path", stderr=""),
            # docker volume inspect pgdata
            CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    [
                        {
                            "Name": "pgdata",
                            "Driver": "local",
                            "Mountpoint": "/var/lib/docker/volumes/pgdata/_data",
                            "Labels": {},
                        }
                    ]
                ),
                stderr="",
            ),
            # du for pgdata
            CompletedProcess([], 0, stdout="2048\t/path", stderr=""),
        ]

        units = discovery.discover_backup_units()

        assert len(units) == 1
        assert units[0].name == "myapp"
        assert units[0].type == "stack"
        assert len(units[0].containers) == 2
        assert len(units[0].volumes) == 2
        assert units[0].has_databases is True
