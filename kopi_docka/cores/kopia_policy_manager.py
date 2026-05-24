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
# @version:     7.1.2
#
# ------------------------------------------------------------------------------
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

from __future__ import annotations

from ..helpers.logging import get_logger

logger = get_logger(__name__)


class KopiaPolicyManager:
    """Encapsulates Kopia policy operations for a given repository (profile)."""

    def __init__(self, repo):
        # repo is an instance of KopiaRepository
        self.repo = repo

    # --- Global defaults ---

    def apply_global_defaults(self) -> None:
        """Apply global defaults (compression, retention) from Config. Best-effort.

        Called from both ``KopiaRepository.initialize()`` (new repos) and
        ``KopiaRepository.connect()`` (every connect — idempotent: Kopia treats
        identical ``--global`` writes as a no-op). Plan 0028 made this the
        single source of policy truth — there are no per-path policy writes
        in the backup hot path anymore.
        """
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

    # --- Listing / inspection ---

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

    def delete_policy(self, host: str, username: str, path: str) -> bool:
        """Delete a single retention policy. Returns True on success."""
        target = f"{username}@{host}:{path}"
        result = self._run(
            ["kopia", "policy", "delete", target],
            check=False,
            timeout=600,
        )
        return result is not None and result.returncode == 0

    def delete_policies_batch(self, entries: list) -> bool:
        """Delete multiple policies in a single kopia call (one repo transaction).

        entries: list of target dicts with keys 'userName', 'host', 'path'.
        Returns True if all were deleted successfully.
        Remote backends (rclone, S3, etc.) need time to read+write repo metadata;
        batching avoids 41 separate round-trips.
        """
        targets = [
            f"{e.get('userName', '')}@{e.get('host', '')}:{e.get('path', '')}"
            for e in entries
        ]
        result = self._run(
            ["kopia", "policy", "delete", *targets],
            check=False,
            timeout=600,
        )
        return result is not None and result.returncode == 0

    # --- Low-level passthrough ---

    def _run(self, args, check: bool = True, timeout: int = 300):
        # Default 300s = 120s rclone-serve cold-start (matches Plan 0026's
        # kopia_rclone_startup_timeout default) + ~3 min for the actual operation.
        # Pre-Plan-0026 default was 120s, but the OS-level timeout has to be
        # LARGER than the rclone-startup-timeout Kopia waits on internally —
        # otherwise we'd kill the subprocess before Kopia even finished spawning
        # rclone, which we saw in v7.2.0 prod logs after the migration set
        # startupTimeout=120s.
        if "--config-file" not in args:
            args = [*args, "--config-file", self.repo._get_config_file()]
        return self.repo._run(args, check=check, timeout=timeout)
