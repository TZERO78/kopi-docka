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
from ..helpers.dependency_installer import DependencyInstaller


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
        """Interactive setup for filesystem backend using Rich CLI"""
        from kopi_docka.helpers import ui_utils as utils
        from kopi_docka.i18n import t, get_current_language
        
        lang = get_current_language()
        
        utils.print_header("Filesystem Backend Setup")
        utils.print_info("Store backups on local disk or network-attached storage")
        utils.print_separator()
        
        # Get repository path
        default_path = "/backup/kopia-repository"
        path_str = utils.prompt_text(
            "Repository path",
            default=default_path
        )
        
        # Expand and resolve path
        path = Path(path_str).expanduser().resolve()
        
        # Create directory if not exists
        if not path.exists():
            if utils.prompt_confirm("Directory does not exist. Create it?"):
                try:
                    path.mkdir(parents=True, mode=0o700)
                    utils.print_success(f"Created directory: {path}")
                except Exception as e:
                    utils.print_error(f"Failed to create directory: {e}")
                    raise ConfigurationError(f"Failed to create directory: {e}")
            else:
                utils.print_error("Repository directory required")
                raise ConfigurationError("Repository directory required")
        
        # Check permissions
        if not os.access(path, os.W_OK):
            utils.print_error(f"No write permission for: {path}")
            utils.print_warning("Run with sudo or choose a different path")
            raise ConfigurationError(f"No write permission for: {path}")
        
        utils.print_separator()
        utils.print_success(f"Repository path: {path}")
        
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
