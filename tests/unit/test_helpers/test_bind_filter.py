"""Unit tests for the user-editable host-internal bind-mount filter (Plan 0041)."""

import json

import pytest

from kopi_docka.helpers import bind_filter
from kopi_docka.types import BindMountInfo


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """Isolate the module-level cache and env between tests."""
    monkeypatch.delenv(bind_filter._ENV_VAR, raising=False)
    bind_filter.reset_cache()
    yield
    bind_filter.reset_cache()


@pytest.mark.unit
class TestShippedDefaults:
    def test_defaults_load_from_template(self):
        prefixes, basenames = bind_filter.get_host_internal_filter()
        assert "/etc" in prefixes
        assert "/var/lib/docker" in prefixes
        assert "docker.sock" in basenames
        # host root is NOT part of the list — it is hardcoded in the property
        assert "/" not in prefixes

    def test_result_is_cached(self):
        first = bind_filter.get_host_internal_filter()
        second = bind_filter.get_host_internal_filter()
        assert first is second


@pytest.mark.unit
class TestUserOverride:
    def test_env_override_replaces_prefixes(self, tmp_path, monkeypatch):
        f = tmp_path / "filter.json"
        f.write_text(json.dumps({"prefixes": ["/only/this"]}))
        monkeypatch.setenv(bind_filter._ENV_VAR, str(f))
        bind_filter.reset_cache()

        prefixes, basenames = bind_filter.get_host_internal_filter()
        assert prefixes == ("/only/this",)
        # basenames not defined in the user file → shipped default kept
        assert "docker.sock" in basenames

    def test_user_can_remove_etc(self, tmp_path, monkeypatch):
        """Removing /etc from the list makes /etc/passwd backupable again."""
        f = tmp_path / "filter.json"
        f.write_text(json.dumps({"prefixes": ["/proc", "/sys"]}))
        monkeypatch.setenv(bind_filter._ENV_VAR, str(f))
        bind_filter.reset_cache()

        assert BindMountInfo(source="/etc/passwd", destination="/x").is_host_internal is False
        assert BindMountInfo(source="/proc", destination="/x").is_host_internal is True

    def test_host_root_still_blocked_even_with_empty_filter(self, tmp_path, monkeypatch):
        """Safety guardrail: '/' is hardcoded and cannot be re-enabled via the file."""
        f = tmp_path / "filter.json"
        f.write_text(json.dumps({"prefixes": [], "basenames": []}))
        monkeypatch.setenv(bind_filter._ENV_VAR, str(f))
        bind_filter.reset_cache()

        assert BindMountInfo(source="/", destination="/host/root").is_host_internal is True


@pytest.mark.unit
class TestMalformedFallback:
    def test_invalid_json_falls_back_to_defaults(self, tmp_path, monkeypatch):
        f = tmp_path / "filter.json"
        f.write_text("{not valid json")
        monkeypatch.setenv(bind_filter._ENV_VAR, str(f))
        bind_filter.reset_cache()

        prefixes, _ = bind_filter.get_host_internal_filter()
        assert "/etc" in prefixes  # shipped default survived

    def test_wrong_type_ignored(self, tmp_path, monkeypatch):
        f = tmp_path / "filter.json"
        f.write_text(json.dumps({"prefixes": "not-a-list"}))
        monkeypatch.setenv(bind_filter._ENV_VAR, str(f))
        bind_filter.reset_cache()

        prefixes, _ = bind_filter.get_host_internal_filter()
        assert "/etc" in prefixes
