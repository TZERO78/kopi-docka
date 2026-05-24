"""Unit tests for kopi_docka.helpers.sudo_helper (Plan 0037 / v7.5.4)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kopi_docka.helpers.sudo_helper import (
    SudoUserInfo,
    chown_to_sudo_user,
    find_in_sudo_user_home,
    get_sudo_user_info,
    sudo_user_home_path,
)


@pytest.fixture
def clean_sudo_env(monkeypatch):
    """Strip all SUDO_* env vars so each test starts from a known state."""
    for var in ("SUDO_USER", "SUDO_UID", "SUDO_GID"):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


@pytest.mark.unit
class TestGetSudoUserInfo:
    def test_under_sudo_returns_populated_info(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "alice")
        clean_sudo_env.setenv("SUDO_UID", "1000")
        clean_sudo_env.setenv("SUDO_GID", "1000")

        info = get_sudo_user_info()

        assert info.name == "alice"
        assert info.uid == 1000
        assert info.gid == 1000
        assert info.home == Path("/home/alice")
        assert info.invoked_with_sudo is True

    def test_no_sudo_returns_current_process_ids(self, clean_sudo_env):
        info = get_sudo_user_info()

        assert info.name is None
        assert info.uid == os.getuid()
        assert info.gid == os.getgid()
        assert info.home is None
        assert info.invoked_with_sudo is False

    def test_shell_injection_name_rejected(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "; rm -rf /")
        clean_sudo_env.setenv("SUDO_UID", "1000")

        info = get_sudo_user_info()

        # Username failed validation — treat as no-sudo from name's point of view
        assert info.name is None
        assert info.home is None
        assert info.invoked_with_sudo is False
        # But uid/gid env vars are still parsed
        assert info.uid == 1000

    def test_path_traversal_in_name_rejected(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "../etc")
        info = get_sudo_user_info()
        assert info.name is None
        assert info.invoked_with_sudo is False

    def test_garbage_uid_falls_back_to_current(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "alice")
        clean_sudo_env.setenv("SUDO_UID", "not-a-number")
        info = get_sudo_user_info()
        assert info.uid == os.getuid()

    def test_valid_punctuation_in_name_accepted(self, clean_sudo_env):
        # Dots, dashes, underscores allowed (real-world: user.name, user-name, _admin)
        for valid in ("user.name", "user-name", "_admin", "user_2", "123abc"):
            clean_sudo_env.setenv("SUDO_USER", valid)
            info = get_sudo_user_info()
            assert info.name == valid, f"{valid!r} should be accepted"
            assert info.invoked_with_sudo is True


@pytest.mark.unit
class TestChownToSudoUser:
    def test_noop_without_sudo(self, clean_sudo_env, tmp_path):
        f = tmp_path / "x"
        f.write_text("hi")
        before = f.stat()

        chown_to_sudo_user(f)

        after = f.stat()
        assert before.st_uid == after.st_uid
        assert before.st_gid == after.st_gid

    def test_chown_called_under_sudo(self, clean_sudo_env, tmp_path):
        clean_sudo_env.setenv("SUDO_USER", "alice")
        clean_sudo_env.setenv("SUDO_UID", "12345")
        clean_sudo_env.setenv("SUDO_GID", "12345")

        f = tmp_path / "x"
        f.write_text("hi")

        with patch("kopi_docka.helpers.sudo_helper.os.chown") as mock_chown:
            chown_to_sudo_user(f)

        mock_chown.assert_called_once_with(f, 12345, 12345)

    def test_chown_failure_does_not_raise(self, clean_sudo_env, tmp_path, caplog):
        clean_sudo_env.setenv("SUDO_USER", "alice")
        clean_sudo_env.setenv("SUDO_UID", "12345")

        f = tmp_path / "x"
        f.write_text("hi")

        with patch(
            "kopi_docka.helpers.sudo_helper.os.chown",
            side_effect=PermissionError("denied"),
        ):
            chown_to_sudo_user(f)  # must not raise

    def test_invalid_sudo_user_treated_as_no_sudo(self, clean_sudo_env, tmp_path):
        clean_sudo_env.setenv("SUDO_USER", "evil; rm -rf /")
        clean_sudo_env.setenv("SUDO_UID", "12345")

        f = tmp_path / "x"
        f.write_text("hi")

        with patch("kopi_docka.helpers.sudo_helper.os.chown") as mock_chown:
            chown_to_sudo_user(f)

        # Invalid name → no chown attempt at all
        mock_chown.assert_not_called()


@pytest.mark.unit
class TestFindInSudoUserHome:
    def test_returns_none_without_sudo(self, clean_sudo_env):
        assert find_in_sudo_user_home(".config/rclone/rclone.conf") is None

    def test_returns_path_when_file_exists(self, clean_sudo_env, tmp_path):
        # Make tmp_path masquerade as /home/alice by patching the home prop.
        # Approach: set SUDO_USER=alice, override Path(/home/alice) by patching
        # the home Path construction in get_sudo_user_info.
        clean_sudo_env.setenv("SUDO_USER", "alice")
        fake_home = tmp_path / "alice"
        fake_home.mkdir()
        target = fake_home / ".config" / "rclone" / "rclone.conf"
        target.parent.mkdir(parents=True)
        target.write_text("[remote]\n")

        # Patch sudo_user home construction
        with patch(
            "kopi_docka.helpers.sudo_helper.get_sudo_user_info",
            return_value=SudoUserInfo(
                name="alice",
                uid=12345,
                gid=12345,
                home=fake_home,
                invoked_with_sudo=True,
            ),
        ):
            result = find_in_sudo_user_home(".config/rclone/rclone.conf")

        assert result == target

    def test_returns_none_when_file_missing(self, clean_sudo_env, tmp_path):
        with patch(
            "kopi_docka.helpers.sudo_helper.get_sudo_user_info",
            return_value=SudoUserInfo(
                name="alice",
                uid=12345,
                gid=12345,
                home=tmp_path / "alice",  # doesn't exist
                invoked_with_sudo=True,
            ),
        ):
            result = find_in_sudo_user_home(".config/rclone/rclone.conf")

        assert result is None

    def test_permission_error_treated_as_not_found(self, clean_sudo_env, tmp_path):
        fake_home = tmp_path / "alice"
        fake_home.mkdir()

        with patch(
            "kopi_docka.helpers.sudo_helper.get_sudo_user_info",
            return_value=SudoUserInfo(
                name="alice", uid=1, gid=1, home=fake_home, invoked_with_sudo=True,
            ),
        ), patch.object(Path, "exists", side_effect=PermissionError("denied")):
            result = find_in_sudo_user_home(".config/rclone/rclone.conf")

        assert result is None

    def test_invalid_sudo_user_returns_none(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "; rm -rf /")
        assert find_in_sudo_user_home(".config/rclone/rclone.conf") is None


@pytest.mark.unit
class TestSudoUserHomePath:
    """``sudo_user_home_path`` is the existence-agnostic sibling of
    ``find_in_sudo_user_home`` — used for error-message hints."""

    def test_returns_none_without_sudo(self, clean_sudo_env):
        assert sudo_user_home_path(".config/rclone/rclone.conf") is None

    def test_returns_path_regardless_of_existence(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "alice")
        result = sudo_user_home_path(".config/rclone/rclone.conf")
        # File doesn't have to exist — caller wants the path for a message
        assert result == Path("/home/alice/.config/rclone/rclone.conf")

    def test_invalid_name_returns_none(self, clean_sudo_env):
        clean_sudo_env.setenv("SUDO_USER", "evil; rm")
        assert sudo_user_home_path(".config/x") is None
