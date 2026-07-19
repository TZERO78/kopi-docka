"""Unit tests for in-container → host compose path resolution (Plan 0042)."""

from pathlib import Path

import pytest

from kopi_docka.cores.docker_discovery import (
    DockerDiscovery,
    build_mount_index,
    resolve_container_path_to_host,
)
from kopi_docka.types import ContainerInfo


def _container(cid, name, mounts=None, labels=None, compose_files=None):
    return ContainerInfo(
        id=cid,
        name=name,
        image="img:latest",
        status="running",
        labels=labels or {},
        environment={},
        volumes=[],
        compose_files=compose_files or [],
        inspect_data={"Mounts": mounts or []},
    )


PORTAINER_MOUNT = {
    "Type": "volume",
    "Name": "portainer_portainer_data",
    "Source": "/var/lib/docker/volumes/portainer_portainer_data/_data",
    "Destination": "/data",
    "RW": True,
}


@pytest.mark.unit
class TestBuildMountIndex:
    def test_collects_volume_and_bind_sources(self):
        containers = [
            _container("p", "portainer", mounts=[PORTAINER_MOUNT]),
            _container("x", "app", mounts=[
                {"Type": "bind", "Source": "/opt/app", "Destination": "/cfg"},
            ]),
        ]
        idx = build_mount_index(containers)
        assert ("/data", "/var/lib/docker/volumes/portainer_portainer_data/_data") in idx
        assert ("/cfg", "/opt/app") in idx

    def test_sorted_longest_destination_first(self):
        containers = [_container("x", "app", mounts=[
            {"Type": "bind", "Source": "/a", "Destination": "/data"},
            {"Type": "bind", "Source": "/b", "Destination": "/data/inner"},
        ])]
        idx = build_mount_index(containers)
        assert idx[0][0] == "/data/inner"  # most specific first

    def test_skips_incomplete_mounts(self):
        containers = [_container("x", "app", mounts=[
            {"Type": "bind", "Source": "", "Destination": "/data"},
            {"Type": "volume", "Name": "v", "Destination": ""},
        ])]
        assert build_mount_index(containers) == []


@pytest.mark.unit
class TestResolvePath:
    def test_portainer_compose_resolves(self, monkeypatch):
        idx = build_mount_index([_container("p", "portainer", mounts=[PORTAINER_MOUNT])])
        target = "/var/lib/docker/volumes/portainer_portainer_data/_data/compose/6/docker-compose.yml"
        monkeypatch.setattr(Path, "exists", lambda self: str(self) == target)

        host = resolve_container_path_to_host(
            Path("/data/compose/6/docker-compose.yml"), idx
        )
        assert host == Path(target)

    def test_longest_prefix_wins(self, monkeypatch):
        idx = build_mount_index([_container("x", "app", mounts=[
            {"Type": "bind", "Source": "/outer", "Destination": "/data"},
            {"Type": "bind", "Source": "/inner", "Destination": "/data/compose"},
        ])])
        monkeypatch.setattr(Path, "exists", lambda self: True)
        host = resolve_container_path_to_host(Path("/data/compose/6/x.yml"), idx)
        assert host == Path("/inner/6/x.yml")

    def test_none_when_no_prefix(self, monkeypatch):
        idx = build_mount_index([_container("p", "portainer", mounts=[PORTAINER_MOUNT])])
        monkeypatch.setattr(Path, "exists", lambda self: True)
        assert resolve_container_path_to_host(Path("/other/x.yml"), idx) is None

    def test_none_when_translated_missing(self, monkeypatch):
        idx = build_mount_index([_container("p", "portainer", mounts=[PORTAINER_MOUNT])])
        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert resolve_container_path_to_host(
            Path("/data/compose/6/docker-compose.yml"), idx
        ) is None


@pytest.mark.unit
class TestDiscoveryIntegration:
    def _discovery(self):
        d = DockerDiscovery.__new__(DockerDiscovery)
        d.docker_socket = "/var/run/docker.sock"
        return d

    def test_rewrites_in_container_compose_path(self, monkeypatch):
        from kopi_docka.types import BackupUnit

        target = "/var/lib/docker/volumes/portainer_portainer_data/_data/compose/6/docker-compose.yml"
        monkeypatch.setattr(Path, "exists", lambda self: str(self) == target)

        portainer = _container("p", "portainer", mounts=[PORTAINER_MOUNT])
        n8n = _container("n", "n8n", compose_files=[Path("/data/compose/6/docker-compose.yml")])
        unit = BackupUnit(name="n8n", type="stack", containers=[n8n])
        unit.compose_files = [Path("/data/compose/6/docker-compose.yml")]

        self._discovery()._resolve_compose_paths([unit], [portainer, n8n])
        assert unit.compose_files == [Path(target)]

    def test_leaves_host_compose_path_untouched(self, monkeypatch):
        from kopi_docka.types import BackupUnit

        host_path = "/opt/docker/npm/docker-compose.yml"
        monkeypatch.setattr(Path, "exists", lambda self: str(self) == host_path)

        npm = _container("m", "npm", mounts=[
            {"Type": "bind", "Source": "/opt/docker/npm/data", "Destination": "/data"},
        ], compose_files=[Path(host_path)])
        unit = BackupUnit(name="npm", type="stack", containers=[npm])
        unit.compose_files = [Path(host_path)]

        self._discovery()._resolve_compose_paths([unit], [npm])
        assert unit.compose_files == [Path(host_path)]
