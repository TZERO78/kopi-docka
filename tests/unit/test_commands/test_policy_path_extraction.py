"""Tests for ``advanced policy prune`` and ``doctor`` policy alignment.

Plan 0028 made ``policy prune`` a *legacy* cleanup: every per-path Kopia
policy on this host/user under a kopi-docka-managed prefix is considered
obsolete, regardless of whether a matching snapshot still exists. The
``doctor`` command flags any leftover per-path entry as "Legacy".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Fixed host/user so the cmd_prune safety guards match the synthetic policies.
_TEST_HOST = "test-host"
_TEST_USER = "test-user"


def _flat_snapshot(path: str, snap_id: str = "snap-x") -> dict:
    return {
        "id": snap_id,
        "path": path,
        "timestamp": "2026-05-23T10:00:00Z",
        "tags": {},
        "size": 0,
    }


def _policy(path: str, host: str = _TEST_HOST, user: str = _TEST_USER) -> dict:
    return {"target": {"userName": user, "host": host, "path": path}}


# ---------------------------------------------------------------------------
# cmd_prune — kopi_docka.commands.advanced.policy_commands
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPolicyPruneLegacyCleanup:
    """Plan 0028: every per-path policy on this host is legacy, regardless of
    whether a matching snapshot still exists. ``policy prune`` removes them
    in one batch call. Cross-host / unknown-prefix policies stay untouched."""

    def _run_prune(self, policies, *, dry_run=True, monkeypatch=None):
        from kopi_docka.commands.advanced import policy_commands

        ctx = MagicMock()
        ctx.obj = {"config": MagicMock()}

        mock_repo = MagicMock()
        mock_repo.is_connected.return_value = True

        mock_policy_mgr = MagicMock()
        mock_policy_mgr.list_policies.return_value = policies
        mock_policy_mgr.delete_policies_batch.return_value = True

        # Pin host/user so the safety guards match _policy() defaults.
        if monkeypatch is not None:
            monkeypatch.setattr(policy_commands.socket, "gethostname",
                                lambda: _TEST_HOST)
            monkeypatch.setattr(policy_commands.getpass, "getuser",
                                lambda: _TEST_USER)

        with (
            patch.object(policy_commands, "KopiaRepository",
                         return_value=mock_repo),
            patch.object(policy_commands, "KopiaPolicyManager",
                         return_value=mock_policy_mgr),
        ):
            policy_commands.cmd_prune(ctx, dry_run=dry_run, force=True)

        return mock_policy_mgr

    def test_policy_with_matching_snapshot_still_pruned(self, monkeypatch):
        """Plan 0028 change: a per-path policy is obsolete even when its
        path is still actively snapshotted — global covers it."""
        policies = [
            _policy("/var/lib/docker/volumes/alive_vol/_data"),
            _policy("/var/lib/docker/volumes/dead_vol/_data"),
        ]

        mock_policy_mgr = self._run_prune(
            policies, dry_run=False, monkeypatch=monkeypatch
        )

        mock_policy_mgr.delete_policies_batch.assert_called_once()
        deleted = mock_policy_mgr.delete_policies_batch.call_args.args[0]
        deleted_paths = sorted(t["path"] for t in deleted)
        assert deleted_paths == [
            "/var/lib/docker/volumes/alive_vol/_data",
            "/var/lib/docker/volumes/dead_vol/_data",
        ]

    def test_no_per_path_policies_means_no_deletion(self, monkeypatch):
        mock_policy_mgr = self._run_prune(
            [{"target": {"path": "(global)"}}],
            dry_run=False, monkeypatch=monkeypatch,
        )

        mock_policy_mgr.delete_policies_batch.assert_not_called()

    def test_dry_run_does_not_delete(self, monkeypatch):
        policies = [_policy("/var/lib/docker/volumes/x/_data")]

        mock_policy_mgr = self._run_prune(
            policies, dry_run=True, monkeypatch=monkeypatch
        )

        mock_policy_mgr.delete_policies_batch.assert_not_called()

    def test_foreign_host_policy_never_touched(self, monkeypatch):
        """Cross-host restore safety (Plan 0024): another host's policies
        on a shared repo must NOT be pruned by this host's ``policy prune``."""
        policies = [
            _policy("/var/lib/docker/volumes/mine/_data"),
            _policy("/var/lib/docker/volumes/other/_data", host="other-host"),
        ]

        mock_policy_mgr = self._run_prune(
            policies, dry_run=False, monkeypatch=monkeypatch
        )

        mock_policy_mgr.delete_policies_batch.assert_called_once()
        deleted_paths = [
            t["path"] for t in mock_policy_mgr.delete_policies_batch.call_args.args[0]
        ]
        assert deleted_paths == ["/var/lib/docker/volumes/mine/_data"]

    def test_unknown_prefix_not_touched(self, monkeypatch):
        """Defense in depth: a custom path the user set themselves
        (e.g. ``/home/me/manual``) is never touched even when host/user match."""
        policies = [
            _policy("/var/lib/docker/volumes/mine/_data"),
            _policy("/home/me/manual"),
        ]

        mock_policy_mgr = self._run_prune(
            policies, dry_run=False, monkeypatch=monkeypatch
        )

        mock_policy_mgr.delete_policies_batch.assert_called_once()
        deleted_paths = [
            t["path"] for t in mock_policy_mgr.delete_policies_batch.call_args.args[0]
        ]
        assert deleted_paths == ["/var/lib/docker/volumes/mine/_data"]

    def test_staging_paths_are_owned_prefixes_too(self, monkeypatch):
        """Staging-dir policies left by very old kopi-docka versions (pre-Plan
        0026) are also under an owned prefix and must be cleaned up."""
        policies = [
            _policy("/var/cache/kopi-docka/staging/recipes/old-unit"),
        ]

        mock_policy_mgr = self._run_prune(
            policies, dry_run=False, monkeypatch=monkeypatch
        )

        mock_policy_mgr.delete_policies_batch.assert_called_once()


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
