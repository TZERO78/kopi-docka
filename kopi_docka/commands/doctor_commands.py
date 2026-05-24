################################################################################
# KOPI-DOCKA
#
# @file:        doctor_commands.py
# @module:      kopi_docka.commands
# @description: Doctor command - comprehensive system health check
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.5.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Doctor command - comprehensive system health check.

Checks:
1. System Information
2. Core Dependencies (with categories)
3. Systemd Integration
4. Backend Dependencies
5. Configuration status
6. Repository status (Kopia connection - the single source of truth)
7. Retention policy alignment (policy targets vs snapshot source paths)

Note: Repository connection status IS the definitive check. If Kopia can
connect to the repository, the underlying storage (filesystem, rclone, s3, etc.)
is automatically working. No separate backend checks needed.
"""

from pathlib import Path
from typing import Optional
import os
import platform

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..helpers import Config, get_logger, detect_repository_type
from ..helpers.dependency_helper import DependencyHelper
from ..cores import KopiaRepository, DependencyManager

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def _extract_storage_info(kopia_params: str, repo_type: str) -> dict:
    """
    Extract storage-specific info from kopia_params for display purposes only.

    This is purely for informational display - NOT a connectivity check.
    The actual connectivity is verified by Kopia repository status.

    Args:
        kopia_params: The kopia_params string
        repo_type: Detected repository type

    Returns:
        Dict with extracted info (remote_path, bucket, etc.)
    """
    import shlex

    info = {}

    if not kopia_params:
        return info

    try:
        parts = shlex.split(kopia_params)

        if repo_type == "filesystem":
            # Extract --path
            for i, part in enumerate(parts):
                if part == "--path" and i + 1 < len(parts):
                    info["path"] = parts[i + 1]
                elif part.startswith("--path="):
                    info["path"] = part.split("=", 1)[1]

        elif repo_type == "rclone":
            # Extract --remote-path
            for part in parts:
                if part.startswith("--remote-path="):
                    info["remote"] = part.split("=", 1)[1]

        elif repo_type in ("s3", "b2", "gcs"):
            # Extract --bucket
            for i, part in enumerate(parts):
                if part == "--bucket" and i + 1 < len(parts):
                    info["bucket"] = parts[i + 1]
                elif part.startswith("--bucket="):
                    info["bucket"] = part.split("=", 1)[1]

        elif repo_type == "azure":
            # Extract --container
            for i, part in enumerate(parts):
                if part == "--container" and i + 1 < len(parts):
                    info["container"] = parts[i + 1]
                elif part.startswith("--container="):
                    info["container"] = part.split("=", 1)[1]

        elif repo_type == "sftp":
            # Extract --path (contains user@host:path)
            for i, part in enumerate(parts):
                if part == "--path" and i + 1 < len(parts):
                    info["target"] = parts[i + 1]
                elif part.startswith("--path="):
                    info["target"] = part.split("=", 1)[1]

    except Exception:
        pass

    return info


# -------------------------
# Helper Functions for Sections
# -------------------------


def _check_kopia_params_sanity(kopia_params: str) -> list:
    """Detect broken kopia_params shapes that would silently break backups.

    Returns a list of ``(code, severity, detail)`` tuples. Currently
    targets the Tailscale/SFTP wizard bug shipped in v7.0.0 – v7.3.13,
    where the wizard produced ``--path=HOST:PATH`` and forgot
    ``--username`` / ``--keyfile``. Kopia accepts the broken form at
    ``repository connect`` but then hangs on every snapshot.

    Severity:
      - ``error``    : config is broken; backups will not work
      - ``warning``  : likely broken; user should verify

    See: Plan 0029 (kopi-docka v7.4.0 changelog).
    """
    import re

    issues = []
    params = (kopia_params or "").strip()
    if not params:
        return issues

    backend = params.split(None, 1)[0].lower()
    if backend != "sftp":
        return issues

    path_match = re.search(r"--path=(\S+)", params)
    if path_match:
        path_value = path_match.group(1)
        if ":" in path_value:
            host_part = path_value.split(":", 1)[0]
            # Hostname-shaped prefixes (not Windows drive letters etc.):
            # contain a dot or are obviously a non-trivial label.
            if re.match(r"^[a-zA-Z][a-zA-Z0-9.\-]+$", host_part) and (
                "." in host_part or len(host_part) > 1
            ):
                issues.append((
                    "broken_path_with_host_prefix",
                    "error",
                    f"--path={path_value} embeds the host. Kopia expects "
                    f"--path=PATH and --host=HOST as separate flags. "
                    f"Legacy v7.0–v7.3.13 wizard bug.",
                ))

    if "--username=" not in params and "--username " not in params:
        issues.append((
            "missing_username",
            "error",
            "--username=... is missing (required by Kopia's SFTP backend).",
        ))

    if (
        "--keyfile=" not in params
        and "--keyfile " not in params
        and "--key-data=" not in params
        and "--sftp-password=" not in params
    ):
        issues.append((
            "missing_auth",
            "error",
            "No auth flag set (--keyfile / --key-data / --sftp-password).",
        ))

    return issues


def _show_backend_sanity(cfg: Optional[Config], warnings: list, issues: list):
    """Section 5.1 — surface broken kopia_params shapes (Plan 0029)."""
    if not cfg:
        return

    kopia_params = cfg.get("kopia", "kopia_params", fallback="")
    if not kopia_params:
        return

    backend = kopia_params.strip().split(None, 1)[0].lower()
    if backend != "sftp":
        # The check is SFTP-specific (Tailscale wizard bug). Skip silently
        # for rclone/filesystem/s3/etc. so we don't add visual noise.
        return

    console.print("[bold]5.1 Backend Sanity[/bold]")
    console.print("-" * 40)

    sanity_issues = _check_kopia_params_sanity(kopia_params)

    sanity_table = Table(box=box.SIMPLE, show_header=False)
    sanity_table.add_column("Check", style="cyan", width=24)
    sanity_table.add_column("Status", width=18)
    sanity_table.add_column("Details", style="dim")

    has_path_bug = any(code == "broken_path_with_host_prefix" for code, *_ in sanity_issues)
    has_missing_user = any(code == "missing_username" for code, *_ in sanity_issues)
    has_missing_auth = any(code == "missing_auth" for code, *_ in sanity_issues)

    sanity_table.add_row(
        "SFTP --path format",
        "[red]✗ Broken[/red]" if has_path_bug else "[green]OK[/green]",
        "Includes host prefix (legacy bug)" if has_path_bug else "Separate --path / --host",
    )
    sanity_table.add_row(
        "SFTP --username",
        "[red]✗ Missing[/red]" if has_missing_user else "[green]OK[/green]",
        "Required by Kopia SFTP backend" if has_missing_user else "Present",
    )
    sanity_table.add_row(
        "SFTP auth",
        "[red]✗ Missing[/red]" if has_missing_auth else "[green]OK[/green]",
        "--keyfile / --sftp-password" if has_missing_auth else "Present",
    )

    console.print(sanity_table)

    if sanity_issues:
        for _code, _severity, detail in sanity_issues:
            issues.append(f"kopia_params: {detail}")

        console.print()
        console.print(
            "[yellow]Migration:[/yellow] this config was likely written by the "
            "v7.0.0–v7.3.13 Tailscale wizard (bug fixed in v7.4.0). "
            "Repair the config in place with:"
        )
        console.print()
        console.print(
            "  [cyan]sudo kopi-docka advanced config repair-kopia-params[/cyan]"
        )
        console.print()
        console.print(
            "[dim]The command rebuilds kopia_params from your existing "
            "[bold][credentials][/bold] section (peer FQDN, ssh user, key path, "
            "known_hosts). Pass [bold]--dry-run[/bold] to preview, "
            "[bold]--yes[/bold] to skip the confirmation prompt.[/dim]"
        )
        console.print()
        console.print(
            "[dim]After repair, run:[/dim] [cyan]sudo kopi-docka advanced repo init[/cyan] "
            "[dim](reconnects to the existing repository with the corrected params).[/dim]"
        )

    console.print()


def _show_system_info():
    """Display simplified system information."""
    import kopi_docka

    console.print("[bold]1. System Information[/bold]")
    console.print("-" * 40)

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("OS", platform.system())
    table.add_row("Python Version", platform.python_version())
    table.add_row("Kopi-Docka Version", kopi_docka.__version__)

    console.print(table)
    console.print()


def _show_core_dependencies(dep_manager: DependencyManager):
    """Display core dependency status with categories."""
    console.print("[bold]2. Core Dependencies[/bold]")
    console.print("-" * 40)

    table = Table(box=box.SIMPLE)
    table.add_column("Tool", style="cyan", width=15)
    table.add_column("Category", style="magenta", width=12)
    table.add_column("Status", width=12)
    table.add_column("Version", style="yellow", width=15)
    table.add_column("Path", style="dim")

    for dep_name, dep_info in dep_manager.dependencies.items():
        tool_info = DependencyHelper.check(dep_name)

        category = str(dep_info.get("category", "UNKNOWN")).replace("DependencyCategory.", "")

        if tool_info.installed:
            status = "[green]✓ Installed[/green]"
            version = tool_info.version or "N/A"
            path = tool_info.path or "N/A"
        else:
            status = "[red]✗ Missing[/red]"
            version = "—"
            path = "—"

        table.add_row(dep_name, category, status, version, path)

    console.print(table)
    console.print()


def _show_systemd_status():
    """Display systemd integration status."""
    console.print("[bold]3. Systemd Integration[/bold]")
    console.print("-" * 40)

    systemd_tools = ["systemctl", "journalctl"]
    tool_status = DependencyHelper.check_all(systemd_tools)

    table = Table(box=box.SIMPLE)
    table.add_column("Tool", style="cyan", width=15)
    table.add_column("Status", width=15)
    table.add_column("Version", style="yellow")

    for tool_name, tool_info in tool_status.items():
        if tool_info.installed:
            status = "[green]✓ Available[/green]"
            version = tool_info.version or "N/A"
        else:
            status = "[yellow]○ Missing[/yellow]"
            version = "—"

        table.add_row(tool_name, status, version)

    console.print(table)

    if not all(t.installed for t in tool_status.values()):
        console.print("[yellow]⚠ Some features may be limited without systemd[/yellow]")

    console.print()


def _show_backend_dependencies(cfg: Optional[Config], warnings: Optional[list] = None):
    """Display backend-specific dependencies.

    ``warnings`` accumulates user-visible health warnings (same list the
    rest of the doctor checks append to). Accepting it here lets the
    rclone/Google-Drive performance heuristic add to the summary even
    though the check itself lives in the backend-dependencies section.
    """
    if warnings is None:
        warnings = []
    console.print("[bold]4. Backend Dependencies[/bold]")
    console.print("-" * 40)

    if not cfg:
        console.print("[dim]No configuration - backends not loaded[/dim]")
        console.print()
        return

    # Get backend type from config
    kopia_params = cfg.get("kopia", "kopia_params", fallback="")
    repo_type = detect_repository_type(kopia_params)

    if repo_type == "unknown":
        console.print("[dim]No backend configured[/dim]")
        console.print()
        return

    # Try to load the backend and check dependencies
    try:
        from ..backends import get_backend_class

        backend_class = get_backend_class(repo_type)
        if backend_class and hasattr(backend_class, 'REQUIRED_TOOLS'):
            backend = backend_class(cfg.to_dict())

            table = Table(box=box.SIMPLE)
            table.add_column("Backend", style="cyan", width=15)
            table.add_column("Tool", style="white", width=15)
            table.add_column("Status", width=15)
            table.add_column("Version", style="yellow")

            if hasattr(backend, 'get_dependency_status'):
                dep_status = backend.get_dependency_status()

                for tool_name, tool_info in dep_status.items():
                    if tool_info.installed:
                        status = "[green]✓[/green]"
                        version = tool_info.version or "N/A"
                    else:
                        status = "[red]✗ Missing[/red]"
                        version = "—"

                    table.add_row(repo_type.upper(), tool_name, status, version)

                console.print(table)
            else:
                console.print(f"[dim]Backend {repo_type} does not support dependency checking[/dim]")
        else:
            console.print(f"[dim]Backend {repo_type} has no dependency requirements[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not check backend dependencies: {e}[/yellow]")

    # Performance warning for rclone backends, especially against Google Drive.
    # Kopia upstream marks rclone as "[Not maintained]" and a single backup
    # snapshot routinely takes 1-5 minutes per source over GDrive; users see
    # 30+ minute backups for repos that would take seconds over SFTP. See
    # docs/TROUBLESHOOTING.md → "Backups against rclone+Google Drive feel
    # very slow" for measurements and alternatives.
    if repo_type == "rclone":
        is_gdrive = any(s in kopia_params.lower() for s in ("gdrive", "drive:", "google"))
        message = (
            "[yellow]⚠ rclone backend in use.[/yellow] Kopia upstream marks the "
            "rclone backend as 'Not maintained' in its CLI docs."
        )
        if is_gdrive:
            message += (
                "\n   On Google Drive in particular each `kopia snapshot create` "
                "round-trip costs 1-5 minutes. Consider switching to a native "
                "Kopia backend ([bold]Tailscale[/bold]/[bold]SFTP[/bold] for "
                "self-hosted, [bold]Backblaze B2[/bold] for cloud) for an order-"
                "of-magnitude speedup."
            )
        else:
            message += (
                "\n   For native Kopia backends (S3, B2, SFTP, etc.) performance "
                "is typically much better; consider one of those if your provider "
                "supports it."
            )
        message += (
            "\n   [dim]See docs/TROUBLESHOOTING.md → \"Backups against "
            "rclone+Google Drive feel very slow\" for details.[/dim]"
        )
        console.print(message)
        warnings.append(
            "rclone backend in use — known slow on Google Drive (see TROUBLESHOOTING.md)"
        )

    console.print()


# -------------------------
# Commands
# -------------------------


def _check_policy_alignment(repo, console: Console, warnings: list):
    """Show global retention policy and flag any leftover per-path policies as legacy.

    Plan 0028 made the global policy the single source of retention truth.
    Per-path policies still in the repository are leftovers from older
    kopi-docka versions — they're harmless (Kopia merges per-path on top of
    global), but they slow down rclone backends and should be pruned.
    """
    from ..cores.kopia_policy_manager import KopiaPolicyManager

    console.print("[bold]7. Retention Policy[/bold]")
    console.print("-" * 40)

    policy_table = Table(box=box.SIMPLE, show_header=False)
    policy_table.add_column("Check", style="cyan", width=30)
    policy_table.add_column("Status", width=15)
    policy_table.add_column("Details", style="dim")

    try:
        policy_mgr = KopiaPolicyManager(repo)
        policies = policy_mgr.list_policies()

        # Extract per-path policy targets (exclude global)
        legacy_targets = set()
        for policy in policies:
            target = policy.get("target", {})
            path = target.get("path", "")
            if path and path != "(global)":
                legacy_targets.add(path)

        snapshots = repo.list_snapshots()
        snapshot_sources = {snap.get("path", "") for snap in snapshots if snap.get("path")}

        global_policy = policy_mgr.get_global_policy()
        retention = global_policy.get("retention", {}) if isinstance(global_policy, dict) else {}
        if retention:
            retention_desc = ", ".join(
                f"{k.replace('keep', 'keep_').lower()}={v}"
                for k, v in retention.items()
                if v is not None
            )
            policy_table.add_row(
                "Global Retention",
                "[green]OK[/green]",
                retention_desc or "(defaults)",
            )
        else:
            policy_table.add_row(
                "Global Retention",
                "[yellow]Missing[/yellow]",
                "Reconnect to apply defaults from config",
            )

        if legacy_targets:
            policy_table.add_row(
                "Legacy Per-Path Policies",
                f"[yellow]{len(legacy_targets)}[/yellow]",
                "Obsolete — from older kopi-docka versions",
            )
            for path in sorted(legacy_targets):
                policy_table.add_row("", "", f"  {path}")
            policy_table.add_row(
                "", "",
                "[dim]Fix: kopi-docka advanced policy prune[/dim]",
            )
            warnings.append(
                f"{len(legacy_targets)} legacy per-path retention policies — "
                "run 'kopi-docka advanced policy prune' to clean them up"
            )
        else:
            policy_table.add_row(
                "Legacy Per-Path Policies",
                "[green]None[/green]",
                "Global-only — clean state",
            )

        policy_table.add_row("Snapshot Sources", "", str(len(snapshot_sources)))

    except Exception as e:
        policy_table.add_row("Policy Check", "[yellow]Skipped[/yellow]", str(e)[:60])

    console.print(policy_table)
    console.print()


def _check_backup_freshness(cfg: "Config", console: Console, warnings: list):
    """Show last-backup age per unit and highlight overdue units."""
    from ..cores.missed_backup_checker import MissedBackupChecker
    from ..helpers.metadata_reader import MetadataReader

    console.print("[bold]8. Backup Freshness[/bold]")
    console.print("-" * 40)

    freshness_table = Table(box=box.SIMPLE)
    freshness_table.add_column("Unit", style="cyan", width=20)
    freshness_table.add_column("Last Success", width=20)
    freshness_table.add_column("Age", width=12)
    freshness_table.add_column("Status", width=15)

    try:
        metadata_dir = cfg.backup_base_path / "metadata"
        reader = MetadataReader(metadata_dir)
        checker = MissedBackupChecker(cfg, reader)

        unit_names = reader.get_unit_names()
        if not unit_names:
            console.print("[dim]No backup metadata found[/dim]")
            console.print()
            return

        missed_set = {u.name for u in checker.check_all_units()}

        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)

        for name in unit_names:
            entries = reader.read_all(unit_name=name)
            last_success = next((m for m in entries if m.success), None)

            if last_success is None:
                freshness_table.add_row(name, "—", "—", "[red]Never[/red]")
                warnings.append(f"Unit '{name}' has no successful backup on record")
                continue

            ts = last_success.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age_hours = (now - ts).total_seconds() / 3600
            if age_hours < 24:
                age_str = f"{age_hours:.1f}h"
            else:
                age_str = f"{age_hours / 24:.1f}d"

            ts_str = ts.strftime("%Y-%m-%d %H:%M")

            if name in missed_set:
                status = "[red]OVERDUE[/red]"
                warnings.append(f"Unit '{name}' backup is overdue ({age_str} old)")
            else:
                status = "[green]OK[/green]"

            freshness_table.add_row(name, ts_str, age_str, status)

        console.print(freshness_table)

    except Exception as e:
        console.print(f"[yellow]Could not check backup freshness: {e}[/yellow]")

    console.print()


def _check_dr_readiness(cfg: "Config", console: Console, warnings: list) -> None:
    """Section 9 — Disaster Recovery Readiness (Plan 0030).

    The DR bundle intentionally does NOT carry the SSH private key for
    SFTP/Tailscale backends. This section makes the externally-held key
    visible in everyday operation: shows its path + SHA256 (so the user
    can record it for verification), warns if it's missing right now.

    Silent for non-SFTP backends (filesystem repos need nothing extra;
    cloud backends are flagged at export time, not here).
    """
    from ..cores.disaster_recovery_manager import sha256_file

    kopia_params = cfg.get("kopia", "kopia_params", fallback="") or ""
    backend = kopia_params.strip().split(None, 1)[0].lower()
    if backend != "sftp":
        return

    # Extract --keyfile= and --known-hosts= via shlex (kopia_params is
    # the canonical source after Plan 0029 / v7.4.0).
    import shlex
    keyfile_path = ""
    known_hosts = ""
    try:
        for tok in shlex.split(kopia_params):
            if tok.startswith("--keyfile="):
                keyfile_path = tok.split("=", 1)[1]
            elif tok.startswith("--known-hosts="):
                known_hosts = tok.split("=", 1)[1]
    except ValueError:
        return

    console.print("[bold]9. Disaster Recovery Readiness[/bold]")
    console.print("-" * 40)

    dr_table = Table(box=box.SIMPLE, show_header=False)
    dr_table.add_column("Check", style="cyan", width=24)
    dr_table.add_column("Status", width=18)
    dr_table.add_column("Details", style="dim")

    dr_table.add_row("Backend Type", "", backend)

    # SSH key presence + fingerprint
    if not keyfile_path:
        dr_table.add_row(
            "SSH Key",
            "[yellow]Not in params[/yellow]",
            "kopia_params has no --keyfile=…",
        )
        warnings.append(
            "kopia_params is SFTP but has no --keyfile — DR recovery from a "
            "fresh system will need it (run: advanced config repair-kopia-params)"
        )
    else:
        kf = Path(keyfile_path)
        if not kf.exists():
            dr_table.add_row("SSH Key", "[red]✗ MISSING[/red]", keyfile_path)
            warnings.append(
                f"SSH key referenced in kopia_params is missing: {keyfile_path} "
                f"— DR recovery from a fresh system will fail without it"
            )
        elif not os.access(keyfile_path, os.R_OK):
            dr_table.add_row(
                "SSH Key",
                "[yellow]✗ Not readable[/yellow]",
                keyfile_path,
            )
            warnings.append(
                f"SSH key {keyfile_path} exists but is not readable by this "
                f"process (try: sudo kopi-docka doctor)"
            )
        else:
            dr_table.add_row("SSH Key", "[green]✓ Found[/green]", keyfile_path)
            sha = sha256_file(kf)
            if sha:
                dr_table.add_row(
                    "SSH Key SHA256",
                    "",
                    f"{sha}",
                )
                dr_table.add_row(
                    "",
                    "",
                    "[dim]Record this for DR verification[/dim]",
                )

    # Known hosts (advisory, not blocking)
    if known_hosts:
        if Path(known_hosts).exists():
            dr_table.add_row("Known Hosts", "[green]✓ Found[/green]", known_hosts)
        else:
            dr_table.add_row(
                "Known Hosts",
                "[yellow]✗ Missing[/yellow]",
                known_hosts,
            )

    console.print(dr_table)
    console.print()


def cmd_doctor(ctx: typer.Context, verbose: bool = False):
    """
    Run comprehensive system health check.

    Checks:
    1. System Information
    2. Core Dependencies (with categories)
    3. Systemd Integration
    4. Backend Dependencies
    5. Configuration status
    6. Repository status (connection is the single source of truth)
    """
    console.print()
    console.print(
        Panel.fit("[bold cyan]Kopi-Docka System Health Check[/bold cyan]", border_style="cyan")
    )
    console.print()

    issues = []
    warnings = []

    cfg = get_config(ctx)
    dep_manager = DependencyManager()

    # ═══════════════════════════════════════════
    # Section 1: System Information
    # ═══════════════════════════════════════════
    _show_system_info()

    # ═══════════════════════════════════════════
    # Section 2: Core Dependencies (with categories)
    # ═══════════════════════════════════════════
    _show_core_dependencies(dep_manager)

    # Check for critical missing dependencies
    dep_status = dep_manager.check_all()
    if not dep_status.get("kopia", False):
        issues.append("Kopia is not installed")
    if not dep_status.get("docker", False):
        issues.append("Docker is not running")

    # ═══════════════════════════════════════════
    # Section 3: Systemd Integration
    # ═══════════════════════════════════════════
    _show_systemd_status()

    # ═══════════════════════════════════════════
    # Section 4: Backend Dependencies
    # ═══════════════════════════════════════════
    _show_backend_dependencies(cfg, warnings)

    # ═══════════════════════════════════════════
    # Section 5: Configuration
    # ═══════════════════════════════════════════
    console.print("[bold]5. Configuration[/bold]")
    console.print("-" * 40)

    config_table = Table(box=box.SIMPLE, show_header=False)
    config_table.add_column("Property", style="cyan", width=20)
    config_table.add_column("Status", width=15)
    config_table.add_column("Details", style="dim")

    kopia_params = ""

    if cfg:
        config_table.add_row("Config File", "[green]Found[/green]", str(cfg.config_file))

        # Check password
        try:
            password = cfg.get_password()
            if password and password not in ("kopi-docka", "CHANGE_ME_TO_A_SECURE_PASSWORD", ""):
                config_table.add_row("Password", "[green]Configured[/green]", "")
            else:
                config_table.add_row(
                    "Password",
                    "[yellow]Default/Missing[/yellow]",
                    "Run: kopi-docka advanced repo init",
                )
                warnings.append("Password is default or missing")
        except Exception:
            config_table.add_row("Password", "[red]Error[/red]", "Could not read password")
            issues.append("Could not read password from config")

        # Check kopia_params
        kopia_params = cfg.get("kopia", "kopia_params", fallback="")
        if kopia_params:
            config_table.add_row(
                "Kopia Params",
                "[green]Configured[/green]",
                kopia_params[:50] + "..." if len(kopia_params) > 50 else kopia_params,
            )
        else:
            config_table.add_row(
                "Kopia Params", "[red]Missing[/red]", "Run: kopi-docka advanced config new"
            )
            issues.append("Kopia parameters not configured")
    else:
        config_table.add_row(
            "Config File", "[red]Not Found[/red]", "Run: kopi-docka advanced config new"
        )
        issues.append("No configuration file found")

    console.print(config_table)
    console.print()

    # ═══════════════════════════════════════════
    # Section 5.1: Backend Sanity (Plan 0029)
    # Catches broken kopia_params shapes — e.g. the v7.0.0–v7.3.13
    # Tailscale wizard that shipped --path=HOST:PATH and forgot
    # --username / --keyfile. Backups would otherwise silently hang
    # on first connect.
    # ═══════════════════════════════════════════
    _show_backend_sanity(cfg, warnings, issues)

    # ═══════════════════════════════════════════
    # Section 6: Repository Status
    # (Kopia connection is the SINGLE SOURCE OF TRUTH)
    # ═══════════════════════════════════════════
    if cfg:
        console.print("[bold]6. Repository Status[/bold]")
        console.print("-" * 40)

        repo_table = Table(box=box.SIMPLE, show_header=False)
        repo_table.add_column("Property", style="cyan", width=20)
        repo_table.add_column("Status", width=15)
        repo_table.add_column("Details", style="dim")

        # Show repository type (from config parsing, no API call needed)
        repo_type = detect_repository_type(kopia_params)
        repo_table.add_row("Repository Type", "", repo_type)

        # Show storage-specific info (parsed from config, no API call)
        storage_info = _extract_storage_info(kopia_params, repo_type)
        if storage_info:
            for key, value in storage_info.items():
                display_key = key.replace("_", " ").title()
                repo_table.add_row(display_key, "", value)

        # THE ACTUAL CHECK: Kopia repository connection
        repo = None
        try:
            repo = KopiaRepository(cfg)

            if repo.is_connected():
                repo_table.add_row("Connection", "[green]Connected[/green]", "")
                repo_table.add_row("Profile", "", repo.profile_name)

                # Get snapshot count
                try:
                    snapshots = repo.list_snapshots()
                    repo_table.add_row("Snapshots", "", str(len(snapshots)))
                except Exception:
                    repo_table.add_row("Snapshots", "[yellow]Unknown[/yellow]", "")

                # Get backup units count
                try:
                    units = repo.list_backup_units()
                    repo_table.add_row("Backup Units", "", str(len(units)))
                except Exception:
                    repo_table.add_row("Backup Units", "[yellow]Unknown[/yellow]", "")
            else:
                repo_table.add_row("Connection", "[yellow]Not Connected[/yellow]", "")
                warnings.append("Repository not connected")

                # Helpful message based on repo type
                if repo_type == "unknown":
                    repo_table.add_row("", "", "Run: kopi-docka advanced config new")
                else:
                    repo_table.add_row("", "", "Run: kopi-docka advanced repo init")

        except Exception as e:
            repo_table.add_row("Connection", "[red]Error[/red]", str(e)[:50])
            issues.append(f"Repository check failed: {e}")

        console.print(repo_table)
        console.print()

        # Section 7: Retention Policy Alignment
        # ═══════════════════════════════════════════
        if repo and repo.is_connected():
            _check_policy_alignment(repo, console, warnings)

        # Section 8: Backup Freshness
        # ═══════════════════════════════════════════
        if cfg:
            _check_backup_freshness(cfg, console, warnings)

        # Section 9: Disaster Recovery Readiness (Plan 0030)
        # ═══════════════════════════════════════════
        if cfg:
            _check_dr_readiness(cfg, console, warnings)

    # ═══════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════
    console.print("-" * 40)

    if not issues and not warnings:
        console.print(
            Panel.fit(
                "[green]All systems operational![/green]\n\n"
                "Kopi-Docka is ready to backup your Docker containers.",
                title="[bold green]Health Check Passed[/bold green]",
                border_style="green",
            )
        )
    elif issues:
        issue_list = "\n".join(f"  - {i}" for i in issues)
        warning_list = "\n".join(f"  - {w}" for w in warnings) if warnings else ""

        message = f"[red]Issues found ({len(issues)}):[/red]\n{issue_list}"
        if warnings:
            message += f"\n\n[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}"

        console.print(
            Panel.fit(message, title="[bold red]Health Check Failed[/bold red]", border_style="red")
        )
    else:
        warning_list = "\n".join(f"  - {w}" for w in warnings)
        console.print(
            Panel.fit(
                f"[yellow]Warnings ({len(warnings)}):[/yellow]\n{warning_list}\n\n"
                "System is functional but may need attention.",
                title="[bold yellow]Health Check Warnings[/bold yellow]",
                border_style="yellow",
            )
        )

    console.print()

    # Verbose output
    if verbose:
        console.print("[bold]Detailed Dependency Status:[/bold]")
        dep_manager.print_status(verbose=True)


# -------------------------
# Registration
# -------------------------


def register(app: typer.Typer):
    """Register doctor command."""

    @app.command("doctor")
    def _doctor_cmd(
        ctx: typer.Context,
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    ):
        """Run comprehensive system health check."""
        cmd_doctor(ctx, verbose)
