"""Unit tests for helpers/config.py — Config class, models, and pure functions."""

import json
import os
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from kopi_docka.helpers.config import (
    Config,
    RetentionConfig,
    detect_repository_type,
    extract_filesystem_path,
    generate_secure_password,
)


# ============================================================================
# Pure function tests
# ============================================================================

class TestDetectRepositoryType:
    def test_filesystem(self):
        assert detect_repository_type("filesystem --path /backup") == "filesystem"

    def test_s3(self):
        assert detect_repository_type("s3 --bucket mybucket") == "s3"

    def test_rclone(self):
        assert detect_repository_type("rclone --remote-path gdrive:backup") == "rclone"

    def test_b2(self):
        assert detect_repository_type("b2 --bucket mybucket") == "b2"

    def test_azure(self):
        assert detect_repository_type("azure --container mycontainer") == "azure"

    def test_gcs(self):
        assert detect_repository_type("gcs --bucket mybucket") == "gcs"

    def test_sftp(self):
        assert detect_repository_type("sftp --path user@host:/backup") == "sftp"

    def test_webdav(self):
        assert detect_repository_type("webdav --url https://example.com") == "webdav"

    def test_unknown_type(self):
        assert detect_repository_type("ftp --host example.com") == "unknown"

    def test_empty_string(self):
        assert detect_repository_type("") == "unknown"

    def test_none_like_empty(self):
        assert detect_repository_type("   ") == "unknown"

    def test_case_insensitive(self):
        assert detect_repository_type("S3 --bucket mybucket") == "s3"


class TestExtractFilesystemPath:
    def test_extracts_path(self):
        assert extract_filesystem_path("filesystem --path /backup/kopia") == "/backup/kopia"

    def test_extracts_path_with_equals(self):
        assert extract_filesystem_path("filesystem --path=/backup/kopia") == "/backup/kopia"

    def test_non_filesystem_returns_none(self):
        assert extract_filesystem_path("s3 --bucket mybucket") is None

    def test_empty_returns_none(self):
        assert extract_filesystem_path("") is None

    def test_none_like_returns_none(self):
        assert extract_filesystem_path(None) is None

    def test_filesystem_without_path_flag_returns_none(self):
        assert extract_filesystem_path("filesystem --other-flag /backup") is None


class TestGenerateSecurePassword:
    def test_default_length(self):
        pwd = generate_secure_password()
        assert len(pwd) == 32

    def test_custom_length(self):
        assert len(generate_secure_password(16)) == 16
        assert len(generate_secure_password(64)) == 64

    def test_returns_string(self):
        assert isinstance(generate_secure_password(), str)

    def test_unique_each_time(self):
        assert generate_secure_password() != generate_secure_password()


# ============================================================================
# RetentionConfig Pydantic model tests
# ============================================================================

class TestRetentionConfig:
    def test_defaults(self):
        r = RetentionConfig()
        assert r.latest == 10
        assert r.hourly == 0
        assert r.daily == 7
        assert r.weekly == 4
        assert r.monthly == 12
        assert r.annual == 3

    def test_custom_values(self):
        r = RetentionConfig(latest=5, daily=14)
        assert r.latest == 5
        assert r.daily == 14

    def test_zero_allowed(self):
        r = RetentionConfig(latest=0, hourly=0)
        assert r.latest == 0

    def test_invalid_negative_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RetentionConfig(latest=-1)

    def test_invalid_over_max_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RetentionConfig(latest=200)  # max is 100


# ============================================================================
# Config class tests (with real tmp files)
# ============================================================================

def make_config_file(tmp_path: Path, data: dict) -> Path:
    """Write a JSON config file to tmp_path."""
    config_file = tmp_path / "kopi-docka.json"
    config_file.write_text(json.dumps(data), encoding="utf-8")
    config_file.chmod(0o600)
    return config_file


MINIMAL_CONFIG = {
    "kopia": {
        "profile": "default",
        "kopia_params": "filesystem --path /backup/kopia",
        "password": "testpassword123",
    },
    "backup": {
        "base_path": "/backup/kopi-docka",
    },
    "retention": {
        "latest": 10,
        "daily": 7,
    },
}


@pytest.fixture
def cfg(tmp_path):
    config_file = make_config_file(tmp_path, MINIMAL_CONFIG)
    return Config(config_path=config_file)


