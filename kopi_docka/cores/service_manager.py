################################################################################
# KOPI-DOCKA
#
# @file:        service_manager.py
# @module:      kopi_docka.service_manager
# @description: Systemd-friendly daemon orchestrating scheduled cold backups.
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Integrates sd_notify when systemd features are available
# - LockFile prevents concurrent runs via fcntl-based PID locking
# - write_systemd_units emits service and timer files for deployment
################################################################################

"""
Kopi-Docka — service.py
========================
Systemd-freundlicher Daemon + Timer-Helper für Kopi-Docka.

Ziele (KISS):
- Sauberer Daemon mit sd_notify (READY/STATUS/STOPPING/WATCHDOG)
- Watchdog-Unterstützung (systemd WatchdogSec)
- Locking gegen Parallelstarts
- Signal-Handling (SIGTERM/SIGINT/SIGHUP)
- Optionale, einfache Zeitsteuerung (Intervalle) ODER Nutzung via systemd-Timer
- Einfache Helper zum Schreiben von Unit-Dateien

Hinweis:
- Für echte Produktions-Jobs empfiehlt sich der **systemd-Timer** (siehe README).
- Der Daemon kann alternativ intern in festen Intervallen Backups starten.
"""

import os
import sys
import time
import signal
import fcntl
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

from ..helpers.logging import get_logger
from ..helpers.ui_utils import (
    print_header,
    print_info,
    print_success,
    print_error,
    run_command,
)

LOGGER = get_logger("kopi_docka.service")

# -------- systemd detection --------
try:
    from systemd import daemon as systemd_daemon  # type: ignore

    HAS_SYSTEMD = True
except Exception:  # pragma: no cover - optional dep
    systemd_daemon = None  # type: ignore
    HAS_SYSTEMD = False


