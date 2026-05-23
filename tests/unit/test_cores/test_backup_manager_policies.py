"""Unit tests for BackupManager policy management (Plan 0026).

Covers _ensure_policies smart-skip and auto_prune_orphaned_policies.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.helpers.policy_state import PolicyStateManager
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo


def _mock_config():
    cfg = Mock()
    # Standard retention used by _ensure_policies
    cfg.getint.side_effect = lambda section, key, default: default
    return cfg


def _bm_with_state(tmp_path: Path) -> BackupManager:
    """BackupManager instance with mocked repo/policy_manager but a real PolicyStateManager
    pointed at tmp_path. __init__ bypassed."""
    bm = BackupManager.__new__(BackupManager)
    bm.config = _mock_config()
    bm.repo = Mock()
    bm.repo.profile_name = "testprofile"
    bm.policy_manager = Mock()
    bm.policy_state = PolicyStateManager(
        "testprofile", state_path=tmp_path / "policy_state.json"
    )
    return bm


def _unit(name: str = "u1", *, volumes: list[str] | None = None) -> BackupUnit:
    vols = volumes or ["/var/lib/docker/volumes/u1_data/_data"]
    return BackupUnit(
        name=name,
        type="stack",
        containers=[
            ContainerInfo(
                id="c1",
                name=f"{name}_svc",
                image="nginx:latest",
                status="running",
                database_type=None,
                inspect_data={},
            )
        ],
        volumes=[
            VolumeInfo(name=f"{name}_v{i}", driver="local", mountpoint=m, size_bytes=0)
            for i, m in enumerate(vols)
        ],
        compose_files=[],
    )


# ---------------------------------------------------------------------------
# _ensure_policies — staging removal + smart-skip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnsurePoliciesStagingRemoved:
    def test_no_staging_policies_set(self, tmp_path: Path):
        """Plan 0026 Phase A: _ensure_policies must not set policies on staging dirs.
        Pre-7.2.0 this set 3 policies per unit (recipes/networks/docker-config).
        After Phase A: zero. Global policy covers them via inheritance."""
        bm = _bm_with_state(tmp_path)
        bm._ensure_policies(_unit())

        # Inspect every call's target argument
        targets = [
            call.args[0]
            for call in bm.policy_manager.set_retention_for_target.call_args_list
        ]
        assert all("staging" not in t for t in targets), (
            f"Staging paths must not get per-path policies; got: {targets}"
        )


@pytest.mark.unit
class TestEnsurePoliciesSmartSkip:
    def test_first_run_applies_each_volume(self, tmp_path: Path):
        bm = _bm_with_state(tmp_path)
        bm._ensure_policies(
            _unit(volumes=["/var/lib/docker/volumes/a/_data", "/var/lib/docker/volumes/b/_data"])
        )
        assert bm.policy_manager.set_retention_for_target.call_count == 2

    def test_second_run_skips_unchanged(self, tmp_path: Path):
        """Hash matches → kopia policy set is skipped — the whole point of Phase C."""
        bm = _bm_with_state(tmp_path)
        unit = _unit()
        bm._ensure_policies(unit)
        first_count = bm.policy_manager.set_retention_for_target.call_count
        bm._ensure_policies(unit)
        # No new calls on the second run
        assert bm.policy_manager.set_retention_for_target.call_count == first_count

    def test_hash_recorded_only_after_success(self, tmp_path: Path):
        """If `kopia policy set` raises (e.g. backend timeout), state must NOT
        record the hash — otherwise we'd silently skip retry forever."""
        bm = _bm_with_state(tmp_path)
        bm.policy_manager.set_retention_for_target.side_effect = RuntimeError("simulated timeout")

        bm._ensure_policies(_unit())

        # Failure path: nothing stored
        assert bm.policy_state.known_targets() == set()

        # Next run also retries (no skip)
        bm.policy_manager.set_retention_for_target.reset_mock(side_effect=True)
        bm.policy_manager.set_retention_for_target.side_effect = None
        bm._ensure_policies(_unit())
        assert bm.policy_manager.set_retention_for_target.call_count == 1

    def test_retention_change_triggers_reapply(self, tmp_path: Path):
        bm = _bm_with_state(tmp_path)
        bm._ensure_policies(_unit())
        assert bm.policy_manager.set_retention_for_target.call_count == 1

        # Change retention → hash changes → reapply
        bm.config.getint.side_effect = lambda section, key, default: (
            999 if key == "daily" else default
        )
        bm._ensure_policies(_unit())
        assert bm.policy_manager.set_retention_for_target.call_count == 2


