"""Persistent state cache for per-target Kopia policies.

`kopia policy set` is a metadata round-trip even when nothing changed
(Kopia's SetPolicy unconditionally calls ReplaceManifests, see
upstream policy_manager.go). On slow remote backends like rclone/GDrive
each call costs ~15-40s. For a host with multiple volumes and weekly-stable
retention, that's pure overhead.

This module fingerprints the policy we *would* apply and skips the kopia call
if the previous run already applied an identical policy to the same target.
On config change, the fingerprint changes and the policy is reapplied. The
hash is written only after a successful `kopia policy set` — so a failed
apply automatically retries on the next run.

State file layout (JSON):

    {
        "<profile_name>": {
            "<target_path>": "sha256:<hex>",
            ...
        },
        ...
    }

Keyed by `kopia_profile` (not by repository URL) — `profile_name` is already
unique per Kopia config file and survives backend URL changes.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .logging import get_logger

logger = get_logger(__name__)


def compute_policy_hash(target: str, retention: Dict[str, int]) -> str:
    """Deterministic fingerprint of (target, retention) for a per-target policy.

    Sort keys to keep the hash stable across Python dict iteration order.
    Prefixed with the algorithm so future hash upgrades stay distinguishable.
    """
    payload = json.dumps(
        {"target": target, "retention": retention},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PolicyStateManager:
    """Tracks last-applied policy hashes per (profile, target).

    Reads the state file lazily on construction; writes are atomic
    (tempfile + os.replace) so a crash mid-write cannot leave a corrupt
    file behind — the previous good state survives.
    """

    def __init__(self, profile: str, state_path: Optional[Path] = None):
        self.profile = profile
        self.state_path = state_path or self._default_state_path()
        self._state: Dict[str, Any] = self._load()

    @staticmethod
    def _default_state_path() -> Path:
        # Mirrors kopia's `~/.config/kopia/repository-<profile>.config` layout
        # so user/root contexts stay parallel. With sudo, HOME is /root.
        return Path.home() / ".config" / "kopi-docka" / "policy_state.json"

    def _load(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            with self.state_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning(
                    "Policy state file %s has unexpected shape — ignoring",
                    self.state_path,
                )
                return {}
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "Could not read policy state %s: %s — starting fresh",
                self.state_path, e,
            )
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.state_path.parent),
            prefix=".policy_state.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
            os.replace(tmp, self.state_path)
            try:
                os.chmod(self.state_path, 0o600)
            except OSError:
                pass  # best-effort on filesystems without unix perms
        except OSError as e:
            logger.warning("Could not write policy state %s: %s", self.state_path, e)
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    def is_current(self, target: str, expected_hash: str) -> bool:
        """Return True iff this target's last successful apply matches expected_hash."""
        return self._state.get(self.profile, {}).get(target) == expected_hash

    def mark_applied(self, target: str, applied_hash: str) -> None:
        """Record a successful apply. Persists immediately so a crash before the next
        target still preserves what we've already done."""
        self._state.setdefault(self.profile, {})[target] = applied_hash
        self._save()

    def remove(self, target: str) -> None:
        """Drop a target — used when its policy is auto-pruned."""
        if self._state.get(self.profile, {}).pop(target, None) is not None:
            self._save()

    def known_targets(self) -> set:
        """All targets we've ever applied for the current profile."""
        return set(self._state.get(self.profile, {}).keys())
