"""Unit tests for the Plan 0028 Phase 2 source-collection helpers.

These tests pin the discovery side of the backup pipeline:
``_collect_recipe_sources``, ``_collect_network_sources``,
``_collect_docker_config_sources``, ``_collect_volume_sources``,
and the aggregate ``_collect_backup_sources``. They verify the
*shape* of the returned BackupSource objects (path, kind, tag set)
without mocking Kopia — the snapshot loop is exercised elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.helpers.constants import (
    BACKUP_SCOPE_FULL,
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
)
from kopi_docka.types import BackupSource, BackupUnit, ContainerInfo, VolumeInfo


def _make_manager(tmp_path: Path) -> BackupManager:
    bm = BackupManager.__new__(BackupManager)
    bm.config = Mock()
    bm.config.getint.side_effect = lambda section, key, default: default
    bm.config.getlist.return_value = []
    bm.config.backup_base_path = tmp_path / "kopi-docka"
    bm.repo = Mock()
    bm.policy_manager = Mock()
    bm.hooks_manager = Mock()
    bm.exclude_patterns = []
    bm.max_workers = 2
    return bm


def _unit(tmp_path: Path, *, with_compose: bool = True, volumes: int = 1) -> BackupUnit:
    compose_files = []
    if with_compose:
        compose_dir = tmp_path / "project"
        compose_dir.mkdir()
        cf = compose_dir / "docker-compose.yml"
        cf.write_text("services: {}\n")
        (compose_dir / ".env").write_text("FOO=bar\n")
        compose_files.append(cf)

    vol_list = [
        VolumeInfo(
            name=f"vol{i}",
            driver="local",
            mountpoint=f"/var/lib/docker/volumes/u1_vol{i}/_data",
            size_bytes=1024 * (i + 1),
        )
        for i in range(volumes)
    ]
    return BackupUnit(
        name="u1",
        type="stack",
        containers=[
            ContainerInfo(
                id="c1",
                name="u1_svc",
                image="nginx:latest",
                status="running",
                database_type=None,
                inspect_data={
                    "NetworkSettings": {"Networks": {"u1_net": {}, "bridge": {}}}
                },
            )
        ],
        volumes=vol_list,
        compose_files=compose_files,
    )


# ---------------------------------------------------------------------------
# Volume sources — direct mode only, mountpoint + tags verbatim
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectVolumeSources:
    def test_emits_one_source_per_volume_in_direct_mode(self, tmp_path):
        bm = _make_manager(tmp_path)
        unit = _unit(tmp_path, with_compose=False, volumes=3)

        sources = bm._collect_volume_sources(unit, "bk-1", BACKUP_SCOPE_STANDARD)

        assert [s.kind for s in sources] == ["volume", "volume", "volume"]
        paths = [s.path for s in sources]
        assert paths == [
            "/var/lib/docker/volumes/u1_vol0/_data",
            "/var/lib/docker/volumes/u1_vol1/_data",
            "/var/lib/docker/volumes/u1_vol2/_data",
        ]

    def test_volume_tags_include_unit_volume_backup_id_format(self, tmp_path):
        bm = _make_manager(tmp_path)
        unit = _unit(tmp_path, with_compose=False, volumes=1)

        [src] = bm._collect_volume_sources(unit, "bk-42", BACKUP_SCOPE_STANDARD)

        assert src.tags["type"] == "volume"
        assert src.tags["unit"] == "u1"
        assert src.tags["volume"] == "vol0"
        assert src.tags["backup_id"] == "bk-42"
        assert src.tags["backup_format"] == "direct"
        assert src.tags["size_bytes"] == "1024"

    def test_emits_nothing_in_tar_mode(self, tmp_path):
        """TAR mode is excluded because its snapshot path is a stdin stream,
        not a filesystem path BackupSource can describe."""
        bm = _make_manager(tmp_path)
        unit = _unit(tmp_path, with_compose=False, volumes=2)

        with patch(
            "kopi_docka.helpers.constants.BACKUP_FORMAT_DEFAULT", "tar"
        ):
            sources = bm._collect_volume_sources(unit, "bk-1", BACKUP_SCOPE_STANDARD)

        assert sources == []


# ---------------------------------------------------------------------------
# Recipe sources — exercise the real filesystem staging logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectRecipeSources:
    def test_collects_compose_file_and_emits_one_source(self, tmp_path, monkeypatch):
        bm = _make_manager(tmp_path)
        # Redirect STAGING_BASE_DIR to a writable scratch path
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )

        unit = _unit(tmp_path)

        fake_inspect = json.dumps([{"Config": {"Env": ["FOO=bar"]}}])
        with patch(
            "kopi_docka.cores.backup_manager.run_command",
            return_value=Mock(stdout=fake_inspect),
        ):
            [src] = bm._collect_recipe_sources(unit, "bk-7", BACKUP_SCOPE_STANDARD)

        assert src.kind == "recipe"
        assert src.path.endswith("staging/recipes/u1")
        assert src.tags["type"] == "recipe"
        assert src.tags["unit"] == "u1"
        assert src.tags["backup_id"] == "bk-7"
        # Compose file was staged
        assert (Path(src.path) / "docker-compose.yml").exists()
        # Env file copied into project-files
        assert (Path(src.path) / "project-files" / ".env").exists()

    def test_sensitive_env_vars_are_redacted_in_inspect(self, tmp_path, monkeypatch):
        bm = _make_manager(tmp_path)
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )

        unit = _unit(tmp_path)

        fake_inspect = json.dumps(
            [{"Config": {"Env": ["DB_PASSWORD=hunter2", "PUBLIC=visible"]}}]
        )
        with patch(
            "kopi_docka.cores.backup_manager.run_command",
            return_value=Mock(stdout=fake_inspect),
        ):
            [src] = bm._collect_recipe_sources(unit, "bk-7", BACKUP_SCOPE_STANDARD)

        inspect_file = Path(src.path) / "u1_svc_inspect.json"
        assert inspect_file.exists()
        env = json.loads(inspect_file.read_text())[0]["Config"]["Env"]
        assert "DB_PASSWORD=***REDACTED***" in env
        assert "PUBLIC=visible" in env


# ---------------------------------------------------------------------------
# Network sources
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectNetworkSources:
    def test_only_custom_networks_are_staged(self, tmp_path, monkeypatch):
        bm = _make_manager(tmp_path)
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )

        unit = _unit(tmp_path, with_compose=False)

        net_inspect = json.dumps([{"Name": "u1_net", "Driver": "bridge"}])
        with patch(
            "kopi_docka.cores.backup_manager.run_command",
            return_value=Mock(stdout=net_inspect),
        ):
            [src] = bm._collect_network_sources(unit, "bk-9", BACKUP_SCOPE_STANDARD)

        assert src.kind == "network"
        assert src.tags["network_count"] == "1"
        # The default `bridge` network is filtered out — only u1_net staged
        networks = json.loads((Path(src.path) / "networks.json").read_text())
        assert {n["Name"] for n in networks} == {"u1_net"}

    def test_unit_without_custom_networks_emits_empty_list(self, tmp_path):
        bm = _make_manager(tmp_path)

        # Container only has default `bridge` network
        unit = BackupUnit(
            name="u2",
            type="stack",
            containers=[
                ContainerInfo(
                    id="c",
                    name="c",
                    image="nginx",
                    status="running",
                    database_type=None,
                    inspect_data={"NetworkSettings": {"Networks": {"bridge": {}}}},
                )
            ],
            volumes=[],
            compose_files=[],
        )

        sources = bm._collect_network_sources(unit, "bk-1", BACKUP_SCOPE_STANDARD)
        assert sources == []


# ---------------------------------------------------------------------------
# Docker config sources
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectDockerConfigSources:
    def test_returns_empty_when_no_docker_config_present(self, tmp_path, monkeypatch):
        bm = _make_manager(tmp_path)
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )
        # Force /etc/docker/daemon.json + systemd overrides to "not exist"
        original_exists = Path.exists

        def fake_exists(self):
            if str(self).startswith("/etc/docker") or str(self).startswith(
                "/etc/systemd"
            ):
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)

        sources = bm._collect_docker_config_sources(
            _unit(tmp_path, with_compose=False), "bk-1", BACKUP_SCOPE_FULL
        )
        assert sources == []


# ---------------------------------------------------------------------------
# Aggregate collector — order + scope gating
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectBackupSources:
    """The aggregate must produce sources in this order:
    recipes → networks → docker_config → volumes
    and gate the staging-dir sources on backup_scope just like backup_unit does.
    """

    def test_minimal_scope_skips_recipes_and_networks(self, tmp_path):
        bm = _make_manager(tmp_path)
        unit = _unit(tmp_path, with_compose=False, volumes=2)

        sources = bm._collect_backup_sources(unit, "bk-1", BACKUP_SCOPE_MINIMAL)

        # Only volume sources for minimal scope
        assert [s.kind for s in sources] == ["volume", "volume"]

    def test_standard_scope_includes_recipes_networks_and_volumes(
        self, tmp_path, monkeypatch
    ):
        bm = _make_manager(tmp_path)
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )

        unit = _unit(tmp_path, volumes=1)

        with patch(
            "kopi_docka.cores.backup_manager.run_command",
            return_value=Mock(stdout=json.dumps([{"Name": "u1_net"}])),
        ):
            sources = bm._collect_backup_sources(
                unit, "bk-1", BACKUP_SCOPE_STANDARD
            )

        kinds = [s.kind for s in sources]
        # Order matters: recipes first, then networks, then volumes (no
        # docker_config in standard scope)
        assert kinds == ["recipe", "network", "volume"]
        assert "docker_config" not in kinds

    def test_full_scope_includes_docker_config_when_available(
        self, tmp_path, monkeypatch
    ):
        bm = _make_manager(tmp_path)
        monkeypatch.setattr(
            "kopi_docka.cores.backup_manager.STAGING_BASE_DIR",
            tmp_path / "staging",
        )

        # Fake an /etc/docker/daemon.json so docker_config staging fires
        fake_etc = tmp_path / "etc-docker"
        fake_etc.mkdir()
        (fake_etc / "daemon.json").write_text('{"log-driver":"json-file"}')

        original_exists = Path.exists
        original_is_file = Path.is_file
        original_copy2 = None

        def fake_exists(self):
            if str(self) == "/etc/docker/daemon.json":
                return True
            if str(self) == "/etc/systemd/system/docker.service.d":
                return False
            return original_exists(self)

        def fake_is_file(self):
            if str(self) == "/etc/docker/daemon.json":
                return True
            return original_is_file(self)

        import shutil as _shutil
        original_copy2 = _shutil.copy2

        def fake_copy2(src, dst, *args, **kwargs):
            if str(src) == "/etc/docker/daemon.json":
                return original_copy2(str(fake_etc / "daemon.json"), dst)
            return original_copy2(src, dst, *args, **kwargs)

        monkeypatch.setattr(Path, "exists", fake_exists)
        monkeypatch.setattr(Path, "is_file", fake_is_file)
        monkeypatch.setattr("shutil.copy2", fake_copy2)

        unit = _unit(tmp_path, volumes=1)

        with patch(
            "kopi_docka.cores.backup_manager.run_command",
            return_value=Mock(stdout=json.dumps([{"Name": "u1_net"}])),
        ):
            sources = bm._collect_backup_sources(unit, "bk-1", BACKUP_SCOPE_FULL)

        kinds = [s.kind for s in sources]
        assert kinds == ["recipe", "network", "docker_config", "volume"]

    def test_aggregate_returns_only_backup_source_instances(self, tmp_path):
        bm = _make_manager(tmp_path)
        unit = _unit(tmp_path, with_compose=False, volumes=1)

        sources = bm._collect_backup_sources(unit, "bk-1", BACKUP_SCOPE_MINIMAL)
        assert sources
        for s in sources:
            assert isinstance(s, BackupSource)
