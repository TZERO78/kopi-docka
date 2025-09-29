"""
Dependency management for Kopi-Docka.

This module handles checking and installing system dependencies.
"""

import logging
import os
import shutil
import subprocess
from typing import List, Dict, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DependencyManager:
    """Manages system dependencies for Kopi-Docka."""
    
    # Define all dependencies with metadata
    DEPENDENCIES = {
        'docker': {
            'check_command': 'docker',
            'check_method': 'check_docker',
            'packages': {
                'debian': 'docker.io',
                'redhat': 'docker',
                'arch': 'docker',
                'alpine': 'docker'
            },
            'required': True,
            'description': 'Docker container runtime',
            'install_notes': 'May require adding user to docker group'
        },
        'kopia': {
            'check_command': 'kopia',
            'check_method': 'check_kopia',
            'packages': {
                'debian': None,  # Special installation
                'redhat': None,  # Special installation
                'arch': 'kopia',  # AUR
                'alpine': None  # Not available
            },
            'required': True,
            'description': 'Kopia backup tool',
            'special_install': True,
            'version_command': ['kopia', 'version']
        },
        'tar': {
            'check_command': 'tar',
            'check_method': 'check_tar',
            'packages': {
                'debian': 'tar',
                'redhat': 'tar',
                'arch': 'tar',
                'alpine': 'tar'
            },
            'required': True,
            'description': 'Archive tool for volume backups'
        },
        'openssl': {
            'check_command': 'openssl',
            'check_method': 'check_openssl',
            'packages': {
                'debian': 'openssl',
                'redhat': 'openssl',
                'arch': 'openssl',
                'alpine': 'openssl'
            },
            'required': True,
            'description': 'Encryption for disaster recovery bundles'
        },
        'du': {
            'check_command': 'du',
            'check_method': 'check_coreutils',
            'packages': {
                'debian': 'coreutils',
                'redhat': 'coreutils',
                'arch': 'coreutils',
                'alpine': 'coreutils'
            },
            'required': False,
            'description': 'Disk usage estimation'
        },
        'hostname': {
            'check_command': 'hostname',
            'check_method': 'check_hostname',
            'packages': {
                'debian': 'hostname',
                'redhat': 'hostname',
                'arch': 'inetutils',
                'alpine': 'hostname'
            },
            'required': False,
            'description': 'System hostname detection'
        },
        'git': {
            'check_command': 'git',
            'check_method': 'check_git',
            'packages': {
                'debian': 'git',
                'redhat': 'git',
                'arch': 'git',
                'alpine': 'git'
            },
            'required': False,
            'description': 'Version control (for recovery scripts)'
        },
        'curl': {
            'check_command': 'curl',
            'check_method': 'check_curl',
            'packages': {
                'debian': 'curl',
                'redhat': 'curl',
                'arch': 'curl',
                'alpine': 'curl'
            },
            'required': False,
            'description': 'Download tool (for recovery scripts)'
        }
    }
    
    def __init__(self):
        """Initialize dependency manager."""
        self.distro = self._detect_distro()
        
    def _detect_distro(self) -> str:
        """
        Detect Linux distribution.
        
        Returns:
            Distribution name: 'debian', 'redhat', 'arch', 'alpine', or 'unknown'
        """
        # Check for various distro-specific files
        if os.path.exists('/etc/debian_version'):
            return 'debian'
        elif os.path.exists('/etc/redhat-release'):
            return 'redhat'
        elif os.path.exists('/etc/arch-release'):
            return 'arch'
        elif os.path.exists('/etc/alpine-release'):
            return 'alpine'
        elif os.path.exists('/etc/os-release'):
            # Try to parse os-release for more info
            try:
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    if 'debian' in content or 'ubuntu' in content:
                        return 'debian'
                    elif 'rhel' in content or 'centos' in content or 'fedora' in content:
                        return 'redhat'
                    elif 'arch' in content:
                        return 'arch'
                    elif 'alpine' in content:
                        return 'alpine'
            except Exception:
                pass
        
        return 'unknown'
    
    # Individual check methods (for backward compatibility and direct access)
    
    @staticmethod
    def check_docker() -> bool:
        """
        Check if Docker is installed and accessible.
        
        Returns:
            True if Docker is available and running
        """
        try:
            result = subprocess.run(
                ['docker', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def check_kopia() -> bool:
        """
        Check if Kopia is installed and accessible.
        
        Returns:
            True if Kopia is available
        """
        return shutil.which('kopia') is not None
    
    @staticmethod
    def check_tar() -> bool:
        """
        Check if tar is installed and accessible.
        
        Returns:
            True if tar is available
        """
        return shutil.which('tar') is not None
    
    @staticmethod
    def check_openssl() -> bool:
        """
        Check if OpenSSL is installed and accessible.
        
        Returns:
            True if OpenSSL is available
        """
        return shutil.which('openssl') is not None
    
    @staticmethod
    def check_coreutils() -> bool:
        """
        Check if coreutils (du, etc.) is installed.
        
        Returns:
            True if coreutils commands are available
        """
        return shutil.which('du') is not None
    
    @staticmethod
    def check_hostname() -> bool:
        """
        Check if hostname command is available.
        
        Returns:
            True if hostname is available
        """
        return shutil.which('hostname') is not None
    
    @staticmethod
    def check_git() -> bool:
        """
        Check if git is installed.
        
        Returns:
            True if git is available
        """
        return shutil.which('git') is not None
    
    @staticmethod
    def check_curl() -> bool:
        """
        Check if curl is installed.
        
        Returns:
            True if curl is available
        """
        return shutil.which('curl') is not None
    
    def check_dependency(self, name: str) -> bool:
        """
        Check if a specific dependency is installed.
        
        Args:
            name: Dependency name from DEPENDENCIES dict
            
        Returns:
            True if dependency is installed
        """
        dep = self.DEPENDENCIES.get(name)
        if not dep:
            return False
        
        # Use specific check method if available
        if 'check_method' in dep:
            method_name = dep['check_method']
            method = getattr(self, method_name, None)
            if method:
                return method()
        
        # Fallback to command check
        return shutil.which(dep['check_command']) is not None
    
    def check_all(self, include_optional: bool = True) -> Dict[str, bool]:
        """
        Check all dependencies.
        
        Args:
            include_optional: Include optional dependencies in check
            
        Returns:
            Dictionary mapping dependency name to installation status
        """
        results = {}
        for name, dep in self.DEPENDENCIES.items():
            if not include_optional and not dep['required']:
                continue
            results[name] = self.check_dependency(name)
        return results
    
    def get_missing(self, required_only: bool = True) -> List[str]:
        """
        Get list of missing dependencies.
        
        Args:
            required_only: Only check required dependencies
            
        Returns:
            List of missing dependency names
        """
        missing = []
        for name, dep in self.DEPENDENCIES.items():
            if required_only and not dep['required']:
                continue
            if not self.check_dependency(name):
                missing.append(name)
        return missing
    
    def get_version(self, name: str) -> Optional[str]:
        """
        Get version of installed dependency.
        
        Args:
            name: Dependency name
            
        Returns:
            Version string or None if not available
        """
        dep = self.DEPENDENCIES.get(name)
        if not dep or not self.check_dependency(name):
            return None
        
        if name == 'docker':
            try:
                result = subprocess.run(
                    ['docker', 'version', '--format', '{{.Server.Version}}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        
        elif name == 'kopia':
            try:
                result = subprocess.run(
                    ['kopia', 'version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.strip():
                            return line.strip().split()[0]
            except Exception:
                pass
        
        elif 'version_command' in dep:
            try:
                result = subprocess.run(
                    dep['version_command'] + ['--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip().split('\n')[0]
            except Exception:
                pass
        
        return None
    
    def get_install_commands(self) -> List[str]:
        """
        Get installation commands for current distro.
        
        Returns:
            List of shell commands to install missing dependencies
        """
        missing = self.get_missing()
        if not missing:
            return []
        
        commands = []
        packages = []
        special = []
        
        for dep_name in missing:
            dep = self.DEPENDENCIES[dep_name]
            if dep.get('special_install'):
                special.append(dep_name)
            else:
                package = dep['packages'].get(self.distro)
                if package:
                    packages.append(package)
        
        # Build install commands based on distro
        if self.distro == 'debian' and packages:
            commands.append(f"sudo apt update")
            commands.append(f"sudo apt install -y {' '.join(packages)}")
        elif self.distro == 'redhat' and packages:
            commands.append(f"sudo yum install -y {' '.join(packages)}")
        elif self.distro == 'arch' and packages:
            commands.append(f"sudo pacman -S --noconfirm {' '.join(packages)}")
        elif self.distro == 'alpine' and packages:
            commands.append(f"sudo apk add {' '.join(packages)}")
        
        # Special installations
        if 'kopia' in special:
            commands.extend(self._get_kopia_install_commands())
        
        # Docker post-install
        if 'docker' in missing:
            commands.append("# Post-install: Add user to docker group")
            commands.append(f"sudo usermod -aG docker $USER")
            commands.append("# Note: You need to log out and back in for group changes")
        
        return commands
    
    def _get_kopia_install_commands(self) -> List[str]:
        """
        Get Kopia-specific installation commands.
        
        Returns:
            List of commands to install Kopia
        """
        if self.distro == 'debian':
            return [
                "# Install Kopia repository",
                "curl -s https://kopia.io/signing-key | sudo gpg --dearmor -o /usr/share/keyrings/kopia-keyring.gpg",
                'echo "deb [signed-by=/usr/share/keyrings/kopia-keyring.gpg] http://packages.kopia.io/apt/ stable main" | sudo tee /etc/apt/sources.list.d/kopia.list',
                "sudo apt update",
                "sudo apt install -y kopia"
            ]
        elif self.distro == 'redhat':
            return [
                "# Install Kopia repository",
                "rpm --import https://kopia.io/signing-key",
                "cat <<EOF | sudo tee /etc/yum.repos.d/kopia.repo",
                "[kopia]",
                "name=Kopia",
                "baseurl=http://packages.kopia.io/rpm/stable/\$basearch/",
                "gpgcheck=1",
                "enabled=1",
                "gpgkey=https://kopia.io/signing-key",
                "EOF",
                "sudo yum install -y kopia"
            ]
        elif self.distro == 'arch':
            return [
                "# Install from AUR (requires yay or similar AUR helper)",
                "yay -S kopia-bin"
            ]
        else:
            return [
                "# Manual installation required",
                "# Visit: https://kopia.io/docs/installation/",
                "# Or download directly:",
                "curl -L https://github.com/kopia/kopia/releases/latest/download/kopia-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m) -o kopia",
                "chmod +x kopia",
                "sudo mv kopia /usr/local/bin/"
            ]
    
    def install_interactive(self, auto_yes: bool = False) -> bool:
        """
        Interactively install missing dependencies.
        
        Args:
            auto_yes: Skip confirmation prompts
            
        Returns:
            True if installation successful
        """
        missing = self.get_missing()
        
        if not missing:
            print("✓ All required dependencies are installed!")
            return True
        
        print("\n⚠ Missing Dependencies:")
        print("-" * 50)
        
        for dep_name in missing:
            dep = self.DEPENDENCIES[dep_name]
            status = "REQUIRED" if dep['required'] else "Optional"
            print(f"  ✗ {dep_name:<12} : {dep['description']}")
            print(f"    Status: {status}")
            if dep.get('install_notes'):
                print(f"    Note: {dep['install_notes']}")
        
        print("-" * 50)
        print(f"Distribution detected: {self.distro}")
        
        commands = self.get_install_commands()
        
        if not commands:
            print(f"\n⚠ Cannot auto-install on '{self.distro}' distribution")
            print("\nPlease install manually:")
            for dep in missing:
                print(f"  - {dep}")
            print("\nFor installation help, visit:")
            print("  https://github.com/TZERO78/kopi-docka/wiki/Installation")
            return False
        
        print("\n📋 Installation commands that will be executed:")
        print("-" * 50)
        for cmd in commands:
            if cmd.startswith('#'):
                print(f"  {cmd}")
            else:
                print(f"  $ {cmd}")
        print("-" * 50)
        
        if not auto_yes:
            response = input("\n❓ Execute these commands? [y/N]: ")
            if response.lower() != 'y':
                print("Installation cancelled.")
                return False
        
        # Execute commands
        print("\n🚀 Starting installation...\n")
        
        for cmd in commands:
            if cmd.startswith('#'):
                print(f"\n{cmd}")
                continue
            
            print(f"Running: {cmd}")
            
            # Special handling for multiline commands (like cat <<EOF)
            if 'EOF' in cmd or cmd.startswith('cat'):
                print("⚠ This command needs manual execution")
                print(f"Please run:\n{cmd}")
                input("Press Enter when done...")
                continue
            
            result = subprocess.run(cmd, shell=True)
            if result.returncode != 0:
                print(f"✗ Command failed with exit code {result.returncode}")
                response = input("Continue anyway? [y/N]: ")
                if response.lower() != 'y':
                    return False
        
        # Verify installation
        print("\n🔍 Verifying installation...")
        still_missing = self.get_missing()
        
        if not still_missing:
            print("\n✅ All dependencies successfully installed!")
            return True
        else:
            print("\n⚠ Some dependencies are still missing:")
            for dep in still_missing:
                print(f"  - {dep}")
            print("\nYou may need to:")
            print("  1. Restart your shell/terminal")
            print("  2. Log out and back in (for Docker group)")
            print("  3. Install these manually")
            return False
    
    def print_status(self, verbose: bool = False):
        """
        Print dependency status report.
        
        Args:
            verbose: Show detailed information including versions
        """
        print("\n" + "=" * 60)
        print("KOPI-DOCKA DEPENDENCY STATUS")
        print("=" * 60)
        
        print(f"\n📦 System: {self.distro.capitalize() if self.distro != 'unknown' else 'Unknown'} Linux")
        
        results = self.check_all(include_optional=True)
        
        required_deps = []
        optional_deps = []
        
        for name, installed in results.items():
            dep = self.DEPENDENCIES[name]
            dep_info = {
                'name': name,
                'installed': installed,
                'description': dep['description'],
                'required': dep['required']
            }
            
            if verbose and installed:
                version = self.get_version(name)
                if version:
                    dep_info['version'] = version
            
            if dep['required']:
                required_deps.append(dep_info)
            else:
                optional_deps.append(dep_info)
        
        # Print required dependencies
        print("\n📌 Required Dependencies:")
        print("-" * 40)
        all_required_ok = True
        
        for dep in required_deps:
            status = "✓" if dep['installed'] else "✗"
            version = f" (v{dep.get('version', 'unknown')})" if verbose and dep.get('version') else ""
            print(f"{status} {dep['name']:<12} : {dep['description']}{version}")
            
            if not dep['installed']:
                all_required_ok = False
        
        # Print optional dependencies
        print("\n📎 Optional Dependencies:")
        print("-" * 40)
        
        for dep in optional_deps:
            status = "✓" if dep['installed'] else "○"
            version = f" (v{dep.get('version', 'unknown')})" if verbose and dep.get('version') else ""
            print(f"{status} {dep['name']:<12} : {dep['description']}{version}")
        
        print("=" * 60)
        
        if not all_required_ok:
            print("\n⚠ Missing required dependencies detected!")
            print("Run: kopi-docka install-deps")
        else:
            print("\n✅ All required dependencies are installed!")
            print("Ready to backup! Run: kopi-docka backup --dry-run")
        
        print()
    
    def export_requirements(self) -> Dict[str, any]:
        """
        Export dependency requirements for documentation.
        
        Returns:
            Dictionary with all dependency requirements
        """
        return {
            'system': self.distro,
            'dependencies': self.DEPENDENCIES,
            'status': self.check_all(include_optional=True),
            'missing': self.get_missing(required_only=False)
        }