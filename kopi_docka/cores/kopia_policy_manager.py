# policy.py
#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        policy.py
# @module:      kopi_docka.policy
# @description: Policy helpers for Kopia (compression, retention, targets).
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

from __future__ import annotations

from typing import Optional

from ..helpers.logging import get_logger

logger = get_logger(__name__)


class KopiaPolicyManager:
    """Encapsulates Kopia policy operations for a given repository (profile)."""

    def __init__(self, repo):
        # repo is an instance of KopiaRepository
        self.repo = repo

    # --- Global defaults ---

    def apply_global_defaults(self) -> None:
        """Apply global defaults (compression, retention) from Config. Best-effort."""
        try:
            compression = self.repo.config.get("kopia", "compression", fallback="zstd")
            self._run(["kopia", "policy", "set", "--global", "--compression", compression], check=False)
        except Exception as e:
            logger.debug("Global compression policy skipped: %s", e)

        try:
            daily = str(self.repo.config.getint("retention", "daily", fallback=7))
            weekly = str(self.repo.config.getint("retention", "weekly", fallback=4))
            monthly = str(self.repo.config.getint("retention", "monthly", fallback=12))
            # Note: --keep-yearly not available in Kopia 0.21
            self._run([
                "kopia", "policy", "set", "--global",
                "--keep-latest", "10",
                "--keep-daily", daily,
                "--keep-weekly", weekly,
                "--keep-monthly", monthly,
            ], check=False)
        except Exception as e:
            logger.debug("Global retention policy skipped: %s", e)

    # --- Targeted policies ---

    def set_retention_for_target(
        self,
        target: str,
        *,
        keep_latest: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,  # Kept for API compatibility, but ignored
    ) -> None:
        """Set retention for a specific policy target (e.g., a path or user@host:path)."""
        args = ["kopia", "policy", "set", target]
        if keep_latest is not None:
            args += ["--keep-latest", str(keep_latest)]
        if keep_daily is not None:
            args += ["--keep-daily", str(keep_daily)]
        if keep_weekly is not None:
            args += ["--keep-weekly", str(keep_weekly)]
        if keep_monthly is not None:
            args += ["--keep-monthly", str(keep_monthly)]
        # keep_yearly intentionally not used (Kopia 0.21 doesn't support it)
        self._run(args, check=True)

    def set_compression_for_target(self, target: str, compression: str = "zstd") -> None:
        """Set compression for a specific target."""
        self._run(["kopia", "policy", "set", target, "--compression", compression], check=True)

    # --- Low-level passthrough ---

    def _run(self, args, check: bool = True):
        # Ensure we pass the repo's profile/config every time
        if "--config-file" not in args:
            args = [*args, "--config-file", self.repo._get_config_file()]
        return self.repo._run(args, check=check)