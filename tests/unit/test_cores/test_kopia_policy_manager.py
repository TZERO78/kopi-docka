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
    def test_success_returns_true(self, policy):
        policy.repo._run = Mock(return_value=make_proc(returncode=0))
        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)
        assert result is True

    def test_failure_returns_false(self, policy):
        policy.repo._run = Mock(return_value=make_proc(returncode=1))
        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)
        assert result is False

    def test_none_result_returns_false(self, policy):
        policy.repo._run = Mock(return_value=None)
        result = policy.update_global_retention(10, 0, 7, 4, 12, 3)
        assert result is False

    def test_passes_correct_args(self, policy):
        policy.repo._run = Mock(return_value=make_proc(returncode=0))
        policy.update_global_retention(5, 2, 14, 8, 24, 6)
        call_args = policy.repo._run.call_args[0][0]
        assert "--keep-latest" in call_args
        assert "5" in call_args
        assert "--keep-daily" in call_args
        assert "14" in call_args
        assert "--global" in call_args

    def test_passes_annual_arg(self, policy):
        policy.repo._run = Mock(return_value=make_proc(returncode=0))
        policy.update_global_retention(10, 0, 7, 4, 12, 3)
        call_args = policy.repo._run.call_args[0][0]
        assert "--keep-annual" in call_args
        assert "3" in call_args


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
