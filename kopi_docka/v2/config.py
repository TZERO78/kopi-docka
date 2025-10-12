"""
Pydantic Configuration Models for Kopi-Docka v2.1

Type-safe, validated JSON configuration with schema validation.
Replaces the old INI-based config system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class BackendConfig(BaseModel):
    """Storage backend configuration"""
    
    type: Literal["filesystem", "tailscale", "rclone", "s3", "b2", "webdav", "gdrive"]
    repository_path: str = Field(
        ...,
        description="Backend-specific path (e.g., '/backup/kopia', 'sftp://host:/path', 's3://bucket/prefix')"
    )
    credentials: Dict[str, Any] = Field(
        default_factory=dict,
        description="Backend-specific credentials (SSH keys, API keys, etc.)"
    )
    
    @field_validator("type")
    @classmethod
    def validate_backend_type(cls, v: str) -> str:
        """Validate backend type"""
        valid_types = {"filesystem", "tailscale", "rclone", "s3", "b2", "webdav", "gdrive"}
        if v not in valid_types:
            raise ValueError(f"Invalid backend type: {v}. Must be one of {valid_types}")
        return v


class KopiaConfig(BaseModel):
    """Kopia-specific configuration"""
    
    profile: str = Field(
        default="kopi-docka",
        description="Kopia profile name"
    )
    compression: str = Field(
        default="zstd",
        description="Compression algorithm (zstd, pgzip, s2-default, etc.)"
    )
    encryption: str = Field(
        default="AES256-GCM-HMAC-SHA256",
        description="Encryption algorithm"
    )
    cache_directory: Optional[Path] = Field(
        default=Path("/var/cache/kopi-docka"),
        description="Kopia cache directory"
    )
    
    @field_validator("cache_directory", mode="before")
    @classmethod
    def validate_cache_dir(cls, v: Any) -> Optional[Path]:
        """Convert string to Path"""
        if v is None:
            return None
        if isinstance(v, str):
            return Path(v).expanduser()
        return v


class BackupUnit(BaseModel):
    """Individual backup unit (container/service)"""
    
    name: str = Field(..., description="Unit name (container name)")
    enabled: bool = Field(default=True, description="Enable/disable this unit")
    pre_backup: List[str] = Field(
        default_factory=list,
        description="Commands to run before backup"
    )
    post_backup: List[str] = Field(
        default_factory=list,
        description="Commands to run after backup"
    )
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate unit name"""
        if not v or not v.strip():
            raise ValueError("Unit name cannot be empty")
        return v.strip()


class BackupConfig(BaseModel):
    """Backup configuration"""
    
    base_path: Path = Field(
        default=Path("/backup/kopi-docka"),
        description="Base path for backup operations"
    )
    parallel_workers: Union[int, Literal["auto"]] = Field(
        default="auto",
        description="Number of parallel workers (auto = CPU count)"
    )
    units: List[BackupUnit] = Field(
        default_factory=list,
        description="List of backup units"
    )
    exclude_patterns: List[str] = Field(
        default_factory=list,
        description="Glob patterns to exclude from backups"
    )
    stop_timeout: int = Field(
        default=30,
        description="Container stop timeout in seconds"
    )
    start_timeout: int = Field(
        default=60,
        description="Container start timeout in seconds"
    )
    database_backup: bool = Field(
        default=True,
        description="Enable database backups"
    )
    
    @field_validator("base_path", mode="before")
    @classmethod
    def validate_base_path(cls, v: Any) -> Path:
        """Convert string to Path"""
        if isinstance(v, str):
            return Path(v).expanduser()
        return v
    
    @field_validator("parallel_workers")
    @classmethod
    def validate_workers(cls, v: Union[int, str]) -> Union[int, str]:
        """Validate worker count"""
        if v == "auto":
            return v
        if isinstance(v, int):
            if v < 1 or v > 32:
                raise ValueError("parallel_workers must be between 1 and 32")
            return v
        raise ValueError("parallel_workers must be 'auto' or an integer")


class RetentionConfig(BaseModel):
    """Snapshot retention policy"""
    
    daily: int = Field(default=7, ge=0, description="Daily snapshots to keep")
    weekly: int = Field(default=4, ge=0, description="Weekly snapshots to keep")
    monthly: int = Field(default=12, ge=0, description="Monthly snapshots to keep")
    yearly: int = Field(default=5, ge=0, description="Yearly snapshots to keep")


