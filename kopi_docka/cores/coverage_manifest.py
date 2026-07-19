################################################################################
# KOPI-DOCKA
#
# @file:        coverage_manifest.py
# @module:      kopi_docka.cores
# @description: Builds a per-unit backup coverage manifest (Plan 0040 Phase 2 / #129).
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025-2026 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - The manifest is a receipt: for every dependency discovered on a backup unit
#   it records whether it was backed up, deliberately skipped (runtime), left
#   unprotected, or is unsupported. This makes gaps EXPLICIT instead of silent —
#   the core intent of issue #129. It does NOT gate the backup (no fail-closed);
#   completeness (incl. secrets) is the design choice, transparency is the goal.
# - Pure analyzer: build_manifest(unit) derives everything from the unit plus
#   filesystem checks, so both the backup path and dry-run can use it.
################################################################################
"""Backup coverage manifest builder for Kopi-Docka."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

from ..helpers.logging import get_logger
from ..types import BackupUnit, BindMountInfo

logger = get_logger(__name__)

# Coverage statuses
STATUS_BACKED_UP = "backed_up"            # captured by this backup
STATUS_SKIPPED_RUNTIME = "skipped_runtime"  # runtime-only host internal, not data
STATUS_NOT_PROTECTED = "not_protected"    # persistent dependency NOT captured
STATUS_NOT_SUPPORTED = "not_supported"    # discovered but Kopi-Docka can't handle it

# Config-file globs the recipe collector captures next to each compose file.
_CONFIG_PATTERNS = (".env*", "*.conf", "*.config", "*.toml")


@dataclass
class CoverageEntry:
    kind: str          # volume | bind | runtime_mount | compose_file | env_file | project_file | swarm_secret | swarm_config
    identifier: str    # host path or name
    status: str
    detail: str = ""


@dataclass
class CoverageManifest:
    unit: str
    entries: List[CoverageEntry] = field(default_factory=list)

    def add(self, kind: str, identifier: str, status: str, detail: str = "") -> None:
        self.entries.append(CoverageEntry(kind=kind, identifier=identifier, status=status, detail=detail))

    @property
    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {
            "total": len(self.entries),
            STATUS_BACKED_UP: 0,
            STATUS_SKIPPED_RUNTIME: 0,
            STATUS_NOT_PROTECTED: 0,
            STATUS_NOT_SUPPORTED: 0,
        }
        for e in self.entries:
            counts[e.status] = counts.get(e.status, 0) + 1
        return counts

    @property
    def has_gaps(self) -> bool:
        """True if any persistent dependency is unprotected or unsupported."""
        return any(e.status in (STATUS_NOT_PROTECTED, STATUS_NOT_SUPPORTED) for e in self.entries)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.unit,
            "summary": self.summary,
            "has_gaps": self.has_gaps,
            "dependencies": [asdict(e) for e in self.entries],
        }


def build_manifest(unit: BackupUnit) -> CoverageManifest:
    """Analyze a backup unit and return its coverage manifest.

    Pure w.r.t. the unit + filesystem: safe to call in dry-run (nothing is
    written or mutated).
    """
    m = CoverageManifest(unit=unit.name)

    _classify_mounts(unit, m)
    _classify_compose_and_config(unit, m)
    _classify_compose_declared(unit, m)

    return m


# --------------------------------------------------------------------------- #
# Mounts (authoritative — straight from docker inspect)
# --------------------------------------------------------------------------- #


def _classify_mounts(unit: BackupUnit, m: CoverageManifest) -> None:
    """Walk every container's inspect Mounts and classify each one.

    Uses the raw inspect data (not just the filtered discovery lists) so runtime
    mounts that were deliberately skipped still show up in the manifest.
    """
    backed_up_volumes = {v.name for v in unit.volumes}
    seen: set = set()

    for c in unit.containers:
        mounts = (c.inspect_data or {}).get("Mounts", []) or []
        for mount in mounts:
            mtype = mount.get("Type")

            if mtype == "volume":
                name = mount.get("Name")
                if not name or ("volume", name) in seen:
                    continue
                seen.add(("volume", name))
                if name in backed_up_volumes:
                    m.add("volume", name, STATUS_BACKED_UP)
                else:
                    m.add("volume", name, STATUS_NOT_PROTECTED, "named volume not in backup set")

            elif mtype == "bind":
                source = mount.get("Source")
                if not source or ("bind", source) in seen:
                    continue
                seen.add(("bind", source))
                if BindMountInfo(source=source, destination=mount.get("Destination", "")).is_host_internal:
                    m.add("runtime_mount", source, STATUS_SKIPPED_RUNTIME, "host internal (OS path / socket / pseudo-fs)")
                else:
                    m.add("bind", source, STATUS_BACKED_UP,
                          f"→ {mount.get('Destination', '')}" + (" (ro)" if mount.get("RW") is False else ""))

            elif mtype == "tmpfs":
                dest = mount.get("Destination", "")
                if ("tmpfs", dest) in seen:
                    continue
                seen.add(("tmpfs", dest))
                m.add("runtime_mount", dest, STATUS_SKIPPED_RUNTIME, "tmpfs (ephemeral, not data)")


# --------------------------------------------------------------------------- #
# Compose files + adjacent config actually captured by the recipe collector
# --------------------------------------------------------------------------- #


def _classify_compose_and_config(unit: BackupUnit, m: CoverageManifest) -> None:
    compose_dirs: set = set()
    for cf in unit.compose_files:
        if cf.exists():
            m.add("compose_file", str(cf), STATUS_BACKED_UP)
            compose_dirs.add(cf.parent)
        else:
            m.add("compose_file", str(cf), STATUS_NOT_PROTECTED, "referenced compose file not found on host")

    # Adjacent config files the recipe collector globs (.env*, *.conf, ...).
    for d in compose_dirs:
        for pattern in _CONFIG_PATTERNS:
            for f in sorted(d.glob(pattern)):
                if f.is_file() and str(f) not in {e.identifier for e in m.entries}:
                    m.add("project_file", str(f), STATUS_BACKED_UP, f"config next to compose ({pattern})")


# --------------------------------------------------------------------------- #
# Compose-declared dependencies (env_file, secrets, configs) — surfaces gaps
# --------------------------------------------------------------------------- #


def _classify_compose_declared(unit: BackupUnit, m: CoverageManifest) -> None:
    """Parse compose files for env_file / secrets / configs and flag anything
    that lives outside the captured compose dir or that we can't protect.

    Best-effort: a compose file we cannot parse is recorded as not_supported
    rather than raising.
    """
    try:
        import yaml
    except Exception:  # pragma: no cover - yaml is a declared dependency
        return

    captured = {e.identifier for e in m.entries if e.status == STATUS_BACKED_UP}
    compose_dirs = {cf.parent for cf in unit.compose_files if cf.exists()}

    for cf in unit.compose_files:
        if not cf.exists():
            continue
        try:
            data = yaml.safe_load(cf.read_text()) or {}
        except Exception as e:
            m.add("compose_file", str(cf), STATUS_NOT_SUPPORTED, f"could not parse compose: {e}")
            continue
        if not isinstance(data, dict):
            continue

        _scan_env_files(data, cf.parent, compose_dirs, captured, m)
        _scan_secrets_configs(data, "secrets", cf.parent, captured, m)
        _scan_secrets_configs(data, "configs", cf.parent, captured, m)


def _scan_env_files(data: dict, compose_dir: Path, compose_dirs: set, captured: set, m: CoverageManifest) -> None:
    services = data.get("services") or {}
    if not isinstance(services, dict):
        return
    seen: set = set()
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        ef = svc.get("env_file")
        if ef is None:
            continue
        items = ef if isinstance(ef, list) else [ef]
        for item in items:
            path_str = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path_str, str):
                continue
            resolved = (compose_dir / path_str).resolve()
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)

            if key in captured:
                continue  # already captured as a project_file
            if not resolved.exists():
                m.add("env_file", key, STATUS_NOT_PROTECTED, "declared env_file not found on host")
            elif resolved.parent not in compose_dirs:
                m.add("env_file", key, STATUS_NOT_PROTECTED, "env_file lives outside the compose directory")
            else:
                # inside a compose dir but not matched by the config globs
                m.add("env_file", key, STATUS_BACKED_UP, "env_file inside compose directory")


def _scan_secrets_configs(data: dict, section: str, compose_dir: Path, captured: set, m: CoverageManifest) -> None:
    block = data.get(section) or {}
    if not isinstance(block, dict):
        return
    kind = "swarm_secret" if section == "secrets" else "swarm_config"
    for name, spec in block.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("external"):
            m.add(kind, str(name), STATUS_NOT_SUPPORTED, f"external {section[:-1]} (managed by Docker/Swarm)")
            continue
        file_ref = spec.get("file")
        if not isinstance(file_ref, str):
            continue
        resolved = (compose_dir / file_ref).resolve()
        if str(resolved) in captured:
            continue
        if not resolved.exists():
            m.add(kind, str(resolved), STATUS_NOT_PROTECTED, f"{section[:-1]} file not found on host")
        else:
            m.add(kind, str(resolved), STATUS_NOT_PROTECTED, f"{section[:-1]} file not captured by backup")


def render_summary(m: CoverageManifest) -> List[str]:
    """Operator-readable lines summarizing coverage (for dry-run / logs)."""
    s = m.summary
    lines = [
        f"Coverage: {s[STATUS_BACKED_UP]} backed up, "
        f"{s[STATUS_SKIPPED_RUNTIME]} runtime-skipped, "
        f"{s[STATUS_NOT_PROTECTED]} unprotected, "
        f"{s[STATUS_NOT_SUPPORTED]} unsupported",
    ]
    for e in m.entries:
        if e.status in (STATUS_NOT_PROTECTED, STATUS_NOT_SUPPORTED):
            lines.append(f"  ⚠ {e.status}: {e.kind} {e.identifier} — {e.detail}")
    return lines
