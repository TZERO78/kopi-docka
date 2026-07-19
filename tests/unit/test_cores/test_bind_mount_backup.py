"""
Unit tests for persistent bind-mount discovery and backup (Plan 0040 / #129).

Covers:
- BindMountInfo.is_runtime_only classification
- DockerDiscovery._parse_container_info bind-mount extraction + runtime skip
- DockerDiscovery._aggregate_bind_mounts dedup across containers
- DockerDiscovery._group_into_units attaches bind mounts to units
- DockerDiscovery._discover_containers includes stopped compose containers
- BackupManager._collect_bind_mount_sources emits correct BackupSources
- BackupManager._start_containers only restarts previously-running containers
"""

import pytest
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from kopi_docka.cores.docker_discovery import DockerDiscovery
from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.types import BindMountInfo, ContainerInfo, BackupUnit
from kopi_docka.helpers.constants import DOCKER_COMPOSE_PROJECT_LABEL


def make_discovery() -> DockerDiscovery:
    discovery = DockerDiscovery.__new__(DockerDiscovery)
    discovery.docker_socket = "/var/run/docker.sock"
    return discovery


def _container_inspect(cid, name, labels=None, mounts=None, status="running"):
    return {
        "Id": cid,
        "Name": f"/{name}",
        "Config": {"Image": "nginx:latest", "Labels": labels or {}, "Env": []},
        "State": {"Status": status},
        "Mounts": mounts or [],
    }


# =============================================================================
# Runtime-only classification
# =============================================================================


@pytest.mark.unit
class TestBindMountClassification:
    @pytest.mark.parametrize(
        "source",
        [
            "/var/run/docker.sock",
            "/run/docker.sock",
            "/proc",
            "/proc/sys",
            "/sys/fs/cgroup",
            "/dev",
            "/dev/net/tun",
            "/run",
            "/run/systemd",
            "/var/run",
            "/var/run/dbus",
        ],
    )
    def test_runtime_only_sources(self, source):
        assert BindMountInfo(source=source, destination="/x").is_runtime_only is True

    @pytest.mark.parametrize(
        "source",
        [
            "/home/user/vw-data",
            "/opt/app/config",
            "/etc/myapp/app.conf",
            "/srv/data",
            "/devops/data",  # must NOT match /dev prefix
            "/procurement",  # must NOT match /proc prefix
        ],
    )
    def test_persistent_sources(self, source):
        assert BindMountInfo(source=source, destination="/x").is_runtime_only is False


# =============================================================================
# Bind-mount parsing in _parse_container_info
# =============================================================================


@pytest.mark.unit
class TestParseBindMounts:
    def test_extracts_persistent_bind_and_skips_runtime(self):
        discovery = make_discovery()
        data = _container_inspect(
            "c1",
            "vaultwarden",
            mounts=[
                {"Type": "bind", "Source": "/home/u/vw-data", "Destination": "/data", "RW": True},
                {"Type": "bind", "Source": "/var/run/docker.sock",
                 "Destination": "/var/run/docker.sock", "RW": False},
                {"Type": "volume", "Name": "pgdata", "Destination": "/db"},
            ],
        )

        info = discovery._parse_container_info(data)

        assert info.volumes == ["pgdata"]
        assert len(info.bind_mounts) == 1
        bind = info.bind_mounts[0]
        assert bind.source == "/home/u/vw-data"
        assert bind.destination == "/data"
        assert bind.read_only is False
        assert bind.container_ids == ["c1"]

    def test_read_only_flag_from_rw_false(self):
        discovery = make_discovery()
        data = _container_inspect(
            "c1", "app",
            mounts=[{"Type": "bind", "Source": "/etc/app", "Destination": "/etc/app", "RW": False}],
        )
        info = discovery._parse_container_info(data)
        assert info.bind_mounts[0].read_only is True


# =============================================================================
# Aggregation across containers
# =============================================================================


