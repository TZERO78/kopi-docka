import subprocess

import kopi_docka.cores.restore_manager as restore_manager


def make_manager() -> restore_manager.RestoreManager:
    """Create a RestoreManager instance without running __init__."""
    return restore_manager.RestoreManager.__new__(
        restore_manager.RestoreManager
    )


def test_list_containers_on_network_parses_output(monkeypatch):
    rm = make_manager()

    sample_output = "abc123;web\nxyz789;db\n"

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=sample_output, stderr="")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    containers = rm._list_containers_on_network("mynet", include_stopped=True)

    assert containers == [("abc123", "web"), ("xyz789", "db")]


def test_stop_containers_stops_and_returns_ids(monkeypatch):
    rm = make_manager()

    captured = {}

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    ids = rm._stop_containers([("abc123", "web"), ("xyz789", "db")], "mynet")

    assert ids == ["abc123", "xyz789"]
    assert captured["cmd"] == ["docker", "stop", "abc123", "xyz789"]


def test_stop_containers_handles_failure(monkeypatch):
    rm = make_manager()

    def fake_run(cmd, description, timeout=None, check=True, **kwargs):
        raise restore_manager.SubprocessError(cmd, 1, "boom")

    monkeypatch.setattr(restore_manager, "run_command", fake_run)

    ids = rm._stop_containers([("abc123", "web")], "mynet")

    assert ids == []
