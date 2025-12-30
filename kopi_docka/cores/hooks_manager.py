#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        hooks_manager.py
# @module:      kopi_docka.cores
# @description: Manages pre/post backup hooks for custom user scripts
# @author:      Markus F. (TZERO78) & Claude AI
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.2.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Backup hooks management module for Kopi-Docka.

Allows users to run custom scripts at various backup/restore stages:
- pre_backup: Before backup starts (e.g., enable Nextcloud maintenance mode)
- post_backup: After backup completes (e.g., disable maintenance mode)
- pre_restore: Before restore starts
- post_restore: After restore completes

Configuration in config file:
[backup.hooks]
pre_backup = "/path/to/pre-backup.sh"
post_backup = "/path/to/post-backup.sh"
"""

import os
import time
from pathlib import Path
from typing import List

from ..helpers.logging import get_logger
from ..helpers.config import Config
from ..helpers.ui_utils import run_command, SubprocessError
from ..helpers.constants import (
    HOOK_PRE_BACKUP,
    HOOK_POST_BACKUP,
    HOOK_PRE_RESTORE,
    HOOK_POST_RESTORE,
)

logger = get_logger(__name__)


class HooksManager:
    """Manages execution of user-defined backup/restore hooks."""

    def __init__(self, config: Config):
        """
        Initialize hooks manager.

        Args:
            config: Kopi-Docka configuration
        """
        self.config = config
        self.executed_hooks: List[str] = []

    def execute_hook(self, hook_type: str, unit_name: str = None, timeout: int = 300) -> bool:
        """
        Execute a hook script if configured.

        Args:
            hook_type: Type of hook (pre_backup, post_backup, etc.)
            unit_name: Name of the backup unit (optional, for context)
            timeout: Max execution time in seconds

        Returns:
            True if hook executed successfully (or no hook configured)
            False if hook failed
        """
        # Get hook script path from config
        hook_script = self.config.get("backup.hooks", hook_type, fallback=None)

        if not hook_script:
            logger.debug(f"No {hook_type} hook configured", extra={"hook_type": hook_type})
            return True  # No hook = success

        hook_path = Path(hook_script).expanduser()

        if not hook_path.exists():
            logger.warning(
                f"Hook script not found: {hook_path}",
                extra={"hook_type": hook_type, "path": str(hook_path)},
            )
            return False

        if not hook_path.is_file() or not os.access(hook_path, os.X_OK):
            logger.warning(
                f"Hook script not executable: {hook_path}",
                extra={"hook_type": hook_type, "path": str(hook_path)},
            )
            return False

        # Execute hook
        logger.info(
            f"Executing {hook_type} hook: {hook_path}",
            extra={"hook_type": hook_type, "unit_name": unit_name},
        )

        try:
            start_time = time.time()

            # Prepare environment variables for hook
            env = os.environ.copy()
            env["KOPI_DOCKA_HOOK_TYPE"] = hook_type
            if unit_name:
                env["KOPI_DOCKA_UNIT_NAME"] = unit_name

            # Use run_command for automatic subprocess tracking
            result = run_command(
                [str(hook_path)],
                f"Executing {hook_type} hook",
                timeout=timeout,
                env=env,
                check=False,  # Don't raise on non-zero exit
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                logger.info(
                    f"Hook {hook_type} completed successfully in {duration:.1f}s",
                    extra={
                        "hook_type": hook_type,
                        "duration": duration,
                        "stdout": result.stdout[:500] if result.stdout else "",
                    },
                )
                self.executed_hooks.append(f"{hook_type}:{hook_path.name}")
                return True
            else:
                logger.error(
                    f"Hook {hook_type} failed with exit code {result.returncode}",
                    extra={
                        "hook_type": hook_type,
                        "exit_code": result.returncode,
                        "stderr": result.stderr[:500] if result.stderr else "",
                        "stdout": result.stdout[:500] if result.stdout else "",
                    },
                )
                return False

        except SubprocessError as e:
            # run_command raises SubprocessError on timeout
            if "timeout" in str(e).lower():
                logger.error(
                    f"Hook {hook_type} timed out after {timeout}s",
                    extra={"hook_type": hook_type, "timeout": timeout},
                )
            else:
                logger.error(
                    f"Hook {hook_type} execution failed: {e}",
                    extra={"hook_type": hook_type, "error": str(e)},
                )
            return False
        except Exception as e:
            logger.error(
                f"Hook {hook_type} execution failed: {e}",
                extra={"hook_type": hook_type, "error": str(e)},
            )
            return False

    def execute_pre_backup(self, unit_name: str = None) -> bool:
        """Execute pre-backup hook."""
        return self.execute_hook(HOOK_PRE_BACKUP, unit_name)

    def execute_post_backup(self, unit_name: str = None) -> bool:
        """Execute post-backup hook."""
        return self.execute_hook(HOOK_POST_BACKUP, unit_name)

    def execute_pre_restore(self, unit_name: str = None) -> bool:
        """Execute pre-restore hook."""
        return self.execute_hook(HOOK_PRE_RESTORE, unit_name)

    def execute_post_restore(self, unit_name: str = None) -> bool:
        """Execute post-restore hook."""
        return self.execute_hook(HOOK_POST_RESTORE, unit_name)

    def get_executed_hooks(self) -> List[str]:
        """Get list of executed hooks."""
        return self.executed_hooks.copy()