class TestConfigInit:
    def test_loads_existing_file(self, tmp_path):
        config_file = make_config_file(tmp_path, MINIMAL_CONFIG)
        cfg = Config(config_path=config_file)
        assert cfg.config_file == config_file

    def test_creates_default_if_missing(self, tmp_path):
        config_file = tmp_path / "new-config.json"
        cfg = Config(config_path=config_file)
        assert config_file.exists()

    def test_unreadable_existing_config_raises_instead_of_silent_fallback(
        self, tmp_path, monkeypatch
    ):
        """v7.3.8: when one of the auto-discovered config paths exists but
        is not readable (typical: /etc/kopi-docka.json without sudo), the
        previous version silently fell through and created a second config
        in $HOME with the default password and default repo path — a real
        data-loss footgun. Raise loudly with a sudo hint instead.
        """
        from kopi_docka.helpers import constants

        existing = tmp_path / "etc-kopi-docka.json"
        existing.write_text('{"version": "3.0"}')

        monkeypatch.setitem(
            constants.DEFAULT_CONFIG_PATHS, "root", existing,
        )
        monkeypatch.setitem(
            constants.DEFAULT_CONFIG_PATHS, "user",
            tmp_path / "nonexistent-user-config.json",
        )

        # Pretend the file is unreadable.
        import os as _os
        real_access = _os.access

        def fake_access(path, mode):
            if str(path) == str(existing) and mode == _os.R_OK:
                return False
            return real_access(path, mode)

        monkeypatch.setattr(_os, "access", fake_access)

        with pytest.raises(PermissionError) as exc:
            Config()

        msg = str(exc.value)
        assert str(existing) in msg
        # The HOME fallback must NOT have been created
        assert not (tmp_path / "nonexistent-user-config.json").exists()

    def test_unreadable_etc_includes_sudo_hint(self, tmp_path, monkeypatch):
        """When the unreadable path is under /etc/, the error message must
        point users at sudo — that's the recovery 99 % of the time."""
        from kopi_docka.helpers import constants

        # Use a path that string-starts with /etc/ to trigger the hint.
        # We don't actually need the file at that path; we monkeypatch
        # Path.exists / os.access to lie convincingly.
        fake_etc = Path("/etc/kopi-docka-test.json")
        monkeypatch.setitem(constants.DEFAULT_CONFIG_PATHS, "root", fake_etc)
        monkeypatch.setitem(
            constants.DEFAULT_CONFIG_PATHS, "user",
            tmp_path / "user.json",
        )

        original_exists = Path.exists
        def fake_exists(self):
            if str(self) == str(fake_etc):
                return True
            return original_exists(self)
        monkeypatch.setattr(Path, "exists", fake_exists)

        import os as _os
        monkeypatch.setattr(
            _os, "access",
            lambda p, m: False if str(p) == str(fake_etc) and m == _os.R_OK
                                else True,
        )

        with pytest.raises(PermissionError) as exc:
            Config()

        assert "sudo" in str(exc.value).lower()


class TestConfigGet:
    def test_get_existing_value(self, cfg):
        assert cfg.get("kopia", "profile") == "default"

    def test_get_missing_key_returns_fallback(self, cfg):
        assert cfg.get("kopia", "nonexistent", fallback="default") == "default"

    def test_get_missing_section_returns_fallback(self, cfg):
        assert cfg.get("nosection", "nokey", fallback=42) == 42

    def test_get_none_fallback(self, cfg):
        assert cfg.get("kopia", "nonexistent") is None


class TestConfigGetInt:
    def test_getint_valid(self, cfg):
        assert cfg.getint("retention", "latest") == 10

    def test_getint_fallback_on_missing(self, cfg):
        assert cfg.getint("retention", "nonexistent", fallback=99) == 99

    def test_getint_fallback_on_non_numeric(self, cfg):
        # Inject non-numeric into an unvalidated key after load
        cfg.set("custom", "count", "not-a-number")
        assert cfg.getint("custom", "count", fallback=5) == 5


class TestConfigGetBoolean:
    def test_getboolean_true_string(self, cfg):
        cfg.set("backup", "database_backup", "true")
        assert cfg.getboolean("backup", "database_backup") is True

    def test_getboolean_false_string(self, cfg):
        cfg.set("backup", "database_backup", "false")
        assert cfg.getboolean("backup", "database_backup") is False

    def test_getboolean_bool_value(self, cfg):
        cfg.set("backup", "database_backup", True)
        assert cfg.getboolean("backup", "database_backup") is True

    def test_getboolean_fallback(self, cfg):
        assert cfg.getboolean("backup", "nonexistent", fallback=True) is True