# -------- Locking --------
class LockFile:
    """Einfaches PID-Lock via fcntl. Default Pfad deckt sich mit RuntimeDirectory."""

    def __init__(self, path: str = "/run/kopi-docka/kopi-docka.lock"):
        self.path = path
        self.fd: Optional[int] = None

    def acquire(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another kopi-docka service instance is running.")
        os.ftruncate(self.fd, 0)
        os.write(self.fd, str(os.getpid()).encode())

    def release(self) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


# -------- systemd notify helpers --------
def _has_notify_socket() -> bool:
    return bool(os.getenv("NOTIFY_SOCKET"))


def sd_notify_ready(status: Optional[str] = None) -> None:
    if not (HAS_SYSTEMD and _has_notify_socket()):
        return
    try:
        msg = "READY=1"
        if status:
            msg += f"\nSTATUS={status}"
        systemd_daemon.notify(msg)  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass


def sd_notify_status(status: str) -> None:
    if not (HAS_SYSTEMD and _has_notify_socket()):
        return
    try:
        systemd_daemon.notify(f"STATUS={status}")  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass


def sd_notify_stopping(status: Optional[str] = None) -> None:
    if not (HAS_SYSTEMD and _has_notify_socket()):
        return
    try:
        msg = "STOPPING=1"
        if status:
            msg += f"\nSTATUS={status}"
        systemd_daemon.notify(msg)  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass


def sd_notify_watchdog() -> None:
    """Send WATCHDOG=1 wenn Watchdog konfiguriert ist."""
    if not (HAS_SYSTEMD and _has_notify_socket()):
        return
    try:
        systemd_daemon.notify("WATCHDOG=1")  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass


# -------- Config --------
@dataclass
class ServiceConfig:
    # Wie wird ein Backup gestartet, wenn der Daemon intern triggert:
    backup_cmd: str = "/usr/bin/env kopi-docka backup"

    # Optional: interne Taktung in Minuten (wenn kein systemd-Timer genutzt wird)
    interval_minutes: Optional[int] = None  # z.B. 1440 für täglich

    # Optional: Mindestabstand zwischen Läufen (Safety)
    min_interval: timedelta = timedelta(minutes=30)

    # Log-Level (nur Weitergabe an Projekt-Logger-Konfiguration, hier informativ)
    log_level: str = "INFO"


# -------- Service --------
class KopiDockaService:
    def __init__(self, cfg: ServiceConfig):
        self.cfg = cfg
        self.running = True
        self.lock = LockFile()
        self._last_run: Optional[datetime] = None

        # systemd Watchdog-Intervall berechnen (falls gesetzt)
        self._watchdog_usec = int(os.getenv("WATCHDOG_USEC", "0") or 0)
        self._watchdog_interval: Optional[float] = None
        if self._watchdog_usec and _has_notify_socket():
            # Heartbeat bei halber Watchdog-Timeout-Zeit
            self._watchdog_interval = max(1.0, (self._watchdog_usec / 1_000_000) / 2)

    # ----- signal handling -----
    def _sigterm(self, *_):
        LOGGER.info("Received SIGTERM -> stopping…")
        self.running = False

    def _sigint(self, *_):
        LOGGER.info("Received SIGINT -> stopping…")
        self.running = False

    def _sighup(self, *_):
        LOGGER.info("Received SIGHUP -> reload (noop)")

    # ----- core -----
    def start(self) -> int:
        # Signale installieren
        signal.signal(signal.SIGTERM, self._sigterm)
        signal.signal(signal.SIGINT, self._sigint)
        signal.signal(signal.SIGHUP, self._sighup)

        # Lock
        try:
            self.lock.acquire()
        except Exception as e:
            LOGGER.error(str(e))
            return 1

        try:
            sd_notify_ready("Waiting (idle)")
            return self._run_loop()
        finally:
            try:
                sd_notify_stopping("Stopping service")
            finally:
                self.lock.release()

    def _maybe_run_backup(self) -> None:
        now = datetime.now()
        if self._last_run is not None and (now - self._last_run) < self.cfg.min_interval:
            return

        LOGGER.info("Starting backup run…")
        sd_notify_status("Running backup")
        try:
            res = run_command(
                ["bash", "-c", self.cfg.backup_cmd],
                "Running backup command",
                check=False,
                show_output=False,
            )
            for line in (res.stdout or "").splitlines():
                LOGGER.info("BACKUP | %s", line)
            if res.returncode != 0:
                LOGGER.error("Backup finished with non-zero exit code: %s", res.returncode)
            else:
                LOGGER.info("Backup finished successfully")
        except Exception as e:  # robust gegen Unerwartetes
            LOGGER.exception("Backup execution failed: %s", e)
        finally:
            self._last_run = datetime.now()
            sd_notify_status(f"Last backup: {self._last_run:%Y-%m-%d %H:%M:%S}")

    def _run_loop(self) -> int:
        interval = self.cfg.interval_minutes
        if not interval:
            LOGGER.info(
                "No internal schedule configured (interval_minutes=None). "
                "Idling; prefer systemd timer to trigger backups."
            )
        else:
            LOGGER.info("Internal schedule active: every %d minutes", interval)

        next_watchdog = time.monotonic() + (self._watchdog_interval or 1e9)

        while self.running:
            # Watchdog-Heartbeat
            if self._watchdog_interval is not None and time.monotonic() >= next_watchdog:
                sd_notify_watchdog()
                next_watchdog = time.monotonic() + self._watchdog_interval

            # Interner Zeitplan
            if interval:
                if self._last_run is None or (datetime.now() - self._last_run) >= timedelta(
                    minutes=interval
                ):
                    self._maybe_run_backup()

            time.sleep(1.0)

        LOGGER.info("Service loop ended.")
        return 0


# -------- systemd unit helpers --------


def write_systemd_units(output_dir: Path = Path("/etc/systemd/system")) -> None:
    """Schreibt gehärtete Service- und Timer-Units aus Templates."""
    print_header("Writing systemd units", str(output_dir))

    # Determine template directory
    template_dir = Path(__file__).parent.parent / "templates" / "systemd"

    # Mapping of output files to template files
    templates_map = {
        "kopi-docka.service": "kopi-docka.service.template",
        "kopi-docka.timer": "kopi-docka.timer.template",
        "kopi-docka-backup.service": "kopi-docka-backup.service.template",
    }

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read and write each template
    for output_name, template_name in templates_map.items():
        template_path = template_dir / template_name

        if not template_path.exists():
            print_error(f"Template file not found: {template_path}")
            raise FileNotFoundError(
                f"Template file not found: {template_path}\n"
                f"Please ensure kopi-docka is properly installed with all template files."
            )

        # Read template content
        template_content = template_path.read_text()

        # Write to output directory
        output_path = output_dir / output_name
        output_path.write_text(template_content)
        LOGGER.info("Wrote %s", output_path)
        print_info(f"✓ {output_path}")

    LOGGER.info("All systemd units written to %s", output_dir)
    print_success(f"Systemd units written to {output_dir}")


# -------- Minimaler CLI-Entry für Standalone-Nutzung --------
def _parse_args(argv: List[str]) -> Tuple[str, ServiceConfig]:
    """Kleiner Argumentparser (für optionalen Direktaufruf).

    Subcommands:
      - daemon: persistenten Daemon starten (optional internes Intervall)
      - write-units: Beispiel-systemd-Units schreiben
    """
    import argparse

    p = argparse.ArgumentParser(prog="kopi-docka-service")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daemon", help="Run service daemon")
    d.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
        help="Run internal backup every N minutes (else idle; prefer systemd timer)",
    )
    d.add_argument(
        "--backup-cmd",
        default="/usr/bin/env kopi-docka backup",
        help="Command to start a backup run",
    )
    d.add_argument("--log-level", default="INFO", help="Log level (INFO/DEBUG/…)")

    wu = sub.add_parser("write-units", help="Write example systemd unit files")
    wu.add_argument("--output-dir", default="/etc/systemd/system")

    ns = p.parse_args(argv)
    if ns.cmd == "daemon":
        cfg = ServiceConfig(
            backup_cmd=ns.backup_cmd,
            interval_minutes=ns.interval_minutes,
            log_level=ns.log_level,
        )
        return ns.cmd, cfg
    else:
        cfg = ServiceConfig()
        setattr(cfg, "_output_dir", ns.output_dir)  # type: ignore[attr-defined]
        return ns.cmd, cfg


def main(argv: Optional[List[str]] = None) -> int:
    cmd, cfg = _parse_args(argv or sys.argv[1:])
    if cmd == "daemon":
        svc = KopiDockaService(cfg)
        return svc.start()
    elif cmd == "write-units":
        write_systemd_units(Path(getattr(cfg, "_output_dir", "/etc/systemd/system")))
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
