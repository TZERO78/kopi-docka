"""
Unit tests for BindRestoreEngine (Plan 0040 / #129).

The engine restores persistent bind-mount snapshots back to their original
host path, so a backup that captured bind data (incl. secrets) is actually
recoverable through the wizard.
"""

import pytest
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from kopi_docka.cores.restore.bind_restore import BindRestoreEngine


def make_engine(non_interactive=True):
    repo = Mock()
    repo.restore_snapshot = Mock()
    repo._get_config_file = Mock(return_value="/cfg/kopia.config")
    return BindRestoreEngine(repo, non_interactive=non_interactive), repo


def _snap(source="/opt/vw-data", dest="/data", snap_id="abc123def456", ro=False):
    return {
        "id": snap_id,
        "tags": {
            "type": "bind",
            "bind_source": source,
            "bind_destination": dest,
            "read_only": "true" if ro else "false",
        },
    }


@pytest.mark.unit
class TestRestoreAll:
    def test_empty_returns_zero(self):
        engine, repo = make_engine()
        assert engine.restore_all([], "unit") == 0
        repo.restore_snapshot.assert_not_called()

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_counts_successful_restores(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        s1 = _snap(source=str(tmp_path / "a"))
        s2 = _snap(source=str(tmp_path / "b"))
        assert engine.restore_all([s1, s2], "unit") == 2
        assert repo.restore_snapshot.call_count == 2

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_skips_snapshot_without_source(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        bad = {"id": "x", "tags": {"type": "bind"}}  # no bind_source
        good = _snap(source=str(tmp_path / "a"))
        assert engine.restore_all([bad, good], "unit") == 1
        repo.restore_snapshot.assert_called_once()


@pytest.mark.unit
class TestExecute:
    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_restores_to_host_path_and_creates_dir(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        target = tmp_path / "vw-data"  # does not exist yet

        ok = engine._execute(str(target), "snap123456789", "vault", None)

        assert ok is True
        assert target.exists()  # engine mkdir -p'd the host path
        # restored the snapshot through KopiaRepository (not direct subprocess)
        repo.restore_snapshot.assert_called_once()
        assert repo.restore_snapshot.call_args.args[0] == "snap123456789"
        # rsync was invoked to sync into place
        rsync_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "rsync"]
        assert len(rsync_calls) == 1
        assert rsync_calls[0].args[0][-1] == f"{target}/"

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_safety_backup_when_existing_content(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        target = tmp_path / "vw-data"
        target.mkdir()
        (target / "db.sqlite3").write_text("secret")  # existing content

        engine._execute(str(target), "snap1", "vault", None)

        tar_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "tar"]
        assert len(tar_calls) == 1  # safety backup taken before overwrite

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_no_safety_backup_for_empty_path(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        target = tmp_path / "empty"
        target.mkdir()

        engine._execute(str(target), "snap1", "vault", None)

        tar_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "tar"]
        assert tar_calls == []

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_rsync_failure_falls_back_to_cp(self, mock_run, tmp_path):
        target = tmp_path / "vw-data"

        def side_effect(cmd, *a, **k):
            rc = 1 if cmd[0] == "rsync" else 0
            return CompletedProcess([], rc, stdout="", stderr="")

        mock_run.side_effect = side_effect
        engine, repo = make_engine()
        ok = engine._execute(str(target), "snap1", "vault", None)

        assert ok is True
        cp_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "cp"]
        assert len(cp_calls) == 1

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    def test_registers_temp_dir_with_safety_handler(self, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine()
        handler = Mock()
        engine._execute(str(tmp_path / "d"), "snap1", "vault", handler)
        handler.register_temp_dir.assert_called_once()


@pytest.mark.unit
class TestInteractive:
    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    @patch("builtins.input", return_value="no")
    def test_no_prints_manual_and_skips(self, mock_input, mock_run, tmp_path):
        engine, repo = make_engine(non_interactive=False)
        assert engine.restore_all([_snap(source=str(tmp_path / "a"))], "unit") == 0
        repo.restore_snapshot.assert_not_called()

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    @patch("builtins.input", return_value="q")
    def test_quit_skips(self, mock_input, mock_run, tmp_path):
        engine, repo = make_engine(non_interactive=False)
        assert engine.restore_all([_snap(source=str(tmp_path / "a"))], "unit") == 0
        repo.restore_snapshot.assert_not_called()

    @patch("kopi_docka.cores.restore.bind_restore.run_command")
    @patch("builtins.input", return_value="yes")
    def test_yes_restores(self, mock_input, mock_run, tmp_path):
        mock_run.return_value = CompletedProcess([], 0, stdout="", stderr="")
        engine, repo = make_engine(non_interactive=False)
        assert engine.restore_all([_snap(source=str(tmp_path / "a"))], "unit") == 1
        repo.restore_snapshot.assert_called_once()
