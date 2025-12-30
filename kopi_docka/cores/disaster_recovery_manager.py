################################################################################
# KOPI-DOCKA
#
# @file:        disaster_recovery_manager.py
# @module:      kopi_docka.cores
# @description: Creates encrypted disaster recovery bundles and supporting scripts.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Bundles Kopia status, config, password, and restore instructions
# - Encrypts archives with openssl AES-256-CBC and PBKDF2 salt
# - Stores checksum metadata to verify bundle integrity before use
################################################################################

"""
Disaster Recovery module for Kopi-Docka.

Creates encrypted recovery bundles containing everything needed to
reconnect to the Kopia repository and bring services back on a fresh host.
"""

from __future__ import annotations

import json
import hashlib
import subprocess
import tarfile
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from ..helpers.logging import get_logger
from ..helpers.config import Config
from ..helpers.ui_utils import run_command
from ..cores.repository_manager import KopiaRepository
from ..helpers.constants import VERSION


logger = get_logger(__name__)


class DisasterRecoveryManager:
    """
    Creates and manages disaster recovery bundles.

    Bundle contents:
      - kopia-repository.json (status dump)
      - kopia-password.txt (repo password)
      - kopi-docka.conf (your config)
      - recover.sh (guided reconnect script)
      - RECOVERY-INSTRUCTIONS.txt (human steps)
      - backup-status.json (recent snapshot info)
    The bundle is packed as tar.gz and encrypted with AES-256 (openssl -pbkdf2).
    """

    def __init__(self, config: Config):
        self.config = config
        self.repo = KopiaRepository(config)

    def create_recovery_bundle(
        self,
        output_dir: Optional[Path] = None,
        write_password_file: bool = True,
    ) -> Path:
        """
        Create an encrypted recovery bundle.

        Args:
            output_dir: Target directory (defaults to [backup] recovery_bundle_path).
            write_password_file: If True, create a .PASSWORD sidecar next to the archive.

        Returns:
            Path to the encrypted archive (<name>.tar.gz.enc)
        """
        if output_dir is None:
            output_dir = Path(
                self.config.get("backup", "recovery_bundle_path", "/backup/recovery")
            ).expanduser()

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_name = f"kopi-docka-recovery-{timestamp}"
        work_dir = Path("/tmp") / bundle_name
        work_dir.mkdir(parents=True, exist_ok=True)

        # Register CleanupHandler for interrupt-safe cleanup
        from ..cores.safe_exit_manager import SafeExitManager, CleanupHandler
        import shutil

        safe_exit = SafeExitManager.get_instance()
        cleanup_handler = CleanupHandler(name="disaster_recovery")

        # Register temp dir cleanup
        def cleanup_temp_dir():
            if work_dir.exists():
                shutil.rmtree(work_dir)
                logger.info(f"CleanupHandler: Removed temp dir {work_dir}")

        cleanup_handler.register_cleanup("temp_dir", cleanup_temp_dir)
        safe_exit.register_handler(cleanup_handler)

        try:
            logger.info("Creating disaster recovery bundle...", extra={"bundle": bundle_name})

            # 1) recovery info
            recovery_info = self._create_recovery_info()
            (work_dir / "recovery-info.json").write_text(json.dumps(recovery_info, indent=2))

            # 2) kopia repo status + password
            self._export_kopia_config(work_dir)

            # 3) kopi-docka.conf
            if self.config.config_file and Path(self.config.config_file).exists():
                import shutil

                shutil.copy(self.config.config_file, work_dir / "kopi-docka.conf")

            # 3.5) rclone.conf (if using rclone backend)
            rclone_conf_path = self._find_rclone_config()
            if rclone_conf_path and rclone_conf_path.exists():
                import shutil

                shutil.copy(rclone_conf_path, work_dir / "rclone.conf")
                logger.info(f"Added rclone.conf to recovery bundle from {rclone_conf_path}")

            # 4) recover.sh
            self._create_recovery_script(work_dir, recovery_info)

            # 5) human instructions
            self._create_recovery_instructions(work_dir, recovery_info)

            # 6) last backup status
            backup_status = self._get_backup_status()
            (work_dir / "backup-status.json").write_text(json.dumps(backup_status, indent=2))

            # 7) archive + encrypt
            archive_path = output_dir / f"{bundle_name}.tar.gz.enc"

            # Register partial archive cleanup
            def cleanup_partial_archive():
                if archive_path.exists():
                    archive_path.unlink()
                    logger.warning(f"CleanupHandler: Removed incomplete archive {archive_path}")

            cleanup_handler.register_cleanup("partial_archive", cleanup_partial_archive)

            password = self._create_encrypted_archive(work_dir, archive_path)

            # 8) sidecar README (+ optional PASSWORD)
            self._create_companion_files(archive_path, password, recovery_info, write_password_file)

            logger.info(
                "Recovery bundle created",
                extra={"archive": str(archive_path), "output_dir": str(output_dir)},
            )

            # Optional retention: rotate old bundles
            self._rotate_bundles(
                output_dir,
                keep=self.config.getint("backup", "recovery_bundle_retention", 3),
            )

            # Success: unregister cleanup handler and cleanup temp dir
            safe_exit.unregister_handler(cleanup_handler)

            # Normal cleanup (on success)
            if work_dir.exists():
                shutil.rmtree(work_dir)

            return archive_path

        except Exception:
            # On exception: CleanupHandler will handle cleanup on abort
            # Re-raise to let caller handle
            raise

    # ---------------- internal helpers ----------------

    def _find_rclone_config(self) -> Optional[Path]:
        """
        Find rclone.conf path from config or fallback locations.

        Returns:
            Path to rclone.conf if found, None otherwise
        """
        # 1. Check kopia_params for --rclone-args='--config=PATH'
        kopia_params = self.config.get("kopia", "kopia_params", fallback="")
        if "--rclone-args=" in kopia_params:
            # Extract path from --rclone-args='--config=/path/to/rclone.conf'
            import re

            match = re.search(r"--rclone-args=['\"]?--config=([^'\"\\s]+)", kopia_params)
            if match:
                path = Path(match.group(1))
                if path.exists():
                    return path

        # 2. Fallback: Standard locations
        import os

        candidates = [
            Path("/root/.config/rclone/rclone.conf"),
        ]
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            candidates.append(Path(f"/home/{sudo_user}/.config/rclone/rclone.conf"))

        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate
            except PermissionError:
                pass

        return None

    def _create_recovery_info(self) -> Dict[str, Any]:
        repo_status: Dict[str, Any] = {}
        try:
            result = subprocess.run(
                ["kopia", "repository", "status", "--json"],
                env=self.repo._get_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                repo_status = json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"Could not get repository status: {e}")

        # Extract repository connection info from Kopia's own status
        repo_type, connection = self._extract_repo_from_status(repo_status)

        # Collect file paths for smart restore
        paths = {}

        # Config file
        if self.config.config_file:
            paths["config"] = str(Path(self.config.config_file).resolve())

        # Rclone config
        rclone_path = self._find_rclone_config()
        if rclone_path:
            paths["rclone"] = str(rclone_path)

        # Password file (if configured)
        password_file = self.config.get("kopia", "password_file", fallback=None)
        if password_file:
            password_path = Path(password_file)
            if password_path.exists():
                paths["password"] = str(password_path.resolve())

        return {
            "created_at": datetime.now().isoformat(),
            "kopi_docka_version": VERSION,
            "hostname": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
            "repository": {
                "type": repo_type,
                "connection": connection,
                "encryption": self.config.get("kopia", "encryption"),
                "compression": self.config.get("kopia", "compression"),
                "status": repo_status,
            },
            "kopia_version": self._get_kopia_version(),
            "docker_version": self._get_docker_version(),
            "python_version": self._get_python_version(),
            "paths": paths,
        }

    def _extract_repo_from_status(self, repo_status: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Extract repository type and connection info from Kopia status JSON.

        This is more reliable than parsing kopia_params string.
        """
        storage = repo_status.get("storage", {})
        storage_type = storage.get("type", "unknown")
        storage_config = storage.get("config", {})

        # Map Kopia storage types to our naming
        if storage_type == "filesystem":
            path = storage_config.get("path", "")
            return "filesystem", {"path": path}

        elif storage_type == "s3":
            bucket = storage_config.get("bucket", "")
            return "s3", {"bucket": bucket}

        elif storage_type == "b2":
            bucket = storage_config.get("bucket", "")
            return "b2", {"bucket": bucket}

        elif storage_type == "azure":
            container = storage_config.get("container", "")
            return "azure", {"container": container}

        elif storage_type == "gcs":
            bucket = storage_config.get("bucket", "")
            return "gcs", {"bucket": bucket}

        elif storage_type == "sftp":
            host = storage_config.get("host", "")
            path = storage_config.get("path", "")
            return "sftp", {"host": host, "path": path}

        elif storage_type == "rclone":
            remote_path = storage_config.get("remotePath", "")
            return "rclone", {"remotePath": remote_path}

        else:
            # Fallback for unknown types
            return storage_type, storage_config

    def _export_kopia_config(self, out_dir: Path) -> None:
        try:
            result = subprocess.run(
                ["kopia", "repository", "status", "--json"],
                env=self.repo._get_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                (out_dir / "kopia-repository.json").write_text(result.stdout)

            # Save password (the bundle gets encrypted afterward)
            (out_dir / "kopia-password.txt").write_text(self.config.kopia_password or "")
        except Exception as e:
            logger.error(f"Could not export Kopia config: {e}")

    def _create_recovery_script(self, out_dir: Path, info: Dict[str, Any]) -> None:
        repo_type = info["repository"]["type"]
        conn = info["repository"]["connection"]
        created = info["created_at"]

        lines = [
            "#!/bin/bash",
            "#",
            f"# Kopi-Docka Disaster Recovery Script",
            f"# Generated: {created}",
            "#",
            "set -euo pipefail",
            "",
            'echo "========================================"',
            'echo "Kopi-Docka Disaster Recovery"',
            'echo "========================================"',
            "",
            "# Check root",
            'if [ "${EUID:-$(id -u)}" -ne 0 ]; then',
            '  echo "Please run as root (sudo)"; exit 1; fi',
            "",
            "# Require docker & kopia",
            'command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found"; exit 1; }',
            'command -v kopia  >/dev/null 2>&1 || { echo "ERROR: kopia not found. Install from https://kopia.io"; exit 1; }',
            "",
            "# Install Kopi-Docka if not available (optional hint)",
            "if ! command -v kopi-docka >/dev/null 2>&1; then",
            '  echo "NOTE: kopi-docka CLI not found. Install it according to your deployment (package/source).";',
            "fi",
            "",
            "# Helper: Get path from recovery-info.json",
            "get_path() {",
            "    python3 -c \"import json, sys; d=json.load(open('$(dirname \\\"$0\\\")/recovery-info.json')); print(d.get('paths', {}).get('$1', ''))\" 2>/dev/null || echo \"\"",
            "}",
            "",
            "# Helper: Safe restore with interactive backup",
            "safe_restore() {",
            '    local SOURCE="$1"',
            '    local DEST="$2"',
            '    local DESC="${3:-File}"',
            "    ",
            '    echo ""',
            '    echo "📄 Restoring $DESC..."',
            "    ",
            '    if [ ! -f "$SOURCE" ]; then',
            '        echo "  ⚠️  Source not in bundle: $SOURCE"',
            "        return 1",
            "    fi",
            "    ",
            '    if [ ! -f "$DEST" ]; then',
            '        echo "  → Target does not exist: $DEST"',
            '        mkdir -p "$(dirname "$DEST")"',
            '        cp "$SOURCE" "$DEST"',
            '        echo "  ✅ Created: $DEST"',
            "        return 0",
            "    fi",
            "    ",
            '    if cmp -s "$SOURCE" "$DEST"; then',
            '        echo "  ℹ️  Target is identical. Skipping."',
            "        return 0",
            "    fi",
            "    ",
            '    echo "  ⚠️  Target exists and differs: $DEST"',
            '    read -p "  Overwrite (backup will be created)? [y/N]: " -n 1 -r',
            "    echo",
            "    ",
            "    if [[ $REPLY =~ ^[Yy]$ ]]; then",
            '        local BACKUP="${DEST}.bak.$(date +%s)"',
            '        cp "$DEST" "$BACKUP"',
            '        echo "  📦 Backup: $BACKUP"',
            '        cp "$SOURCE" "$DEST"',
            '        echo "  ✅ Restored: $DEST"',
            "    else",
            '        echo "  ⏭️  Skipped by user."',
            "    fi",
            "}",
            "",
            "# Restore main configuration",
            'TARGET_CONF=$(get_path "config")',
            '[ -z "$TARGET_CONF" ] && TARGET_CONF="/etc/kopi-docka.conf"',
            'safe_restore "$(dirname "$0")/kopi-docka.conf" "$TARGET_CONF" "Kopi-Docka Configuration"',
            "",
            "# Restore rclone.conf (if present)",
            'if [ -f "$(dirname "$0")/rclone.conf" ]; then',
            '    TARGET_RCLONE=$(get_path "rclone")',
            '    [ -z "$TARGET_RCLONE" ] && TARGET_RCLONE="/root/.config/rclone/rclone.conf"',
            '    safe_restore "$(dirname "$0")/rclone.conf" "$TARGET_RCLONE" "Rclone Configuration"',
            "fi",
            "",
            "# Restore password file (if configured)",
            'TARGET_PASS=$(get_path "password")',
            'if [ -n "$TARGET_PASS" ] && [ -f "$(dirname "$0")/kopia-password.txt" ]; then',
            '    safe_restore "$(dirname "$0")/kopia-password.txt" "$TARGET_PASS" "Repository Password File"',
            "fi",
            "",
            "# Read Kopia password for immediate use",
            'export KOPIA_PASSWORD="$(cat "$(dirname "$0")/kopia-password.txt")"',
            'if [ -z "$KOPIA_PASSWORD" ]; then echo "ERROR: Empty KOPIA_PASSWORD"; exit 1; fi',
            "",
            'echo ""',
            'echo "Connecting to Kopia repository..."',
        ]

        # repo connect section
        if repo_type == "filesystem":
            lines += [
                f'kopia repository connect filesystem --path="{conn["path"]}"',
            ]
        elif repo_type == "s3":
            lines += [
                'read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID',
                'read -s -p "AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY; echo',
                "export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY",
                f'kopia repository connect s3 --bucket="{conn["bucket"]}" '
                '--access-key="$AWS_ACCESS_KEY_ID" --secret-access-key="$AWS_SECRET_ACCESS_KEY"',
            ]
        elif repo_type == "b2":
            lines += [
                'read -p "B2 Account ID: " B2_ACCOUNT_ID',
                'read -s -p "B2 Account Key: " B2_ACCOUNT_KEY; echo',
                f'kopia repository connect b2 --bucket="{conn["bucket"]}" '
                '--key-id="$B2_ACCOUNT_ID" --key="$B2_ACCOUNT_KEY"',
            ]
        elif repo_type == "azure":
            lines += [
                'read -p "Azure Storage Account: " AZURE_ACCOUNT',
                'read -s -p "Azure Storage Key: " AZURE_KEY; echo',
                f'kopia repository connect azure --container="{conn["container"]}" '
                '--storage-account="$AZURE_ACCOUNT" --storage-key="$AZURE_KEY"',
            ]
        elif repo_type == "gcs":
            lines += [
                'echo "Place your GCP service account JSON at /root/gcp-sa.json (or set GOOGLE_APPLICATION_CREDENTIALS)"',
                'read -p "GCS Bucket: " GCS_BUCKET',
                "export GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS:-/root/gcp-sa.json}",
                'test -f "$GOOGLE_APPLICATION_CREDENTIALS" || { echo "Missing service account JSON"; exit 1; }',
                'kopia repository connect gcs --bucket="$GCS_BUCKET"',
            ]
        elif repo_type == "rclone":
            # Rclone requires special handling
            remote_path = conn.get("remotePath", "")
            lines += [
                f"# Rclone repository: {remote_path}",
                'echo "Ensure rclone.conf is restored above and rclone remote is configured."',
                f'kopia repository connect rclone --remote-path="{remote_path}"',
            ]
        else:
            # generic / custom schemes: let user connect manually
            lines += [
                f'echo "Repository type: {repo_type}"',
                'echo "Unsupported auto-connect for this repository scheme. Connect manually, e.g.:"',
                'echo "  kopia repository connect <provider> <options>"',
                f'echo "Connection info: {json.dumps(conn)}"',
                "exit 1",
            ]

        lines += [
            "",
            'echo "Verifying repository connection..."',
            "kopia repository status || { echo ERROR; exit 1; }",
            "",
            'echo ""',
            'echo "========================================"',
            'echo "✅ Recovery Complete!"',
            'echo "========================================"',
            "",
            'echo "⚠️  IMPORTANT: Automation is NOT active yet."',
            'echo ""',
            'echo "To restore automated backups, run:"',
            'echo "  sudo kopi-docka admin service write-units"',
            'echo "  sudo systemctl enable --now kopi-docka.timer"',
            'echo ""',
            'echo "To verify the schedule:"',
            'echo "  systemctl list-timers | grep kopi-docka"',
            'echo ""',
            'echo "Next steps:"',
            'echo "  * Verify repository: kopi-docka admin repo status"',
            'echo "  * List snapshots:    kopi-docka admin snapshot list --snapshots"',
            'echo "  * Start restore:     kopi-docka restore"',
            'echo ""',
        ]

        script = "\n".join(lines)
        path = out_dir / "recover.sh"
        path.write_text(script)
        path.chmod(0o755)

    def _create_recovery_instructions(self, out_dir: Path, info: Dict[str, Any]) -> None:
        rpt = info["repository"]
        lines = [
            "KOPI-DOCKA DISASTER RECOVERY INSTRUCTIONS",
            "==========================================",
            "",
            f"Created: {info['created_at']}",
            f"System:  {info['hostname']}",
            "",
            "REPOSITORY",
            "----------",
            f"Type:   {rpt['type']}",
            f"Config: {json.dumps(rpt['connection'], indent=2)}",
            f"Enc:    {rpt['encryption']}",
            f"Comp:   {rpt['compression']}",
            "",
            "STEPS",
            "-----",
            "1) Prepare a fresh Linux host with Docker and Kopia installed.",
            "2) Decrypt and extract this bundle (see README next to the archive).",
            "3) Run: sudo ./recover.sh",
            "4) Connect to the Kopia repository (guided).",
            "5) Start the restore wizard: kopi-docka restore",
            "",
            "NOTES",
            "-----",
            "- This system uses COLD backups of container volumes and compose/inspect data.",
            "- Databases are restored implicitly via their volumes (no separate DB dumps).",
            "- Test recovery regularly.",
            "",
        ]
        (out_dir / "RECOVERY-INSTRUCTIONS.txt").write_text("\n".join(lines))

    def _get_backup_status(self) -> Dict[str, Any]:
        status = {"timestamp": datetime.now().isoformat(), "snapshots": []}
        try:
            snaps = self.repo.list_snapshots()
            status["snapshots"] = snaps[:10] if isinstance(snaps, list) else []
        except Exception as e:
            logger.error(f"Could not get backup status: {e}")
        return status

    def _create_encrypted_archive(self, src_dir: Path, out_file: Path) -> str:
        """
        Create tar.gz of src_dir and encrypt with openssl AES-256-CBC PBKDF2.

        Returns:
            password used for encryption
        """
        # Random strong password (printable, shell-safe)
        alphabet = string.ascii_letters + string.digits + "_-"
        password = "".join(secrets.choice(alphabet) for _ in range(48))

        tar_path = out_file.with_suffix("")  # remove .enc
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(src_dir, arcname=src_dir.name)

        # Use run_command for automatic subprocess tracking
        run_command(
            [
                "openssl",
                "enc",
                "-aes-256-cbc",
                "-salt",
                "-pbkdf2",
                "-in",
                str(tar_path),
                "-out",
                str(out_file),
                "-pass",
                f"pass:{password}",
            ],
            "Encrypting recovery bundle with OpenSSL AES-256-CBC",
            check=True,
        )

        tar_path.unlink(missing_ok=True)
        return password

    def _create_companion_files(
        self,
        archive_path: Path,
        password: str,
        info: Dict[str, Any],
        write_password_file: bool,
    ) -> None:
        checksum = self._sha256(archive_path)

        readme = f"""KOPI-DOCKA DISASTER RECOVERY BUNDLE
====================================

Archive:  {archive_path.name}
SHA256:   {checksum}

DECRYPTION
----------
# Store the password securely (password is NOT inside this file)
# Example:
openssl enc -aes-256-cbc -salt -pbkdf2 -d \\
  -in {archive_path.name} \\
  -out {archive_path.stem} \\
  -pass pass:'<YOUR_PASSWORD>'

tar -xzf {archive_path.stem}

NEXT
----
cd {archive_path.stem.replace('.tar.gz', '')}
sudo ./recover.sh

INFO
----
Repo Type: {info['repository']['type']}
Repo Conn: {json.dumps(info['repository']['connection'], indent=2)}

Generated by Kopi-Docka v{VERSION}
"""
        (archive_path.parent / f"{archive_path.name}.README").write_text(readme)

        if write_password_file:
            pw_path = archive_path.parent / f"{archive_path.name}.PASSWORD"
            pw_path.write_text(f"{password}\n")
            pw_path.chmod(0o600)
            logger.warning(
                "Recovery password written to sidecar file. Store it in a secure place and consider moving it away from the archive.",
                extra={"password_file": str(pw_path)},
            )
        else:
            # Log a reminder without exposing the password
            logger.warning("Recovery password NOT written to disk. Store it securely NOW.")

    def _rotate_bundles(self, directory: Path, keep: int) -> None:
        try:
            bundles = sorted(directory.glob("kopi-docka-recovery-*.tar.gz.enc"))
            if keep > 0 and len(bundles) > keep:
                for old in bundles[:-keep]:
                    logger.info(f"Removing old recovery bundle: {old}")
                    old.unlink(missing_ok=True)
                    for suffix in (".README", ".PASSWORD"):
                        p = Path(str(old) + suffix)
                        if p.exists():
                            p.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Bundle rotation failed: {e}")

    # --------------- small utils ---------------

    def _sha256(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _get_kopia_version(self) -> str:
        try:
            result = run_command(
                ["kopia", "version"],
                "Getting Kopia version",
                timeout=5,
                check=False,
            )
            return (result.stdout or "").strip().split("\n")[0] or "unknown"
        except Exception:
            return "unknown"

    def _get_docker_version(self) -> str:
        try:
            result = run_command(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                "Getting Docker version",
                timeout=5,
                check=False,
            )
            return (result.stdout or "").strip() or "unknown"
        except Exception:
            return "unknown"

    def _get_python_version(self) -> str:
        import sys

        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
