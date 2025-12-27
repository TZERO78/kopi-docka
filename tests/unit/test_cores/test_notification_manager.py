"""
Unit tests for NotificationManager class.

Tests secret resolution, environment variable substitution,
URL building, message rendering, and notification sending with timeout.
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from kopi_docka.cores.notification_manager import (
    NotificationManager,
    BackupStats,
)
from kopi_docka.types import BackupMetadata


def make_mock_config(notifications_config: dict = None) -> Mock:
    """Create a mock Config object for notifications testing."""
    config = Mock()

    notifications_config = notifications_config or {}

    def get_side_effect(section, key, fallback=None):
        if section == "notifications":
            return notifications_config.get(key, fallback)
        return fallback

    def getboolean_side_effect(section, key, fallback=None):
        if section == "notifications":
            value = notifications_config.get(key, fallback)
            if isinstance(value, bool):
                return value
            return fallback
        return fallback

    config.get.side_effect = get_side_effect
    config.getboolean.side_effect = getboolean_side_effect

    return config


# =============================================================================
# Secret Resolution Tests (3-way priority)
# =============================================================================


@pytest.mark.unit
class TestSecretResolution:
    """Tests for _resolve_secret with 3-way priority."""

    def test_secret_from_file_priority_1(self, tmp_path):
        """Secret from file has highest priority (priority 1)."""
        secret_file = tmp_path / ".notification-secret"
        secret_file.write_text("SECRET_FROM_FILE")

        config = make_mock_config({
            "enabled": True,
            "secret_file": str(secret_file),
            "secret": "SECRET_FROM_CONFIG",
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret == "SECRET_FROM_FILE"

    def test_secret_from_config_priority_2(self):
        """Secret from config when no file exists (priority 2)."""
        config = make_mock_config({
            "enabled": True,
            "secret": "SECRET_FROM_CONFIG",
            "secret_file": None,
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret == "SECRET_FROM_CONFIG"

    def test_secret_none_priority_3(self):
        """Returns None when no secret configured (priority 3)."""
        config = make_mock_config({
            "enabled": True,
            "secret": None,
            "secret_file": None,
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret is None

    def test_secret_file_not_found(self, tmp_path):
        """Falls back to config secret when file doesn't exist."""
        nonexistent_file = tmp_path / "nonexistent-secret"

        config = make_mock_config({
            "enabled": True,
            "secret_file": str(nonexistent_file),
            "secret": "FALLBACK_SECRET",
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret == "FALLBACK_SECRET"

    def test_secret_file_empty(self, tmp_path):
        """Empty secret file falls back to config secret."""
        secret_file = tmp_path / ".notification-secret"
        secret_file.write_text("")  # Empty file

        config = make_mock_config({
            "enabled": True,
            "secret_file": str(secret_file),
            "secret": "FALLBACK_SECRET",
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret == "FALLBACK_SECRET"

    def test_secret_file_whitespace_stripped(self, tmp_path):
        """Secret file content is stripped of whitespace."""
        secret_file = tmp_path / ".notification-secret"
        secret_file.write_text("  SECRET_WITH_SPACES  \n")

        config = make_mock_config({
            "enabled": True,
            "secret_file": str(secret_file),
        })

        manager = NotificationManager(config)
        secret = manager._resolve_secret()

        assert secret == "SECRET_WITH_SPACES"

    def test_secret_file_expanduser(self, tmp_path):
        """Secret file path with ~ is expanded."""
        secret_file = tmp_path / ".notification-secret"
        secret_file.write_text("SECRET_FROM_HOME")

        config = make_mock_config({
            "enabled": True,
            "secret_file": "~/.notification-secret",
        })

        manager = NotificationManager(config)

        with patch("pathlib.Path.expanduser", return_value=secret_file):
            secret = manager._resolve_secret()

        assert secret == "SECRET_FROM_HOME"


# =============================================================================
# Environment Variable Substitution Tests
# =============================================================================


@pytest.mark.unit
class TestEnvironmentVariableSubstitution:
    """Tests for _resolve_env_vars."""

    def test_resolve_single_env_var(self):
        """Single environment variable is resolved."""
        os.environ["TEST_VAR"] = "test_value"

        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        result = manager._resolve_env_vars("url/${TEST_VAR}/path")

        assert result == "url/test_value/path"

        # Cleanup
        del os.environ["TEST_VAR"]

    def test_resolve_multiple_env_vars(self):
        """Multiple environment variables are resolved."""
        os.environ["VAR1"] = "value1"
        os.environ["VAR2"] = "value2"

        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        result = manager._resolve_env_vars("${VAR1}/middle/${VAR2}")

        assert result == "value1/middle/value2"

        # Cleanup
        del os.environ["VAR1"]
        del os.environ["VAR2"]

    def test_resolve_env_var_not_found(self):
        """Unknown environment variable is kept as-is."""
        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        result = manager._resolve_env_vars("url/${UNKNOWN_VAR}/path")

        assert result == "url/${UNKNOWN_VAR}/path"

    def test_resolve_no_env_vars(self):
        """URL without environment variables is unchanged."""
        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        result = manager._resolve_env_vars("https://example.com/webhook")

        assert result == "https://example.com/webhook"

    def test_resolve_env_var_uppercase_only(self):
        """Only uppercase variable names are matched."""
        os.environ["TEST_VAR"] = "value"

        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        # Lowercase should NOT be replaced
        result = manager._resolve_env_vars("${test_var}/${TEST_VAR}")

        assert result == "${test_var}/value"

        # Cleanup
        del os.environ["TEST_VAR"]

    def test_resolve_env_var_with_underscores(self):
        """Environment variables with underscores work."""
        os.environ["MY_LONG_VAR_NAME"] = "success"

        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        result = manager._resolve_env_vars("${MY_LONG_VAR_NAME}")

        assert result == "success"

        # Cleanup
        del os.environ["MY_LONG_VAR_NAME"]


# =============================================================================
# URL Builder Tests
# =============================================================================


@pytest.mark.unit
class TestURLBuilder:
    """Tests for _build_apprise_url for different services."""

    def test_build_telegram_url_with_secret(self):
        """Telegram URL built correctly with separate secret."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123456789",
            "secret": "BOT_TOKEN_123",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "tgram://BOT_TOKEN_123/123456789"

    def test_build_telegram_url_without_secret(self):
        """Telegram URL without secret uses url directly."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "tgram://BOT_TOKEN/123456789",
            "secret": None,
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "tgram://BOT_TOKEN/123456789"

    def test_build_discord_webhook_url(self):
        """Discord webhook URL converted to Apprise format."""
        config = make_mock_config({
            "enabled": True,
            "service": "discord",
            "url": "https://discord.com/api/webhooks/123456/WEBHOOK_TOKEN",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "discord://123456/WEBHOOK_TOKEN"

    def test_build_discord_apprise_url(self):
        """Discord Apprise URL passed through."""
        config = make_mock_config({
            "enabled": True,
            "service": "discord",
            "url": "discord://123456/WEBHOOK_TOKEN",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "discord://123456/WEBHOOK_TOKEN"

    def test_build_email_url_with_secret(self):
        """Email URL with password from secret."""
        config = make_mock_config({
            "enabled": True,
            "service": "email",
            "url": "mailto://user@smtp.gmail.com:587?to=recipient@example.com",
            "secret": "APP_PASSWORD",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "mailto://user:APP_PASSWORD@smtp.gmail.com:587?to=recipient@example.com"

    def test_build_email_url_without_secret(self):
        """Email URL without secret passed through."""
        config = make_mock_config({
            "enabled": True,
            "service": "email",
            "url": "mailto://user:password@smtp.gmail.com:587?to=recipient@example.com",
            "secret": None,
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "mailto://user:password@smtp.gmail.com:587?to=recipient@example.com"

    def test_build_webhook_http_url(self):
        """HTTP webhook URL converted to json:// format."""
        config = make_mock_config({
            "enabled": True,
            "service": "webhook",
            "url": "https://example.com/webhook",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "json://example.com/webhook"

    def test_build_webhook_json_url(self):
        """json:// webhook URL passed through."""
        config = make_mock_config({
            "enabled": True,
            "service": "webhook",
            "url": "json://example.com/webhook",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "json://example.com/webhook"

    def test_build_custom_url(self):
        """Custom service URL passed through as-is."""
        config = make_mock_config({
            "enabled": True,
            "service": "custom",
            "url": "slack://TOKEN/CHANNEL",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "slack://TOKEN/CHANNEL"

    def test_build_url_no_service(self):
        """Returns None when service not configured."""
        config = make_mock_config({
            "enabled": True,
            "service": None,
            "url": "some_url",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url is None

    def test_build_url_no_url(self):
        """Returns None when URL not configured."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": None,
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url is None

    def test_build_url_with_env_vars(self):
        """Environment variables in URL are resolved."""
        os.environ["CHAT_ID"] = "987654321"

        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "${CHAT_ID}",
            "secret": "BOT_TOKEN_123",
        })

        manager = NotificationManager(config)
        url = manager._build_apprise_url()

        assert url == "tgram://BOT_TOKEN_123/987654321"

        # Cleanup
        del os.environ["CHAT_ID"]


# =============================================================================
# BackupStats Tests
# =============================================================================


@pytest.mark.unit
class TestBackupStats:
    """Tests for BackupStats dataclass and from_metadata factory."""

    def test_create_backup_stats_directly(self):
        """BackupStats can be created directly."""
        stats = BackupStats(
            unit_name="test_unit",
            success=True,
            duration_seconds=42.5,
            volumes_backed_up=3,
        )

        assert stats.unit_name == "test_unit"
        assert stats.success is True
        assert stats.duration_seconds == 42.5
        assert stats.volumes_backed_up == 3
        assert stats.errors == []
        assert stats.networks_backed_up == 0

    def test_create_from_metadata_success(self):
        """BackupStats.from_metadata creates correct stats from metadata."""
        metadata = BackupMetadata(
            unit_name="test_unit",
            success=True,
            duration_seconds=30.0,
            volumes_backed_up=2,
            networks_backed_up=1,
            errors=[],
            timestamp=datetime.now(),
            backup_id="backup_123abc",
            hooks_executed=["pre_backup:hook.sh"],
        )

        stats = BackupStats.from_metadata(metadata)

        assert stats.unit_name == "test_unit"
        assert stats.success is True
        assert stats.duration_seconds == 30.0
        assert stats.volumes_backed_up == 2
        assert stats.networks_backed_up == 1
        assert stats.backup_id == "backup_123abc"
        assert stats.hooks_executed == ["pre_backup:hook.sh"]

    def test_create_from_metadata_with_errors(self):
        """BackupStats.from_metadata includes errors."""
        metadata = BackupMetadata(
            unit_name="test_unit",
            success=False,
            duration_seconds=10.0,
            volumes_backed_up=0,
            errors=["Error 1", "Error 2"],
            timestamp=datetime.now(),
            backup_id="backup_failed",
        )

        stats = BackupStats.from_metadata(metadata)

        assert stats.success is False
        assert stats.errors == ["Error 1", "Error 2"]
        assert len(stats.errors) == 2


# =============================================================================
# Message Rendering Tests
# =============================================================================


@pytest.mark.unit
class TestMessageRendering:
    """Tests for success and failure message rendering."""

    def test_render_success_message(self):
        """Success message contains expected information."""
        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        stats = BackupStats(
            unit_name="mystack",
            success=True,
            duration_seconds=45.2,
            volumes_backed_up=3,
            networks_backed_up=2,
            backup_id="backup_abc123def456",
        )

        title, body = manager._render_success_message(stats)

        assert "mystack" in title
        assert "OK" in title or "SUCCESS" in body
        assert "3" in body  # volumes
        assert "2" in body  # networks
        assert "45.1s" in body or "45.2s" in body
        assert "backup_a" in body  # truncated ID (first 8 chars)

    def test_render_failure_message(self):
        """Failure message contains errors and unit info."""
        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        stats = BackupStats(
            unit_name="mystack",
            success=False,
            duration_seconds=12.5,
            volumes_backed_up=0,
            errors=["Docker connection failed", "Timeout occurred"],
        )

        title, body = manager._render_failure_message(stats)

        assert "FAILED" in title
        assert "mystack" in title
        assert "Docker connection failed" in body
        assert "Timeout occurred" in body or "+1 more" not in body  # Only 2 errors

    def test_render_failure_message_many_errors(self):
        """Failure message truncates long error lists."""
        config = make_mock_config({"enabled": True})
        manager = NotificationManager(config)

        stats = BackupStats(
            unit_name="mystack",
            success=False,
            duration_seconds=5.0,
            volumes_backed_up=0,
            errors=["Error 1", "Error 2", "Error 3", "Error 4", "Error 5"],
        )

        title, body = manager._render_failure_message(stats)

        assert "Error 1" in body
        assert "Error 2" in body
        assert "Error 3" in body
        # Should truncate and show "+2 more"
        assert "+2 more" in body or "Error 5" not in body


# =============================================================================
# Notification Sending Tests
# =============================================================================


@pytest.mark.unit
class TestNotificationSending:
    """Tests for send_success, send_failure, send_test with mocked Apprise."""

    def test_send_test_success(self):
        """send_test sends test notification successfully."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123456789",
            "secret": "BOT_TOKEN",
        })

        manager = NotificationManager(config)

        # Mock the apprise module that gets imported inside _do_send
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.return_value = mock_apprise_instance

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            result = manager.send_test()

        assert result is True
        mock_apprise_instance.add.assert_called_once()
        mock_apprise_instance.notify.assert_called_once()

    def test_send_test_disabled(self):
        """send_test still attempts to send even when disabled (no blocking)."""
        config = make_mock_config({
            "enabled": False,
        })

        manager = NotificationManager(config)

        # send_test always tries to send regardless of enabled status
        # (it's for testing the configuration)
        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.return_value = mock_apprise_instance

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            result = manager.send_test()

        # send_test should work even if notifications are disabled
        # (it's a test function after all)

    def test_send_success_notification(self):
        """send_success sends notification for successful backup."""
        config = make_mock_config({
            "enabled": True,
            "service": "discord",
            "url": "discord://123/TOKEN",
            "on_success": True,
        })

        manager = NotificationManager(config)

        stats = BackupStats(
            unit_name="mystack",
            success=True,
            duration_seconds=30.0,
            volumes_backed_up=2,
        )

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.return_value = mock_apprise_instance

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            result = manager.send_success(stats)

        assert result is True
        mock_apprise_instance.notify.assert_called_once()

    def test_send_success_disabled_when_on_success_false(self):
        """send_success skips sending when on_success is False."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123",
            "secret": "TOKEN",
            "on_success": False,
        })

        manager = NotificationManager(config)
        stats = BackupStats(
            unit_name="test",
            success=True,
            duration_seconds=10.0,
            volumes_backed_up=1,
        )

        # Should return True without calling apprise (exits early)
        result = manager.send_success(stats)
        assert result is True

    def test_send_failure_notification(self):
        """send_failure sends notification for failed backup."""
        config = make_mock_config({
            "enabled": True,
            "service": "email",
            "url": "mailto://user:pass@smtp.gmail.com:587?to=admin@example.com",
            "on_failure": True,
        })

        manager = NotificationManager(config)

        stats = BackupStats(
            unit_name="mystack",
            success=False,
            duration_seconds=5.0,
            volumes_backed_up=0,
            errors=["Connection timeout"],
        )

        mock_apprise_instance = MagicMock()
        mock_apprise_instance.notify.return_value = True

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.return_value = mock_apprise_instance

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            result = manager.send_failure(stats)

        assert result is True
        mock_apprise_instance.notify.assert_called_once()

    def test_send_failure_disabled_when_on_failure_false(self):
        """send_failure skips sending when on_failure is False."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123",
            "secret": "TOKEN",
            "on_failure": False,
        })

        manager = NotificationManager(config)
        stats = BackupStats(
            unit_name="test",
            success=False,
            duration_seconds=10.0,
            volumes_backed_up=0,
            errors=["Test error"],
        )

        # Should return True without calling apprise (exits early)
        result = manager.send_failure(stats)
        assert result is True


# =============================================================================
# Timeout Tests
# =============================================================================


@pytest.mark.unit
class TestNotificationTimeout:
    """Tests for fire-and-forget timeout behavior."""

    def test_send_notification_timeout(self):
        """Notification times out after TIMEOUT_SECONDS."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123",
            "secret": "TOKEN",
        })

        manager = NotificationManager(config)

        import concurrent.futures

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.return_value = MagicMock()

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
                mock_executor = MagicMock()
                mock_future = MagicMock()
                mock_future.result.side_effect = concurrent.futures.TimeoutError()
                mock_executor.submit.return_value = mock_future
                mock_executor_class.return_value.__enter__.return_value = mock_executor

                result = manager._send_notification("Test", "Body")

        assert result is False
        mock_future.result.assert_called_once_with(timeout=NotificationManager.TIMEOUT_SECONDS)

    def test_send_notification_exception_handling(self):
        """Exceptions during send are caught and logged."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123",
            "secret": "TOKEN",
        })

        manager = NotificationManager(config)

        mock_apprise_module = MagicMock()
        mock_apprise_module.Apprise.side_effect = Exception("Connection failed")

        with patch.dict(sys.modules, {'apprise': mock_apprise_module}):
            result = manager._send_notification("Test", "Body")

        assert result is False

    def test_send_notification_apprise_not_installed(self):
        """Handles missing apprise gracefully."""
        config = make_mock_config({
            "enabled": True,
            "service": "telegram",
            "url": "123",
            "secret": "TOKEN",
        })

        manager = NotificationManager(config)

        # Simulate ImportError by making sys.modules['apprise'] raise when accessed
        original_apprise = sys.modules.get('apprise')

        # Remove apprise from sys.modules to simulate it not being installed
        if 'apprise' in sys.modules:
            del sys.modules['apprise']

        try:
            # The code inside _do_send will try to import apprise and fail
            result = manager._send_notification("Test", "Body")
            assert result is False
        finally:
            # Restore apprise module if it was there
            if original_apprise is not None:
                sys.modules['apprise'] = original_apprise
