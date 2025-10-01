#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        main.py
# @module:      kopi_docka.main
# @description: Typer-based CLI entry point orchestrating Kopi-Docka operations.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------ 
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Kopi-Docka — main CLI

Typer-based CLI following the "Werkzeugtisch" (tool bench) pattern:
- Configuration is loaded once at startup
- Commands retrieve tools from context instead of parameters
- No custom types in function signatures
"""

from __future__ import annotations

import sys
import shutil
import subprocess
import os
import json
import socket
import time
import secrets
import string
from pathlib import Path
from typing import Optional, List

import typer

from .constants import VERSION
from .config import Config, create_default_config
from .dependencies import DependencyManager
from .logging import get_logger, log_manager
from .discovery import DockerDiscovery
from .backup import BackupManager
from .restore import RestoreManager
from .repository import KopiaRepository
from .dry_run import DryRunReport
from .service import (
    KopiDockaService,
    ServiceConfig,
    write_systemd_units,
)

app = typer.Typer(
    add_completion=False,
    help="Kopi-Docka – Backup & Restore for Docker using Kopia."
)
logger = get_logger(__name__)


# -------------------------
# Application Context
# -------------------------

@app.callback()
def initialize_context(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to configuration file."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)."
    ),
):
    """
    Initialize application context before any command runs.
    Sets up logging and loads configuration once.
    """
    # Set up logging
    try:
        log_manager.configure(level=log_level.upper())
    except Exception:
        import logging
        logging.basicConfig(level=log_level.upper())

    # Initialize context
    ctx.ensure_object(dict)

    # Load configuration once
    try:
        if config_path and config_path.exists():
            cfg = Config(config_path)
        else:
            cfg = Config()
    except Exception:
        cfg = None

    ctx.obj["config"] = cfg
    ctx.obj["config_path"] = config_path


# -------------------------
# Helper Functions
# -------------------------

def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from the tool bench."""
    return ctx.obj.get("config")


def get_repository(ctx: typer.Context) -> Optional[KopiaRepository]:
    """Get or create repository from the tool bench."""
    if "repository" not in ctx.obj:
        cfg = get_config(ctx)
        if cfg:
            ctx.obj["repository"] = KopiaRepository(cfg)
    return ctx.obj.get("repository")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka new-config")
        raise typer.Exit(code=1)
    return cfg


def ensure_dependencies():
    """Ensure all dependencies are installed or exit."""
    deps = DependencyManager()
    missing = deps.get_missing()
    if missing:
        typer.echo("⚠ Missing required dependencies:")
        for dep in missing:
            typer.echo(f"  - {dep}")
        typer.echo("\nRun: kopi-docka install-deps")
        raise typer.Exit(code=1)


def ensure_repository(ctx: typer.Context) -> KopiaRepository:
    """
    Ensure repository is connected for this profile, try auto-connect (and create if needed).
    """
    repo = get_repository(ctx)
    if not repo:
        typer.echo("❌ Repository not available")
        raise typer.Exit(code=1)

    # Already connected?
    try:
        if repo.is_connected():
            return repo
    except Exception:
        pass

    # Auto connect (and create if needed by repo.connect())
    typer.echo("↻ Connecting to Kopia repository…")
    try:
        repo.connect()
    except Exception as e:
        typer.echo(f"✗ Connect failed: {e}")
        typer.echo("  Check: repository_path, password, permissions, mounts.")
        raise typer.Exit(code=1)

    # Verify
    if not repo.is_connected():
        typer.echo("✗ Still not connected after connect().")
        typer.echo("  Tip: 'kopia repository status --config-file ~/.config/kopia/repository-<profile>.config'")
        raise typer.Exit(code=1)

    return repo


def _filter_units(all_units, names: Optional[List[str]]):
    """Filter backup units by name."""
    if not names:
        return all_units
    wanted = set(names)
    return [u for u in all_units if u.name in wanted]


