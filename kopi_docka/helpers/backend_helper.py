################################################################################
# KOPI-DOCKA
#
# @file:        backend_helper.py
# @module:      kopi_docka.helpers
# @description: Shared SFTP-backend helpers — single source of truth for the
#               canonical Kopia SFTP CLI shape (separate --path / --host /
#               --username / --keyfile flags), used by both the direct SFTP
#               wizard and the Tailscale wizard, and by repair-kopia-params.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Shared construction logic for Kopia SFTP backend params.

The SFTP-style backends (direct ``sftp`` and ``tailscale``) build the
same Kopia CLI shape:

    sftp --path=PATH --host=HOST --username=USER --keyfile=KEY
         [--known-hosts=KNOWN_HOSTS] [--port=PORT]

Centralising the string construction here means the wizard, the
``rebuild_kopia_params()`` repair hook, and the doctor sanity check all
agree on the canonical shape — bug fixed once propagates everywhere.

The pre-v7.4 (Tailscale) and pre-v7.6.1 (SFTP) wizards emitted
``--path=user@host:path`` (combined) and forgot ``--username``/
``--keyfile``; Kopia accepted that at ``repository connect`` but every
subsequent snapshot hung under systemd/cron. See Plan 0029 / Plan 0038.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Optional, Union

from .logging import get_logger
from .ui_utils import run_command, SubprocessError

logger = get_logger(__name__)


def build_sftp_kopia_params(
    remote_path: str,
    host: str,
    ssh_user: str,
    ssh_key: str,
    known_hosts: Optional[str] = None,
    port: Optional[Union[int, str]] = None,
) -> str:
    """Build the canonical Kopia SFTP ``kopia_params`` string.

    Verified flag names against ``kopia repository create sftp --help``
    (Kopia 0.23). The required set is ``--path`` + ``--host`` +
    ``--username`` + one of ``--keyfile`` / ``--key-data`` /
    ``--sftp-password``. ``--port`` (NOT ``--sftp-port``) defaults to 22
    and is only emitted when overridden.

    Args:
        remote_path: Absolute path on the remote (passed to ``--path``).
        host: SFTP/SSH server hostname or FQDN (``--host``).
        ssh_user: SSH username (``--username``).
        ssh_key: Path to private key file (``--keyfile``).
        known_hosts: Optional path to ``known_hosts`` file. Omit if
            ssh-keyscan failed — better to let Kopia surface the prompt
            than to ship a half-built flag.
        port: Optional SSH port. Only emitted when not equal to ``22``.

    Returns:
        The space-joined CLI string ready to land in ``kopia_params``.
    """
    params = [
        "sftp",
        f"--path={shlex.quote(remote_path)}",
        f"--host={host}",
        f"--username={ssh_user}",
        f"--keyfile={shlex.quote(ssh_key)}",
    ]
    if known_hosts:
        params.append(f"--known-hosts={shlex.quote(known_hosts)}")
    if port is not None:
        port_str = str(port).strip()
        if port_str and port_str != "22":
            params.append(f"--port={port_str}")
    return " ".join(params)


def ensure_known_hosts(host: str) -> Optional[Path]:
    """Pre-populate ``~/.ssh/known_hosts`` for ``host`` via ssh-keyscan.

    Kopia's SFTP backend cannot answer interactive host-key prompts —
    when launched under systemd/cron it just hangs. We populate
    ``known_hosts`` up front so the first ``repository init`` / connect
    runs unattended.

    Returns the ``known_hosts`` path on success, or ``None`` if no
    usable entry could be guaranteed. Callers should drop the
    ``--known-hosts`` flag in the ``None`` case so Kopia at least
    surfaces a failure on first connect rather than hanging silently.

    Extracted from ``TailscaleBackend._ensure_known_hosts`` (v7.4.0,
    Plan 0029) so the direct SFTP wizard can use it too (Plan 0038).
    """
    from . import ui_utils as utils

    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    if known_hosts.exists():
        try:
            content = known_hosts.read_text()
            if host in content:
                logger.debug("known_hosts already trusts %s", host)
                return known_hosts
        except OSError as e:
            logger.debug("known_hosts read failed: %s", e)

    try:
        scan = run_command(
            ["ssh-keyscan", "-t", "ed25519,rsa,ecdsa", host],
            f"Fetching host key for {host}",
            timeout=15,
            check=False,
        )
    except SubprocessError as e:
        utils.print_warning(
            f"ssh-keyscan failed for {host}: {e}. "
            f"Continuing without --known-hosts; Kopia may prompt on "
            f"first connect, which won't work under systemd/cron."
        )
        return None

    if scan.returncode != 0 or not (scan.stdout or "").strip():
        utils.print_warning(
            f"ssh-keyscan returned no host key for {host}. "
            f"Continuing without --known-hosts; you may need to add "
            f"the key manually if backups stall on connect."
        )
        return None

    try:
        with open(known_hosts, "a", encoding="utf-8") as fh:
            fh.write(scan.stdout)
        known_hosts.chmod(0o600)
    except OSError as e:
        utils.print_warning(
            f"Could not update {known_hosts}: {e}. Continuing without "
            f"--known-hosts."
        )
        return None

    utils.print_info(f"Added host key for {host} to {known_hosts}")
    return known_hosts
