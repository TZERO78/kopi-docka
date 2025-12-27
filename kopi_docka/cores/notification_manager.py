#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        notification_manager.py
# @module:      kopi_docka.cores
# @description: Manages backup notifications via Apprise
# @author:      Markus F. (TZERO78) & AI Assistants
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT License: see LICENSE or https://opensource.org/licenses/MIT
################################################################################

"""
Notification management module for Kopi-Docka.

Supports sending backup status notifications via various services:
- Telegram
- Discord
- Email (SMTP)
- Webhooks (JSON/Generic)
- Custom Apprise URLs

Uses fire-and-forget pattern with timeout to never block backup operations.
"""

import concurrent.futures
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ..helpers.config import Config
from ..helpers.logging import get_logger
from ..types import BackupMetadata

logger = get_logger(__name__)


@dataclass
class BackupStats:
    """Statistics from a backup run for notification templates."""

    unit_name: str
    success: bool
    duration_seconds: float
    volumes_backed_up: int
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    backup_id: str = ""
    networks_backed_up: int = 0
    hooks_executed: List[str] = field(default_factory=list)

    @classmethod
    def from_metadata(cls, metadata: BackupMetadata) -> "BackupStats":
        """Create BackupStats from BackupMetadata."""
        return cls(
            unit_name=metadata.unit_name,
            success=metadata.success,
            duration_seconds=metadata.duration_seconds,
            volumes_backed_up=metadata.volumes_backed_up,
            errors=metadata.errors.copy(),
            timestamp=metadata.timestamp,
            backup_id=metadata.backup_id,
            networks_backed_up=metadata.networks_backed_up,
            hooks_executed=metadata.hooks_executed.copy(),
        )


