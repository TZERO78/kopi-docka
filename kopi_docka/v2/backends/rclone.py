"""
Rclone Backend for Kopi-Docka

Universal cloud storage backend supporting 70+ providers:
Google Drive, Dropbox, OneDrive, S3, B2, and many more!
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base import BackendBase, ConfigurationError, DependencyError
from ..i18n import _
from ..utils.dependency_installer import DependencyInstaller


class RcloneBackend(BackendBase):
    """Universal cloud storage via rclone"""
    
    @property
    def name(self) -> str:
        return "rclone"
    
    @property
    def display_name(self) -> str:
        return _("Rclone (Universal Cloud)")
    
    @property
    def description(self) -> str:
        return _("Support for 70+ cloud providers: Google Drive, Dropbox, OneDrive, S3, B2, and more")
    
    def check_dependencies(self) -> List[str]:
        """Check if Kopia and rclone are installed"""
        missing = []
        if not shutil.which("kopia"):
            missing.append("kopia")
        if not shutil.which("rclone"):
            missing.append("rclone")
        return missing
    
    def install_dependencies(self) -> bool:
        """Install Kopia and rclone"""
        installer = DependencyInstaller()
        
        success = True
        if not shutil.which("kopia"):
            success = success and installer.install_kopia()
        if not shutil.which("rclone"):
            success = success and installer.install_rclone()
        
        return success
    
    def setup_interactive(self) -> Dict[str, Any]:
        """Interactive setup for rclone backend"""
        print("\n" + "=" * 60)
        print(_("Rclone Backend Setup"))
        print("=" * 60)
        
        # List existing remotes
        remotes = self._list_remotes()
        
        if remotes:
            print(f"\n{_('Existing rclone remotes')}:")
            for i, remote in enumerate(remotes, 1):
                remote_type = self._get_remote_type(remote)
                print(f"  {i}. {remote} ({remote_type})")
            print(f"  {len(remotes) + 1}. {_('Create new remote')}")
            
            choice = input(f"\n{_('Select option')} [1-{len(remotes) + 1}]: ").strip()
            
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(remotes):
                    remote_name = remotes[choice_num - 1]
                else:
                    # Create new remote
                    remote_name = self._create_new_remote()
            except (ValueError, IndexError):
                remote_name = remotes[0] if remotes else self._create_new_remote()
        else:
            print(f"\n{_('No rclone remotes found')}.")
            remote_name = self._create_new_remote()
        
        # Get path in remote
        default_path = "kopi-docka-backups"
        remote_path = input(f"\n{_('Path in remote')} [{default_path}]: ").strip()
        if not remote_path:
            remote_path = default_path
        
        # Get rclone config location
        rclone_config = Path.home() / ".config/rclone/rclone.conf"
        if not rclone_config.exists():
            rclone_config = Path.home() / ".rclone.conf"
        
        if not rclone_config.exists():
            raise ConfigurationError(_("Rclone config file not found"))
        
        full_path = f"{remote_name}:{remote_path}"
        print(f"\n✓ {_('Remote path')}: {full_path}")
        
        return {
            "type": "rclone",
            "repository_path": full_path,
            "credentials": {
                "remote_name": remote_name,
                "remote_path": remote_path,
                "rclone_config": str(rclone_config)
            }
        }
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate rclone configuration"""
        errors = []
        
        if "repository_path" not in self.config:
            errors.append(_("Missing repository_path"))
            return (False, errors)
        
        if "credentials" not in self.config:
            errors.append(_("Missing credentials"))
            return (False, errors)
        
        creds = self.config["credentials"]
        
        # Check rclone_config exists
        if "rclone_config" not in creds:
            errors.append(_("Missing rclone_config in credentials"))
        else:
            config_path = Path(creds["rclone_config"])
            if not config_path.exists():
                errors.append(f"{_('Rclone config not found')}: {config_path}")
        
        # Check remote_name exists
        if "remote_name" in creds:
            remote_name = creds["remote_name"]
            remotes = self._list_remotes()
            if remote_name not in remotes:
                errors.append(f"{_('Remote not found')}: {remote_name}")
        
        return (len(errors) == 0, errors)
    
    def test_connection(self) -> bool:
        """Test rclone connection"""
        try:
            remote_path = self.config["repository_path"]
            
            # Test with rclone lsd (list directories)
            result = subprocess.run(
                ["rclone", "lsd", remote_path],
                capture_output=True,
                text=True,
                timeout=30
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
        """
        Get Kopia CLI arguments for rclone backend.
        
        CRITICAL: Uses --embed-rclone-config to avoid timeout issues!
        """
        creds = self.config.get("credentials", {})
        remote_path = self.config["repository_path"]
        rclone_config = creds.get("rclone_config", str(Path.home() / ".config/rclone/rclone.conf"))
        
        return [
            "--remote-path", remote_path,
            "--embed-rclone-config", rclone_config
        ]
    
    def get_backend_type(self) -> str:
        """Kopia backend type"""
        return "rclone"
    
    def get_env_vars(self) -> Dict[str, str]:
        """Get environment variables for rclone"""
        creds = self.config.get("credentials", {})
        rclone_config = creds.get("rclone_config")
        
        if rclone_config:
            return {"RCLONE_CONFIG": rclone_config}
        return {}
    
    # Helper methods
    
    def _list_remotes(self) -> List[str]:
        """List configured rclone remotes"""
        try:
            result = subprocess.run(
                ["rclone", "listremotes"],
                capture_output=True,
                text=True,
                check=True
            )
            # Remove trailing colons from remote names
            return [line.rstrip(':') for line in result.stdout.strip().split('\n') if line]
        except subprocess.CalledProcessError:
            return []
    
    def _get_remote_type(self, remote_name: str) -> str:
        """Get remote type (e.g., 'drive', 's3', 'dropbox')"""
        try:
            result = subprocess.run(
                ["rclone", "config", "dump"],
                capture_output=True,
                text=True,
                check=True
            )
            config_data = json.loads(result.stdout)
            if remote_name in config_data:
                return config_data[remote_name].get("type", "unknown")
        except Exception:
            pass
        return "unknown"
    
    def _create_new_remote(self) -> str:
        """Guide user to create new rclone remote"""
        print(f"\n{_('Creating new rclone remote...')}")
        print(_("This will launch the rclone config wizard."))
        print(_("Follow the prompts to add a new remote."))
        
        input(f"\n{_('Press Enter to continue')}...")
        
        # Launch rclone config
        subprocess.run(["rclone", "config"])
        
        # List remotes again
        remotes = self._list_remotes()
        if not remotes:
            raise ConfigurationError(_("No remotes configured"))
        
        # Return the last (newly created) remote
        return remotes[-1]
    
    def get_recovery_instructions(self) -> str:
        """Get recovery instructions"""
        remote_path = self.config.get("repository_path", "remote:path")
        
        return f"""
## {self.display_name} Recovery

**Remote Path:** `{remote_path}`

### Recovery Steps:

1. **Install rclone**
   ```bash
   curl https://rclone.org/install.sh | sudo bash
   ```

2. **Restore rclone configuration**
   ```bash
   # Copy rclone.conf from recovery bundle
   cp credentials/rclone.conf ~/.config/rclone/rclone.conf
   chmod 600 ~/.config/rclone/rclone.conf
   ```

3. **Test remote connection**
   ```bash
   rclone lsd {remote_path}
   ```

4. **Install Kopia**
   ```bash
   # See: https://kopia.io/docs/installation/
   ```

5. **Connect to repository**
   ```bash
   kopia repository connect rclone \\
     --remote-path {remote_path} \\
     --embed-rclone-config ~/.config/rclone/rclone.conf
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
- The rclone config must contain valid credentials
- Test the remote connection before attempting restore
- Use --embed-rclone-config to avoid timeout issues
"""


# Register backend
from . import register_backend
register_backend(RcloneBackend)
