"""Unit tests for BackupManager policy management after Plan 0028.

Plan 0028 removed the per-path Kopia policy apparatus from the backup hot
path: no more ``_ensure_policies``, ``_apply_target_policy``,
``auto_prune_orphaned_policies``, or ``PolicyStateManager``. Retention is
now a single global policy applied at ``KopiaRepository.initialize()`` and
``connect()`` time.

These tests guard that contract: a ``backup_unit()`` run must NOT call any
per-path policy methods on the policy_manager.
"""

from unittest.mock import Mock, patch

import pytest

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo


def _mock_config():
    cfg = Mock()
    cfg.getint.side_effect = lambda section, key, default: default
    cfg.getlist.return_value = []
    return cfg


def _bm() -> BackupManager:
    """BackupManager with mocked repo + policy_manager. __init__ bypassed."""
    bm = BackupManager.__new__(BackupManager)
    bm.config = _mock_config()
    bm.repo = Mock()
    bm.repo.profile_name = "testprofile"
    bm.policy_manager = Mock(spec=["apply_global_defaults", "list_policies",
                                    "delete_policy", "delete_policies_batch",
                                    "get_global_policy", "update_global_retention"])
    bm.hooks_manager = Mock()
    bm.hooks_manager.execute_pre_backup.return_value = True
    bm.hooks_manager.execute_post_backup.return_value = True
    bm.notification_manager = Mock()
    bm.volume_handler = Mock()
    bm.volume_handler.backup_volume.return_value = "snap-vol-id"
    bm.stop_timeout = 30
    bm.start_timeout = 30
    bm.max_workers = 1
    bm.exclude_patterns = []
    return bm


def _unit() -> BackupUnit:
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
                inspect_data={},
            )
        ],
        volumes=[
            VolumeInfo(
                name="u1_vol",
                driver="local",
                mountpoint="/var/lib/docker/volumes/u1_vol/_data",
                size_bytes=0,
            )
        ],
        compose_files=[],
    )


@pytest.mark.unit
class TestBackupUnitDoesNotWritePerPathPolicies:
    """Plan 0028: the backup hot path must NEVER call per-path policy setters.

    Retention is applied globally on connect()/initialize() — re-writing it
    per target on rclone backends is the original timeout source we eliminated.
    """

    def test_removed_methods_are_gone(self):
        """Hard guarantee that the obsolete entry points no longer exist on
        BackupManager. If anything tries to call them, AttributeError surfaces
        the regression instead of a silent no-op."""
        assert not hasattr(BackupManager, "_ensure_policies")
        assert not hasattr(BackupManager, "_apply_target_policy")
        assert not hasattr(BackupManager, "auto_prune_orphaned_policies")

    def test_policy_manager_has_no_per_path_setters(self):
        """The KopiaPolicyManager itself should also have lost the per-path
        setters — keeps the surface area unambiguous."""
        from kopi_docka.cores.kopia_policy_manager import KopiaPolicyManager

        assert not hasattr(KopiaPolicyManager, "set_retention_for_target")
        assert not hasattr(KopiaPolicyManager, "set_compression_for_target")

    def test_backup_unit_does_not_apply_policies_per_target(self):
        """Run a unit through backup_unit() and assert the policy_manager
        received NO per-path retention/compression calls."""
        bm = _bm()
        with patch("kopi_docka.cores.backup_manager.SafeExitManager") as safe_exit_cls:
            safe_exit_cls.get_instance.return_value = Mock()
            with patch("kopi_docka.cores.backup_manager.ServiceContinuityHandler"):
                bm._stop_containers = Mock()
                bm._start_containers = Mock()
                bm._backup_recipes = Mock(return_value="recipe-snap")
                bm._backup_networks = Mock(return_value=("net-snap", 0))
                bm._backup_docker_config = Mock(return_value=None)
                bm._save_metadata = Mock()
                bm.backup_unit(_unit())

        # Every call recorded on the mock — none of them should be policy writes.
        for call in bm.policy_manager.mock_calls:
            name = call[0]
            assert "set_retention" not in name, f"Unexpected per-path policy call: {call}"
            assert "set_compression" not in name, f"Unexpected per-path policy call: {call}"