class NotificationManager:
    """Manages backup notifications via Apprise.

    Uses fire-and-forget pattern: notifications are sent asynchronously
    with a timeout. Failures are logged but never block backup operations.
    """

    SUPPORTED_SERVICES = {"telegram", "discord", "email", "webhook", "custom"}
    TIMEOUT_SECONDS = 10

    def __init__(self, config: Config):
        """
        Initialize NotificationManager.

        Args:
            config: Kopi-Docka configuration
        """
        self.config = config
        self._enabled = self._is_enabled()

    # --- Configuration Helpers ---

    def _is_enabled(self) -> bool:
        """Check if notifications are enabled."""
        return self.config.getboolean("notifications", "enabled", fallback=False)

    # --- Secret Resolution (3-way priority) ---

    def _resolve_secret(self) -> Optional[str]:
        """
        Resolve notification secret with 3-way priority.

        Priority:
        1. secret_file - Read from external file
        2. secret - Direct value in config
        3. None - No separate secret (might be embedded in URL)

        Returns:
            Secret string or None
        """
        # PRIORITY 1: secret_file
        secret_file_str = self.config.get("notifications", "secret_file", fallback=None)
        if secret_file_str:
            secret_file = Path(secret_file_str).expanduser()
            if secret_file.exists():
                try:
                    secret = secret_file.read_text(encoding="utf-8").strip()
                    if secret:
                        logger.debug(f"Using notification secret from file: {secret_file}")
                        return secret
                except Exception as e:
                    logger.warning(f"Could not read secret file {secret_file}: {e}")

        # PRIORITY 2: secret direct in config
        secret = self.config.get("notifications", "secret", fallback=None)
        if secret:
            logger.debug("Using notification secret from config")
            return secret

        # PRIORITY 3: None (secret might be in URL or not needed)
        return None

    # --- Environment Variable Substitution ---

    def _resolve_env_vars(self, url: str) -> str:
        """
        Replace ${VAR_NAME} with environment variable values.

        Args:
            url: URL string potentially containing ${VAR} patterns

        Returns:
            URL with environment variables resolved
        """
        pattern = r"\$\{([A-Z_][A-Z0-9_]*)\}"

        def replacer(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                logger.warning(f"Environment variable not found: {var_name}")
                return f"${{{var_name}}}"  # Keep original if not found
            return value

        return re.sub(pattern, replacer, url)

    # --- URL Builder ---

    def _build_apprise_url(self) -> Optional[str]:
        """
        Build final Apprise URL from config + secret.

        Returns:
            Apprise-compatible URL or None if not configured
        """
        service = self.config.get("notifications", "service", fallback=None)
        url = self.config.get("notifications", "url", fallback=None)

        if not service or not url:
            return None

        # Resolve environment variables first
        url = self._resolve_env_vars(url)
        secret = self._resolve_secret()

        # Build URL based on service type
        if service == "telegram":
            # Telegram: tgram://BOT_TOKEN/CHAT_ID
            # Config: url = CHAT_ID, secret = BOT_TOKEN
            if secret:
                return f"tgram://{secret}/{url}"
            # If no secret, assume full URL is provided
            return url if url.startswith("tgram://") else f"tgram://{url}"

        elif service == "discord":
            # Discord: discord://WEBHOOK_ID/WEBHOOK_TOKEN
            # Config: url = full webhook URL or ID/TOKEN
            if url.startswith("https://discord.com/api/webhooks/"):
                # Convert webhook URL to Apprise format
                parts = url.replace("https://discord.com/api/webhooks/", "").split("/")
                if len(parts) >= 2:
                    return f"discord://{parts[0]}/{parts[1]}"
            return url if url.startswith("discord://") else f"discord://{url}"

        elif service == "email":
            # Email: mailto://user:pass@smtp.server:port?to=recipient
            # Secret can be SMTP password
            if secret and "@" in url:
                # Try to insert password into URL
                if "://" in url:
                    protocol, rest = url.split("://", 1)
                    if "@" in rest and ":" not in rest.split("@")[0]:
                        user, host_part = rest.split("@", 1)
                        return f"{protocol}://{user}:{secret}@{host_part}"
            return url

        elif service == "webhook":
            # Webhook: json:// or generic://
            if url.startswith(("json://", "jsons://", "generic://", "generics://")):
                return url
            if url.startswith(("http://", "https://")):
                return f"json://{url.replace('http://', '').replace('https://', '')}"
            return f"json://{url}"

        elif service == "custom":
            # Custom: pass through directly (user provides full Apprise URL)
            return url

        logger.warning(f"Unknown notification service: {service}")
        return None

    # --- Template Rendering ---

    def _render_success_message(self, stats: BackupStats) -> Tuple[str, str]:
        """
        Render success notification message.

        Args:
            stats: Backup statistics

        Returns:
            Tuple of (title, body)
        """
        title = f"Backup OK: {stats.unit_name}"
        body = (
            f"Unit: {stats.unit_name}\n"
            f"Status: SUCCESS\n"
            f"Volumes: {stats.volumes_backed_up}\n"
            f"Networks: {stats.networks_backed_up}\n"
            f"Duration: {stats.duration_seconds:.1f}s\n"
            f"Backup-ID: {stats.backup_id[:8]}..."
        )
        return title, body

    def _render_failure_message(self, stats: BackupStats) -> Tuple[str, str]:
        """
        Render failure notification message.

        Args:
            stats: Backup statistics

        Returns:
            Tuple of (title, body)
        """
        title = f"BACKUP FAILED: {stats.unit_name}"

        # Summarize errors (max 3)
        error_summary = "; ".join(stats.errors[:3])
        if len(stats.errors) > 3:
            error_summary += f" (+{len(stats.errors) - 3} more)"

        body = (
            f"Unit: {stats.unit_name}\n"
            f"Status: FAILED\n"
            f"Errors: {error_summary or 'Unknown error'}\n"
            f"Duration: {stats.duration_seconds:.1f}s"
        )
        return title, body

    # --- Public API ---

    def send_success(self, stats: BackupStats) -> bool:
        """
        Send success notification (fire-and-forget).

        Args:
            stats: Backup statistics

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._enabled:
            return True

        # Check on_success setting
        if not self.config.getboolean("notifications", "on_success", fallback=True):
            logger.debug("Success notifications disabled")
            return True

        title, body = self._render_success_message(stats)
        return self._send_notification(title, body)

    def send_failure(self, stats: BackupStats) -> bool:
        """
        Send failure notification (fire-and-forget).

        Args:
            stats: Backup statistics

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._enabled:
            return True

        # Check on_failure setting
        if not self.config.getboolean("notifications", "on_failure", fallback=True):
            logger.debug("Failure notifications disabled")
            return True

        title, body = self._render_failure_message(stats)
        return self._send_notification(title, body)

    def send_test(self) -> bool:
        """
        Send test notification.

        Returns:
            True if sent successfully, False otherwise
        """
        return self._send_notification(
            "Kopi-Docka Test",
            "This is a test notification from Kopi-Docka.\n"
            "If you see this, notifications are working correctly!",
        )

    # --- Fire-and-Forget Wrapper ---

    def _send_notification(self, title: str, body: str) -> bool:
        """
        Send notification with timeout (fire-and-forget).

        Args:
            title: Notification title
            body: Notification body

        Returns:
            True if sent successfully, False otherwise
        """

        def _do_send():
            try:
                import apprise
            except ImportError:
                logger.error("apprise library not installed. " "Install with: pip install apprise")
                return False

            url = self._build_apprise_url()
            if not url:
                logger.warning("No valid notification URL configured")
                return False

            apobj = apprise.Apprise()
            apobj.add(url)

            # Send notification
            result = apobj.notify(title=title, body=body)
            return result

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_send)
                result = future.result(timeout=self.TIMEOUT_SECONDS)

                if result:
                    logger.info(f"Notification sent: {title}")
                else:
                    logger.warning(f"Notification failed: {title}")
                return result

        except concurrent.futures.TimeoutError:
            logger.warning(f"Notification timed out after {self.TIMEOUT_SECONDS}s: {title}")
            return False
        except Exception as e:
            logger.error(f"Notification error: {e}")
            return False
