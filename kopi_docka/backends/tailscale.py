"""
Tailscale Backend for Kopi-Docka

🔥 Killer Feature: Secure, offsite backups over your Tailscale network!

Automatically discovers peers in your Tailnet, shows disk space and latency,
and sets up passwordless SSH access.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.markup import escape

from .base import BackendBase, ConfigurationError, DependencyError
from ..i18n import _
from ..helpers.dependency_installer import DependencyInstaller


@dataclass
class TailscalePeer:
    """Tailscale peer information"""
    hostname: str
    ip: str
    online: bool
    os: str
    disk_free_gb: Optional[float] = None
    ping_ms: Optional[int] = None


class TailscaleBackend(BackendBase):
    """Secure backups over Tailscale VPN"""
    
    @property
    def name(self) -> str:
        return "tailscale"
    
    @property
    def display_name(self) -> str:
        return _("Tailscale Network")
    
    @property
    def description(self) -> str:
        return _("🔥Secure offsite backups over your private Tailscale network (recommended!)")
    
    def check_dependencies(self) -> List[str]:
        """Check if Kopia and Tailscale are installed"""
        missing = []
        if not shutil.which("kopia"):
            missing.append("kopia")
        if not shutil.which("tailscale"):
            missing.append("tailscale")
        return missing
    
    def install_dependencies(self) -> bool:
        """Install Kopia and Tailscale"""
        installer = DependencyInstaller()
        
        success = True
        if not shutil.which("kopia"):
            success = success and installer.install_kopia()
        if not shutil.which("tailscale"):
            success = success and installer.install_tailscale()
        
        return success
    
    def setup_interactive(self) -> Dict[str, Any]:
        """Interactive setup for Tailscale backend using Rich CLI"""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language
        
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
                ("Hostname", "cyan", 20),
                ("IP", "white", 15),
                ("Disk Free", "green", 12),
                ("Latency", "yellow", 10),
            ]
        )
        
        for peer in peers:
            status = "🟢 Online" if peer.online else "🔴 Offline"
            disk_info = f"{peer.disk_free_gb:.1f}GB" if peer.disk_free_gb else "?"
            ping_info = f"{peer.ping_ms}ms" if peer.ping_ms else "?"
            
            table.add_row(status, peer.hostname, peer.ip, disk_info, ping_info)
        
        utils.console.print(table)
        
        # Select peer using numbered selection
        selected_peer = utils.prompt_select(
            t("tailscale.select_peer", lang),
            peers,
            display_fn=lambda p: f"{'🟢' if p.online else '🔴'} {p.hostname} ({p.ip})"
        )
        
        if not selected_peer.online:
            utils.print_warning(t("tailscale.peer_offline", lang))
        
        # Get remote path
        default_path = "/backup/kopi-docka"
        remote_path = utils.prompt_text(
            f"{t('tailscale.backup_path', lang)} {escape(f'[{default_path}]')}",
            default=default_path
        )
        
        if not remote_path.startswith("/"):
            utils.print_error(t("tailscale.path_must_be_absolute", lang))
            raise ConfigurationError("Path must be absolute")
        
        # Setup SSH key
        ssh_key_path = Path.home() / ".ssh" / "kopi-docka_ed25519"
        if not ssh_key_path.exists():
            if utils.prompt_confirm(t("tailscale.setup_ssh_key", lang)):
                self._setup_ssh_key(selected_peer.hostname, ssh_key_path)
        
        # Get SSH user
        ssh_user = utils.prompt_text(
            f"{t('tailscale.ssh_user', lang)} [root]",
            default="root"
        )
        
        # Build SFTP URL
        repository_path = f"sftp://{ssh_user}@{selected_peer.hostname}.tailnet:{remote_path}"
        
        utils.print_separator()
        utils.print_success(f"Repository path: {escape(repository_path)}")
        
        return {
            "type": "sftp",  # Kopia uses SFTP backend
            "repository_path": repository_path,
            "credentials": {
                "peer_hostname": selected_peer.hostname,
                "peer_ip": selected_peer.ip,
                "ssh_user": ssh_user,
                "ssh_key": str(ssh_key_path),
                "remote_path": remote_path
            }
        }
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate Tailscale configuration"""
        errors = []
        
        if "repository_path" not in self.config:
            errors.append(_("Missing repository_path"))
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
            hostname = creds.get("peer_hostname")
            ssh_user = creds.get("ssh_user", "root")
            ssh_key = creds.get("ssh_key")
            
            # Test SSH connection
            cmd = ["ssh", "-i", ssh_key, "-o", "StrictHostKeyChecking=no", 
                   f"{ssh_user}@{hostname}.tailnet", "echo", "test"]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
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
        """Get Kopia CLI arguments for SFTP backend"""
        creds = self.config.get("credentials", {})
        ssh_key = creds.get("ssh_key", str(Path.home() / ".ssh/kopi-docka_ed25519"))
        
        # Extract hostname and path from repository_path
        # Format: sftp://user@hostname.tailnet:/path
        repo_path = self.config["repository_path"]
        
        return [
            "--path", repo_path,
            "--sftp-key-file", ssh_key
        ]
    
    def get_backend_type(self) -> str:
        """Kopia backend type"""
        return "sftp"
    
    # Tailscale-specific helpers
    
    def _is_running(self) -> bool:
        """Check if Tailscale is running"""
        try:
            result = subprocess.run(
                ["tailscale", "status"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def _start_tailscale(self) -> bool:
        """Start Tailscale"""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language
        
        lang = get_current_language()
        
        try:
            subprocess.run(["sudo", "tailscale", "up"], check=True)
            utils.print_success("Tailscale started")
            return True
        except subprocess.CalledProcessError:
            utils.print_error("Failed to start Tailscale")
            return False
    
    def _list_peers(self) -> List[TailscalePeer]:
        """List peers in Tailnet with enriched info"""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
            
            peers = []
            for peer_id, peer_info in data.get("Peer", {}).items():
                hostname = peer_info.get("HostName", "unknown")
                ips = peer_info.get("TailscaleIPs", [])
                ip = ips[0] if ips else "unknown"
                online = peer_info.get("Online", False)
                os = peer_info.get("OS", "unknown")
                
                peer = TailscalePeer(
                    hostname=hostname,
                    ip=ip,
                    online=online,
                    os=os
                )
                
                # Try to get disk space (best effort)
                if online:
                    peer.disk_free_gb = self._get_disk_space(hostname)
                    peer.ping_ms = self._ping_peer(hostname)
                
                peers.append(peer)
            
            # Sort by online status and ping
            peers.sort(key=lambda p: (not p.online, p.ping_ms or 999))
            
            return peers
            
        except Exception as e:
            print(f"⚠️  {_('Failed to list peers')}: {e}")
            return []
    
    def _get_disk_space(self, hostname: str) -> Optional[float]:
        """Get disk space on remote peer (in GB)"""
        try:
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=2",
                 f"root@{hostname}.tailnet", "df", "/", "--output=avail", "--block-size=G"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    # Remove 'G' suffix and convert to float
                    return float(lines[1].rstrip('G'))
        except Exception:
            pass
        return None
    
    def _ping_peer(self, hostname: str) -> Optional[int]:
        """Ping peer and return latency in ms"""
        try:
            result = subprocess.run(
                ["tailscale", "ping", "-c", "1", hostname],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse ping output for latency
                for line in result.stdout.split('\n'):
                    if "time=" in line:
                        time_str = line.split("time=")[1].split()[0]
                        return int(float(time_str.rstrip('ms')))
        except Exception:
            pass
        return None
    
    def _setup_ssh_key(self, hostname: str, key_path: Path) -> bool:
        """Setup SSH key for passwordless access"""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language
        
        lang = get_current_language()
        
        try:
            utils.print_info(t("tailscale.generating_ssh_key", lang))
            
            # Generate ED25519 key
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), 
                 "-N", "", "-C", "kopi-docka-backup"],
                check=True
            )
            
            utils.print_success(t("tailscale.ssh_key_generated", lang))
            
            # Copy to remote
            utils.print_info(f"{t('tailscale.copying_ssh_key', lang)} {hostname}...")
            utils.print_warning("You may need to enter the root password")
            
            subprocess.run(
                ["ssh-copy-id", "-i", str(key_path), f"root@{hostname}.tailnet"],
                check=True
            )
            
            utils.print_success(t("tailscale.ssh_key_copied", lang))
            return True
            
        except subprocess.CalledProcessError as e:
            utils.print_error(f"{t('tailscale.ssh_key_failed', lang)}: {e}")
            return False
    
    def get_recovery_instructions(self) -> str:
        """Get recovery instructions"""
        creds = self.config.get("credentials", {})
        hostname = creds.get("peer_hostname", "backup-server")
        ssh_user = creds.get("ssh_user", "root")
        remote_path = creds.get("remote_path", "/backup/kopi-docka")
        
        return f"""
## {self.display_name} Recovery

**Peer:** `{hostname}.tailnet`
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
   ssh -i ~/.ssh/kopi-docka_ed25519 {ssh_user}@{hostname}.tailnet
   ```

4. **Install Kopia**
   ```bash
   # See: https://kopia.io/docs/installation/
   ```

5. **Connect to repository**
   ```bash
   kopia repository connect sftp \\
     --path sftp://{ssh_user}@{hostname}.tailnet:{remote_path} \\
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


# Register backend
from . import register_backend
register_backend(TailscaleBackend)
