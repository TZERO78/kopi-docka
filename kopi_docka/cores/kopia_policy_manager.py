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
            self._run(
                ["kopia", "policy", "set", "--global", "--compression", compression], check=False
            )
        except Exception as e:
            logger.debug("Global compression policy skipped: %s", e)

        try:
            latest = str(self.repo.config.getint("retention", "latest", fallback=10))
            hourly = str(self.repo.config.getint("retention", "hourly", fallback=0))
            daily = str(self.repo.config.getint("retention", "daily", fallback=7))
            weekly = str(self.repo.config.getint("retention", "weekly", fallback=4))
            monthly = str(self.repo.config.getint("retention", "monthly", fallback=12))
            annual = str(self.repo.config.getint("retention", "annual", fallback=3))
            self._run(
                [
                    "kopia",
                    "policy",
                    "set",
                    "--global",
                    "--keep-latest",
                    latest,
                    "--keep-hourly",
                    hourly,
                    "--keep-daily",
                    daily,
                    "--keep-weekly",
                    weekly,
                    "--keep-monthly",
                    monthly,
                    "--keep-annual",
                    annual,
                ],
                check=False,
            )
        except Exception as e:
            logger.debug("Global retention policy skipped: %s", e)

    # --- Targeted policies ---

    def set_retention_for_target(
        self,
        target: str,
        *,
        keep_latest: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_annual: Optional[int] = None,
    ) -> None:
        """Set retention for a specific policy target (e.g., a path or user@host:path)."""
        args = ["kopia", "policy", "set", target]
        if keep_latest is not None:
            args += ["--keep-latest", str(keep_latest)]
        if keep_hourly is not None:
            args += ["--keep-hourly", str(keep_hourly)]
        if keep_daily is not None:
            args += ["--keep-daily", str(keep_daily)]
        if keep_weekly is not None:
            args += ["--keep-weekly", str(keep_weekly)]
        if keep_monthly is not None:
            args += ["--keep-monthly", str(keep_monthly)]
        if keep_annual is not None:
            args += ["--keep-annual", str(keep_annual)]
        self._run(args, check=True)

    def list_policies(self) -> list:
        """List all Kopia policies (parsed JSON)."""
        import json

        result = self._run(["kopia", "policy", "list", "--json"], check=True)
        if result and result.stdout:
            return json.loads(result.stdout)
        return []

    def get_global_policy(self) -> dict:
        """Read current global Kopia policy as a parsed dict."""
        import json

        result = self._run(["kopia", "policy", "show", "--global", "--json"], check=False)
        if result and result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return {}

    def update_global_retention(
        self,
        latest: int,
        hourly: int,
        daily: int,
        weekly: int,
        monthly: int,
        annual: int,
    ) -> bool:
        """
        Update global Kopia retention policy.

        Returns True on success.
        """
        result = self._run(
            [
                "kopia",
                "policy",
                "set",
                "--global",
                "--keep-latest",
                str(latest),
                "--keep-hourly",
                str(hourly),
                "--keep-daily",
                str(daily),
                "--keep-weekly",
                str(weekly),
                "--keep-monthly",
                str(monthly),
                "--keep-annual",
                str(annual),
            ],
            check=False,
        )
        if result and result.returncode == 0:
            logger.info(
                "Updated global retention: latest=%s daily=%s weekly=%s monthly=%s annual=%s",
                latest, daily, weekly, monthly, annual,
            )
            return True
        logger.warning("Failed to update global retention policy")
        return False

    def set_compression_for_target(self, target: str, compression: str = "zstd") -> None:
        """Set compression for a specific target."""
        self._run(["kopia", "policy", "set", target, "--compression", compression], check=True)

    def delete_policy(self, host: str, username: str, path: str) -> bool:
        """Delete a specific retention policy by host/user/path. Returns True on success."""
        result = self._run(
            ["kopia", "policy", "delete", "--username", username, "--host", host, path],
            check=False,
        )
        return result is not None and result.returncode == 0

    # --- Low-level passthrough ---

    def _run(self, args, check: bool = True, timeout: int = 120):
        # Ensure we pass the repo's profile/config every time
        if "--config-file" not in args:
            args = [*args, "--config-file", self.repo._get_config_file()]
        return self.repo._run(args, check=check, timeout=timeout)
