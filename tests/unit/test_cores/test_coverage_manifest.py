"""
Unit tests for the backup coverage manifest (Plan 0040 Phase 2 / #129).

The manifest is a receipt: every discovered dependency + its status
(backed_up / skipped_runtime / not_protected / not_supported).
"""

import textwrap
import pytest

from kopi_docka.cores.coverage_manifest import (
    build_manifest,
    declared_env_files,
    render_summary,
    STATUS_BACKED_UP,
    STATUS_SKIPPED_RUNTIME,
    STATUS_NOT_PROTECTED,
    STATUS_NOT_SUPPORTED,
)
from kopi_docka.types import BackupUnit, ContainerInfo, VolumeInfo


def _container(mounts=None, inspect_mounts=None):
    return ContainerInfo(
        id="c1", name="app", image="alpine", status="running",
        inspect_data={"Mounts": inspect_mounts or []},
    )


def _unit(containers=None, volumes=None, compose_files=None):
    return BackupUnit(
        name="vault", type="stack",
        containers=containers or [],
        volumes=volumes or [],
        compose_files=compose_files or [],
    )


def _by_kind(m, kind):
    return [e for e in m.entries if e.kind == kind]


@pytest.mark.unit
class TestMountClassification:
    def test_named_volume_backed_up(self):
        c = _container(inspect_mounts=[{"Type": "volume", "Name": "pgdata", "Destination": "/db"}])
        u = _unit(containers=[c], volumes=[VolumeInfo(name="pgdata", driver="local", mountpoint="/m")])
        m = build_manifest(u)
        vol = _by_kind(m, "volume")
        assert len(vol) == 1 and vol[0].status == STATUS_BACKED_UP

    def test_volume_not_in_backup_set_is_unprotected(self):
        c = _container(inspect_mounts=[{"Type": "volume", "Name": "orphan", "Destination": "/x"}])
        u = _unit(containers=[c], volumes=[])  # not in backup set
        m = build_manifest(u)
        assert _by_kind(m, "volume")[0].status == STATUS_NOT_PROTECTED

    def test_persistent_bind_backed_up(self):
        c = _container(inspect_mounts=[
            {"Type": "bind", "Source": "/opt/vw-data", "Destination": "/data", "RW": True}])
        m = build_manifest(_unit(containers=[c]))
        b = _by_kind(m, "bind")
        assert len(b) == 1 and b[0].status == STATUS_BACKED_UP

    def test_runtime_bind_skipped(self):
        c = _container(inspect_mounts=[
            {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}])
        m = build_manifest(_unit(containers=[c]))
        rt = _by_kind(m, "runtime_mount")
        assert len(rt) == 1 and rt[0].status == STATUS_SKIPPED_RUNTIME

    def test_tmpfs_skipped(self):
        c = _container(inspect_mounts=[{"Type": "tmpfs", "Destination": "/tmp"}])
        m = build_manifest(_unit(containers=[c]))
        assert _by_kind(m, "runtime_mount")[0].status == STATUS_SKIPPED_RUNTIME

    def test_dedupes_shared_mounts(self):
        m1 = {"Type": "bind", "Source": "/shared", "Destination": "/s", "RW": True}
        c1 = ContainerInfo(id="c1", name="a", image="i", status="running", inspect_data={"Mounts": [m1]})
        c2 = ContainerInfo(id="c2", name="b", image="i", status="running", inspect_data={"Mounts": [m1]})
        m = build_manifest(_unit(containers=[c1, c2]))
        assert len(_by_kind(m, "bind")) == 1


