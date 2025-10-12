"""
Filesystem Backend for Kopi-Docka

Local filesystem or NAS storage backend.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base import BackendBase, ConfigurationError, DependencyError
from ..i18n import _
from ..utils.dependency_installer import DependencyInstaller


class FilesystemBackend(BackendBase):
    """Local filesystem or NAS storage backend"""
    
    @property
    def name(self) -> str:
        return "filesystem"
    
    @property
    def display_name(self) -> str:
        return _("Local Filesystem / NAS")
    
    @property
    def description(self) -> str:
        return _("Store backups on local disk or network-attached storage (NFS, CIFS, SMB)")
    
    def check_dependencies(self) -> List[str]:
        """Check if Kopia is installed"""
        missing = []
        if not shutil.which("kopia"):
            missing.append("kopia")
        return missing
    
    def install_dependencies(self) -> bool:
        """Install Kopia"""
        installer = DependencyInstaller()
        return installer.install_kopia()
    
    def setup_interactive(self) -> Dict[str, Any]:
        """
        Interactive setup for filesystem backend.
        
        Note: This is a simplified version using print/input.
        Full Textual UI version will be implemented later.
        """
        print("\n" + "=" * 60)
        print(_("Filesystem Backend Setup"))
        print("=" * 60)
        
        # Get repository path
        default_path = "/backup/kopia-repository"
        path_str = input(f"\n{_('Repository path')} [{default_path}]: ").strip()
        
        if not path_str:
            path_str = default_path
        
        # Expand and resolve path
        path = Path(path_str).expanduser().resolve()
        
        # Create directory if not exists
        if not path.exists():
            create = input(f"\n{_('Directory does not exist. Create it?')} (Y/n): ").strip().lower()
            if create in ('', 'y', 'yes'):
                try:
                    path.mkdir(parents=True, mode=0o700)
                    print(f"✓ {_('Created directory')}: {path}")
                except Exception as e:
                    raise ConfigurationError(f"{_('Failed to create directory')}: {e}")
            else:
                raise ConfigurationError(_("Repository directory required"))
        
        # Check permissions
        if not os.access(path, os.W_OK):
            raise ConfigurationError(
                f"{_('No write permission for')}: {path}\n"
                f"{_('Run with sudo or choose a different path')}"
            )
        
        print(f"\n✓ {_('Repository path')}: {path}")
        
        return {
            "type": "filesystem",
            "repository_path": str(path),
            "credentials": {}
        }
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate filesystem configuration"""
        errors = []
        
        # Check repository_path exists
        if "repository_path" not in self.config:
            errors.append(_("Missing repository_path in configuration"))
            return (False, errors)
        
        repo_path = Path(self.config["repository_path"]).expanduser()
        
        # Check if path exists
        if not repo_path.exists():
            errors.append(f"{_('Repository path does not exist')}: {repo_path}")
        
        # Check if writable
        if repo_path.exists() and not os.access(repo_path, os.W_OK):
            errors.append(f"{_('No write permission for')}: {repo_path}")
        
        # Check if path is a directory
        if repo_path.exists() and not repo_path.is_dir():
            errors.append(f"{_('Path is not a directory')}: {repo_path}")
        
        return (len(errors) == 0, errors)
    
    def test_connection(self) -> bool:
        """Test filesystem access"""
        try:
            repo_path = Path(self.config["repository_path"]).expanduser()
            
            # Create test file
            test_file = repo_path / ".kopi-docka-test"
            test_file.write_text("test")
            
            # Read it back
            content = test_file.read_text()
            
            # Delete it
            test_file.unlink()
            
            return content == "test"
            
        except Exception as e:
            print(f"✗ {_('Connection test failed')}: {e}")
            return False
    
    def get_kopia_args(self) -> List[str]:
        """Get Kopia CLI arguments for filesystem backend"""
        return [
            "--path",
            str(Path(self.config["repository_path"]).expanduser())
        ]
    
    def get_backend_type(self) -> str:
        """Kopia backend type"""
        return "filesystem"
    
    def get_recovery_instructions(self) -> str:
        """Get recovery instructions for this backend"""
        repo_path = self.config.get("repository_path", "/backup/kopia-repository")
        
        return f"""
## {self.display_name} Recovery

**Repository Path:** `{repo_path}`

### Recovery Steps:

1. **Mount the filesystem** (if NAS/network storage)
   ```bash
   # Example for NFS:
   sudo mount -t nfs nas.local:/backup /mnt/backup
   
   # Example for CIFS/SMB:
   sudo mount -t cifs //nas.local/backup /mnt/backup -o username=user
   ```

2. **Verify the repository**
   ```bash
   ls -la {repo_path}
   # Should contain Kopia repository files
   ```

3. **Install Kopia** (if not installed)
   ```bash
   # See: https://kopia.io/docs/installation/
   ```

4. **Connect to repository**
   ```bash
   kopia repository connect filesystem --path {repo_path}
   ```

5. **List snapshots**
   ```bash
   kopia snapshot list
   ```

6. **Restore data**
   ```bash
   kopi-docka restore
   # or
   kopia snapshot restore <snapshot-id> /restore/path
   ```

### Notes:
- Ensure the filesystem is mounted and accessible
- Check file permissions (should be readable by current user)
- For NAS: Verify network connectivity
"""


# Register backend
from . import register_backend
register_backend(FilesystemBackend)
