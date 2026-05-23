"""Unit tests for PolicyStateManager and compute_policy_hash."""

import json
from pathlib import Path

import pytest

from kopi_docka.helpers.policy_state import PolicyStateManager, compute_policy_hash


# ---------------------------------------------------------------------------
# compute_policy_hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputePolicyHash:
    def test_returns_sha256_prefixed_hex(self):
        h = compute_policy_hash("/x", {"daily": 7})
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_deterministic_across_calls(self):
        a = compute_policy_hash("/x", {"daily": 7, "weekly": 4})
        b = compute_policy_hash("/x", {"daily": 7, "weekly": 4})
        assert a == b

    def test_independent_of_dict_key_order(self):
        a = compute_policy_hash("/x", {"daily": 7, "weekly": 4})
        b = compute_policy_hash("/x", {"weekly": 4, "daily": 7})
        assert a == b

    def test_sensitive_to_target(self):
        a = compute_policy_hash("/x", {"daily": 7})
        b = compute_policy_hash("/y", {"daily": 7})
        assert a != b

    def test_sensitive_to_retention(self):
        a = compute_policy_hash("/x", {"daily": 7})
        b = compute_policy_hash("/x", {"daily": 14})
        assert a != b


# ---------------------------------------------------------------------------
# PolicyStateManager
# ---------------------------------------------------------------------------


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "policy_state.json"


@pytest.mark.unit
class TestPolicyStateManager:
    def test_is_current_false_when_state_file_missing(self, state_path: Path):
        mgr = PolicyStateManager("p1", state_path=state_path)
        assert mgr.is_current("/x", "sha256:abc") is False

    def test_mark_then_is_current_roundtrip(self, state_path: Path):
        mgr = PolicyStateManager("p1", state_path=state_path)
        mgr.mark_applied("/x", "sha256:abc")
        assert mgr.is_current("/x", "sha256:abc") is True
        # Wrong hash → False
        assert mgr.is_current("/x", "sha256:xyz") is False
        # Wrong target → False
        assert mgr.is_current("/y", "sha256:abc") is False

    def test_mark_applied_persists_to_disk(self, state_path: Path):
        mgr = PolicyStateManager("p1", state_path=state_path)
        mgr.mark_applied("/x", "sha256:abc")
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data == {"p1": {"/x": "sha256:abc"}}

    def test_remove_clears_single_target(self, state_path: Path):
        mgr = PolicyStateManager("p1", state_path=state_path)
        mgr.mark_applied("/x", "sha256:abc")
        mgr.mark_applied("/y", "sha256:def")
        mgr.remove("/x")
        assert mgr.is_current("/x", "sha256:abc") is False
        assert mgr.is_current("/y", "sha256:def") is True

    def test_remove_noop_for_unknown_target(self, state_path: Path):
        mgr = PolicyStateManager("p1", state_path=state_path)
        # Should not raise and should not create a state file
        mgr.remove("/missing")
        assert not state_path.exists()

    def test_state_survives_new_manager_instance(self, state_path: Path):
        mgr1 = PolicyStateManager("p1", state_path=state_path)
        mgr1.mark_applied("/x", "sha256:abc")

        mgr2 = PolicyStateManager("p1", state_path=state_path)
        assert mgr2.is_current("/x", "sha256:abc") is True

    def test_profiles_are_isolated(self, state_path: Path):
        """profile_A's hash must not affect profile_B's lookup — multi-repo
        installs share one state file but different profile keys."""
        mgr_a = PolicyStateManager("profile_a", state_path=state_path)
        mgr_b = PolicyStateManager("profile_b", state_path=state_path)
        mgr_a.mark_applied("/x", "sha256:from_a")
        # Reload b after a wrote
        mgr_b = PolicyStateManager("profile_b", state_path=state_path)
        assert mgr_b.is_current("/x", "sha256:from_a") is False
        # And direct check after each writes its own
        mgr_b.mark_applied("/x", "sha256:from_b")
        mgr_a = PolicyStateManager("profile_a", state_path=state_path)
        assert mgr_a.is_current("/x", "sha256:from_a") is True

    def test_known_targets_returns_current_profile_only(self, state_path: Path):
        mgr_a = PolicyStateManager("profile_a", state_path=state_path)
        mgr_a.mark_applied("/x", "sha256:1")
        mgr_a.mark_applied("/y", "sha256:2")

        mgr_b = PolicyStateManager("profile_b", state_path=state_path)
        mgr_b.mark_applied("/z", "sha256:3")

        mgr_a = PolicyStateManager("profile_a", state_path=state_path)
        assert mgr_a.known_targets() == {"/x", "/y"}

    def test_corrupt_state_file_falls_back_to_empty(self, state_path: Path):
        """A corrupt file shouldn't raise — it should be treated as empty and
        future writes should overwrite it cleanly. Worst case: one extra
        kopia policy set call (same as a fresh install)."""
        state_path.write_text("{not valid json}")
        mgr = PolicyStateManager("p1", state_path=state_path)
        assert mgr.is_current("/x", "sha256:abc") is False
        # Subsequent write replaces the corrupt content
        mgr.mark_applied("/x", "sha256:abc")
        data = json.loads(state_path.read_text())
        assert data == {"p1": {"/x": "sha256:abc"}}

    def test_state_file_top_level_non_dict_is_ignored(self, state_path: Path):
        state_path.write_text(json.dumps(["this", "is", "wrong"]))
        mgr = PolicyStateManager("p1", state_path=state_path)
        assert mgr.is_current("/x", "sha256:abc") is False
