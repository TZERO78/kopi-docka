"""Unit tests for KopiaPolicyManager."""

import json
from unittest.mock import Mock
import pytest

from kopi_docka.cores.kopia_policy_manager import KopiaPolicyManager


@pytest.fixture
def mock_repo():
    repo = Mock()
    repo._get_config_file.return_value = "/tmp/kopia.config"
    return repo


@pytest.fixture
def policy(mock_repo):
    return KopiaPolicyManager(mock_repo)


def make_proc(stdout="", returncode=0):
    proc = Mock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


class TestGetGlobalPolicy:
    def test_returns_parsed_json(self, policy):
        data = {"retentionPolicy": {"keepLatest": 10}}
        policy.repo._run = Mock(return_value=make_proc(json.dumps(data)))
        result = policy.get_global_policy()
        assert result["retentionPolicy"]["keepLatest"] == 10

    def test_returns_empty_dict_on_failure(self, policy):
        policy.repo._run = Mock(return_value=make_proc(returncode=1))
        result = policy.get_global_policy()
        assert result == {}

    def test_returns_empty_dict_on_none_result(self, policy):
        policy.repo._run = Mock(return_value=None)
        result = policy.get_global_policy()
        assert result == {}

    def test_returns_empty_dict_on_empty_stdout(self, policy):
        policy.repo._run = Mock(return_value=make_proc(stdout=""))
        result = policy.get_global_policy()
        assert result == {}


class TestUpdateGlobalRetention:
    """v7.3.9: read-before-write. The first ``_run`` call is always
    ``kopia policy show --global --json`` (cheap read); the ``policy
    set`` call only happens when the current policy doesn't already
    match the requested values. Tests below feed two-element
    ``side_effect`` arrays so both calls are stubbed.
    """

    def _show_response(self, **retention):
        """Build a fake `policy show --global --json` response with the
        given retention values. Empty retention dict by default."""
        return make_proc(
            stdout=json.dumps({"retention": retention}),
            returncode=0,
        )

    def test_skips_write_when_kopia_already_matches(self, policy):
        """The whole point of this fix: a redundant call must NOT issue
        the multi-minute `policy set` round-trip on rclone backends."""
        policy.repo._run = Mock(side_effect=[
            self._show_response(
                keepLatest=10, keepHourly=0, keepDaily=7,
                keepWeekly=4, keepMonthly=12, keepAnnual=3,
            ),
        ])

        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)

        assert result is True
        # Only the read happened; no second call.
        assert policy.repo._run.call_count == 1
        assert "show" in policy.repo._run.call_args_list[0].args[0]

    def test_writes_when_kopia_does_not_match(self, policy):
        policy.repo._run = Mock(side_effect=[
            self._show_response(keepLatest=999),  # drifted
            make_proc(returncode=0),              # the write
        ])

        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)

        assert result is True
        assert policy.repo._run.call_count == 2
        write_args = policy.repo._run.call_args_list[1].args[0]
        assert "set" in write_args
        assert "--keep-latest" in write_args

    def test_writes_when_show_returns_nothing(self, policy):
        """If the show fails for any reason we fall back to writing —
        better safe than skipping when we can't be sure."""
        policy.repo._run = Mock(side_effect=[
            make_proc(returncode=1, stdout=""),   # show fails
            make_proc(returncode=0),              # write
        ])

        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)

        assert result is True
        assert policy.repo._run.call_count == 2

    def test_write_failure_returns_false(self, policy):
        policy.repo._run = Mock(side_effect=[
            self._show_response(keepLatest=999),   # drifted
            make_proc(returncode=1),               # write fails
        ])

        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)

        assert result is False

    def test_writes_when_only_one_value_differs(self, policy):
        """All six values must match — a single mismatch triggers the
        write (otherwise drift in one knob would never be corrected)."""
        policy.repo._run = Mock(side_effect=[
            self._show_response(
                keepLatest=10, keepHourly=0, keepDaily=7,
                keepWeekly=4, keepMonthly=999, keepAnnual=3,  # monthly drifted
            ),
            make_proc(returncode=0),
        ])

        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)

        assert result is True
        assert policy.repo._run.call_count == 2

    def test_passes_correct_args(self, policy):
        policy.repo._run = Mock(side_effect=[
            self._show_response(),       # empty — forces write
            make_proc(returncode=0),
        ])
        policy.update_global_retention(5, 2, 14, 8, 24, 6)

        write_args = policy.repo._run.call_args_list[1].args[0]
        assert "--keep-latest" in write_args
        assert "5" in write_args
        assert "--keep-daily" in write_args
        assert "14" in write_args
        assert "--global" in write_args

    def test_passes_annual_arg(self, policy):
        policy.repo._run = Mock(side_effect=[
            self._show_response(),
            make_proc(returncode=0),
        ])
        policy.update_global_retention(10, 0, 7, 4, 12, 3)
        write_args = policy.repo._run.call_args_list[1].args[0]
        assert "--keep-annual" in write_args
        assert "3" in write_args


class TestRunPassthrough:
    def test_adds_config_file_if_missing(self, policy, mock_repo):
        mock_repo._run = Mock(return_value=make_proc())
        policy._run(["kopia", "policy", "show"])
        called_args = mock_repo._run.call_args[0][0]
        assert "--config-file" in called_args

    def test_does_not_duplicate_config_file(self, policy, mock_repo):
        mock_repo._run = Mock(return_value=make_proc())
        policy._run(["kopia", "--config-file", "/existing.conf", "policy", "show"])
        called_args = mock_repo._run.call_args[0][0]
        assert called_args.count("--config-file") == 1
