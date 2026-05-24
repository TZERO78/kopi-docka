"""End-to-end workflow tests for backup operations.

Plan 0028 Phase 3 reshaped the inner loop: ``backup_unit`` now collects all
backup sources up front (``_collect_backup_sources``) and feeds them to
``KopiaRepository.create_snapshots`` sequentially. These tests verify the
*workflow* — hooks, container stop/start, source ordering, error handling,
DR bundle gating — against that new flow, with the snapshot loop itself
mocked at the ``repo.create_snapshots`` boundary.
"""

from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import Mock, patch

import pytest

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.cores.backup_volume_handler import BackupVolumeHandler
from kopi_docka.helpers.constants import (
    BACKUP_SCOPE_FULL,
    BACKUP_SCOPE_MINIMAL,
    BACKUP_SCOPE_STANDARD,
)
from kopi_docka.types import BackupSource, BackupUnit


def make_mock_config(tmp_path) -> Mock:
    config = Mock()
    config.parallel_workers = 2
    config.getint.return_value = 30
    config.getlist.return_value = []
    config.getboolean.return_value = False
    config.backup_base_path = tmp_path / "kopi-docka-test"
    return config


def make_backup_manager(tmp_path) -> BackupManager:
    manager = BackupManager.__new__(BackupManager)
    manager.config = make_mock_config(tmp_path)
    manager.repo = Mock()
    manager.repo.create_snapshot.return_value = "snap123"
    manager.repo.create_snapshots.return_value = []
    manager.policy_manager = Mock()
    manager.hooks_manager = Mock()
    manager.hooks_manager.execute_pre_backup.return_value = True
    manager.hooks_manager.execute_post_backup.return_value = True
    manager.hooks_manager.get_executed_hooks.return_value = []
    manager.stop_timeout = 30
    manager.start_timeout = 60
    manager.exclude_patterns = []
    manager.volume_handler = BackupVolumeHandler(manager.repo, manager.exclude_patterns)
    manager._collect_backup_sources = Mock(return_value=[])
    return manager


def _make_volume_sources(unit: BackupUnit, backup_id: str) -> list[BackupSource]:
    """Build the BackupSource list Plan 0028 _collect_volume_sources would
    emit in DIRECT mode for the given unit. Helper used to wire up
    _collect_backup_sources mocks without dragging in the staging-dir code.
    """
    return [
        BackupSource(
            path=v.mountpoint,
            kind="volume",
            tags={
                "type": "volume",
                "unit": unit.name,
                "volume": v.name,
                "backup_id": backup_id,
                "backup_format": "direct",
            },
        )
        for v in unit.volumes
    ]


def _wire_snapshot_loop(
    manager: BackupManager,
    unit: BackupUnit,
    *,
    snapshot_id_for=lambda src: f"snap_{src.tags.get('volume', src.kind)}",
    side_effect_for=None,
):
    """Make _collect_backup_sources emit one volume source per unit volume and
    have create_snapshots produce one snapshot ID per source. Optional
    ``side_effect_for(src)`` lets a test raise for a specific source.
    """

    def fake_collect(unit_arg, backup_id, scope):
        return _make_volume_sources(unit_arg, backup_id)

    manager._collect_backup_sources = Mock(side_effect=fake_collect)

    def fake_create_snapshots(sources):
        ids: list[str] = []
        for src in sources:
            if side_effect_for is not None:
                try:
                    result = side_effect_for(src)
                except Exception:
                    ids.append("")
                    continue
                ids.append(result if result else "")
            else:
                ids.append(snapshot_id_for(src))
        return ids

    manager.repo.create_snapshots.side_effect = fake_create_snapshots


