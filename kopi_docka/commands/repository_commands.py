################################################################################
# KOPI-DOCKA
#
# @file:        repository_commands.py
# @module:      kopi_docka.commands
# @description: Repository management commands
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""Repository management commands."""

import json
import subprocess
import shutil
import time
import secrets
import string
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..helpers import Config, get_logger, generate_secure_password
from ..cores import KopiaRepository

logger = get_logger(__name__)
console = Console()


def get_config(ctx: typer.Context) -> Optional[Config]:
    """Get config from context."""
    return ctx.obj.get("config")


def ensure_config(ctx: typer.Context) -> Config:
    """Ensure config exists or exit."""
    cfg = get_config(ctx)
    if not cfg:
        typer.echo("❌ No configuration found")
        typer.echo("Run: kopi-docka admin config new")
        raise typer.Exit(code=1)
    return cfg


def get_repository(ctx: typer.Context) -> Optional[KopiaRepository]:
    """Get or create repository from context."""
    if "repository" not in ctx.obj:
        cfg = get_config(ctx)
        if cfg:
            ctx.obj["repository"] = KopiaRepository(cfg)
    return ctx.obj.get("repository")


def ensure_repository(ctx: typer.Context) -> KopiaRepository:
    """Ensure repository is connected."""
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

    # Auto connect
    typer.echo("↻ Connecting to Kopia repository…")
    try:
        repo.connect()
    except Exception as e:
        typer.echo(f"✗ Connect failed: {e}")
        typer.echo("  Check: kopia_params, password, permissions, mounts.")
        raise typer.Exit(code=1)

    if not repo.is_connected():
        typer.echo("✗ Still not connected after connect().")
        raise typer.Exit(code=1)

    return repo


def _print_kopia_native_status(repo: KopiaRepository) -> None:
    """Print Kopia native status with raw output."""
    typer.echo("\n" + "-" * 60)
    typer.echo("KOPIA (native) STATUS — RAW & JSON")
    typer.echo("-" * 60)

    cfg_file = repo._get_config_file()
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
# Commands
# -------------------------

def cmd_init(ctx: typer.Context):
    """Initialize (or connect to) the Kopia repository."""
    import getpass
    
    if not shutil.which("kopia"):
        typer.echo("❌ Kopia is not installed!")
        typer.echo("Install with: kopi-docka install-deps")
        raise typer.Exit(code=1)

    cfg = ensure_config(ctx)
    
    # ═══════════════════════════════════════════
    # Phase 1: Password Check & Setup (if needed)
    # ═══════════════════════════════════════════
    try:
        current_password = cfg.get_password()
    except ValueError as e:
        typer.echo(f"⚠️  Password issue: {e}")
        current_password = ''
    
    # Check for default/placeholder passwords
    if current_password in ('kopia-docka', 'CHANGE_ME_TO_A_SECURE_PASSWORD', ''):
        typer.echo("╭─────────────────────────────────────────╮")
        typer.echo("│ Repository Password Setup                │")
        typer.echo("╰─────────────────────────────────────────╯")
        typer.echo("")
        typer.echo("⚠️  Default or missing password detected!")
        typer.echo("You need to set a secure password before initialization.")
        typer.echo("")
        typer.echo("This password will:")
        typer.echo("  • Encrypt your backups")
        typer.echo("  • Be required for ALL future operations")
        typer.echo("  • Be UNRECOVERABLE if lost!")
        typer.echo("")
        
        use_generated = typer.confirm("Generate secure random password?", default=True)
        typer.echo("")
        
        if use_generated:
            new_password = generate_secure_password()
            typer.echo("═════════════════════════════════════════════════════════════")
            typer.echo("🔑 GENERATED PASSWORD (save this NOW!):")
            typer.echo("")
            typer.echo(f"   {new_password}")
            typer.echo("")
            typer.echo("═════════════════════════════════════════════════════════════")
            typer.echo("⚠️  Copy this to:")
            typer.echo("   • Password manager (recommended)")
            typer.echo("   • Encrypted USB drive")
            typer.echo("   • Secure physical location")
            typer.echo("═════════════════════════════════════════════════════════════")
            typer.echo("")
            input("Press Enter to continue...")
        else:
            new_password = getpass.getpass("Enter password: ")
            password_confirm = getpass.getpass("Confirm password: ")
            
            if new_password != password_confirm:
                typer.echo("❌ Passwords don't match!")
                raise typer.Exit(1)
            
            if len(new_password) < 12:
                typer.echo(f"\n⚠️  WARNING: Password is short ({len(new_password)} chars)")
                typer.echo("Recommended: At least 12 characters")
                if not typer.confirm("Continue with this password?", default=False):
                    typer.echo("Aborted.")
                    raise typer.Exit(0)
        
        # Save password to config
        typer.echo("\n↻ Saving password to config...")
        cfg.set_password(new_password, use_file=True)
        password_file = cfg.config_file.parent / f".{cfg.config_file.stem}.password"
        typer.echo(f"✓ Password saved: {password_file}")
        typer.echo("")
        
        # IMPORTANT: Reload config to get new password
        cfg = Config(cfg.config_file)
        typer.echo("─────────────────────────────────────────")
        typer.echo("")
    
    # ═══════════════════════════════════════════
    # Phase 2: Repository Initialization
    # ═══════════════════════════════════════════
    repo = KopiaRepository(cfg)
    
    typer.echo("╭─────────────────────────────────────────╮")
    typer.echo("│ Repository Initialization                │")
    typer.echo("╰─────────────────────────────────────────╯")
    typer.echo("")
    typer.echo(f"Profile:     {repo.profile_name}")
    typer.echo(f"Kopia Params: {repo.kopia_params}")
    typer.echo("")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing repository...", total=None)
            repo.initialize()
            progress.update(task, completed=True)
        
        console.print()
        console.print(Panel.fit(
            "[green]✓ Repository initialized successfully![/green]\n\n"
            "[bold]Next steps:[/bold]\n"
            "  • List Docker containers: [cyan]kopi-docka list --units[/cyan]\n"
            "  • Test backup:             [cyan]kopi-docka dry-run[/cyan]\n"
            "  • Create first backup:     [cyan]kopi-docka backup[/cyan]",
            title="[bold green]Setup Complete[/bold green]",
            border_style="green"
        ))
        console.print()
        
    except Exception as e:
        typer.echo(f"✗ Initialization failed: {e}")
        typer.echo("")
        typer.echo("Common issues:")
        typer.echo("  • Repository path not accessible")
        typer.echo("  • Insufficient permissions")
        typer.echo("  • Cloud credentials not configured")
        typer.echo("  • Network connectivity issues")
        typer.echo("")
        typer.echo("For cloud storage (B2/S3/Azure/GCS):")
        typer.echo("  • Check environment variables (AWS_*, B2_*, etc.)")
        typer.echo("  • Verify bucket/container exists")
        typer.echo("  • Test credentials separately")
        typer.echo("")
        raise typer.Exit(code=1)


def cmd_repo_status(ctx: typer.Context):
    """Show Kopia repository status and statistics."""
    ensure_config(ctx)
    repo = ensure_repository(ctx)

    try:
        # Check connection status
        is_conn = False
        try:
            is_conn = repo.is_connected()
        except Exception:
            is_conn = False

        # Get statistics
        snapshots = repo.list_snapshots()
        units = repo.list_backup_units()

        # Build status table
        table = Table(title="Repository Status", show_header=True, header_style="bold cyan")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green" if is_conn else "red")
        
        table.add_row("Profile", repo.profile_name)
        table.add_row("Kopia Params", repo.kopia_params)
        table.add_row("Connected", "✓ Yes" if is_conn else "✗ No")
        table.add_row("Total Snapshots", str(len(snapshots)))
        table.add_row("Backup Units", str(len(units)))

        console.print()
        console.print(table)
        console.print()

        # Show detailed Kopia status if requested (debug)
        if ctx.obj.get('verbose'):
            _print_kopia_native_status(repo)

    except Exception as e:
        console.print(f"[red]✗ Failed to get repository status: {e}[/red]")
        raise typer.Exit(code=1)


def cmd_repo_which_config(ctx: typer.Context):
    """Show which Kopia config file is used."""
    repo = get_repository(ctx) or KopiaRepository(ensure_config(ctx))
    typer.echo(f"Profile         : {repo.profile_name}")
    typer.echo(f"Profile config  : {repo._get_config_file()}")
    typer.echo(f"Default config  : {Path.home() / '.config' / 'kopia' / 'repository.config'}")


def cmd_repo_set_default(ctx: typer.Context):
    """Point default Kopia config at current profile."""
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


def cmd_repo_init_path(
    ctx: typer.Context,
    path: Path,
    profile: Optional[str] = None,
    set_default: bool = False,
    password: Optional[str] = None,
):
    """Create a Kopia filesystem repository at PATH."""
    cfg = ensure_config(ctx)
    repo = KopiaRepository(cfg)

    env = repo._get_env()
    if password:
        env["KOPIA_PASSWORD"] = password

    cfg_file = repo._get_config_file() if not profile else str(
        Path.home() / ".config" / "kopia" / f"repository-{profile}.config"
    )
    Path(cfg_file).parent.mkdir(parents=True, exist_ok=True)

    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    # Create
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

    # Connect
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

    # Verify
    ps = subprocess.run(["kopia", "repository", "status", "--json", "--config-file", cfg_file], env=env, text=True, capture_output=True)
    if ps.returncode != 0:
        typer.echo("✗ status failed after connect:")
        typer.echo(ps.stderr.strip() or ps.stdout.strip())
        raise typer.Exit(code=1)

    typer.echo("✓ Repository created & connected")
    typer.echo(f"  Path    : {path}")
    typer.echo(f"  Profile : {profile or repo.profile_name}")
    typer.echo(f"  Config  : {cfg_file}")

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
            typer.echo("✓ Set as default Kopia config.")
        except Exception as e:
            typer.echo(f"⚠ could not set default: {e}")

    typer.echo("\nUse raw Kopia with this repo:")
    typer.echo(f"  kopia repository status --config-file {cfg_file}")


def cmd_repo_selftest(
    tmpdir: Path = Path("/tmp"),
    keep: bool = False,
    password: Optional[str] = None,
):
    """Create ephemeral test repository."""
    stamp = str(int(time.time()))
    test_profile = f"kopi-docka-selftest-{stamp}"
    repo_dir = Path(tmpdir) / f"kopia-selftest-{stamp}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    if not password:
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(24))

    conf_dir = Path.home() / ".config" / "kopi-docka"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_path = conf_dir / f"selftest-{stamp}.conf"

    conf_path.write_text(
        f"""{{
  "kopia": {{
    "kopia_params": "filesystem --path {repo_dir}",
    "password": "{password}",
    "profile": "{test_profile}"
  }},
  "retention": {{
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
    "yearly": 3
  }}
}}""",
        encoding="utf-8",
    )

    typer.echo(f"Selftest profile   : {test_profile}")
    typer.echo(f"Selftest repo path : {repo_dir}")
    typer.echo(f"Selftest config    : {conf_path}")

    cfg = Config(conf_path)
    test_repo = KopiaRepository(cfg)

    typer.echo("↻ Connecting/creating test repository…")
    try:
        test_repo.initialize()
    except Exception as e:
        typer.echo(f"✗ Could not initialize selftest repo: {e}")
        raise typer.Exit(code=1)

    if not test_repo.is_connected():
        typer.echo("✗ Not connected after initialize().")
        raise typer.Exit(code=1)

    _print_kopia_native_status(test_repo)

    workdir = repo_dir / "data"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "hello.txt").write_text("Hello Kopia!\n", encoding="utf-8")

    typer.echo("Creating snapshot of selftest data…")
    snap_id = test_repo.create_snapshot(str(workdir), tags={"type": "selftest"})
    typer.echo(f"Snapshot ID        : {snap_id}")

    snaps = test_repo.list_snapshots(tag_filter={"type": "selftest"})
    typer.echo(f"Selftest snapshots : {len(snaps)}")

    try:
        test_repo.maintenance_run(full=False)
    except Exception:
        pass

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
        typer.echo("(kept) Inspect manually")


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
# Registration
# -------------------------

def register(app: typer.Typer):
    """Register all repository commands."""
    
    # Simple commands without parameters
    app.command("init")(cmd_init)
    app.command("repo-status")(cmd_repo_status)
    app.command("repo-which-config")(cmd_repo_which_config)
    app.command("repo-set-default")(cmd_repo_set_default)
    app.command("repo-maintenance")(cmd_repo_maintenance)
    
    @app.command("repo-init-path")
    def _repo_init_path_cmd(
        ctx: typer.Context,
        path: Path = typer.Argument(..., help="Repository path"),
        profile: Optional[str] = typer.Option(None, "--profile", help="Profile name"),
        set_default: bool = typer.Option(False, "--set-default/--no-set-default"),
        password: Optional[str] = typer.Option(None, "--password"),
    ):
        """Create a Kopia filesystem repository at PATH."""
        cmd_repo_init_path(ctx, path, profile, set_default, password)
    
    @app.command("repo-selftest")
    def _repo_selftest_cmd(
        tmpdir: Path = typer.Option(Path("/tmp"), "--tmpdir"),
        keep: bool = typer.Option(False, "--keep/--no-keep"),
        password: Optional[str] = typer.Option(None, "--password"),
    ):
        """Create ephemeral test repository."""
        cmd_repo_selftest(tmpdir, keep, password)
