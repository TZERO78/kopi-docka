"""
Integration test: persistent bind-mount backup → restore cycle (Plan 0040 / #129).

Vaultwarden-style stack: a container with a host bind mount (`./vw-data:/data`).
Exercises the real tools end-to-end without root (bind sources are user-owned
host paths, unlike named volumes under /var/lib/docker):

1. real Docker container with a bind mount + compose label
2. real DockerDiscovery parses the bind mount out of `docker inspect`
3. real Kopia filesystem repo snapshots the bind source
4. real BindRestoreEngine restores it after the host data is wiped
5. byte-identical verification (incl. a "secret" file)
"""

import json
import os
import subprocess
import pytest

from kopi_docka.cores.docker_discovery import DockerDiscovery
from kopi_docka.cores.backup_manager import BackupManager
from kopi_docka.cores.restore.bind_restore import BindRestoreEngine
from kopi_docka.types import BackupUnit


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def kopia_available() -> bool:
    try:
        return subprocess.run(["kopia", "--version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
    pytest.mark.skipif(not docker_available(), reason="Docker daemon not available"),
    pytest.mark.skipif(not kopia_available(), reason="Kopia not installed"),
]


class _KopiaAdapter:
    """Minimal repo the BindRestoreEngine needs: restore + config-file path."""

    def __init__(self, config_file: str, env: dict):
        self._config_file = config_file
        self._env = env

    def _get_config_file(self) -> str:
        return self._config_file

    def restore_snapshot(self, snapshot_id: str, target_path: str) -> None:
        subprocess.run(
            ["kopia", "snapshot", "restore", snapshot_id, "--config-file", self._config_file, target_path],
            check=True,
            capture_output=True,
            env=self._env,
        )


@pytest.fixture
def bind_container(tmp_path):
    """Start an alpine container with a host bind mount + compose label."""
    host_dir = tmp_path / "vw-data"
    host_dir.mkdir()
    (host_dir / "db.sqlite3").write_text("VAULT-SECRET-CONTENT")
    (host_dir / "config.json").write_text('{"token": "s3cr3t"}')
    sub = host_dir / "attachments"
    sub.mkdir()
    (sub / "file.bin").write_bytes(b"\x00\x01\x02binary")

    name = f"kopidocka-e2e-{os.getpid()}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            "-v", f"{host_dir}:/data",
            "--label", "com.docker.compose.project=e2e-vault",
            "alpine:latest", "sleep", "600",
        ],
        check=True,
        capture_output=True,
    )
    try:
        yield {"name": name, "host_dir": host_dir}
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture
def ephemeral_repo(tmp_path):
    repo_path = tmp_path / "kopia_repo"
    config_file = tmp_path / "kopia.config"
    env = os.environ.copy()
    env["KOPIA_PASSWORD"] = "e2e-password-123"
    subprocess.run(
        ["kopia", "repository", "create", "filesystem",
         "--path", str(repo_path), "--config-file", str(config_file)],
        check=True, capture_output=True, env=env,
    )
    return {"config_file": str(config_file), "env": env}


def test_bind_mount_backup_restore_cycle(bind_container, ephemeral_repo):
    host_dir = bind_container["host_dir"]
    name = bind_container["name"]

    # 1) Real discovery: parse the container's bind mount from docker inspect
    inspect = subprocess.run(
        ["docker", "inspect", name], check=True, capture_output=True, text=True
    )
    data = json.loads(inspect.stdout)[0]

    discovery = DockerDiscovery.__new__(DockerDiscovery)
    discovery.docker_socket = "/var/run/docker.sock"
    info = discovery._parse_container_info(data)

    binds = {b.source: b for b in info.bind_mounts}
    assert str(host_dir) in binds, f"bind mount not discovered: {info.bind_mounts}"
    assert binds[str(host_dir)].destination == "/data"

    # 2) Real backup-side code: aggregate into a unit and build the BackupSource
    #    (tags + path) through BackupManager — not a hand-rolled snapshot call.
    unit = BackupUnit(name="e2e-vault", type="stack", containers=[info])
    unit.bind_mounts = discovery._aggregate_bind_mounts([info])

    manager = BackupManager.__new__(BackupManager)
    manager.exclude_patterns = []
    sources = manager._collect_bind_mount_sources(unit, "backup-id-e2e", "standard")
    assert len(sources) == 1
    src = sources[0]
    assert src.path == str(host_dir)
    assert src.tags["bind_source"] == str(host_dir)
    assert src.tags["bind_destination"] == "/data"

    # Snapshot exactly what the backup path would: src.path with src.tags
    snap_cmd = ["kopia", "snapshot", "create", src.path,
                "--config-file", ephemeral_repo["config_file"], "--json"]
    for k, v in src.tags.items():
        snap_cmd += ["--tags", f"{k}:{v}"]
    snap = subprocess.run(
        snap_cmd, check=True, capture_output=True, text=True, env=ephemeral_repo["env"]
    )
    out = json.loads(snap.stdout)
    snap_id = out.get("id") or out.get("snapshotID")
    assert snap_id

    # 3) Simulate data loss: wipe the host bind directory contents
    (host_dir / "db.sqlite3").unlink()
    (host_dir / "config.json").write_text("CORRUPTED")
    import shutil
    shutil.rmtree(host_dir / "attachments")

    # 4) Real restore via BindRestoreEngine (non-interactive)
    engine = BindRestoreEngine(
        _KopiaAdapter(ephemeral_repo["config_file"], ephemeral_repo["env"]),
        non_interactive=True,
    )
    bind_snapshot = {"id": snap_id, "tags": src.tags}  # tags built by real backup code
    restored = engine.restore_all([bind_snapshot], "e2e-vault")
    assert restored == 1

    # 5) Byte-identical verification, including the secret
    assert (host_dir / "db.sqlite3").read_text() == "VAULT-SECRET-CONTENT"
    assert (host_dir / "config.json").read_text() == '{"token": "s3cr3t"}'
    assert (host_dir / "attachments" / "file.bin").read_bytes() == b"\x00\x01\x02binary"