def _print_kopia_native_status(repo: KopiaRepository) -> None:
    """
    Print exact Kopia native status (command used, RC, RAW stdout/stderr, pretty JSON if possible).
    Always uses the repo's profile config file.
    """
    typer.echo("\n" + "-" * 60)
    typer.echo("KOPIA (native) STATUS — RAW & JSON")
    typer.echo("-" * 60)

    cfg_file = repo._get_config_file()  # profile config path
    env = repo._get_env()

    cmd_json_verbose = ["kopia", "repository", "status", "--json-verbose", "--config-file", cfg_file]
    cmd_json = ["kopia", "repository", "status", "--json", "--config-file", cfg_file]
    cmd_plain = ["kopia", "repository", "status", "--config-file", cfg_file]

    used_cmd = None
    rc_connected = False
    raw_out = raw_err = ""

    for cmd in (cmd_json_verbose, cmd_json, cmd_plain):
        p = subprocess.run(cmd, env=env, text=True, capture_output=True)
        used_cmd = cmd
        raw_out, raw_err = p.stdout or "", p.stderr or ""
        if p.returncode == 0:
            rc_connected = True
            break

    typer.echo("Command used       : " + " ".join(used_cmd))
    typer.echo(f"Config file        : {cfg_file}")
    typer.echo(f"Env KOPIA_PASSWORD : {'set' if env.get('KOPIA_PASSWORD') else 'unset'}")
    typer.echo(f"Env KOPIA_CACHE    : {env.get('KOPIA_CACHE_DIRECTORY') or '-'}")
    typer.echo(f"Connected (by RC)  : {'✓' if rc_connected else '✗'}")

    typer.echo("\n--- kopia stdout ---")
    typer.echo(raw_out.strip() or "<empty>")
    if raw_err.strip():
        typer.echo("\n--- kopia stderr ---")
        typer.echo(raw_err.strip())

    # Pretty-print JSON if possible
    try:
        parsed = json.loads(raw_out) if raw_out else None
        if parsed is not None:
            typer.echo("\n--- parsed JSON (pretty) ---")
            typer.echo(json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception:
        pass


# -------------------------
# Version & Help
# -------------------------

@app.command("version")
def cmd_version():
    """Show Kopi-Docka version."""
    typer.echo(f"Kopi-Docka {VERSION}")


# -------------------------
# Dependency Management
# -------------------------

@app.command("check")
def cmd_check(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Check system requirements and dependencies."""
    deps = DependencyManager()
    deps.print_status(verbose=verbose)

    # Check repository if config exists
    cfg = get_config(ctx)
    if cfg:
        try:
            repo = KopiaRepository(cfg)
            if repo.is_connected():
                typer.echo("✓ Kopia repository is connected")
                typer.echo(f"  Profile: {repo.profile_name}")
                typer.echo(f"  Repository: {repo.repo_path}")
                if verbose:
                    snapshots = repo.list_snapshots()
                    typer.echo(f"  Snapshots: {len(snapshots)}")
                    units = repo.list_backup_units()
                    typer.echo(f"  Backup units: {len(units)}")
            else:
                typer.echo("✗ Kopia repository not connected")
                typer.echo("  Run: kopi-docka init")
        except Exception as e:
            typer.echo(f"✗ Repository check failed: {e}")
    else:
        typer.echo("✗ No configuration found")
        typer.echo("  Run: kopi-docka new-config")


@app.command("install-deps")
def cmd_install_deps(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be installed"),
):
    """Install missing system dependencies."""
    deps = DependencyManager()

    if dry_run:
        missing = deps.get_missing()
        if missing:
            deps.install_missing(dry_run=True)
        else:
            typer.echo("✓ All dependencies already installed")
        return

    missing = deps.get_missing()
    if missing:
        success = deps.auto_install(force=force)
        if not success:
            raise typer.Exit(code=1)
        typer.echo(f"\n✓ Installed {len(missing)} dependencies")
    else:
        typer.echo("✓ All required dependencies already installed")

    # Hint about config
    if not Path.home().joinpath(".config/kopi-docka/config.conf").exists() and \
       not Path("/etc/kopi-docka.conf").exists():
        typer.echo("\n💡 Tip: Create config with: kopi-docka new-config")


@app.command("deps")
def cmd_deps():
    """Show dependency installation guide."""
    deps = DependencyManager()
    deps.print_install_guide()


# -------------------------
# Configuration Management
# -------------------------

@app.command("config")
def cmd_config(
    ctx: typer.Context,
    show: bool = typer.Option(True, "--show", help="Show current configuration"),
):
    """Show current configuration."""
    cfg = ensure_config(ctx)

    import configparser
    typer.echo(f"Configuration file: {cfg.config_file}")
    typer.echo("=" * 60)

    config = configparser.ConfigParser()
    config.read(cfg.config_file)

    for section in config.sections():
        typer.echo(f"\n[{section}]")
        for option, value in config.items(section):
            if 'password' in option.lower() or 'token' in option.lower():
                value = '***MASKED***'
            typer.echo(f"  {option} = {value}")


@app.command("new-config")
def cmd_new_config(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
    edit: bool = typer.Option(True, "--edit/--no-edit", help="Open in editor after creation"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Custom config path"),
):
    """Create new configuration file."""
    # Check if config exists
    existing_cfg = None
    try:
        if path:
            existing_cfg = Config(path)
        else:
            existing_cfg = Config()
    except Exception:
        pass  # Config doesn't exist, that's fine

    if existing_cfg and existing_cfg.config_file.exists() and not force:
        typer.echo(f"⚠️ Config already exists at: {existing_cfg.config_file}")
        typer.echo("Use --force to overwrite or 'edit-config' to modify")
        raise typer.Exit(code=1)

    typer.echo("Creating new configuration...")
    created_path = create_default_config(path, force)
    typer.echo(f"✓ Config created at: {created_path}")

    if edit:
        editor = os.environ.get('EDITOR', 'nano')
        typer.echo(f"\nOpening in {editor} for initial setup...")
        typer.echo("Important settings to configure:")
        typer.echo("  • repository_path - Where to store backups")
        typer.echo("  • password - Strong password for encryption")
        typer.echo("  • backup paths - Adjust for your system")
        subprocess.call([editor, str(created_path)])


@app.command("edit-config")
def cmd_edit_config(
    ctx: typer.Context,
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Specify editor to use"),
):
    """Edit existing configuration file."""
    cfg = ensure_config(ctx)

    if not editor:
        editor = os.environ.get('EDITOR', 'nano')

    typer.echo(f"Opening {cfg.config_file} in {editor}...")
    subprocess.call([editor, str(cfg.config_file)])

    # Validate after editing
    try:
        Config(cfg.config_file)
        typer.echo("✓ Configuration valid")
    except Exception as e:
        typer.echo(f"⚠️ Configuration might have issues: {e}")


# -------------------------
# Repository Operations
# -------------------------

@app.command("init")
def cmd_init(ctx: typer.Context):
    """Initialize (or connect to) the Kopia repository defined in your config."""
    if not shutil.which("kopia"):
        typer.echo("❌ Kopia is not installed!")
        typer.echo("Install with: kopi-docka install-deps")
        raise typer.Exit(code=1)

    ensure_dependencies()
    cfg = ensure_config(ctx)
    repo = KopiaRepository(cfg)

    typer.echo(f"Using profile: {repo.profile_name}")
    typer.echo(f"Repository: {repo.repo_path}")

    try:
        repo.connect()  # connect → if not initialized: create → connect
        typer.echo("✓ Repository connected")
    except Exception as e:
        typer.echo(f"✗ Init/connect failed: {e}")
        raise typer.Exit(code=1)


@app.command("repo-status")
def cmd_repo_status(ctx: typer.Context):
    """Show Kopia repository status and statistics."""
    ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        typer.echo("=" * 60)
        typer.echo("KOPIA REPOSITORY STATUS")
        typer.echo("=" * 60)

        is_conn = False
        try:
            is_conn = repo.is_connected()
        except Exception:
            is_conn = False

        typer.echo(f"\nProfile: {repo.profile_name}")
        typer.echo(f"Repository: {repo.repo_path}")
        typer.echo(f"Connected: {'✓' if is_conn else '✗'}")

        snapshots = repo.list_snapshots()
        units = repo.list_backup_units()
        typer.echo(f"\nTotal Snapshots: {len(snapshots)}")
        typer.echo(f"Backup Units: {len(units)}")

        # Native status (exact command + raw + parsed)
        _print_kopia_native_status(repo)

        typer.echo("\n" + "=" * 60)

    except Exception as e:
        typer.echo(f"✗ Failed to get repository status: {e}")
        raise typer.Exit(code=1)


@app.command("repo-which-config")
def cmd_repo_which_config(ctx: typer.Context):
    """Show which Kopia config file is used by the current profile and the default path."""
    repo = get_repository(ctx) or KopiaRepository(ensure_config(ctx))
    typer.echo(f"Profile         : {repo.profile_name}")
    typer.echo(f"Profile config  : {repo._get_config_file()}")
    typer.echo(f"Default config  : {Path.home() / '.config' / 'kopia' / 'repository.config'}")


@app.command("repo-set-default")
def cmd_repo_set_default(ctx: typer.Context):
    """
    Point the default Kopia config (repository.config) at the current profile.
    After this, running 'kopia repository status' WITHOUT --config-file will use this profile.
    """
    repo = ensure_repository(ctx)

    src = Path(repo._get_config_file())
    dst = Path.home() / ".config" / "kopia" / "repository.config"
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        try:
            dst.symlink_to(src)
        except Exception:
            from shutil import copy2
            copy2(src, dst)
        typer.echo("✓ Default kopia config set.")
        typer.echo("Test:  kopia repository status")
    except Exception as e:
        typer.echo(f"✗ Could not set default: {e}")
        raise typer.Exit(code=1)


@app.command("repo-init-path")
def cmd_repo_init_path(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Repository path (filesystem backend)."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile name to use (defaults to current)."),
    set_default: bool = typer.Option(False, "--set-default/--no-set-default", help="Also set as default Kopia config."),
    password: Optional[str] = typer.Option(None, "--password", help="Password to use (overrides config/env)."),
):
    """
    Create a Kopia filesystem repository at PATH (exactly like: kopia repository create filesystem --path PATH),
    then connect to it under the chosen profile/config.
    """
    cfg = ensure_config(ctx)
    repo = KopiaRepository(cfg)

    env = repo._get_env()
    if password:
        env["KOPIA_PASSWORD"] = password

    cfg_file = repo._get_config_file() if not profile else str(Path.home() / ".config" / "kopia" / f"repository-{profile}.config")
    Path(cfg_file).parent.mkdir(parents=True, exist_ok=True)

    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    # 1) Create
    cmd_create = [
        "kopia", "repository", "create", "filesystem",
        "--path", str(path),
        "--description", f"Kopi-Docka Backup Repository ({profile or repo.profile_name})",
        "--config-file", cfg_file,
    ]
    p = subprocess.run(cmd_create, env=env, text=True, capture_output=True)
    if p.returncode != 0 and "existing data in storage location" not in (p.stderr or ""):
        typer.echo("✗ create failed:")
        typer.echo(p.stderr.strip() or p.stdout.strip())
        raise typer.Exit(code=1)

    # 2) Connect (idempotent)
    cmd_connect = [
        "kopia", "repository", "connect", "filesystem",
        "--path", str(path),
        "--config-file", cfg_file,
    ]
    pc = subprocess.run(cmd_connect, env=env, text=True, capture_output=True)
    if pc.returncode != 0:
        ps = subprocess.run(["kopia", "repository", "status", "--config-file", cfg_file], env=env, text=True, capture_output=True)
        typer.echo("✗ connect failed:")
        typer.echo(pc.stderr.strip() or pc.stdout.strip() or ps.stderr.strip() or ps.stdout.strip())
        raise typer.Exit(code=1)

    # 3) Verify
    ps = subprocess.run(["kopia", "repository", "status", "--json", "--config-file", cfg_file], env=env, text=True, capture_output=True)
    if ps.returncode != 0:
        typer.echo("✗ status failed after connect:")
        typer.echo(ps.stderr.strip() or ps.stdout.strip())
        raise typer.Exit(code=1)

    typer.echo("✓ Repository created & connected")
    typer.echo(f"  Path    : {path}")
    typer.echo(f"  Profile : {profile or repo.profile_name}")
    typer.echo(f"  Config  : {cfg_file}")

    # 4) Optionally set default
    if set_default:
        src = Path(cfg_file)
        dst = Path.home() / ".config" / "kopia" / "repository.config"
        try:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            try:
                dst.symlink_to(src)
            except Exception:
                from shutil import copy2
                copy2(src, dst)
            typer.echo("✓ Set as default Kopia config. Test:")
            typer.echo("  kopia repository status")
        except Exception as e:
            typer.echo(f"⚠ could not set default: {e}")

    # Hints for raw Kopia
    typer.echo("\nUse raw Kopia with this repo:")
    typer.echo(f"  kopia repository status --config-file {cfg_file}")
    typer.echo(f"  kopia snapshot list --json --config-file {cfg_file}")


@app.command("repo-selftest")
def cmd_repo_selftest(
    tmpdir: Path = typer.Option(Path("/tmp"), "--tmpdir", help="Base dir for ephemeral test repo"),
    keep: bool = typer.Option(False, "--keep/--no-keep", help="Keep repo & config for manual inspection"),
    password: Optional[str] = typer.Option(None, "--password", help="Password for the test repo (default: random)"),
):
    """
    Create an ephemeral test repository, snapshot a dummy file, list snapshots, and clean up.
    Useful to validate Kopia + profile config on this host.
    """
    # Prepare locations & credentials
    stamp = str(int(time.time()))
    test_profile = f"kopi-docka-selftest-{stamp}"
    repo_dir = Path(tmpdir) / f"kopia-selftest-{stamp}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    if not password:
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(24))

    # Minimal temp config for Config()
    conf_dir = Path.home() / ".config" / "kopi-docka"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_path = conf_dir / f"selftest-{stamp}.conf"

    conf_path.write_text(
        f"""
[kopia]
repository_path = {repo_dir}
password = {password}
profile = {test_profile}

[retention]
daily = 7
weekly = 4
monthly = 12
yearly = 3
""".strip(),
        encoding="utf-8",
    )

    typer.echo(f"Selftest profile   : {test_profile}")
    typer.echo(f"Selftest repo path : {repo_dir}")
    typer.echo(f"Selftest config    : {conf_path}")

    cfg = Config(conf_path)
    test_repo = KopiaRepository(cfg)

    # Connect/create
    typer.echo("↻ Connecting/creating test repository…")
    try:
        test_repo.connect()
    except Exception as e:
        typer.echo(f"✗ Could not connect/create selftest repo: {e}")
        raise typer.Exit(code=1)

    if not test_repo.is_connected():
        typer.echo("✗ Not connected after connect().")
        raise typer.Exit(code=1)

    # Native status (raw)
    _print_kopia_native_status(test_repo)

    # Create a small snapshot
    workdir = repo_dir / "data"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "hello.txt").write_text("Hello Kopia!\n", encoding="utf-8")

    typer.echo("Creating snapshot of selftest data…")
    snap_id = test_repo.create_snapshot(str(workdir), tags={"type": "selftest"})
    typer.echo(f"Snapshot ID        : {snap_id}")

    # List snapshots
    snaps = test_repo.list_snapshots(tag_filter={"type": "selftest"})
    typer.echo(f"Selftest snapshots : {len(snaps)}")

    # Optional maintenance (quick)
    try:
        test_repo.maintenance_run(full=False)
    except Exception:
        pass

    # Cleanup
    if not keep:
        typer.echo("Cleaning up selftest repo & config…")
        try:
            test_repo.disconnect()
        except Exception:
            pass
        try:
            import shutil as _shutil
            _shutil.rmtree(repo_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            conf_path.unlink(missing_ok=True)
        except Exception:
            pass
        typer.echo("✓ Cleanup done")
    else:
        typer.echo("(kept) Inspect manually, e.g.:")
        typer.echo(f"  kopia repository status --config-file ~/.config/kopia/repository-{test_repo.profile_name}.config")
        typer.echo(f"  kopia snapshot list --json --config-file ~/.config/kopia/repository-{test_repo.profile_name}.config")


@app.command("repo-maintenance")
def cmd_repo_maintenance(ctx: typer.Context):
    """Run Kopia repository maintenance."""
    ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        repo.maintenance_run()
        typer.echo("✓ Maintenance completed")
    except Exception as e:
        typer.echo(f"Maintenance failed: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Backup & Restore
# -------------------------

@app.command("list")
def cmd_list(
    ctx: typer.Context,
    units: bool = typer.Option(True, "--units", help="List discovered backup units"),
    snapshots: bool = typer.Option(False, "--snapshots", help="List repository snapshots"),
):
    """List backup units or repository snapshots."""
    cfg = ensure_config(ctx)

    if not (units or snapshots):
        units = True

    if units:
        typer.echo("Discovering Docker backup units…")
        try:
            discovery = DockerDiscovery()
            found = discovery.discover_backup_units()
            if not found:
                typer.echo("No units found.")
            else:
                for u in found:
                    typer.echo(
                        f"- {u.name} ({u.type}): {len(u.containers)} containers, {len(u.volumes)} volumes"
                    )
        except Exception as e:
            typer.echo(f"Discovery failed: {e}")
            raise typer.Exit(code=1)

    if snapshots:
        typer.echo("\nListing snapshots…")
        try:
            repo = KopiaRepository(cfg)
            snaps = repo.list_snapshots()
            if not snaps:
                typer.echo("No snapshots found.")
            else:
                for s in snaps:
                    unit = s.get("tags", {}).get("unit", "-")
                    ts = s.get("timestamp", "-")
                    sid = s.get("id", "")
                    typer.echo(f"- {sid} | unit={unit} | {ts}")
        except Exception as e:
            typer.echo(f"Unable to list snapshots: {e}")
            raise typer.Exit(code=1)


@app.command("backup")
def cmd_backup(
    ctx: typer.Context,
    unit: List[str] = typer.Option(None, "--unit", "-u", help="Backup only these units"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate backup"),
    update_recovery_bundle: Optional[bool] = typer.Option(
        None,
        "--update-recovery/--no-update-recovery",
        help="Override config: update disaster recovery bundle",
    ),
):
    """Run a cold backup for selected units (or all)."""
    ensure_dependencies()
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        discovery = DockerDiscovery()
        units = discovery.discover_backup_units()
        selected = _filter_units(units, unit)

        if not selected:
            typer.echo("Nothing to back up (no units found).")
            return

        if dry_run:
            report = DryRunReport(cfg)
            report.generate(selected, update_recovery_bundle)
            return

        bm = BackupManager(cfg)
        overall_ok = True

        for u in selected:
            typer.echo(f"==> Backing up unit: {u.name}")
            meta = bm.backup_unit(u, update_recovery_bundle=update_recovery_bundle)
            if meta.success:
                typer.echo(f"✓ {u.name} completed in {int(meta.duration_seconds)}s")
                if meta.kopia_snapshot_ids:
                    typer.echo(f"   Snapshots: {', '.join(meta.kopia_snapshot_ids)}")
            else:
                overall_ok = False
                typer.echo(f"✗ {u.name} failed in {int(meta.duration_seconds)}s")
                for err in meta.errors or [meta.error_message]:
                    if err:
                        typer.echo(f"   - {err}")

        if not overall_ok:
            raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"Backup failed: {e}")
        raise typer.Exit(code=1)


@app.command("restore")
def cmd_restore(ctx: typer.Context):
    """Launch the interactive restore wizard."""
    cfg = ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        rm = RestoreManager(cfg)
        rm.interactive_restore()
    except Exception as e:
        typer.echo(f"Restore failed: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Service Management
# -------------------------

@app.command("daemon")
def cmd_daemon(
    interval_minutes: Optional[int] = typer.Option(
        None,
        "--interval-minutes",
        help="Run backup every N minutes (prefer systemd timer)",
    ),
    backup_cmd: str = typer.Option(
        "/usr/bin/env kopi-docka backup",
        "--backup-cmd",
        help="Command to start a backup run",
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level for service"
    ),
):
    """Run the systemd-friendly daemon (service)."""
    cfg = ServiceConfig(
        backup_cmd=backup_cmd,
        interval_minutes=interval_minutes,
        log_level=log_level,
    )
    svc = KopiDockaService(cfg)
    rc = svc.start()
    raise typer.Exit(code=rc)


@app.command("write-units")
def cmd_write_units(
    output_dir: Path = typer.Option(
        Path("/etc/systemd/system"),
        "--output-dir",
        help="Where to write systemd unit files",
    )
):
    """Write example systemd service and timer units."""
    try:
        write_systemd_units(output_dir)
        typer.echo(f"✓ Unit files written to: {output_dir}")
        typer.echo("Enable with: sudo systemctl enable --now kopi-docka.timer")
    except Exception as e:
        typer.echo(f"Failed to write units: {e}")
        raise typer.Exit(code=1)


# -------------------------
# Entrypoint
# -------------------------

def main():
    """Main entry point for the application."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
