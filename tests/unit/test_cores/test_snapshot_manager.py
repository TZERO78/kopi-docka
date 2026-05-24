"""Unit tests for SnapshotManager (Plan 0024)."""

from unittest.mock import Mock, patch, MagicMock
import pytest

from kopi_docka.cores.snapshot_manager import SnapshotManager


SAMPLE_SNAPSHOTS = [
    {
        "id": "abc123def456abc123def456abc123de",
        "path": "/backup/mystack",
        "timestamp": "2026-04-01T10:00:00Z",
        "tags": {"unit": "mystack", "type": "recipe"},
        "size": 1024 * 1024 * 50,
    },
    {
        "id": "xyz789xyz789xyz789xyz789xyz789xy",
        "path": "/backup/otherstack",
        "timestamp": "2026-04-02T12:00:00Z",
        "tags": {"unit": "otherstack"},
        "size": 1024 * 1024 * 200,
    },
]


@pytest.fixture
def manager():
    """SnapshotManager with mocked repo and policy."""
    m = SnapshotManager.__new__(SnapshotManager)
    m.repo = Mock()
    m.policy = Mock()
    m.config = Mock()
    m.config.getint.side_effect = lambda section, key, default=0: {
        "latest": 10,
        "hourly": 0,
        "daily": 7,
        "weekly": 4,
        "monthly": 12,
        "annual": 3,
    }.get(key, default)
    return m


class TestCmdDelete:
    def test_delete_with_force_skips_confirm(self, manager):
        manager.repo.delete_snapshot = Mock()
        manager.cmd_delete("abc123", force=True)
        manager.repo.delete_snapshot.assert_called_once_with("abc123")

    def test_delete_aborted_on_no_confirm(self, manager, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "no")
        manager.repo.delete_snapshot = Mock()
        manager.cmd_delete("abc123", force=False)
        manager.repo.delete_snapshot.assert_not_called()

    def test_delete_proceeds_on_yes_confirm(self, manager, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        manager.repo.delete_snapshot = Mock()
        manager.cmd_delete("abc123", force=False)
        manager.repo.delete_snapshot.assert_called_once_with("abc123")

    def test_delete_handles_exception(self, manager, capsys):
        manager.repo.delete_snapshot.side_effect = RuntimeError("kopia error")
        manager.cmd_delete("abc123", force=True)
        # Should not raise — error is printed


class TestCmdPin:
    def test_pin_success(self, manager, capsys):
        manager.repo.pin_snapshot.return_value = True
        manager.cmd_pin("abc123")
        manager.repo.pin_snapshot.assert_called_once_with("abc123")

    def test_pin_failure(self, manager, capsys):
        manager.repo.pin_snapshot.return_value = False
        manager.cmd_pin("abc123")
        manager.repo.pin_snapshot.assert_called_once_with("abc123")


class TestCmdUnpin:
    def test_unpin_success(self, manager):
        manager.repo.unpin_snapshot.return_value = True
        manager.cmd_unpin("abc123")
        manager.repo.unpin_snapshot.assert_called_once_with("abc123")

    def test_unpin_failure(self, manager):
        manager.repo.unpin_snapshot.return_value = False
        manager.cmd_unpin("abc123")
        manager.repo.unpin_snapshot.assert_called_once_with("abc123")


class TestCmdRetentionSet:
    def test_explicit_args_update_policy_and_config(self, manager):
        manager.policy.update_global_retention.return_value = True
        manager.cmd_retention_set(
            latest=10, hourly=0, daily=7, weekly=4, monthly=12, annual=3,
        )
        manager.policy.update_global_retention.assert_called_once_with(10, 0, 7, 4, 12, 3)
        manager.config.update_retention.assert_called_once_with(10, 0, 7, 4, 12, 3)

    def test_does_not_update_config_on_kopia_failure(self, manager):
        manager.policy.update_global_retention.return_value = False
        manager.cmd_retention_set(
            latest=10, hourly=0, daily=7, weekly=4, monthly=12, annual=3,
        )
        manager.config.update_retention.assert_not_called()

    def test_partial_args_keep_other_values_from_config(self, manager):
        """v7.3.7: passing --daily 14 alone must NOT clobber the other five
        values with arbitrary defaults — they come from the current config."""
        manager.policy.update_global_retention.return_value = True
        manager.cmd_retention_set(daily=14)
        # The other 5 values should mirror what manager.config.getint returns
        # (latest=10, hourly=0, weekly=4, monthly=12, annual=3 in the fixture).
        manager.policy.update_global_retention.assert_called_once_with(10, 0, 14, 4, 12, 3)
        manager.config.update_retention.assert_called_once_with(10, 0, 14, 4, 12, 3)

    def test_no_args_no_force_aborts_without_calling_kopia(self, manager):
        """An empty `retention set` invocation is almost certainly user error
        — the call would be a 30-90 s no-op on rclone. Prompt instead."""
        manager.cmd_retention_set()
        manager.policy.update_global_retention.assert_not_called()
        manager.config.update_retention.assert_not_called()

    def test_no_args_with_force_applies_current_config_values(self, manager):
        """--force on an otherwise empty invocation is the documented way to
        explicitly re-write current values back to Kopia."""
        manager.policy.update_global_retention.return_value = True
        manager.cmd_retention_set(force=True)
        manager.policy.update_global_retention.assert_called_once_with(10, 0, 7, 4, 12, 3)
        manager.config.update_retention.assert_called_once_with(10, 0, 7, 4, 12, 3)


class TestCmdPruneEmpty:
    def test_dry_run_does_not_call_expire(self, manager):
        manager.repo.list_snapshots.return_value = SAMPLE_SNAPSHOTS
        manager.cmd_prune_empty(dry_run=True)
        manager.repo.expire_snapshots.assert_not_called()

    def test_dry_run_calls_list_snapshots(self, manager):
        manager.repo.list_snapshots.return_value = SAMPLE_SNAPSHOTS
        manager.cmd_prune_empty(dry_run=True)
        manager.repo.list_snapshots.assert_called_once()

    def test_non_dry_run_calls_expire(self, manager):
        manager.repo.expire_snapshots.return_value = True
        manager.cmd_prune_empty(dry_run=False)
        manager.repo.expire_snapshots.assert_called_once()

    def test_non_dry_run_expire_failure(self, manager):
        manager.repo.expire_snapshots.return_value = False
        manager.cmd_prune_empty(dry_run=False)  # Should not raise


class TestCmdMaintenance:
    def test_quick_maintenance(self, manager):
        manager.cmd_maintenance(full=False)
        manager.repo.maintenance_run.assert_called_once_with(full=False)

    def test_full_maintenance(self, manager):
        manager.cmd_maintenance(full=True)
        manager.repo.maintenance_run.assert_called_once_with(full=True)

    def test_maintenance_handles_exception(self, manager):
        manager.repo.maintenance_run.side_effect = RuntimeError("kopia error")
        manager.cmd_maintenance(full=False)  # Should not raise


class TestPickSnapshot:
    def test_valid_index(self, manager):
        snap = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "1")
        assert snap["id"] == SAMPLE_SNAPSHOTS[0]["id"]

    def test_valid_index_second(self, manager):
        snap = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "2")
        assert snap["id"] == SAMPLE_SNAPSHOTS[1]["id"]

    def test_out_of_range_returns_none(self, manager):
        result = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "99")
        assert result is None

    def test_zero_index_returns_none(self, manager):
        result = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "0")
        assert result is None

    def test_non_numeric_returns_none(self, manager):
        result = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "abc")
        assert result is None

    def test_negative_returns_none(self, manager):
        result = manager._pick_snapshot(SAMPLE_SNAPSHOTS, "-1")
        assert result is None