@pytest.mark.unit
class TestAggregateBindMounts:
    def test_dedupes_same_source_and_merges_container_ids(self):
        discovery = make_discovery()
        discovery._estimate_volume_size = Mock(return_value=42)

        c1 = ContainerInfo(
            id="c1", name="a", image="i", status="running",
            bind_mounts=[BindMountInfo(source="/shared", destination="/s", read_only=False,
                                       container_ids=["c1"])],
        )
        c2 = ContainerInfo(
            id="c2", name="b", image="i", status="running",
            bind_mounts=[BindMountInfo(source="/shared", destination="/s", read_only=True,
                                       container_ids=["c2"])],
        )

        binds = discovery._aggregate_bind_mounts([c1, c2])

        assert len(binds) == 1
        assert binds[0].source == "/shared"
        assert sorted(binds[0].container_ids) == ["c1", "c2"]
        # read-only only if ALL bindings are read-only → here one is RW
        assert binds[0].read_only is False
        assert binds[0].size_bytes == 42

    def test_read_only_when_all_readonly(self):
        discovery = make_discovery()
        discovery._estimate_volume_size = Mock(return_value=None)
        c1 = ContainerInfo(
            id="c1", name="a", image="i", status="running",
            bind_mounts=[BindMountInfo(source="/ro", destination="/s", read_only=True,
                                       container_ids=["c1"])],
        )
        binds = discovery._aggregate_bind_mounts([c1])
        assert binds[0].read_only is True


# =============================================================================
# Grouping attaches bind mounts to units
# =============================================================================


@pytest.mark.unit
class TestGroupingBindMounts:
    def test_stack_unit_gets_bind_mounts(self):
        discovery = make_discovery()
        discovery._estimate_volume_size = Mock(return_value=100)

        c = ContainerInfo(
            id="c1", name="vw", image="vaultwarden", status="running",
            labels={DOCKER_COMPOSE_PROJECT_LABEL: "vault"},
            bind_mounts=[BindMountInfo(source="/opt/vw-data", destination="/data",
                                       container_ids=["c1"])],
        )
        units = discovery._group_into_units([c], [])
        assert len(units) == 1
        assert len(units[0].bind_mounts) == 1
        assert units[0].bind_mounts[0].source == "/opt/vw-data"

    def test_standalone_unit_gets_bind_mounts(self):
        discovery = make_discovery()
        discovery._estimate_volume_size = Mock(return_value=None)
        c = ContainerInfo(
            id="c1", name="solo", image="nginx", status="running",
            bind_mounts=[BindMountInfo(source="/srv/solo", destination="/usr/share/nginx/html",
                                       container_ids=["c1"])],
        )
        units = discovery._group_into_units([c], [])
        assert units[0].type == "standalone"
        assert units[0].bind_mounts[0].source == "/srv/solo"


# =============================================================================
# Stopped compose container discovery
# =============================================================================


@pytest.mark.unit
class TestStoppedContainerDiscovery:
    @patch("kopi_docka.cores.docker_discovery.run_command")
    def test_includes_stopped_compose_container(self, mock_run):
        discovery = make_discovery()
        import json

        mock_run.side_effect = [
            CompletedProcess([], 0, stdout="run1\n", stderr=""),  # ps -q (running)
            CompletedProcess([], 0, stdout="run1\nstop1\n", stderr=""),  # ps -aq --filter
            # inspect run1 (running, compose)
            CompletedProcess([], 0, stdout=json.dumps([_container_inspect(
                "run1", "app_web", labels={DOCKER_COMPOSE_PROJECT_LABEL: "app"})]), stderr=""),
            # inspect stop1 (stopped, compose)
            CompletedProcess([], 0, stdout=json.dumps([_container_inspect(
                "stop1", "app_worker", labels={DOCKER_COMPOSE_PROJECT_LABEL: "app"},
                status="exited")]), stderr=""),
        ]

        containers = discovery._discover_containers()

        ids = {c.id for c in containers}
        assert ids == {"run1", "stop1"}
        stopped = next(c for c in containers if c.id == "stop1")
        assert stopped.is_running is False


# =============================================================================
# BackupManager: bind-mount sources + start-skip
# =============================================================================


