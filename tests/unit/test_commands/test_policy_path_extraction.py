"""Regression tests for the snapshot-path extraction bug in policy + doctor code.

Bug history: both ``cmd_prune`` (``advanced/policy_commands.py``) and
``_check_policy_alignment`` (``doctor_commands.py``) used
``snap.get("source", {}).get("path", "")`` to read snapshot source paths.

But ``KopiaRepository.list_snapshots()`` already flattens the kopia JSON: the returned
dicts have ``path`` at the top level (no ``source`` key). The old extraction therefore
always produced an empty set, which made every per-path policy look orphaned — doctor
warned on healthy repos, and ``policy prune`` would have deleted every per-path policy.

These tests pin the correct shape (`snap["path"]`) so the bug cannot regress.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _flat_snapshot(path: str, snap_id: str = "snap-x") -> dict:
    """Return a snapshot dict in the shape ``KopiaRepository.list_snapshots()`` produces."""
    return {
        "id": snap_id,
        "path": path,
        "timestamp": "2026-05-23T10:00:00Z",
        "tags": {},
        "size": 0,
    }


def _policy(path: str, host: str = "host-a", user: str = "root") -> dict:
    """Return a policy dict in the shape ``kopia policy list --json`` produces."""
    return {
        "target": {
            "userName": user,
            "host": host,
            "path": path,
        }
    }


# ---------------------------------------------------------------------------
# cmd_prune — kopi_docka.commands.advanced.policy_commands
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPolicyPruneOrphanDetection:
    """``cmd_prune`` must only flag policies without a matching snapshot path."""

    def _run_prune(self, snapshots: list[dict], policies: list[dict], *, dry_run: bool = True):
        """Drive ``cmd_prune`` against mocked repo + policy_mgr; return captured output."""
        from kopi_docka.commands.advanced import policy_commands

        ctx = MagicMock()
        ctx.obj = {"config": MagicMock()}

        mock_repo = MagicMock()
        mock_repo.is_connected.return_value = True
        mock_repo.list_snapshots.return_value = snapshots

        mock_policy_mgr = MagicMock()
        mock_policy_mgr.list_policies.return_value = policies
        mock_policy_mgr.delete_policies_batch.return_value = True

        with (
            patch.object(policy_commands, "KopiaRepository", return_value=mock_repo),
            patch.object(policy_commands, "KopiaPolicyManager", return_value=mock_policy_mgr),
        ):
            policy_commands.cmd_prune(ctx, dry_run=dry_run, force=True)

        return mock_policy_mgr

    def test_policy_with_matching_snapshot_is_not_orphan(self):
        """Bug regression: snapshot at /foo must mark policy at /foo as non-orphan."""
        snapshots = [_flat_snapshot("/foo")]
        policies = [_policy("/foo"), _policy("/bar")]

        mock_policy_mgr = self._run_prune(snapshots, policies, dry_run=False)

        mock_policy_mgr.delete_policies_batch.assert_called_once()
        deleted = mock_policy_mgr.delete_policies_batch.call_args.args[0]
        deleted_paths = [t["path"] for t in deleted]
        assert deleted_paths == ["/bar"], (
            "Only /bar has no matching snapshot — /foo must not be pruned"
        )

    def test_all_policies_have_snapshots_means_no_pruning(self):
        snapshots = [_flat_snapshot("/foo"), _flat_snapshot("/baz")]
        policies = [_policy("/foo"), _policy("/baz")]

        mock_policy_mgr = self._run_prune(snapshots, policies, dry_run=False)

        mock_policy_mgr.delete_policies_batch.assert_not_called()

    def test_empty_snapshot_list_does_not_silently_delete_everything(self):
        """Defensive: even with zero snapshots, dry-run must not delete anything."""
        snapshots: list[dict] = []
        policies = [_policy("/foo"), _policy("/bar")]

        mock_policy_mgr = self._run_prune(snapshots, policies, dry_run=True)

        mock_policy_mgr.delete_policies_batch.assert_not_called()


# ---------------------------------------------------------------------------
# _check_policy_alignment — kopi_docka.commands.doctor_commands
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDoctorPolicyAlignment:
    """``_check_policy_alignment`` reports legacy per-path policies after Plan 0028.

    Plan 0028 made global the single source of retention truth, so any per-path
    policy still in the repo is a leftover from older kopi-docka versions. The
    doctor now flags those as "legacy" (with a hint to run ``policy prune``)
    rather than as "orphaned vs uncovered".
    """

    def _run_alignment(self, snapshots: list[dict], policies: list[dict]):
        """Drive ``_check_policy_alignment`` and return collected warnings."""
        from kopi_docka.commands import doctor_commands
        from rich.console import Console

        mock_repo = MagicMock()
        mock_repo.list_snapshots.return_value = snapshots

        mock_policy_mgr = MagicMock()
        mock_policy_mgr.list_policies.return_value = policies
        mock_policy_mgr.get_global_policy.return_value = {
            "retention": {"keepLatest": 10}
        }

        warnings: list[str] = []
        with patch(
            "kopi_docka.cores.kopia_policy_manager.KopiaPolicyManager",
            return_value=mock_policy_mgr,
        ):
            doctor_commands._check_policy_alignment(mock_repo, Console(quiet=True), warnings)

        return warnings

    def test_global_only_repo_produces_no_warning(self):
        """Clean state — only the global policy is present, no per-path leftovers."""
        snapshots = [_flat_snapshot("/foo")]
        policies: list[dict] = []  # global-only repo

        warnings = self._run_alignment(snapshots, policies)

        assert warnings == [], (
            f"Expected no warning for a global-only repo; got {warnings!r}"
        )

    def test_any_per_path_policy_is_flagged_as_legacy(self):
        """Per-path policy left over from older versions must surface as a warning
        even when a matching snapshot exists — Plan 0028 made them obsolete."""
        snapshots = [_flat_snapshot("/foo")]
        policies = [_policy("/foo")]

        warnings = self._run_alignment(snapshots, policies)

        assert any("legacy" in w.lower() for w in warnings), (
            f"Expected a legacy-policy warning; got {warnings!r}"
        )
        assert any("policy prune" in w.lower() for w in warnings), (
            "Warning must point users at 'kopi-docka advanced policy prune'"
        )
