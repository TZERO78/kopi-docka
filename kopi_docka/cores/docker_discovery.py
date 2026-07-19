################################################################################
# KOPI-DOCKA
#
# @file:        docker_discovery.py
# @module:      kopi_docka.cores
# @description: Discovers Docker containers and volumes, grouping them into backup units
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - Collects docker metadata via CLI calls to inspect and compose labels
# - Uses DATABASE_IMAGES to mark containers that require DB handling
# - Yields BackupUnit objects consumed by backup and dry-run modules
################################################################################

"""
Docker discovery module for Kopi-Docka.

Dieses Modul entdeckt Docker-Container und -Volumes und gruppiert sie
zu logischen Backup-Units (Compose-Stapel oder Standalone-Container).
"""

from __future__ import annotations

import json
from typing import List, Dict, Optional, Any
from pathlib import Path

from ..helpers.logging import get_logger
from ..helpers.ui_utils import run_command, SubprocessError
from ..types import BackupUnit, ContainerInfo, VolumeInfo, BindMountInfo
from ..helpers.constants import (
    DOCKER_COMPOSE_PROJECT_LABEL,
    DOCKER_COMPOSE_CONFIG_LABEL,
    DATABASE_IMAGES,
)

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# In-container → host path resolution (Plan 0042)
#
# Stack managers such as Portainer deploy stacks via `docker compose`, so each
# container carries `com.docker.compose.project.config_files` pointing at a path
# *inside the manager container* (e.g. `/data/compose/6/docker-compose.yml`,
# where Portainer's `/data` is a named volume). That path does not exist on the
# host, so the compose file would be silently omitted from the unit recipe. We
# translate it back to its host location through the manager container's mounts,
# making each unit's backup self-contained (no need to restore the manager first).
# --------------------------------------------------------------------------- #


def build_mount_index(containers: List[ContainerInfo]) -> List[tuple[str, str]]:
    """Return ``(destination, host_source)`` pairs from all container mounts.

    Both ``bind`` and ``volume`` mounts are included — for a named volume
    ``docker inspect`` reports ``Source`` as the host path
    (``/var/lib/docker/volumes/<name>/_data``). Sorted longest-destination-first
    so the most specific mount wins during resolution.
    """
    index: List[tuple[str, str]] = []
    seen: set = set()
    for c in containers:
        for m in (c.inspect_data or {}).get("Mounts", []) or []:
            dest = (m.get("Destination") or "").rstrip("/")
            src = (m.get("Source") or "").rstrip("/")
            if not dest or not src:
                continue
            key = (dest, src)
            if key in seen:
                continue
            seen.add(key)
            index.append(key)
    index.sort(key=lambda pair: len(pair[0]), reverse=True)
    return index


def resolve_container_path_to_host(
    path: Path, mount_index: List[tuple[str, str]]
) -> Optional[Path]:
    """Translate an in-container ``path`` to its host location via a mount.

    Finds the longest mount destination that is a prefix of ``path`` and rebuilds
    the host path as ``source + (path - destination)``. Returns the host path only
    if it actually exists (the guard against a wrong prefix match); otherwise None.
    """
    p = str(path).rstrip("/")
    for dest, src in mount_index:  # already longest-first
        if p == dest or p.startswith(dest + "/"):
            remainder = p[len(dest):]
            host = Path(src + remainder)
            try:
                if host.exists():
                    return host
            except OSError:
                continue
    return None