class TestCurrentRetentionFromConfig:
    def test_returns_all_keys(self, manager):
        result = manager._current_retention_from_config()
        assert set(result.keys()) == {"latest", "hourly", "daily", "weekly", "monthly", "annual"}

    def test_values_from_config(self, manager):
        result = manager._current_retention_from_config()
        assert result["latest"] == 10
        assert result["daily"] == 7


class TestFmtSize:
    def test_zero(self):
        assert SnapshotManager._fmt_size(0) == "-"

    def test_negative(self):
        assert SnapshotManager._fmt_size(-1) == "-"

    def test_bytes(self):
        result = SnapshotManager._fmt_size(500)
        assert "B" in result

    def test_kilobytes(self):
        result = SnapshotManager._fmt_size(1500)
        assert "KB" in result

    def test_megabytes(self):
        result = SnapshotManager._fmt_size(1024 * 1024 * 5)
        assert "MB" in result

    def test_gigabytes(self):
        result = SnapshotManager._fmt_size(1024 ** 3 * 2)
        assert "GB" in result


class TestFmtTimestamp:
    def test_empty_string(self):
        assert SnapshotManager._fmt_timestamp("") == "-"

    def test_iso_format(self):
        result = SnapshotManager._fmt_timestamp("2026-04-01T10:00:00Z")
        assert "2026-04-01" in result

    def test_invalid_format_returns_truncated(self):
        result = SnapshotManager._fmt_timestamp("not-a-date-at-all-here")
        assert len(result) > 0


class TestInteractiveManage:
    def test_exits_when_not_connected(self, manager, capsys):
        manager.repo.is_connected.return_value = False
        manager.interactive_manage()
        manager.repo.is_connected.assert_called_once()

    def test_shows_menu_when_connected(self, manager, monkeypatch):
        manager.repo.is_connected.return_value = True
        # Immediately quit
        monkeypatch.setattr("builtins.input", lambda _: "q")
        manager.interactive_manage()


class TestCmdRetentionShow:
    def test_calls_display_retention(self, manager):
        manager.policy.get_global_policy.return_value = {}
        manager.cmd_retention_show()
        manager.policy.get_global_policy.assert_called_once()

    def test_renders_kopia_values_from_retention_key(self, manager, capsys):
        """v7.3.1 fix: Kopia returns retention under the ``retention`` key,
        not ``retentionPolicy``. _display_retention must read it from there
        — otherwise the user sees "Kopia policy unavailable" on a healthy
        repo (the bug that surfaced this fix).
        """
        manager.policy.get_global_policy.return_value = {
            "retention": {
                "keepLatest": 10,
                "keepHourly": 48,
                "keepDaily": 7,
                "keepWeekly": 4,
                "keepMonthly": 24,
                "keepAnnual": 3,
            }
        }
        manager.cmd_retention_show()
        captured = capsys.readouterr()
        output = captured.out
        assert "keepLatest=10" in output
        assert "keepHourly=48" in output
        assert "keepMonthly=24" in output
        assert "Kopia policy unavailable" not in output

    def test_accepts_legacy_retentionPolicy_key_too(self, manager, capsys):
        """Defensive: if Kopia ever ships the older ``retentionPolicy``
        shape again, we still render values."""
        manager.policy.get_global_policy.return_value = {
            "retentionPolicy": {
                "keepLatest": 5,
                "keepDaily": 2,
            }
        }
        manager.cmd_retention_show()
        captured = capsys.readouterr()
        assert "keepLatest=5" in captured.out
        assert "Kopia policy unavailable" not in captured.out

    def test_empty_policy_renders_unavailable(self, manager, capsys):
        manager.policy.get_global_policy.return_value = {}
        manager.cmd_retention_show()
        assert "Kopia policy unavailable" in capsys.readouterr().out