class TestConfigGetList:
    def test_getlist_comma_separated(self, cfg):
        cfg.set("backup", "exclude", "*.log, *.tmp, *.bak")
        result = cfg.getlist("backup", "exclude")
        assert result == ["*.log", "*.tmp", "*.bak"]

    def test_getlist_empty_returns_empty_list(self, cfg):
        assert cfg.getlist("backup", "nonexistent") == []


class TestConfigSet:
    def test_set_creates_section(self, cfg):
        cfg.set("newsection", "key", "value")
        assert cfg.get("newsection", "key") == "value"

    def test_set_updates_existing(self, cfg):
        cfg.set("kopia", "profile", "new-profile")
        assert cfg.get("kopia", "profile") == "new-profile"


class TestConfigSave:
    def test_save_writes_json(self, cfg):
        cfg.set("kopia", "profile", "saved-profile")
        cfg.save()
        data = json.loads(cfg.config_file.read_text())
        assert data["kopia"]["profile"] == "saved-profile"

    def test_save_permissions_600(self, cfg):
        cfg.save()
        mode = oct(os.stat(cfg.config_file).st_mode)[-3:]
        assert mode == "600"

    def test_save_atomic(self, cfg, tmp_path):
        """No leftover temp files after save."""
        cfg.save()
        tmp_files = list(tmp_path.glob(".kopi-docka-config-*.tmp"))
        assert tmp_files == []


class TestUpdateRetention:
    def test_updates_all_fields(self, cfg):
        cfg.update_retention(5, 2, 14, 8, 24, 6)
        assert cfg.get("retention", "latest") == 5
        assert cfg.get("retention", "daily") == 14
        assert cfg.get("retention", "annual") == 6

    def test_persists_to_file(self, cfg):
        cfg.update_retention(5, 2, 14, 8, 24, 6)
        data = json.loads(cfg.config_file.read_text())
        assert data["retention"]["latest"] == 5


class TestPasswordInline:
    def test_get_password_from_config(self, cfg):
        assert cfg.get_password() == "testpassword123"

    def test_set_password_inline(self, cfg):
        cfg.set_password("newpassword456", use_file=False)
        assert cfg.get_password() == "newpassword456"

    def test_no_password_raises_value_error(self, tmp_path):
        data = {**MINIMAL_CONFIG, "kopia": {"profile": "default", "kopia_params": "filesystem --path /x"}}
        cfg = Config(config_path=make_config_file(tmp_path, data))
        with pytest.raises(ValueError, match="No password"):
            cfg.get_password()


class TestPasswordFile:
    def test_set_password_to_file(self, cfg, tmp_path):
        cfg.set_password("filepassword789", use_file=True)
        # Config should now point to password_file
        pw_file = cfg.get("kopia", "password_file")
        assert pw_file
        assert Path(pw_file).exists()
        assert Path(pw_file).read_text().strip() == "filepassword789"

    def test_get_password_from_file(self, cfg):
        cfg.set_password("fromfile", use_file=True)
        assert cfg.get_password() == "fromfile"

    def test_password_file_missing_raises(self, tmp_path):
        data = {
            **MINIMAL_CONFIG,
            "kopia": {
                "profile": "default",
                "kopia_params": "filesystem --path /x",
                "password_file": "/nonexistent/path/to/pw",
                "password": "",
            },
        }
        cfg = Config(config_path=make_config_file(tmp_path, data))
        with pytest.raises(ValueError, match="Password file not found"):
            cfg.get_password()


class TestConfigProperties:
    def test_kopia_profile(self, cfg):
        assert cfg.kopia_profile == "default"

    def test_backup_base_path_is_path(self, cfg):
        assert isinstance(cfg.backup_base_path, Path)

    def test_kopia_compression_default(self, cfg):
        assert cfg.kopia_compression == "zstd"

    def test_kopia_encryption_default(self, cfg):
        assert "AES" in cfg.kopia_encryption

    def test_backup_scope_default(self, cfg):
        assert cfg.backup_scope == "standard"

    def test_stop_timeout_default(self, cfg):
        assert cfg.stop_timeout == 30

    def test_start_timeout_default(self, cfg):
        assert cfg.start_timeout == 60