class DockerDiscovery:
    """
    Entdeckt Docker-Container und -Volumes und gruppiert sie in BackupUnits.
    """

    def __init__(self, docker_socket: str = "/var/run/docker.sock"):
        """
        Args:
            docker_socket: Pfad zum Docker-Socket (wird aktuell nur validiert;
                           CLI nutzt Standard-Socket/DOCKER_HOST)
        """
        self.docker_socket = docker_socket
        self._validate_docker_access()

    # ---------------------------- helpers ----------------------------

    def _validate_docker_access(self):
        """Validiert die Erreichbarkeit des Docker-Daemons."""
        try:
            run_command(
                ["docker", "version"],
                "Checking Docker access",
                timeout=8,
                check=True,
            )
        except SubprocessError as e:
            logger.error(f"Failed to access Docker: {e}", extra={"operation": "discover"})
            raise RuntimeError(f"Docker daemon not accessible: {e.stderr}")
        except Exception as e:
            logger.error(f"Failed to access Docker: {e}", extra={"operation": "discover"})
            raise

    def _run_docker(self, args: List[str]) -> str:
        """Führt einen Docker-Befehl aus und liefert stdout zurück."""
        cmd = ["docker"] + args
        try:
            result = run_command(cmd, f"Running docker {args[0]}", timeout=30, check=True)
            return result.stdout
        except SubprocessError as e:
            logger.error(
                "Docker command failed",
                extra={
                    "operation": "discover",
                    "cmd": " ".join(cmd),
                    "stderr": e.stderr.strip() if e.stderr else "",
                },
            )
            raise

    # ---------------------------- public API ----------------------------

    def discover_backup_units(self) -> List[BackupUnit]:
        """
        Entdeckt Container & Volumes und gruppiert sie in BackupUnits.

        Returns:
            Liste der gefundenen BackupUnits
        """
        logger.info("Starting Docker discovery…", extra={"operation": "discover"})
        containers = self._discover_containers()
        volumes = self._discover_volumes()

        units = self._group_into_units(containers, volumes)
        self._resolve_compose_paths(units, containers)

        logger.info(
            f"Discovered {len(units)} backup units",
            extra={"operation": "discover", "units": len(units)},
        )
        for u in units:
            logger.debug(
                f"Unit {u.name}: {len(u.containers)} containers, {len(u.volumes)} volumes",
                extra={"operation": "discover", "unit_name": u.name},
            )
        return units

    # ---------------------------- discovery ----------------------------

    def _discover_containers(self) -> List[ContainerInfo]:
        """
        Entdeckt zu sichernde Container.

        Umfasst (Plan 0040 / #129):
        - alle **laufenden** Container (``docker ps -q``), und
        - **gestoppte** Container, die zu einem Compose-Projekt gehören
          (``docker ps -aq --filter label=<project>``).

        Gestoppte Standalone-Container (ohne Compose-Label) werden bewusst
        ausgelassen — sonst würde jeder tote Wegwerf-Container zum Backup-Ziel.
        Ein zum Stack gehörender, gerade gestoppter Container samt seiner
        Volumes/Binds darf hingegen nicht stillschweigend fehlen.
        """
        running = self._run_docker(["ps", "-q"])
        # Best effort: a failure of the compose-filter call must not abort the
        # whole run — fall back to the running-only set rather than raising.
        try:
            compose_all = self._run_docker(
                ["ps", "-aq", "--filter", f"label={DOCKER_COMPOSE_PROJECT_LABEL}"]
            )
        except Exception as e:
            logger.warning(
                f"Could not list stopped compose containers, backing up running only: {e}",
                extra={"operation": "discover"},
            )
            compose_all = ""

        ids: List[str] = []
        seen: set[str] = set()
        for out in (running, compose_all):
            for cid in out.strip().split("\n"):
                cid = cid.strip()
                if cid and cid not in seen:
                    seen.add(cid)
                    ids.append(cid)

        if not ids:
            logger.warning("No containers found to back up", extra={"operation": "discover"})
            return []

        containers: List[ContainerInfo] = []

        for cid in ids:
            try:
                inspect = self._run_docker(["inspect", cid])
                data = json.loads(inspect)[0]
                containers.append(self._parse_container_info(data))
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse docker inspect output for container {cid}: {e}",
                    extra={"operation": "discover", "container_id": cid},
                )
            except Exception as e:
                logger.error(
                    f"Failed to inspect container {cid}: {e}",
                    extra={"operation": "discover", "container_id": cid},
                )
        return containers

    def _parse_container_info(self, d: Dict[str, Any]) -> ContainerInfo:
        """Erstellt ein ContainerInfo aus docker inspect-JSON."""
        cid = d["Id"]
        name = d["Name"].lstrip("/")
        image = d["Config"]["Image"]
        status = d["State"]["Status"]
        labels = (d["Config"].get("Labels") or {}) or {}

        # Env (ohne Redaction; Redaction erfolgt bei Recipe-Backup)
        env_map: Dict[str, str] = {}
        for e in d["Config"].get("Env", []) or []:
            if "=" in e:
                k, v = e.split("=", 1)
                env_map[k] = v

        # Mounts: named volumes + persistente Bind-Mounts (Plan 0040 / #129).
        # Host-interne Binds (host root /, docker.sock, /proc, /sys, /dev, /etc und
        # weitere OS-Bäume) werden klassifiziert und übersprungen — nie als
        # gewöhnliche Dateien archiviert.
        vol_names: List[str] = []
        bind_mounts: List[BindMountInfo] = []
        for m in d.get("Mounts", []) or []:
            mtype = m.get("Type")
            if mtype == "volume" and m.get("Name"):
                vol_names.append(m["Name"])
            elif mtype == "bind" and m.get("Source"):
                bind = BindMountInfo(
                    source=m["Source"],
                    destination=m.get("Destination", ""),
                    read_only=(m.get("RW") is False),
                    container_ids=[cid],
                )
                if bind.is_host_internal:
                    logger.debug(
                        f"Skipping host-internal bind mount {bind.source} on {name}",
                        extra={"operation": "discover", "container": name},
                    )
                    continue
                bind_mounts.append(bind)

        # Compose-Dateien (Label kann mehrere Dateien enthalten, kommagetrennt)
        compose_files: List[Path] = []
        if DOCKER_COMPOSE_CONFIG_LABEL in labels:
            raw = labels.get(DOCKER_COMPOSE_CONFIG_LABEL) or ""
            for p in raw.split(","):
                p = p.strip()
                if p:
                    compose_files.append(Path(p).expanduser())

        # DB-Typ (nur informativ für Sortierung/Anzeige)
        db_type = self._detect_database_type(image)

        return ContainerInfo(
            id=cid,
            name=name,
            image=image,
            status=status,
            labels=labels,
            environment=env_map,
            volumes=vol_names,
            bind_mounts=bind_mounts,
            compose_files=compose_files,
            inspect_data=d,
            database_type=db_type,
        )

    def _detect_database_type(self, image: str) -> Optional[str]:
        img = (image or "").lower()
        for db_type, cfg in DATABASE_IMAGES.items():
            for pat in cfg.get("patterns", []):
                if pat in img:
                    return db_type
        return None

    def _discover_volumes(self) -> List[VolumeInfo]:
        """
        Entdeckt Docker-Volumes.
        Nutzt JSON pro Zeile: docker volume ls --format '{{json .}}'
        """
        out = self._run_docker(["volume", "ls", "--format", "{{json .}}"])
        if not out.strip():
            return []

        vols: List[VolumeInfo] = []
        for line in out.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                vname = entry.get("Name")
                if not vname:
                    continue

                vinsp = self._run_docker(["volume", "inspect", vname])
                vdata = json.loads(vinsp)[0]

                v = VolumeInfo(
                    name=vdata["Name"],
                    driver=vdata["Driver"],
                    mountpoint=vdata["Mountpoint"],
                    labels=(vdata.get("Labels") or {}) or {},
                )
                # Größe (optional, best effort)
                v.size_bytes = self._estimate_volume_size(v.mountpoint)
                vols.append(v)
            except Exception as e:
                logger.error(
                    f"Failed to inspect volume: {e}",
                    extra={"operation": "discover", "volume_line": line[:120]},
                )
        return vols

    def _estimate_volume_size(self, mountpoint: str) -> Optional[int]:
        """Schätzt die Größe via 'du -sb' (best effort)."""
        try:
            result = run_command(
                ["du", "-sb", mountpoint],
                "Estimating volume size",
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                parts = result.stdout.split("\t", 1)
                if parts and parts[0].strip():
                    return int(parts[0])
        except Exception as e:
            logger.debug(f"Could not estimate volume size: {e}", extra={"operation": "discover"})
        return None

    # ---------------------------- grouping ----------------------------

    def _group_into_units(
        self, containers: List[ContainerInfo], volumes: List[VolumeInfo]
    ) -> List[BackupUnit]:
        """
        Gruppiert Container & Volumes in Units (Compose-Stacks zuerst).
        """
        units: List[BackupUnit] = []
        processed: set[str] = set()
        vmap: Dict[str, VolumeInfo] = {v.name: v for v in volumes}

        # Compose-Stacks gruppieren
        stacks: Dict[str, List[ContainerInfo]] = {}
        for c in containers:
            stack = c.labels.get(DOCKER_COMPOSE_PROJECT_LABEL) or ""
            stack = stack.strip()
            if stack:
                stacks.setdefault(stack, []).append(c)
                processed.add(c.id)

        # Units für Stacks
        for stack_name, c_list in stacks.items():
            unit = BackupUnit(name=stack_name, type="stack", containers=c_list)

            # Compose-Dateien aus erstem Container mit Pfaden übernehmen
            for c in c_list:
                if c.compose_files:
                    unit.compose_files = c.compose_files
                    break

            # Volumes über alle Container aggregieren
            used = set()
            for c in c_list:
                used.update(c.volumes)
            unit.volumes = [vmap[n] for n in used if n in vmap]

            # Reverse-Mapping: volume.container_ids
            for v in unit.volumes:
                for c in c_list:
                    if v.name in c.volumes:
                        v.container_ids.append(c.id)

            # Persistente Bind-Mounts über alle Container aggregieren
            unit.bind_mounts = self._aggregate_bind_mounts(c_list)

            units.append(unit)

        # Units für Standalone-Container
        for c in containers:
            if c.id in processed:
                continue
            unit = BackupUnit(name=c.name, type="standalone", containers=[c])
            unit.volumes = [vmap[n] for n in c.volumes if n in vmap]
            for v in unit.volumes:
                v.container_ids.append(c.id)
            unit.bind_mounts = self._aggregate_bind_mounts([c])
            units.append(unit)

        # Sortierung: DB-lastige Einheiten zuerst, dann Name
        units.sort(key=lambda u: (0 if u.has_databases else 1, u.name.lower()))
        return units

    def _resolve_compose_paths(
        self, units: List[BackupUnit], containers: List[ContainerInfo]
    ) -> None:
        """Rewrite in-container compose paths to their host location (Plan 0042).

        A compose file whose labeled path does not exist on the host (Portainer &
        co. store it inside the manager's volume) is translated through the
        manager container's mounts, so the file is captured into this unit's own
        recipe instead of being stranded inside another container's volume.
        """
        mount_index = build_mount_index(containers)
        if not mount_index:
            return
        for unit in units:
            if not unit.compose_files:
                continue
            resolved: List[Path] = []
            for cf in unit.compose_files:
                if cf.exists():
                    resolved.append(cf)
                    continue
                host = resolve_container_path_to_host(cf, mount_index)
                if host is not None:
                    logger.info(
                        f"Resolved in-container compose path {cf} → {host}",
                        extra={"operation": "discover", "unit_name": unit.name},
                    )
                    resolved.append(host)
                else:
                    resolved.append(cf)  # unresolved → stays, reported as a gap
            unit.compose_files = resolved

    def _aggregate_bind_mounts(self, containers: List[ContainerInfo]) -> List[BindMountInfo]:
        """Dedupliziert persistente Bind-Mounts über eine Container-Liste.

        Mehrere Container eines Stacks können denselben Host-Pfad einbinden;
        er wird nur einmal als Backup-Ziel geführt, die betroffenen
        container_ids werden zusammengeführt. Größe best effort via ``du``.
        Read-only gilt nur, wenn *alle* Einbindungen read-only sind.
        """
        by_source: Dict[str, BindMountInfo] = {}
        for c in containers:
            for b in c.bind_mounts:
                existing = by_source.get(b.source)
                if existing is None:
                    merged = BindMountInfo(
                        source=b.source,
                        destination=b.destination,
                        read_only=b.read_only,
                        container_ids=[c.id],
                    )
                    by_source[b.source] = merged
                else:
                    if c.id not in existing.container_ids:
                        existing.container_ids.append(c.id)
                    existing.read_only = existing.read_only and b.read_only

        binds = list(by_source.values())
        for b in binds:
            b.size_bytes = self._estimate_volume_size(b.source)
        return binds