# ---------------------------------------------------------------------------
# auto_prune_orphaned_policies — safety + correctness
# ---------------------------------------------------------------------------


def _policy(path: str, host: str = "testhost", user: str = "testuser"):
    return {"target": {"path": path, "host": host, "userName": user}}


def _snap(path: str):
    return {"path": path}


@pytest.mark.unit
class TestAutoPruneOrphanedPolicies:
    def _bm(self, tmp_path: Path, policies, snapshots):
        bm = _bm_with_state(tmp_path)
        bm.policy_manager.list_policies.return_value = policies
        bm.policy_manager.delete_policies_batch.return_value = True
        bm.repo.list_snapshots.return_value = snapshots
        return bm

    def test_owned_orphan_under_volumes_prefix_is_pruned(self, tmp_path, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[_policy("/var/lib/docker/volumes/dead-vol/_data")],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_called_once()
        deleted = bm.policy_manager.delete_policies_batch.call_args.args[0]
        assert deleted[0]["path"] == "/var/lib/docker/volumes/dead-vol/_data"

    def test_owned_orphan_under_staging_prefix_is_pruned(self, tmp_path, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[_policy("/var/cache/kopi-docka/staging/recipes/legacy-unit")],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_called_once()

    def test_foreign_host_policy_never_touched(self, tmp_path, monkeypatch):
        """Cross-host restore safety (Plan 0024): if we connect to another machine's
        repo, we MUST NOT delete that host's per-path policies."""
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[_policy("/var/lib/docker/volumes/x/_data", host="other-host")],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_foreign_user_policy_never_touched(self, tmp_path, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[_policy("/var/lib/docker/volumes/x/_data", user="other-user")],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_active_snapshot_path_not_pruned(self, tmp_path, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        path = "/var/lib/docker/volumes/alive/_data"
        bm = self._bm(tmp_path, policies=[_policy(path)], snapshots=[_snap(path)])
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_unknown_prefix_not_pruned_even_if_owned(self, tmp_path, monkeypatch):
        """Defense-in-depth: even if a policy looks orphaned, we only prune under
        known kopi-docka prefixes — don't touch /home/user/custom etc."""
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[_policy("/home/user/custom")],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_global_policy_never_touched(self, tmp_path, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = self._bm(
            tmp_path,
            policies=[{"target": {"path": "(global)", "host": "", "userName": ""}}],
            snapshots=[],
        )
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_pruned_targets_removed_from_smart_skip_state(self, tmp_path, monkeypatch):
        """If a path is pruned, its smart-skip entry must go too — otherwise a
        returning path would silently skip reapplying."""
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        path = "/var/lib/docker/volumes/old/_data"
        bm = self._bm(tmp_path, policies=[_policy(path)], snapshots=[])
        bm.policy_state.mark_applied(path, "sha256:stale")
        assert path in bm.policy_state.known_targets()

        bm.auto_prune_orphaned_policies()
        assert path not in bm.policy_state.known_targets()

    def test_uses_flat_snap_path_key(self, tmp_path, monkeypatch):
        """Regression test for the v7.1.5 Phase 0 bug — list_snapshots() returns
        flat dicts with snap['path'], NOT snap['source']['path']. If we read the
        wrong key, snapshot_paths is empty → owned policies for ACTIVE volumes
        get deleted. Catastrophic."""
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        path = "/var/lib/docker/volumes/alive/_data"
        # Snapshot in the new flat format
        bm = self._bm(tmp_path, policies=[_policy(path)], snapshots=[{"path": path}])
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()

    def test_list_failure_skips_prune_silently(self, tmp_path, monkeypatch):
        """If we can't talk to the repo, don't crash the backup — auto-prune
        is a best-effort cleanup, not a hard requirement."""
        monkeypatch.setattr("socket.gethostname", lambda: "testhost")
        monkeypatch.setattr("getpass.getuser", lambda: "testuser")
        bm = _bm_with_state(tmp_path)
        bm.policy_manager.list_policies.side_effect = RuntimeError("repo down")
        bm.repo.list_snapshots.return_value = []
        # Must not raise
        bm.auto_prune_orphaned_policies()
        bm.policy_manager.delete_policies_batch.assert_not_called()