@pytest.mark.unit
class TestComposeAndConfig:
    def test_compose_file_backed_up(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text("services: {}\n")
        m = build_manifest(_unit(compose_files=[cf]))
        cfe = [e for e in m.entries if e.kind == "compose_file"]
        assert cfe and cfe[0].status == STATUS_BACKED_UP

    def test_missing_compose_file_unprotected(self, tmp_path):
        cf = tmp_path / "gone.yml"
        m = build_manifest(_unit(compose_files=[cf]))
        assert [e for e in m.entries if e.kind == "compose_file"][0].status == STATUS_NOT_PROTECTED

    def test_adjacent_env_captured_as_project_file(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text("services: {}\n")
        (tmp_path / ".env").write_text("A=1\n")
        m = build_manifest(_unit(compose_files=[cf]))
        pf = [e for e in m.entries if e.kind == "project_file"]
        assert any(e.identifier.endswith(".env") and e.status == STATUS_BACKED_UP for e in pf)


@pytest.mark.unit
class TestComposeDeclared:
    def test_env_file_outside_compose_dir_unprotected(self, tmp_path):
        cdir = tmp_path / "stack"
        cdir.mkdir()
        outside = tmp_path / "shared"
        outside.mkdir()
        (outside / "common.env").write_text("X=1\n")
        cf = cdir / "docker-compose.yml"
        cf.write_text(textwrap.dedent("""
            services:
              app:
                image: alpine
                env_file:
                  - ../shared/common.env
        """))
        m = build_manifest(_unit(compose_files=[cf]))
        ef = [e for e in m.entries if e.kind == "env_file"]
        assert ef and ef[0].status == STATUS_NOT_PROTECTED
        assert "outside" in ef[0].detail

    def test_external_swarm_secret_not_supported(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text(textwrap.dedent("""
            services:
              app:
                image: alpine
            secrets:
              db_password:
                external: true
        """))
        m = build_manifest(_unit(compose_files=[cf]))
        sec = [e for e in m.entries if e.kind == "swarm_secret"]
        assert sec and sec[0].status == STATUS_NOT_SUPPORTED

    def test_unparseable_compose_marked_not_supported(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text("services: [unbalanced\n")  # invalid YAML
        m = build_manifest(_unit(compose_files=[cf]))
        # compose_file appears twice: backed_up (exists) + not_supported (parse fail)
        statuses = {e.status for e in m.entries if e.kind == "compose_file"}
        assert STATUS_NOT_SUPPORTED in statuses


@pytest.mark.unit
class TestSummaryAndRender:
    def test_summary_counts_and_has_gaps(self, tmp_path):
        c = _container(inspect_mounts=[
            {"Type": "bind", "Source": "/opt/data", "Destination": "/data", "RW": True},
            {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/sock"},
        ])
        cf = tmp_path / "docker-compose.yml"
        cf.write_text(textwrap.dedent("""
            services:
              app:
                image: alpine
            secrets:
              s:
                external: true
        """))
        m = build_manifest(_unit(containers=[c], compose_files=[cf]))
        s = m.summary
        assert s[STATUS_BACKED_UP] >= 1
        assert s[STATUS_SKIPPED_RUNTIME] == 1
        assert s[STATUS_NOT_SUPPORTED] == 1
        assert m.has_gaps is True

    def test_no_gaps_when_all_covered(self):
        c = _container(inspect_mounts=[{"Type": "bind", "Source": "/opt/data", "Destination": "/d", "RW": True}])
        m = build_manifest(_unit(containers=[c]))
        assert m.has_gaps is False

    def test_to_dict_shape(self):
        c = _container(inspect_mounts=[{"Type": "bind", "Source": "/opt/data", "Destination": "/d", "RW": True}])
        d = build_manifest(_unit(containers=[c])).to_dict()
        assert set(d.keys()) >= {"unit", "summary", "has_gaps", "dependencies"}
        assert d["dependencies"][0]["kind"] == "bind"

    def test_render_summary_lists_gaps(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text("services:\n  app:\n    image: alpine\nsecrets:\n  s:\n    external: true\n")
        lines = render_summary(build_manifest(_unit(compose_files=[cf])))
        assert any("unsupported" in lines[0] for _ in [0])
        assert any("swarm_secret" in ln for ln in lines[1:])


@pytest.mark.unit
class TestDeclaredEnvFiles:
    """declared_env_files() returns exactly what the manifest reports as backed up."""

    def _compose(self, d, body):
        cf = d / "docker-compose.yml"
        cf.write_text(textwrap.dedent(body))
        return cf

    def test_env_file_without_dot_prefix_is_returned(self, tmp_path):
        (tmp_path / "dashboard.env").write_text("A=1\n")
        cf = self._compose(tmp_path, """
            services:
              dashboard:
                image: alpine
                env_file: dashboard.env
        """)
        assert declared_env_files([cf]) == [(tmp_path / "dashboard.env").resolve()]

    def test_list_and_dict_forms(self, tmp_path):
        (tmp_path / "a.env").write_text("A=1\n")
        (tmp_path / "b.env").write_text("B=1\n")
        cf = self._compose(tmp_path, """
            services:
              x:
                env_file: [a.env]
              y:
                env_file:
                  - path: ./b.env
                    required: false
                  - a.env
        """)
        names = [p.name for p in declared_env_files([cf])]
        assert names == ["a.env", "b.env"]

    def test_outside_subdir_and_missing_are_skipped(self, tmp_path):
        stack = tmp_path / "stack"
        (stack / "env").mkdir(parents=True)
        (stack / "env" / "sub.env").write_text("S=1\n")
        (tmp_path / "shared.env").write_text("X=1\n")
        cf = self._compose(stack, """
            services:
              app:
                env_file: [../shared.env, env/sub.env, missing.env]
        """)
        assert declared_env_files([cf]) == []

    def test_unparseable_compose_is_skipped(self, tmp_path):
        cf = tmp_path / "docker-compose.yml"
        cf.write_text("services: [unclosed\n")
        assert declared_env_files([cf]) == []

    def test_manifest_and_helper_agree(self, tmp_path):
        (tmp_path / "dashboard.env").write_text("A=1\n")
        cf = self._compose(tmp_path, """
            services:
              dashboard:
                env_file: dashboard.env
        """)
        m = build_manifest(_unit(compose_files=[cf]))
        backed = {e.identifier for e in m.entries if e.kind == "env_file" and e.status == STATUS_BACKED_UP}
        assert backed == {str(p) for p in declared_env_files([cf])}
