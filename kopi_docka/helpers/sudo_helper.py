################################################################################
# KOPI-DOCKA
#
# @file:        sudo_helper.py
# @module:      kopi_docka.helpers
# @description: Central SUDO_USER/SUDO_UID/SUDO_GID handling — replaces the
#               11+ duplicated inline patterns previously scattered across
#               cores/, helpers/, and backends/.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Sudo-invocation helpers.

When kopi-docka runs under ``sudo``, the process is root but several
side-effect paths need to attribute work back to the invoking user:

* The DR-bundle ZIP should be owned by the invoking user (not root) so
  the user can move/delete it without further sudo.
* The Restore-Wizard reads/writes config files in the user's home;
  ownership must match.
* rclone.conf typically lives in ``~/.config/rclone/rclone.conf`` of the
  invoking user, NOT root — the rclone backend has to find it there.

Before this module existed, the same SUDO_USER / SUDO_UID / SUDO_GID
env-var reading + validation + chown logic was duplicated across 4 files
with **three different validation niveaus** (some checked the username
against a shell-injection regex, others didn't). This module unifies
all of that.

Plan 0037 / v7.5.4.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)

# Linux usernames are POSIX-friendly. This rejects anything that could
# be used for shell injection if interpolated into a path or command.
# Same regex previously used in disaster_recovery_manager and rclone
# backend — now the single source of truth.
_VALID_USERNAME = re.compile(r"^[a-zA-Z0-9._-]+$")


@dataclass(frozen=True)
class SudoUserInfo:
    """Information about the user that invoked the current process via sudo.

    All numeric fields are populated even when not running under sudo —
    in that case they reflect the current process's uid/gid and
    ``invoked_with_sudo`` is False. ``name`` and ``home`` are populated
    only when SUDO_USER is set AND passes shell-injection validation.

    Attributes:
        name: SUDO_USER if validated, else None.
        uid: SUDO_UID if set, else os.getuid().
        gid: SUDO_GID if set, else os.getgid().
        home: /home/<name> when name is valid, else None.
        invoked_with_sudo: True iff SUDO_USER was set AND validated.
    """

    name: Optional[str]
    uid: int
    gid: int
    home: Optional[Path]
    invoked_with_sudo: bool


def get_sudo_user_info() -> SudoUserInfo:
    """Read SUDO_USER / SUDO_UID / SUDO_GID env-vars and validate.

    Cheap, no I/O — safe to call repeatedly.

    Returns:
        Populated SudoUserInfo. If not running under sudo, uid/gid
        reflect current process and invoked_with_sudo=False.
    """
    raw_name = os.environ.get("SUDO_USER")
    valid_name = raw_name if raw_name and _VALID_USERNAME.match(raw_name) else None

    try:
        uid = int(os.environ.get("SUDO_UID", os.getuid()))
    except (TypeError, ValueError):
        uid = os.getuid()
    try:
        gid = int(os.environ.get("SUDO_GID", os.getgid()))
    except (TypeError, ValueError):
        gid = os.getgid()

    return SudoUserInfo(
        name=valid_name,
        uid=uid,
        gid=gid,
        home=Path(f"/home/{valid_name}") if valid_name else None,
        invoked_with_sudo=valid_name is not None,
    )


def chown_to_sudo_user(path: Path) -> None:
    """Chown ``path`` to the sudo invoking user, if running under sudo.

    No-op when:
      - Not running under sudo (uid/gid stay current process owner)
      - SUDO_USER is missing or fails validation
      - The chown itself fails (logged as warning, no exception raised
        — fixing ownership is best-effort, the file is still usable)

    Args:
        path: file or directory to chown
    """
    info = get_sudo_user_info()
    if not info.invoked_with_sudo:
        return
    try:
        os.chown(path, info.uid, info.gid)
        logger.info("Set ownership of %s to %s (uid=%s)", path, info.name, info.uid)
    except OSError as e:
        logger.warning(
            "Could not chown %s to %s (uid=%s): %s",
            path, info.name, info.uid, e,
        )


def find_in_sudo_user_home(relative: str) -> Optional[Path]:
    """Return ``/home/<sudo_user>/<relative>`` if it exists, else None.

    Convenient for finding user-level config files (rclone.conf, .ssh/,
    etc.) when running as root via sudo. Returns None when:
      - Not running under sudo (no home directory to look in)
      - SUDO_USER is missing or fails validation
      - The path doesn't exist (or isn't accessible)

    The PermissionError case is treated as "not found" — same defensive
    behavior the inline patterns had before unification.

    Args:
        relative: path relative to the sudo user's home directory,
            e.g. ".config/rclone/rclone.conf"

    Returns:
        Absolute Path if it exists, else None.
    """
    info = get_sudo_user_info()
    if not info.home:
        return None
    candidate = info.home / relative
    try:
        return candidate if candidate.exists() else None
    except PermissionError:
        return None


def sudo_user_home_path(relative: str) -> Optional[Path]:
    """Return ``/home/<sudo_user>/<relative>`` regardless of existence.

    Use this when you want to build a path for an error message or
    documentation hint (e.g. "place your config at /home/X/.config/...").
    For "does it exist?" checks use :func:`find_in_sudo_user_home`.

    Returns None if not running under sudo.
    """
    info = get_sudo_user_info()
    if not info.home:
        return None
    return info.home / relative
