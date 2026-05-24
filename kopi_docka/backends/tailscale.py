"""
Tailscale Backend for Kopi-Docka

🔥 Killer Feature: Secure, offsite backups over your Tailscale network!

Automatically discovers peers in your Tailnet, shows disk space and latency,
and sets up passwordless SSH access.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.markup import escape

from .base import BackendBase, ConfigurationError, DependencyError
from ..i18n import _
from ..helpers.dependency_helper import DependencyHelper, ToolInfo
from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError

logger = get_logger(__name__)


@dataclass
class TailscalePeer:
    """Tailscale peer information.

    ``hostname`` is the bare device name shown in `tailscale status`
    (e.g. ``TZERO-SERVER``). ``dns_name`` is the full tailnet-DNS FQDN
    reported by `tailscale status --json` under ``DNSName``
    (e.g. ``tzero-server.beetal-vega.ts.net``). The FQDN is what should
    end up in SSH commands and Kopia ``--host`` parameters — the bare
    hostname depends on a search-domain being active, which doesn't
    hold under sudo / systemd-units / various distros. Pre-v7.3.12 the
    code synthesised a fake ``<hostname>.tailnet`` suffix that no
    Tailnet uses anymore.
    """

    hostname: str
    ip: str
    online: bool
    os: str
    dns_name: str = ""  # FQDN from `tailscale status --json` DNSName field
    disk_free_gb: Optional[float] = None
    ping_ms: Optional[int] = None

    @property
    def fqdn(self) -> str:
        """Return the FQDN if available, otherwise fall back to the bare hostname."""
        return self.dns_name or self.hostname


class TailscaleBackend(BackendBase):
    """Secure backups over Tailscale VPN"""

    REQUIRED_TOOLS = ["tailscale", "ssh", "ssh-keygen", "ssh-copy-id"]

    @property
    def name(self) -> str:
        return "tailscale"

    @property
    def display_name(self) -> str:
        return _("Tailscale Network")

    @property
    def description(self) -> str:
        return _("🔥Secure offsite backups over your private Tailscale network (recommended!)")

    def configure(self) -> Dict[str, Any]:
        """Wrapper for compatibility with simple backends"""
        return self.setup_interactive()

    def check_dependencies(self) -> List[str]:
        """
        Check if all required tools are installed.

        Returns:
            List of missing tool names (empty if all present)
        """
        return DependencyHelper.missing(self.REQUIRED_TOOLS)

    def get_dependency_status(self) -> Dict[str, ToolInfo]:
        """
        Get status of all required tools for Tailscale backend.

        Returns:
            Dict mapping tool name to ToolInfo
        """
        return DependencyHelper.check_all(self.REQUIRED_TOOLS)

    def install_dependencies(self) -> bool:
        """
        Stub method - automatic installation removed (Think Simple strategy).

        Users must install dependencies manually or use Server-Baukasten.
        https://github.com/TZERO78/Server-Baukasten

        Raises:
            NotImplementedError: Automatic installation is not supported
        """
        raise NotImplementedError(
            "Automatic dependency installation has been removed. "
            "Please install tailscale, ssh, ssh-keygen, and ssh-copy-id manually "
            "or use Server-Baukasten: https://github.com/TZERO78/Server-Baukasten"
        )

    def setup_interactive(self) -> Dict[str, Any]:
        """Interactive setup for Tailscale backend using Rich CLI"""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language

        # Check dependencies before proceeding with setup
        missing = self.check_dependencies()
        if missing:
            error_msg = (
                f"Missing required tools for Tailscale backend: {', '.join(missing)}\n\n"
                f"Please install manually.\n\n"
                f"Automated Setup:\n"
                f"  Use Server-Baukasten for automated system preparation:\n"
                f"  https://github.com/TZERO78/Server-Baukasten"
            )
            raise DependencyError(error_msg)

        lang = get_current_language()

        # Check if Tailscale is running
        if not self._is_running():
            utils.print_warning(t("tailscale.not_connected", lang))

            if utils.prompt_confirm(t("tailscale.connect_prompt", lang)):
                self._start_tailscale()
            else:
                raise ConfigurationError(_("Tailscale must be running"))

        # Discover peers with spinner
        utils.print_info(t("tailscale.loading_peers", lang))
        peers = self._list_peers()

        if not peers:
            utils.print_error(t("tailscale.no_peers", lang))
            raise ConfigurationError(_("No peers found in Tailnet"))

        # Show peers in a nice table
        table = utils.create_table(
            "Available Backup Targets",
            [
                ("Status", "white", 8),
                ("Hostname", "cyan", 25),
                ("IP", "white", 15),
                ("Latency", "yellow", 10),
            ],
        )

        for peer in peers:
            status = "🟢 Online" if peer.online else "🔴 Offline"
            ping_info = f"{peer.ping_ms}ms" if peer.ping_ms else "?"

            table.add_row(status, peer.hostname, peer.ip, ping_info)

        utils.console.print(table)

        # Select peer using numbered selection
        selected_peer = utils.prompt_select(
            t("tailscale.select_peer", lang),
            peers,
            display_fn=lambda p: f"{'🟢' if p.online else '🔴'} {p.hostname} ({p.ip})",
        )

        if not selected_peer.online:
            utils.print_warning(t("tailscale.peer_offline", lang))

        # Get remote path
        default_path = "/backup/kopi-docka"
        remote_path = utils.prompt_text(
            f"{t('tailscale.backup_path', lang)} {escape(f'[{default_path}]')}",
            default=default_path,
        )

        if not remote_path.startswith("/"):
            utils.print_error(t("tailscale.path_must_be_absolute", lang))
            raise ConfigurationError("Path must be absolute")

        # Setup SSH key
        ssh_key_path = Path.home() / ".ssh" / "kopi-docka_ed25519"
        if not ssh_key_path.exists():
            if utils.prompt_confirm(t("tailscale.setup_ssh_key", lang)):
                self._setup_ssh_key(selected_peer.fqdn, ssh_key_path)
        else:
            utils.print_info(
                f"SSH key already exists at {ssh_key_path} — reusing it."
            )
            # Make sure the existing key works against this peer; if not,
            # offer manual / auto deployment.
            self._ensure_key_on_remote(selected_peer.fqdn, ssh_key_path)

        # Get SSH user
        ssh_user = utils.prompt_text(f"{t('tailscale.ssh_user', lang)} [root]", default="root")

        # Build Kopia SFTP parameters using the FQDN — bare hostname depends on
        # search-domain resolution which doesn't always work under sudo / systemd.
        peer_fqdn = selected_peer.fqdn
        kopia_params = (
            f"sftp --path={peer_fqdn}:{remote_path} --host={peer_fqdn}"
        )

        utils.print_separator()
        utils.print_success(f"Kopia params: {escape(kopia_params)}")

        return {
            "type": "sftp",  # Kopia uses SFTP backend
            "kopia_params": kopia_params,
            "credentials": {
                "peer_hostname": selected_peer.hostname,
                "peer_fqdn": peer_fqdn,
                "peer_ip": selected_peer.ip,
                "ssh_user": ssh_user,
                "ssh_key": str(ssh_key_path),
                "remote_path": remote_path,
            },
        }

    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate Tailscale configuration"""
        errors = []

        # Check for kopia_params
        if "kopia_params" not in self.config:
            errors.append(_("Missing kopia_params"))
            return (False, errors)

        if "credentials" not in self.config:
            errors.append(_("Missing credentials"))
            return (False, errors)

        creds = self.config["credentials"]

        # Check SSH key exists
        if "ssh_key" in creds:
            key_path = Path(creds["ssh_key"])
            if not key_path.exists():
                errors.append(f"{_('SSH key not found')}: {key_path}")

        # Check Tailscale is running
        if not self._is_running():
            errors.append(_("Tailscale is not running"))

        return (len(errors) == 0, errors)

    def test_connection(self) -> bool:
        """Test connection to Tailscale peer"""
        try:
            creds = self.config["credentials"]
            # Prefer the FQDN written by setup_interactive (v7.3.12+); fall
            # back to the bare hostname for configs created before that.
            host = creds.get("peer_fqdn") or creds.get("peer_hostname")
            ssh_user = creds.get("ssh_user", "root")
            ssh_key = creds.get("ssh_key")

            # Test SSH connection
            cmd = [
                "ssh",
                "-i",
                ssh_key,
                "-o",
                "StrictHostKeyChecking=no",
                f"{ssh_user}@{host}",
                "echo",
                "test",
            ]

            result = run_command(
                cmd,
                "Testing SSH connection",
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                print(f"✓ {_('Connection successful')}")
                return True
            else:
                print(f"✗ {_('Connection failed')}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"✗ {_('Connection timeout')}")
            return False
        except Exception as e:
            print(f"✗ {_('Connection test failed')}: {e}")
            return False

    def get_kopia_args(self) -> List[str]:
        """Get Kopia CLI arguments for SFTP backend.

        Parses kopia_params to extract path. Falls back to default SSH key.
        """
        import shlex

        ssh_key = str(Path.home() / ".ssh/kopi-docka_ed25519")
        repo_path = None

        # Parse from kopia_params (e.g., "sftp --path=hostname:/backup --host=hostname")
        kopia_params = self.config.get("kopia_params", "")
        if kopia_params:
            try:
                parts = shlex.split(kopia_params)
                for part in parts:
                    if part.startswith("--path="):
                        repo_path = part.split("=", 1)[1]
                    elif part == "--path" and parts.index(part) + 1 < len(parts):
                        repo_path = parts[parts.index(part) + 1]
            except ValueError:
                pass

        if not repo_path:
            return []

        return ["--path", repo_path, "--sftp-key-file", ssh_key]

    def get_backend_type(self) -> str:
        """Kopia backend type"""
        return "sftp"

    def get_status(self) -> dict:
        """
        Get detailed status information about the configured Tailscale peer.

        This method is designed to be called AFTER setup when SSH keys are configured.
        Returns detailed information including disk space, connectivity, etc.

        Returns:
            dict: Status information with keys:
                - online: bool
                - hostname: str
                - ip: str
                - ping_ms: Optional[int]
                - disk_free_gb: Optional[float]
                - disk_total_gb: Optional[float]
                - ssh_connected: bool
                - tailscale_running: bool
        """

        status = {
            "tailscale_running": self._is_running(),
            "online": False,
            "hostname": None,
            "ip": None,
            "ping_ms": None,
            "disk_free_gb": None,
            "disk_total_gb": None,
            "ssh_connected": False,
        }

        # Check if we have a configured peer
        if "credentials" not in self.config:
            return status

        creds = self.config["credentials"]
        hostname = creds.get("peer_hostname")
        ip = creds.get("peer_ip")
        ssh_user = creds.get("ssh_user", "root")
        ssh_key = creds.get("ssh_key")

        if not hostname:
            return status

        status["hostname"] = hostname
        status["ip"] = ip

        # Check if peer is online via Tailscale
        if status["tailscale_running"]:
            status["ping_ms"] = self._ping_peer(hostname)
            status["online"] = status["ping_ms"] is not None

        # Check SSH connectivity and get disk info
        if ssh_key and Path(ssh_key).exists():
            try:
                # Test SSH connection and get disk space in one go
                result = run_command(
                    [
                        "ssh",
                        "-i",
                        ssh_key,
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "ConnectTimeout=3",
                        "-o",
                        "BatchMode=yes",
                        f"{ssh_user}@{hostname}",
                        "df",
                        "/",
                        "--output=size,avail",
                        "--block-size=G",
                    ],
                    "Checking disk space via SSH",
                    timeout=5,
                    check=False,
                )

                if result.returncode == 0:
                    status["ssh_connected"] = True

                    # Parse disk space output
                    lines = result.stdout.strip().split("\n")
                    if len(lines) >= 2:
                        # Second line contains: total_size available_size
                        parts = lines[1].split()
                        if len(parts) >= 2:
                            status["disk_total_gb"] = float(parts[0].rstrip("G").strip())
                            status["disk_free_gb"] = float(parts[1].rstrip("G").strip())
            except (OSError, ValueError, SubprocessError) as e:
                logger.warning(f"SSH disk-space check failed for {hostname}: {e}")

        return status

    # Tailscale-specific helpers

    def _is_running(self) -> bool:
        """Check if Tailscale is running"""
        try:
            result = run_command(
                ["tailscale", "status"],
                "Checking Tailscale status",
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _start_tailscale(self) -> bool:
        """Start Tailscale"""
        from kopi_docka.helpers import ui_utils as utils

        try:
            run_command(["sudo", "tailscale", "up"], "Starting Tailscale", timeout=30)
            utils.print_success("Tailscale started")
            return True
        except SubprocessError:
            utils.print_error("Failed to start Tailscale")
            return False

    def _list_peers(self) -> List[TailscalePeer]:
        """List peers in Tailnet with enriched info"""
        try:
            result = run_command(
                ["tailscale", "status", "--json"],
                "Getting peer list",
                timeout=10,
            )
            data = json.loads(result.stdout)

            peers = []
            for peer_id, peer_info in data.get("Peer", {}).items():
                hostname = peer_info.get("HostName", "unknown")
                # `tailscale status --json` returns DNSName with a trailing
                # dot, e.g. "tzero-server.beetal-vega.ts.net." — strip it so
                # downstream consumers can append paths cleanly.
                dns_name = peer_info.get("DNSName", "").rstrip(".")
                ips = peer_info.get("TailscaleIPs", [])
                ip = ips[0] if ips else "unknown"
                online = peer_info.get("Online", False)
                os = peer_info.get("OS", "unknown")

                peer = TailscalePeer(
                    hostname=hostname, ip=ip, online=online, os=os,
                    dns_name=dns_name,
                )

                # Get latency via Tailscale ping (no SSH required)
                if online:
                    peer.ping_ms = self._ping_peer(hostname)

                peers.append(peer)

            # Sort by online status and ping
            peers.sort(key=lambda p: (not p.online, p.ping_ms or 999))

            return peers

        except Exception as e:
            print(f"⚠️  {_('Failed to list peers')}: {e}")
            return []

    def _ping_peer(self, hostname: str) -> Optional[int]:
        """Ping peer and return latency in ms"""
        try:
            result = run_command(
                ["tailscale", "ping", "-c", "1", hostname],
                f"Pinging {hostname}",
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                # Parse ping output for latency
                for line in result.stdout.split("\n"):
                    if "time=" in line:
                        parts = line.split("time=")
                        if len(parts) < 2:
                            continue
                        tokens = parts[1].split()
                        if not tokens:
                            continue
                        return int(float(tokens[0].rstrip("ms")))
        except (OSError, ValueError, SubprocessError) as e:
            logger.debug(f"Ping latency check failed: {e}")
        return None

    def _setup_ssh_key(self, host: str, key_path: Path) -> bool:
        """Setup SSH key for passwordless access.

        Two installation modes — the user picks one:

        - **Automatic**: ``ssh-copy-id``. Needs the remote to accept
          password-auth as root, which not every NAS does, but is the
          one-step path on most Linux servers. After it lands, we try to
          mirror the key to a Unraid-style persistent path if the remote
          looks tmpfs-rooted.
        - **Manual**: print the public key, let the user paste it
          wherever it belongs (NAS web UI, ``/boot/config/ssh/root`` on
          Unraid, ``~/.ssh/authorized_keys`` via a different account, …).
          Works against any remote, even ones with no password-auth.

        Both paths end with a passwordless-SSH verification so a broken
        setup fails loudly here, not on the first Kopia call.
        """
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language

        lang = get_current_language()

        try:
            utils.print_info(t("tailscale.generating_ssh_key", lang))

            # Generate ED25519 key
            run_command(
                [
                    "ssh-keygen",
                    "-t",
                    "ed25519",
                    "-f",
                    str(key_path),
                    "-N",
                    "",
                    "-C",
                    "kopi-docka-backup",
                ],
                "Generating SSH key",
                timeout=30,
            )

            utils.print_success(t("tailscale.ssh_key_generated", lang))

            # Ask user how they want to deploy the public key to the remote.
            return self._deploy_public_key(host, key_path)

        except SubprocessError as e:
            utils.print_error(f"{t('tailscale.ssh_key_failed', lang)}: {e}")
            return False

    def _deploy_public_key(self, host: str, key_path: Path) -> bool:
        """Offer two key-deployment modes (auto / manual) and execute the
        chosen one. Returns True iff passwordless SSH works at the end.
        """
        from kopi_docka.helpers import ui_utils as utils

        pub_key_path = Path(str(key_path) + ".pub")
        pub_key = pub_key_path.read_text().strip() if pub_key_path.exists() else ""

        utils.console.print()
        utils.console.print(
            "[bold cyan]How should the public key reach the remote?[/bold cyan]"
        )
        utils.console.print(
            "  [cyan]1[/cyan]  Automatic — run `ssh-copy-id` (needs root password "
            "auth on the remote)"
        )
        utils.console.print(
            "  [cyan]2[/cyan]  Manual — show the key, I'll paste it where it "
            "belongs (NAS web UI, Unraid persistent path, etc.)"
        )

        choice = utils.prompt_text("Choose [1/2]", default="1").strip()

        if choice == "2":
            self._deploy_public_key_manual(host, pub_key, key_path)
        else:
            self._deploy_public_key_auto(host, key_path)

        # Both paths end with the same verification.
        return self._verify_passwordless(host, key_path)

    def _deploy_public_key_auto(self, host: str, key_path: Path) -> None:
        """ssh-copy-id path. Mirrors to a persistent file if the remote
        looks tmpfs-rooted (Unraid pattern)."""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language

        lang = get_current_language()

        utils.print_info(f"{t('tailscale.copying_ssh_key', lang)} {host}...")
        utils.print_warning("You may need to enter the root password")

        try:
            run_command(
                ["ssh-copy-id", "-i", str(key_path), f"root@{host}"],
                "Copying SSH key to remote",
                timeout=60,
                show_output=True,
            )
            utils.print_success(t("tailscale.ssh_key_copied", lang))
            # Unraid-style persistence — generic test for /boot/config/ssh.
            self._mirror_key_to_persistent_path(host, key_path)
        except SubprocessError as e:
            utils.print_error(
                f"ssh-copy-id failed: {e}. You may want to retry with the "
                f"manual option (display the key and paste it yourself)."
            )

    def _deploy_public_key_manual(self, host: str, pub_key: str, key_path: Path) -> None:
        """Show the public key and wait for the user to install it on the
        remote however they like. Works against any remote — Unraid USB
        boot, Synology DSM web UI, TrueNAS via the GUI, etc.
        """
        from kopi_docka.helpers import ui_utils as utils

        utils.console.print()
        utils.console.print(
            "[bold]Public key to install on the remote:[/bold]"
        )
        utils.console.print()
        utils.console.print(f"  [cyan]{pub_key}[/cyan]")
        utils.console.print()
        utils.console.print(
            "[dim]Paste this into the remote's authorized_keys file. "
            "Common locations:[/dim]"
        )
        utils.console.print(
            "[dim]  • Standard Linux server: ~/.ssh/authorized_keys "
            "(or /root/.ssh/authorized_keys when connecting as root)[/dim]"
        )
        utils.console.print(
            "[dim]  • Unraid: /boot/config/ssh/root  (persistent — survives "
            "reboots; Unraid copies it to /root/.ssh/ on boot)[/dim]"
        )
        utils.console.print(
            "[dim]  • Synology DSM: Control Panel → Terminal & SNMP → "
            "user's SSH key (or ~/.ssh/authorized_keys via SSH)[/dim]"
        )
        utils.console.print(
            "[dim]  • TrueNAS: System Settings → Shell → "
            "/root/.ssh/authorized_keys[/dim]"
        )
        utils.console.print()
        utils.prompt_text(
            "Press Enter once the key is installed on the remote",
            default="",
        )

    def _mirror_key_to_persistent_path(self, host: str, key_path: Path) -> None:
        """If the remote's /root/ is tmpfs (NAS-style boot, Unraid etc.),
        copy authorized_keys into the conventional persistent location
        (/boot/config/ssh/root). No-op on standard Linux servers where
        /root/.ssh/authorized_keys is already persistent.
        """
        from kopi_docka.helpers import ui_utils as utils

        # 1) Probe: does the remote have an Unraid-style persistent SSH dir?
        try:
            probe = run_command(
                [
                    "ssh", "-i", str(key_path),
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=10",
                    f"root@{host}",
                    "test -d /boot/config/ssh && echo yes || echo no",
                ],
                "Probing for persistent SSH config path",
                timeout=15,
                check=False,
            )
        except SubprocessError as e:
            logger.debug("Persistent-path probe failed (skipping mirror): %s", e)
            return

        if "yes" not in (probe.stdout or ""):
            # Standard Linux — /root/.ssh/authorized_keys is already on
            # persistent storage, nothing more to do.
            logger.debug(
                "Remote %s: no /boot/config/ssh detected — treating /root as "
                "persistent (standard Linux server).",
                host,
            )
            return

        # 2) Mirror the key
        utils.print_info(
            f"Detected USB-boot/tmpfs-style remote (e.g. Unraid). "
            f"Also writing authorized_keys to /boot/config/ssh/root for "
            f"reboot-persistence…"
        )
        try:
            run_command(
                [
                    "ssh", "-i", str(key_path),
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "BatchMode=yes",
                    f"root@{host}",
                    # Append to /boot/config/ssh/root (don't overwrite — other
                    # keys may already live there for the user's other tools).
                    # touch+chmod first so the file exists with safe perms.
                    "mkdir -p /boot/config/ssh && "
                    "touch /boot/config/ssh/root && "
                    "chmod 600 /boot/config/ssh/root && "
                    # Only append if our key isn't already present
                    "(grep -qFx \"$(cat /root/.ssh/authorized_keys | tail -n1)\" "
                    "/boot/config/ssh/root || "
                    "cat /root/.ssh/authorized_keys | tail -n1 "
                    ">> /boot/config/ssh/root) && "
                    "echo persistent-write-ok",
                ],
                "Writing persistent SSH key",
                timeout=30,
                check=True,
            )
            utils.print_success(
                "SSH key also stored at /boot/config/ssh/root — "
                "survives remote reboots."
            )
        except SubprocessError as e:
            utils.print_warning(
                f"Could not write persistent SSH key path on remote: {e}. "
                f"The key works for now but may be lost on remote reboot. "
                f"Manually copy /root/.ssh/authorized_keys → "
                f"/boot/config/ssh/root on the remote to fix this."
            )

    def _verify_passwordless(self, host: str, key_path: Path) -> bool:
        """One last check that the installed key actually unlocks
        passwordless SSH. Returns True on success. If it fails, the
        caller can decide whether to retry the deployment or continue —
        but at least the next Kopia call won't be a surprise.
        """
        from kopi_docka.helpers import ui_utils as utils

        try:
            result = run_command(
                [
                    "ssh", "-i", str(key_path),
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=10",
                    "-o", "PasswordAuthentication=no",
                    f"root@{host}",
                    "echo passwordless-ok",
                ],
                "Verifying passwordless SSH",
                timeout=15,
                check=False,
            )
            if "passwordless-ok" in (result.stdout or ""):
                utils.print_success(
                    f"Passwordless SSH to {host} verified — Kopia will be able "
                    f"to back up without prompting."
                )
                return True
            utils.print_warning(
                f"Passwordless SSH check did NOT succeed (exit "
                f"{result.returncode}). The key was supplied but the remote is "
                f"still refusing key-based auth. Likely causes: sshd_config "
                f"disallowing pubkey auth, wrong permissions on /root/.ssh/, "
                f"or the key didn't land in the expected file. Run "
                f"`ssh -i {key_path} -v root@{host}` manually to see the "
                f"negotiation."
            )
            return False
        except SubprocessError as e:
            utils.print_warning(
                f"Could not verify passwordless SSH: {e}. "
                f"Test manually with: ssh -i {key_path} root@{host}"
            )
            return False

    def _ensure_key_on_remote(self, host: str, key_path: Path) -> None:
        """Existing local key: check if it already gets us passwordless SSH
        to this peer. If yes, do nothing. If no, offer the same auto/manual
        deployment as a fresh key would get.
        """
        from kopi_docka.helpers import ui_utils as utils

        if self._verify_passwordless(host, key_path):
            return

        utils.console.print()
        utils.print_warning(
            "Existing local SSH key doesn't authenticate against this peer "
            "yet — let's install it."
        )
        self._deploy_public_key(host, key_path)

    def get_recovery_instructions(self) -> str:
        """Get recovery instructions"""
        creds = self.config.get("credentials", {})
        hostname = creds.get("peer_hostname", "backup-server")
        # v7.3.12: prefer the real FQDN written by setup_interactive;
        # fall back to bare hostname for very old configs.
        host = creds.get("peer_fqdn") or hostname
        ssh_user = creds.get("ssh_user", "root")
        remote_path = creds.get("remote_path", "/backup/kopi-docka")

        return f"""
## {self.display_name} Recovery

**Peer:** `{host}`
**Remote Path:** `{remote_path}`

### Recovery Steps:

1. **Install and start Tailscale**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

2. **Restore SSH key**
   ```bash
   # Copy SSH key from recovery bundle
   cp credentials/ssh-keys/kopi-docka_ed25519 ~/.ssh/
   chmod 600 ~/.ssh/kopi-docka_ed25519
   ```

3. **Test connection to peer**
   ```bash
   tailscale ping {hostname}
   ssh -i ~/.ssh/kopi-docka_ed25519 {ssh_user}@{host}
   ```

4. **Install Kopia**
   ```bash
   # See: https://kopia.io/docs/installation/
   ```

5. **Connect to repository**
   ```bash
   kopia repository connect sftp \\
     --path sftp://{ssh_user}@{host}:{remote_path} \\
     --sftp-key-file ~/.ssh/kopi-docka_ed25519
   ```

6. **List snapshots**
   ```bash
   kopia snapshot list
   ```

7. **Restore data**
   ```bash
   kopi-docka restore
   ```

### Notes:
- Ensure you're logged into the same Tailnet
- The backup peer must be online
- SSH key must have correct permissions (600)
"""
