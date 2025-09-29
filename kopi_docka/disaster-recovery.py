"""
Disaster Recovery module for Kopi-Docka.

This module creates and manages disaster recovery bundles that contain
everything needed to restore from a completely fresh system.
"""

import json
import logging
import subprocess
import tarfile
import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import secrets
import string

from .config import Config
from .repository import KopiaRepository
from .constants import VERSION


logger = logging.getLogger(__name__)


class DisasterRecoveryManager:
    """
    Creates and manages disaster recovery bundles.
    
    These bundles contain everything needed to restore from scratch:
    - Kopia repository configuration
    - Encryption keys/passwords
    - Cloud storage credentials
    - Docker configuration
    - Recovery instructions
    """
    
    def __init__(self, config: Config):
        """
        Initialize disaster recovery manager.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.repo = KopiaRepository(config)
    
    def create_recovery_bundle(self, output_path: Optional[Path] = None) -> Path:
        """
        Create a disaster recovery bundle.
        
        Args:
            output_path: Where to save the bundle (default: current directory)
            
        Returns:
            Path to the created bundle
        """
        if output_path is None:
            output_path = Path.cwd()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        bundle_name = f"kopi-docka-recovery-{timestamp}"
        bundle_dir = Path("/tmp") / bundle_name
        bundle_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            logger.info("Creating disaster recovery bundle...")
            
            # 1. Create recovery info JSON
            recovery_info = self._create_recovery_info()
            with open(bundle_dir / 'recovery-info.json', 'w') as f:
                json.dump(recovery_info, f, indent=2)
            
            # 2. Export Kopia repository configuration
            self._export_kopia_config(bundle_dir)
            
            # 3. Save current Kopi-Docka configuration
            if self.config.config_file.exists():
                import shutil
                shutil.copy(self.config.config_file, bundle_dir / 'kopi-docka.conf')
            
            # 4. Create recovery script
            self._create_recovery_script(bundle_dir, recovery_info)
            
            # 5. Create recovery instructions
            self._create_recovery_instructions(bundle_dir, recovery_info)
            
            # 6. Get latest backup status
            backup_status = self._get_backup_status()
            with open(bundle_dir / 'backup-status.json', 'w') as f:
                json.dump(backup_status, f, indent=2)
            
            # 7. Create encrypted archive
            archive_path = output_path / f"{bundle_name}.tar.gz.enc"
            password = self._create_encrypted_archive(bundle_dir, archive_path)
            
            # 8. Create companion file with instructions
            self._create_companion_file(archive_path, password, recovery_info)
            
            logger.info(f"Recovery bundle created: {archive_path}")
            logger.info(f"Companion file: {archive_path}.README")
            
            return archive_path
            
        finally:
            # Cleanup temp directory
            import shutil
            if bundle_dir.exists():
                shutil.rmtree(bundle_dir)
    
    def _create_recovery_info(self) -> Dict[str, Any]:
        """
        Create recovery information document.
        
        Returns:
            Dictionary with all recovery information
        """
        # Get repository info
        repo_status = {}
        try:
            result = subprocess.run(
                ['kopia', 'repository', 'status', '--json'],
                env=self.repo._get_env(),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                repo_status = json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"Could not get repository status: {e}")
        
        # Determine repository type and connection info
        repo_path = str(self.config.kopia_repository_path)
        repo_type = "filesystem"
        connection_info = {"path": repo_path}
        
        if repo_path.startswith('s3://'):
            repo_type = "s3"
            connection_info = {
                "bucket": repo_path.replace('s3://', ''),
                "note": "AWS credentials needed (see recovery script)"
            }
        elif repo_path.startswith('b2://'):
            repo_type = "b2"
            connection_info = {
                "bucket": repo_path.replace('b2://', ''),
                "note": "Backblaze credentials needed"
            }
        elif repo_path.startswith('azure://'):
            repo_type = "azure"
            connection_info = {
                "container": repo_path.replace('azure://', ''),
                "note": "Azure credentials needed"
            }
        elif repo_path.startswith('gs://'):
            repo_type = "gcs"
            connection_info = {
                "bucket": repo_path.replace('gs://', ''),
                "note": "Google Cloud credentials needed"
            }
        
        return {
            "created_at": datetime.now().isoformat(),
            "kopi_docka_version": VERSION,
            "hostname": subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip(),
            "repository": {
                "type": repo_type,
                "connection": connection_info,
                "encryption": self.config.get('kopia', 'encryption'),
                "compression": self.config.get('kopia', 'compression'),
            },
            "kopia_version": self._get_kopia_version(),
            "docker_version": self._get_docker_version(),
            "python_version": self._get_python_version(),
        }
    
    def _export_kopia_config(self, bundle_dir: Path):
        """
        Export Kopia repository configuration.
        
        Args:
            bundle_dir: Directory to save configuration
        """
        try:
            # Export repository config
            result = subprocess.run(
                ['kopia', 'repository', 'status', '--json'],
                env=self.repo._get_env(),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                with open(bundle_dir / 'kopia-repository.json', 'w') as f:
                    f.write(result.stdout)
            
            # Save password separately (encrypted in main bundle)
            with open(bundle_dir / 'kopia-password.txt', 'w') as f:
                f.write(self.config.kopia_password)
            
        except Exception as e:
            logger.error(f"Could not export Kopia config: {e}")
    
    def _create_recovery_script(self, bundle_dir: Path, recovery_info: Dict[str, Any]):
        """
        Create automated recovery script.
        
        Args:
            bundle_dir: Directory to save script
            recovery_info: Recovery information
        """
        repo_type = recovery_info['repository']['type']
        
        script_content = '''#!/bin/bash
#
# Kopi-Docka Disaster Recovery Script
# Generated: {timestamp}
#
# This script helps restore your Docker backup system from scratch

set -e

echo "========================================"
echo "Kopi-Docka Disaster Recovery"
echo "========================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo)"
    exit 1
fi

# Function to check command exists
command_exists() {{
    command -v "$1" >/dev/null 2>&1
}}

# Check prerequisites
echo "Checking prerequisites..."

if ! command_exists docker; then
    echo "ERROR: Docker is not installed"
    echo "Please install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! command_exists kopia; then
    echo "Installing Kopia..."
    curl -s https://kopia.io/signing-key | apt-key add -
    echo "deb http://packages.kopia.io/apt/ stable main" | tee /etc/apt/sources.list.d/kopia.list
    apt update
    apt install -y kopia
fi

if ! command_exists python3; then
    echo "ERROR: Python 3 is not installed"
    exit 1
fi

# Install Kopi-Docka
echo "Installing Kopi-Docka..."
if [ ! -d "kopi-docka" ]; then
    git clone https://github.com/yourusername/kopi-docka.git
fi
cd kopi-docka
pip3 install -e .

# Restore configuration
echo "Restoring configuration..."
mkdir -p /etc
cp ../kopi-docka.conf /etc/kopi-docka.conf

# Read Kopia password
KOPIA_PASSWORD=$(cat ../kopia-password.txt)
export KOPIA_PASSWORD

# Connect to repository
echo "Connecting to Kopia repository..."
'''.format(timestamp=recovery_info['created_at'])
        
        # Add repository-specific connection
        if repo_type == 'filesystem':
            script_content += '''
kopia repository connect filesystem \\
    --path={path}
'''.format(path=recovery_info['repository']['connection']['path'])
        
        elif repo_type == 's3':
            script_content += '''
echo "Enter AWS credentials:"
read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
read -s -p "AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
echo

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY

kopia repository connect s3 \\
    --bucket={bucket} \\
    --access-key=$AWS_ACCESS_KEY_ID \\
    --secret-access-key=$AWS_SECRET_ACCESS_KEY
'''.format(bucket=recovery_info['repository']['connection']['bucket'])
        
        elif repo_type == 'b2':
            script_content += '''
echo "Enter Backblaze B2 credentials:"
read -p "B2 Account ID: " B2_ACCOUNT_ID
read -s -p "B2 Account Key: " B2_ACCOUNT_KEY
echo

kopia repository connect b2 \\
    --bucket={bucket} \\
    --key-id=$B2_ACCOUNT_ID \\
    --key=$B2_ACCOUNT_KEY
'''.format(bucket=recovery_info['repository']['connection']['bucket'])
        
        script_content += '''

# Verify connection
echo "Verifying repository connection..."
kopia repository status

# List available backups
echo ""
echo "Available backup units:"
kopi-docka list --units

echo ""
echo "========================================"
echo "Recovery environment ready!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Run: kopi-docka list --units"
echo "2. Run: kopi-docka restore"
echo "3. Follow the restoration wizard"
echo ""
'''
        
        script_path = bundle_dir / 'recover.sh'
        script_path.write_text(script_content)
        script_path.chmod(0o755)
    
    def _create_recovery_instructions(self, bundle_dir: Path, recovery_info: Dict[str, Any]):
        """
        Create human-readable recovery instructions.
        
        Args:
            bundle_dir: Directory to save instructions
            recovery_info: Recovery information
        """
        instructions = f'''
KOPI-DOCKA DISASTER RECOVERY INSTRUCTIONS
==========================================

Created: {recovery_info['created_at']}
System: {recovery_info['hostname']}

CRITICAL INFORMATION:
--------------------
Repository Type: {recovery_info['repository']['type']}
Repository Location: {json.dumps(recovery_info['repository']['connection'], indent=2)}
Encryption: {recovery_info['repository']['encryption']}

RECOVERY STEPS:
---------------

1. PREPARE NEW SYSTEM
   - Install Ubuntu/Debian Linux
   - Install Docker: https://docs.docker.com/engine/install/
   - Ensure you have root/sudo access

2. EXTRACT THIS BUNDLE
   After decrypting, you'll have:
   - recovery-info.json: This information
   - kopi-docka.conf: Your configuration
   - kopia-password.txt: Repository password (KEEP SECURE!)
   - recover.sh: Automated recovery script
   - backup-status.json: Last backup status

3. RUN RECOVERY SCRIPT
   chmod +x recover.sh
   sudo ./recover.sh

4. CLOUD STORAGE CREDENTIALS
   Depending on your repository type, you'll need:
'''
        
        if recovery_info['repository']['type'] == 's3':
            instructions += '''
   - AWS Access Key ID
   - AWS Secret Access Key
   - Optional: AWS Region
'''
        elif recovery_info['repository']['type'] == 'b2':
            instructions += '''
   - Backblaze Account ID
   - Backblaze Application Key
'''
        elif recovery_info['repository']['type'] == 'azure':
            instructions += '''
   - Azure Storage Account Name
   - Azure Storage Account Key
'''
        elif recovery_info['repository']['type'] == 'gcs':
            instructions += '''
   - Google Cloud Service Account JSON
'''
        
        instructions += '''

5. RESTORE YOUR CONTAINERS
   Once connected to the repository:
   
   a) List available backups:
      kopi-docka list --units
   
   b) Start restore wizard:
      kopi-docka restore
   
   c) Select the backup point you want to restore
   
   d) The wizard will:
      - Restore all volumes
      - Recreate containers with original settings
      - Restore database contents
      - Start all services

6. VERIFY RESTORATION
   docker ps                    # Check running containers
   docker-compose ps            # Check compose stacks
   docker volume ls             # Check volumes
   journalctl -u kopi-docka     # Check logs

SECURITY NOTES:
---------------
- The kopia-password.txt file contains your encryption key
- NEVER share this bundle unencrypted
- Store copies in multiple secure locations
- Test recovery procedure regularly

SUPPORT:
--------
Documentation: https://github.com/yourusername/kopi-docka
Issues: https://github.com/yourusername/kopi-docka/issues

'''
        
        (bundle_dir / 'RECOVERY-INSTRUCTIONS.txt').write_text(instructions)
    
    def _get_backup_status(self) -> Dict[str, Any]:
        """
        Get current backup status.
        
        Returns:
            Dictionary with backup status information
        """
        status = {
            "timestamp": datetime.now().isoformat(),
            "units": [],
            "snapshots": []
        }
        
        try:
            # Get backup units
            units = self.repo.list_backup_units()
            status["units"] = units
            
            # Get recent snapshots
            snapshots = self.repo.list_snapshots()
            status["snapshots"] = snapshots[:10]  # Last 10 snapshots
            
        except Exception as e:
            logger.error(f"Could not get backup status: {e}")
        
        return status
    
    def _create_encrypted_archive(self, bundle_dir: Path, output_path: Path) -> str:
        """
        Create encrypted archive of the bundle.
        
        Args:
            bundle_dir: Directory to archive
            output_path: Output path for encrypted archive
            
        Returns:
            Encryption password
        """
        # Generate strong password
        password = ''.join(secrets.choice(
            string.ascii_letters + string.digits + string.punctuation
        ) for _ in range(32))
        
        # Create tar.gz
        tar_path = output_path.with_suffix('')
        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(bundle_dir, arcname=bundle_dir.name)
        
        # Encrypt with openssl
        subprocess.run([
            'openssl', 'enc', '-aes-256-cbc', '-salt', '-pbkdf2',
            '-in', str(tar_path),
            '-out', str(output_path),
            '-pass', f'pass:{password}'
        ], check=True)
        
        # Remove unencrypted tar
        tar_path.unlink()
        
        return password
    
    def _create_companion_file(self, archive_path: Path, password: str, recovery_info: Dict[str, Any]):
        """
        Create companion file with decryption instructions.
        
        Args:
            archive_path: Path to encrypted archive
            password: Encryption password
            recovery_info: Recovery information
        """
        companion_content = f'''
KOPI-DOCKA DISASTER RECOVERY BUNDLE
====================================

This is your disaster recovery bundle for Docker backups.
Created: {recovery_info['created_at']}
System: {recovery_info['hostname']}

FILE INFORMATION:
-----------------
Encrypted Archive: {archive_path.name}
SHA256 Checksum: {self._calculate_checksum(archive_path)}

DECRYPTION PASSWORD:
--------------------
{password}

⚠️  STORE THIS PASSWORD SECURELY!
⚠️  Without it, recovery is impossible!

DECRYPTION COMMAND:
-------------------
openssl enc -aes-256-cbc -salt -pbkdf2 -d \\
    -in {archive_path.name} \\
    -out {archive_path.stem} \\
    -pass pass:'{password}'

tar -xzf {archive_path.stem}

QUICK RECOVERY:
---------------
1. Decrypt the archive (command above)
2. Enter the extracted directory
3. Run: sudo ./recover.sh
4. Follow the prompts

WHAT'S INCLUDED:
----------------
✓ Kopia repository configuration
✓ Encryption keys and passwords  
✓ Cloud storage connection details
✓ Docker configuration
✓ Automated recovery script
✓ Step-by-step instructions

IMPORTANT:
----------
Store this bundle in multiple secure locations:
- Password manager (recommended)
- Encrypted USB drive
- Secure cloud storage
- Physical safe (printed)

Repository Type: {recovery_info['repository']['type']}
Repository: {json.dumps(recovery_info['repository']['connection'], indent=2)}

For detailed instructions, decrypt the bundle and read
RECOVERY-INSTRUCTIONS.txt

====================================
Generated by Kopi-Docka v{VERSION}
'''
        
        companion_path = Path(str(archive_path) + '.README')
        companion_path.write_text(companion_content)
        
        # Also create a minimal version with just the password
        password_path = Path(str(archive_path) + '.PASSWORD')
        password_path.write_text(f"Decryption Password: {password}\n")
        password_path.chmod(0o600)
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _get_kopia_version(self) -> str:
        """Get Kopia version."""
        try:
            result = subprocess.run(['kopia', 'version'], capture_output=True, text=True)
            return result.stdout.strip().split('\n')[0]
        except:
            return "unknown"
    
    def _get_docker_version(self) -> str:
        """Get Docker version."""
        try:
            result = subprocess.run(
                ['docker', 'version', '--format', '{{.Server.Version}}'],
                capture_output=True, text=True
            )
            return result.stdout.strip()
        except:
            return "unknown"
    
    def _get_python_version(self) -> str:
        """Get Python version."""
        import sys
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"