@pytest.mark.unit
class TestBackupWorkflow:
    """End-to-end backup workflow against the Plan 0028 sequential flow."""

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_complete_backup_flow_success(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """Full backup flow: hooks → discovery → stop → snapshot → start → metadata."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(name="teststack", containers=2, volumes=2)
        _wire_snapshot_loop(manager, unit)

        call_order: list[str] = []

        manager.hooks_manager.execute_pre_backup.side_effect = (
            lambda x: (call_order.append("pre_hook"), True)[1]
        )
        manager.hooks_manager.execute_post_backup.side_effect = (
            lambda x: (call_order.append("post_hook"), True)[1]
        )

        def track_stop(containers, service_handler):
            call_order.append("stop")

        def track_start(containers, service_handler):
            call_order.append("start")

        original_create = manager.repo.create_snapshots.side_effect

        def tracking_create(sources):
            call_order.append("snapshot")
            return original_create(sources)

        manager.repo.create_snapshots.side_effect = tracking_create

        with patch.object(manager, "_stop_containers", side_effect=track_stop):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert call_order == ["pre_hook", "stop", "snapshot", "start", "post_hook"]
        assert metadata.success is True
        assert metadata.unit_name == "teststack"
        assert metadata.backup_id is not None
        assert metadata.volumes_backed_up == 2
        assert metadata.errors == []
        assert metadata.backup_scope == BACKUP_SCOPE_MINIMAL

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_pre_hook_failure_aborts_before_discovery(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()

        with patch.object(manager, "_stop_containers") as mock_stop:
            with patch.object(manager, "_start_containers") as mock_start:
                manager.hooks_manager.execute_pre_backup.return_value = False
                metadata = manager.backup_unit(unit)

        mock_stop.assert_not_called()
        mock_start.assert_not_called()
        manager._collect_backup_sources.assert_not_called()
        manager.repo.create_snapshots.assert_not_called()
        assert metadata.success is False
        assert any("Pre-backup hook failed" in e for e in metadata.errors)
        assert metadata.volumes_backed_up == 0

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_container_stop_failure_still_runs_snapshots(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        from kopi_docka.helpers.ui_utils import SubprocessError

        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)
        _wire_snapshot_loop(manager, unit)
        mock_run.side_effect = SubprocessError(
            "docker stop failed", "", "Container not found"
        )

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_start_containers", side_effect=track_start):
            with patch.object(manager, "_save_metadata"):
                metadata = manager.backup_unit(
                    unit, backup_scope=BACKUP_SCOPE_MINIMAL
                )

        assert start_called is True
        assert metadata.volumes_backed_up == 1

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_volume_backup_partial_failure(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """One source raises in create_snapshots → empty string for that index;
        backup_unit records the per-source error and continues."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=3)

        def side(src):
            if src.tags["volume"] == unit.volumes[1].name:
                raise RuntimeError("Volume 2 backup failed")
            return f"snap_{src.tags['volume']}"

        _wire_snapshot_loop(manager, unit, side_effect_for=side)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert metadata.volumes_backed_up == 2
        assert len(metadata.errors) == 1
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_container_start_failure_does_not_corrupt_backup_success(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        from kopi_docka.helpers.ui_utils import SubprocessError

        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)
        _wire_snapshot_loop(manager, unit)

        def run_cmd_side_effect(cmd, *args, **kwargs):
            if "start" in cmd:
                raise SubprocessError("docker start failed", "", "Error starting")
            return CompletedProcess([], 0, stdout="", stderr="")

        mock_run.side_effect = run_cmd_side_effect

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_save_metadata"):
                metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.volumes_backed_up == 1
        assert metadata.success is True  # Start failure logged, not in errors

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_backup_id_consistent_across_snapshots(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=3)
        _wire_snapshot_loop(manager, unit)

        seen_backup_ids: set[str] = set()
        original_create = manager.repo.create_snapshots.side_effect

        def capture_create(sources):
            for src in sources:
                seen_backup_ids.add(src.tags["backup_id"])
            return original_create(sources)

        manager.repo.create_snapshots.side_effect = capture_create

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert seen_backup_ids == {metadata.backup_id}

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_empty_unit_no_snapshots_no_errors(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = BackupUnit(
            name="empty-unit", type="standalone",
            containers=[], volumes=[], compose_files=[],
        )

        with patch.object(manager, "_save_metadata"):
            metadata = manager.backup_unit(unit, backup_scope=BACKUP_SCOPE_MINIMAL)

        assert metadata.success is True
        assert metadata.volumes_backed_up == 0
        assert metadata.errors == []
        manager._collect_backup_sources.assert_called_once()

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_collect_backup_sources_drives_what_gets_snapshotted(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """The set of sources from ``_collect_backup_sources`` is the source
        of truth — backup_unit must not derive sources from anywhere else."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=3)

        only_first = [
            BackupSource(
                path=unit.volumes[0].mountpoint,
                kind="volume",
                tags={"unit": unit.name, "volume": unit.volumes[0].name,
                      "backup_id": "ignored", "backup_format": "direct",
                      "type": "volume"},
            )
        ]
        manager._collect_backup_sources = Mock(return_value=only_first)
        manager.repo.create_snapshots.return_value = ["snap-only"]

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert metadata.volumes_backed_up == 1
        assert metadata.kopia_snapshot_ids == ["snap-only"]

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_post_hook_failure_recorded_but_backup_completes(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.execute_post_backup.return_value = False
        unit = backup_unit_factory()
        _wire_snapshot_loop(manager, unit)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert metadata.volumes_backed_up == 1
        assert any("Post-backup hook failed" in e for e in metadata.errors)
        assert metadata.success is False

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_snapshot_exception_still_restarts_containers(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """A blow-up inside create_snapshots must not skip the finally branch
        that restarts containers — leaving them stopped is the worst outcome."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(containers=2)
        manager._collect_backup_sources = Mock(
            side_effect=lambda u, bid, scope: _make_volume_sources(u, bid)
        )
        manager.repo.create_snapshots.side_effect = RuntimeError("Catastrophic")

        start_called = False

        def track_start(containers, service_handler):
            nonlocal start_called
            start_called = True

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers", side_effect=track_start):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert start_called is True
        assert metadata.success is False
        assert metadata.errors

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_metadata_is_persisted(self, mock_run, backup_unit_factory, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()
        _wire_snapshot_loop(manager, unit)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata") as mock_save:
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert saved.unit_name == unit.name
        assert saved.backup_id == metadata.backup_id

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_executed_hooks_tracked_in_metadata(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.get_executed_hooks.return_value = [
            "pre-backup: /scripts/pre.sh",
            "post-backup: /scripts/post.sh",
        ]
        unit = backup_unit_factory()
        _wire_snapshot_loop(manager, unit)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert metadata.hooks_executed == [
            "pre-backup: /scripts/pre.sh",
            "post-backup: /scripts/post.sh",
        ]

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_volumes_are_snapshotted_in_a_single_create_snapshots_call(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        """Plan 0028 collapses the per-volume ThreadPool into a single
        sequential create_snapshots(sources) call."""
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory(volumes=4)
        _wire_snapshot_loop(manager, unit)

        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    metadata = manager.backup_unit(
                        unit, backup_scope=BACKUP_SCOPE_MINIMAL
                    )

        assert manager.repo.create_snapshots.call_count == 1
        sources_passed = manager.repo.create_snapshots.call_args[0][0]
        assert [s.tags["volume"] for s in sources_passed] == [
            v.name for v in unit.volumes
        ]
        assert metadata.volumes_backed_up == 4

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_dr_bundle_updated_on_success(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        unit = backup_unit_factory()
        _wire_snapshot_loop(manager, unit)

        mock_dr_manager = Mock()
        with patch.object(manager, "_stop_containers"):
            with patch.object(manager, "_start_containers"):
                with patch.object(manager, "_save_metadata"):
                    with patch(
                        "kopi_docka.cores.disaster_recovery_manager.DisasterRecoveryManager",
                        return_value=mock_dr_manager,
                    ):
                        manager.backup_unit(
                            unit,
                            backup_scope=BACKUP_SCOPE_MINIMAL,
                            update_recovery_bundle=True,
                        )

        mock_dr_manager.create_recovery_bundle.assert_called_once()

    @patch("kopi_docka.cores.backup_manager.run_command")
    def test_dr_bundle_skipped_on_failure(
        self, mock_run, backup_unit_factory, tmp_path
    ):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        manager = make_backup_manager(tmp_path)
        manager.hooks_manager.execute_pre_backup.return_value = False
        unit = backup_unit_factory()

        mock_dr_manager = Mock()
        with patch.object(manager, "_start_containers"):
            with patch(
                "kopi_docka.cores.disaster_recovery_manager.DisasterRecoveryManager",
                return_value=mock_dr_manager,
            ):
                metadata = manager.backup_unit(
                    unit,
                    backup_scope=BACKUP_SCOPE_MINIMAL,
                    update_recovery_bundle=True,
                )

        mock_dr_manager.create_recovery_bundle.assert_not_called()
        assert metadata.success is False