def make_backup_manager() -> BackupManager:
    manager = BackupManager.__new__(BackupManager)
    manager.config = Mock()
    manager.repo = Mock()
    manager.stop_timeout = 30
    manager.start_timeout = 60
    manager.exclude_patterns = []
    return manager


@pytest.mark.unit
class TestCollectBindMountSources:
    def test_emits_source_per_bind_with_tags(self):
        manager = make_backup_manager()
        unit = BackupUnit(
            name="vault", type="stack",
            bind_mounts=[
                BindMountInfo(source="/opt/vw-data", destination="/data", read_only=False,
                              container_ids=["c1"], size_bytes=2048),
            ],
        )

        sources = manager._collect_bind_mount_sources(unit, "bid-1", "standard")

        assert len(sources) == 1
        src = sources[0]
        assert src.path == "/opt/vw-data"
        assert src.kind == "bind"
        assert src.tags["bind_source"] == "/opt/vw-data"
        assert src.tags["bind_destination"] == "/data"
        assert src.tags["read_only"] == "false"
        assert src.tags["backup_id"] == "bid-1"
        assert src.tags["size_bytes"] == "2048"

    def test_included_in_collect_backup_sources(self):
        from kopi_docka.helpers.constants import BACKUP_SCOPE_MINIMAL

        manager = make_backup_manager()
        manager._collect_recipe_sources = Mock(return_value=[])
        unit = BackupUnit(
            name="vault", type="stack",
            bind_mounts=[BindMountInfo(source="/opt/vw-data", destination="/data",
                                       container_ids=["c1"])],
        )
        # MINIMAL scope skips recipes/networks/config; volumes empty → only binds
        sources = manager._collect_backup_sources(unit, "bid", BACKUP_SCOPE_MINIMAL)
        kinds = [s.kind for s in sources]
        assert "bind" in kinds


@pytest.mark.unit
class TestExcludePatterns:
    def test_bind_sources_carry_exclude_patterns(self):
        manager = make_backup_manager()
        manager.exclude_patterns = ["*.log", "cache/*"]
        unit = BackupUnit(
            name="vault", type="stack",
            bind_mounts=[BindMountInfo(source="/opt/vw", destination="/data",
                                       container_ids=["c1"])],
        )
        sources = manager._collect_bind_mount_sources(unit, "bid", "standard")
        assert sources[0].exclude_patterns == ["*.log", "cache/*"]

    def test_empty_exclude_patterns_become_none(self):
        manager = make_backup_manager()
        manager.exclude_patterns = []
        unit = BackupUnit(
            name="vault", type="stack",
            bind_mounts=[BindMountInfo(source="/opt/vw", destination="/data",
                                       container_ids=["c1"])],
        )
        sources = manager._collect_bind_mount_sources(unit, "bid", "standard")
        assert sources[0].exclude_patterns is None

    def test_create_snapshots_forwards_exclude_patterns(self):
        from kopi_docka.cores.repository_manager import KopiaRepository
        from kopi_docka.types import BackupSource

        repo = KopiaRepository.__new__(KopiaRepository)
        repo.create_snapshot = Mock(return_value="snap1")
        src = BackupSource(path="/opt/vw", kind="bind", tags={"type": "bind"},
                           exclude_patterns=["*.log"])

        repo.create_snapshots([src])

        repo.create_snapshot.assert_called_once()
        assert repo.create_snapshot.call_args.kwargs["exclude_patterns"] == ["*.log"]


@pytest.mark.unit
class TestStartContainersSkipsStopped:
    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_does_not_start_previously_stopped_containers(self, mock_run):
        manager = make_backup_manager()
        service_handler = Mock()

        running = ContainerInfo(id="r1", name="web", image="nginx", status="running")
        stopped = ContainerInfo(id="s1", name="worker", image="nginx", status="exited")

        with patch.object(manager, "_wait_container_healthy"):
            manager._start_containers([running, stopped], service_handler)

        started_ids = [call.args[0][2] for call in mock_run.call_args_list
                       if call.args[0][:2] == ["docker", "start"]]
        assert started_ids == ["r1"]