class ScheduleConfig(BaseModel):
    """Backup schedule configuration"""
    
    enabled: bool = Field(default=True, description="Enable scheduled backups")
    time: str = Field(
        default="02:00",
        description="Time to run daily backups (HH:MM format)"
    )
    
    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        """Validate time format"""
        import re
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", v):
            raise ValueError("Time must be in HH:MM format (00:00 - 23:59)")
        return v


class TaildropConfig(BaseModel):
    """Taildrop configuration for DR bundles"""
    
    enabled: bool = Field(default=False, description="Enable Taildrop for DR bundles")
    target_device: Optional[str] = Field(
        default=None,
        description="Target device name in Tailnet"
    )
    
    @model_validator(mode="after")
    def validate_taildrop(self) -> TaildropConfig:
        """Validate Taildrop configuration"""
        if self.enabled and not self.target_device:
            raise ValueError("target_device required when Taildrop is enabled")
        return self


class DisasterRecoveryConfig(BaseModel):
    """Disaster recovery bundle configuration"""
    
    enabled: bool = Field(default=True, description="Enable DR bundle creation")
    bundle_path: Path = Field(
        default=Path("/backup/recovery"),
        description="Path to store DR bundles"
    )
    retention: int = Field(
        default=3,
        ge=1,
        description="Number of DR bundles to keep"
    )
    taildrop: TaildropConfig = Field(
        default_factory=TaildropConfig,
        description="Taildrop configuration"
    )
    
    @field_validator("bundle_path", mode="before")
    @classmethod
    def validate_bundle_path(cls, v: Any) -> Path:
        """Convert string to Path"""
        if isinstance(v, str):
            return Path(v).expanduser()
        return v


class KopiDockaConfig(BaseModel):
    """Main Kopi-Docka configuration"""
    
    version: str = Field(default="2.1.0", description="Config file version")
    backend: BackendConfig
    kopia: KopiaConfig = Field(default_factory=KopiaConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    disaster_recovery: DisasterRecoveryConfig = Field(default_factory=DisasterRecoveryConfig)
    
    def save(self, path: Path) -> None:
        """Save configuration to JSON file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2, exclude_none=True))
        # Set secure permissions (600)
        path.chmod(0o600)
    
    @classmethod
    def load(cls, path: Path) -> KopiDockaConfig:
        """Load configuration from JSON file"""
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        return cls.model_validate_json(path.read_text())
    
    @classmethod
    def get_default_path(cls) -> Path:
        """Get default configuration path"""
        import os
        if os.geteuid() == 0:  # Running as root
            return Path("/etc/kopi-docka/config.json")
        else:
            return Path.home() / ".config" / "kopi-docka" / "config.json"
    
    def get_password(self) -> str:
        """
        Get repository password from credentials.
        
        Password can be stored in:
        1. credentials['password'] - Direct password (insecure!)
        2. credentials['password_file'] - Path to password file
        
        Returns:
            Repository password
            
        Raises:
            ValueError: If password not found or inaccessible
        """
        # Check direct password first
        if "password" in self.backend.credentials:
            pwd = self.backend.credentials["password"]
            if pwd and isinstance(pwd, str):
                return pwd
        
        # Check password file
        if "password_file" in self.backend.credentials:
            pwd_file_str = self.backend.credentials["password_file"]
            if pwd_file_str:
                pwd_file = Path(pwd_file_str).expanduser()
                if pwd_file.exists():
                    try:
                        pwd = pwd_file.read_text(encoding="utf-8").strip()
                        if pwd:
                            return pwd
                        else:
                            raise ValueError(f"Password file is empty: {pwd_file}")
                    except Exception as e:
                        raise ValueError(f"Cannot read password file {pwd_file}: {e}")
                else:
                    raise ValueError(f"Password file not found: {pwd_file}")
        
        # No password configured
        raise ValueError(
            "No password configured in backend.credentials.\n"
            "Add 'password' or 'password_file' to credentials."
        )
    
    def set_password(self, password: str, use_file: bool = False) -> None:
        """
        Set repository password in configuration.
        
        Args:
            password: The password to store
            use_file: If True, store in external file; if False, store directly
        """
        if use_file:
            # Store in external password file
            config_path = self.get_default_path()
            password_file = config_path.parent / f".{config_path.stem}.password"
            
            # Create parent directory if needed
            password_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write password
            password_file.write_text(password + "\n", encoding="utf-8")
            password_file.chmod(0o600)
            
            # Update config to reference the file
            self.backend.credentials["password_file"] = str(password_file)
            if "password" in self.backend.credentials:
                del self.backend.credentials["password"]
        else:
            # Store directly in config (plaintext)
            self.backend.credentials["password"] = password
            if "password_file" in self.backend.credentials:
                del self.backend.credentials["password_file"]
