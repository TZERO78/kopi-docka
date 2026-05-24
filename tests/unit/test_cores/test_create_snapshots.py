"""Tests for ``KopiaRepository.create_snapshots`` (Plan 0028 Phase 3).

The method is intentionally sequential — see the docstring on
``create_snapshots`` for the rationale and the Kopia upstream issue
(``kopia/kopia#1725``) tracking native multi-path support. These tests pin
the contract that single-source failures are isolated (empty string at the
failing index, rest of the list still produced) so callers can map
results back to their input.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from kopi_docka.cores.repository_manager import KopiaRepository
from kopi_docka.types import BackupSource


def _make_repo() -> KopiaRepository:
    repo = KopiaRepository.__new__(KopiaRepository)
    repo._rclone_timeout_patched = True
    repo._connected_cache = None
    return repo


def _src(path: str, kind: str = "volume", **tags) -> BackupSource:
    return BackupSource(path=path, kind=kind, tags={"type": kind, **tags})


@pytest.mark.unit
class TestCreateSnapshots:
    def test_empty_input_returns_empty_list(self):
        repo = _make_repo()
        repo.create_snapshot = Mock(return_value="should-not-be-called")

        assert repo.create_snapshots([]) == []
        repo.create_snapshot.assert_not_called()

    def test_happy_path_returns_one_id_per_source_in_order(self):
        repo = _make_repo()
        repo.create_snapshot = Mock(side_effect=["s1", "s2", "s3"])

        sources = [
            _src("/a", kind="recipe"),
            _src("/b", kind="network"),
            _src("/c", kind="volume"),
        ]

        ids = repo.create_snapshots(sources)

        assert ids == ["s1", "s2", "s3"]
        assert repo.create_snapshot.call_count == 3
        call_paths = [c.args[0] for c in repo.create_snapshot.call_args_list]
        assert call_paths == ["/a", "/b", "/c"]

    def test_partial_failure_isolates_to_empty_string_index(self):
        """A failure on one source must not abort the loop. The failing index
        gets an empty string; the remaining sources still run."""
        repo = _make_repo()
        repo.create_snapshot = Mock(
            side_effect=["s1", RuntimeError("backend hiccup"), "s3"]
        )

        ids = repo.create_snapshots(
            [_src("/a"), _src("/b"), _src("/c")]
        )

        assert ids == ["s1", "", "s3"]
        assert repo.create_snapshot.call_count == 3

    def test_all_sources_fail_returns_all_empty(self):
        repo = _make_repo()
        repo.create_snapshot = Mock(side_effect=RuntimeError("repo down"))

        ids = repo.create_snapshots([_src("/a"), _src("/b")])

        assert ids == ["", ""]

    def test_tags_are_forwarded_to_create_snapshot(self):
        repo = _make_repo()
        repo.create_snapshot = Mock(return_value="s1")

        src = _src("/vol", kind="volume", unit="u1", volume="v1",
                   backup_id="bk-1", backup_scope="standard")
        repo.create_snapshots([src])

        kwargs = repo.create_snapshot.call_args.kwargs
        assert kwargs["tags"]["unit"] == "u1"
        assert kwargs["tags"]["volume"] == "v1"
        assert kwargs["tags"]["backup_id"] == "bk-1"

    def test_loop_is_sequential_not_parallel(self):
        """The order of side_effects matters — we should see them consumed
        in input order, never out of order (which a ThreadPool could do)."""
        repo = _make_repo()
        call_order: list[str] = []

        def record(path, tags=None, exclude_patterns=None):
            call_order.append(path)
            return f"snap-{path}"

        repo.create_snapshot = Mock(side_effect=record)

        repo.create_snapshots([_src("/a"), _src("/b"), _src("/c")])

        assert call_order == ["/a", "/b", "/c"]
