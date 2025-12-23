# Feature-Plan: Advanced Restore mit Machine-Selection

[← Back to README](../README.md)

## Executive Summary

**Problem:** User können nur Backups von der aktuellen Maschine restoren. Bei Hardware-Crash oder Multi-Server-Setup ist Cross-Machine-Restore nicht möglich.

**Use-Case:** Server "homeserver1" crasht. User will auf neuer Hardware "homeserver-new" die Backups von "homeserver1" restoren.

**Lösung:** Neuer `--advanced` Modus für `restore`, der alle Maschinen im Repository anzeigt und Cross-Machine-Restore ermöglicht.

**Geschätzter Aufwand:** 2-3 Wochen für vollständige Implementation

---

## 1. Datenmodell-Analyse

### 1.1 Kopia Snapshot-Struktur

Kopia Snapshots enthalten Metadata, die die Quelle identifizieren:

```json
{
  "id": "k1234567890abcdef",
  "source": {
    "host": "homeserver1",              // ← Hostname
    "userName": "root",                 // ← User
    "path": "/var/lib/docker/volumes/..." // ← Pfad
  },
  "startTime": "2025-01-20T02:00:00Z",
  "tags": {
    "type": "volume",
    "unit": "wordpress",
    "backup_id": "uuid-123",
    "timestamp": "2025-01-20T02:00:00Z"
  }
}
```

**Wichtig:** Der `source.host` Wert wird von Kopia automatisch gesetzt und entspricht dem Hostname der Maschine, die das Backup erstellt hat.

### 1.2 Aktuelle Problematik

```python
# restore_manager.py - _find_restore_points()
def _find_restore_points(self) -> List[RestorePoint]:
    snaps = self.repo.list_snapshots()  # ← Listet alle Snapshots
    # ...
    # PROBLEM: Kein Filter nach Hostname!
```

**Kopia CLI Verhalten:**
- `kopia snapshot list` zeigt standardmäßig nur Snapshots der aktuellen Maschine
- `kopia snapshot list --all` zeigt alle Snapshots aller Maschinen

**Aktueller Code:**
```python
# repository_manager.py:431-469
def list_snapshots(self, tag_filter: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    proc = self._run(["kopia", "snapshot", "list", "--json"], check=True)
    # ↑ PROBLEM: Kein --all Flag!
```

### 1.3 Benötigte Metadaten

| Feld | Quelle | Beschreibung |
|------|--------|--------------|
| `host` | `source.host` | Hostname der Backup-Maschine |
| `userName` | `source.userName` | User, der Backup erstellt hat |
| `lastBackup` | Aggregiert | Timestamp des neuesten Backups |
| `backupCount` | Aggregiert | Anzahl der Snapshots |
| `unitNames` | Aggregiert | Liste der Backup-Units |

### 1.4 Erweiterte Tag-Strategie

Aktuell werden bereits nützliche Tags gesetzt:

```python
tags = {
    "type": "volume",       # recipe, volume, networks
    "unit": "wordpress",    # Unit-Name
    "backup_id": "uuid",    # Gruppierung
    "timestamp": "iso8601", # Zeitstempel
}
```

**Optional: Expliziter Hostname-Tag (Future-Proofing)**

```python
tags = {
    ...
    "hostname": socket.gethostname(),  # NEU: Expliziter Hostname
}
```

**Vorteil:** Unabhängig von Kopia-internem `source.host`.
**Nachteil:** Redundant, da Kopia bereits `source.host` liefert.

**Entscheidung:** Kopia's `source.host` nutzen, kein zusätzlicher Tag.

---

## 2. Discovery-Mechanismus

### 2.1 Repository-Scan-Strategie

```python
# Neue Klasse/Methode in repository_manager.py
def list_all_snapshots(self) -> List[Dict[str, Any]]:
    """List ALL snapshots from ALL machines in repository."""
    proc = self._run(["kopia", "snapshot", "list", "--all", "--json"], check=True)
    # ...
```

### 2.2 Machine-Aggregation

```python
@dataclass
class MachineInfo:
    """Information about a backup source machine."""
    hostname: str
    last_backup: datetime
    backup_count: int
    units: List[str]
    total_size: int

def discover_machines(self) -> List[MachineInfo]:
    """Discover all machines that have backups in repository."""
    all_snapshots = self.list_all_snapshots()

    machines: Dict[str, MachineInfo] = {}

    for snap in all_snapshots:
        source = snap.get("source", {})
        host = source.get("host", "unknown")

        if host not in machines:
            machines[host] = MachineInfo(
                hostname=host,
                last_backup=datetime.min,
                backup_count=0,
                units=[],
                total_size=0
            )

        m = machines[host]
        m.backup_count += 1

        # Timestamp parsen
        ts_str = snap.get("startTime") or snap.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts > m.last_backup:
                    m.last_backup = ts
            except ValueError:
                pass

        # Unit extrahieren
        tags = snap.get("tags", {})
        unit = tags.get("unit")
        if unit and unit not in m.units:
            m.units.append(unit)

        # Size aggregieren
        stats = snap.get("stats", {})
        m.total_size += stats.get("totalSize", 0)

    return sorted(machines.values(), key=lambda m: m.last_backup, reverse=True)
```

### 2.3 Performance bei 1000+ Snapshots

**Problem:** Repository mit vielen Snapshots kann langsam werden.

**Optimierungen:**

1. **Lazy Loading:** Erst Maschinen-Liste, dann Details on-demand
2. **Caching:** Maschinen-Info für Session cachen
3. **Streaming:** Kopia Output streamen statt komplett laden

```python
# Caching-Strategie
class MachineCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Optional[List[MachineInfo]] = None
        self._timestamp: Optional[datetime] = None
        self._ttl = timedelta(seconds=ttl_seconds)

    def get_machines(self, repo: KopiaRepository) -> List[MachineInfo]:
        if self._is_valid():
            return self._cache

        self._cache = repo.discover_machines()
        self._timestamp = datetime.now()
        return self._cache

    def _is_valid(self) -> bool:
        if not self._cache or not self._timestamp:
            return False
        return datetime.now() - self._timestamp < self._ttl
```

### 2.4 Hostname-Extraktion

```python
def _extract_hostname(self, snapshot: Dict[str, Any]) -> str:
    """Extract hostname from snapshot metadata."""
    # Primär: source.host (Kopia Standard)
    source = snapshot.get("source", {})
    if "host" in source:
        return source["host"]

    # Fallback: Expliziter Tag (falls in Zukunft gesetzt)
    tags = snapshot.get("tags", {})
    if "hostname" in tags:
        return tags["hostname"]

    # Letzter Fallback
    return "unknown"
```

---

## 3. UI/UX-Design

### 3.1 CLI-Interface

**Neuer Parameter:**

```bash
# Standard-Restore (aktuelle Maschine)
sudo kopi-docka restore

# Advanced Restore (Cross-Machine)
sudo kopi-docka restore --advanced
```

### 3.2 Wizard-Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    ADVANCED RESTORE WIZARD                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Select Source Machine                               │
│  ─────────────────────────────                               │
│  📋 Machines with backups in repository:                     │
│                                                              │
│  1. 🖥️  homeserver1                                          │
│        Last backup: 2025-01-20 02:00:00                      │
│        Units: wordpress, nextcloud, gitlab (3 total)         │
│        Snapshots: 156                                        │
│                                                              │
│  2. 🖥️  homeserver2                                          │
│        Last backup: 2025-01-23 02:00:00                      │
│        Units: traefik, monitoring (2 total)                  │
│        Snapshots: 89                                         │
│                                                              │
│  3. 💻 laptop                                                │
│        Last backup: 2025-01-22 14:30:00                      │
│        Units: dev-stack (1 total)                            │
│        Snapshots: 42                                         │
│                                                              │
│  🎯 Select machine (number, or 'q' to quit): _              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Nach Maschinen-Auswahl:

```
┌──────────────────────────────────────────────────────────────┐
│  Step 2: Select Backup Session                               │
│  ─────────────────────────────                               │
│  Source: homeserver1                                         │
│                                                              │
│  📅 Available backup sessions:                               │
│                                                              │
│  1. 📅 2025-01-20 02:00:00                                  │
│     Units: wordpress, nextcloud, gitlab                      │
│     Total volumes: 8                                         │
│                                                              │
│  2. 📅 2025-01-19 02:00:00                                  │
│     Units: wordpress, nextcloud, gitlab                      │
│     Total volumes: 8                                         │
│                                                              │
│  ... (weitere Sessions)                                      │
│                                                              │
│  🎯 Select session (number, or 'b' for back, 'q' to quit): _│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Cross-Machine-Warnings

```
┌──────────────────────────────────────────────────────────────┐
│  ⚠️  CROSS-MACHINE RESTORE WARNING                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  You are about to restore from a DIFFERENT machine:         │
│                                                              │
│  Source:      homeserver1                                    │
│  Target:      homeserver-new (current)                       │
│                                                              │
│  ⚠️  Potential Issues:                                       │
│  • Container names may conflict with existing containers     │
│  • Network names may conflict with existing networks         │
│  • Volume names may conflict with existing volumes           │
│  • Paths in configs may need adjustment                      │
│                                                              │
│  💡 Recommendations:                                         │
│  • Review docker-compose.yml after restore                   │
│  • Check for port conflicts                                  │
│  • Verify network configuration                              │
│                                                              │
│  ⚠️  Proceed with cross-machine restore? (yes/no): _        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.4 Status-Indikatoren

| Symbol | Bedeutung |
|--------|-----------|
| 🖥️ | Server/Desktop |
| 💻 | Laptop |
| ☁️ | Cloud/VPS |
| ✅ | Online/Erreichbar |
| ❌ | Offline/Unerreichbar |
| ⭐ | Aktuelle Maschine |

### 3.5 Konflikt-Handling

```python
class ConflictResolution(Enum):
    SKIP = "skip"           # Überspringe konfligierende Ressource
    RENAME = "rename"       # Füge Suffix hinzu (z.B. wordpress_restored)
    OVERWRITE = "overwrite" # Überschreibe bestehende Ressource
    ASK = "ask"             # Frage für jede Ressource einzeln

# UI für Konflikte
"""
⚠️  Container 'wordpress_web_1' already exists!

Options:
  1. Skip this container
  2. Rename to 'wordpress_web_1_restored'
  3. Stop and remove existing, then restore
  4. Ask for each conflict

Your choice (1-4): _
"""
```

---

## 4. Implementierungs-Roadmap

### Phase 1: Foundation (Week 1)

**Ziel:** Machine-Discovery-Infrastruktur

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 1.1 | `repository_manager.py` | `list_all_snapshots()` mit `--all` Flag |
| 1.2 | `repository_manager.py` | `discover_machines()` Methode |
| 1.3 | `types.py` | Neuer Dataclass `MachineInfo` |
| 1.4 | Unit-Tests | Tests für Machine-Discovery |

**Commit 1:** "feat: Add machine discovery for cross-machine restore"

### Phase 2: CLI & UI (Week 1-2)

**Ziel:** `--advanced` Parameter und Wizard-UI

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 2.1 | `backup_commands.py` | `--advanced` Parameter für `restore` |
| 2.2 | `restore_manager.py` | `advanced_interactive_restore()` Methode |
| 2.3 | `restore_manager.py` | Machine-Selection-UI |
| 2.4 | `helpers/ui_utils.py` | Neue UI-Komponenten für Machine-List |
| 2.5 | Unit-Tests | Tests für UI-Flow |

**Commit 2:** "feat: Add --advanced flag for cross-machine restore wizard"

### Phase 3: Cross-Restore-Logic (Week 2)

**Ziel:** Restore von anderer Maschine ermöglichen

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 3.1 | `restore_manager.py` | `_find_restore_points_for_machine()` |
| 3.2 | `restore_manager.py` | Cross-Machine-Warnings |
| 3.3 | `restore_manager.py` | Konflikt-Detection |
| 3.4 | Unit-Tests | Tests für Cross-Restore |

**Commit 3:** "feat: Implement cross-machine restore with conflict detection"

### Phase 4: Backward-Compatibility (Week 2-3)

**Ziel:** Alte Backups ohne Hostname-Info behandeln

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 4.1 | `repository_manager.py` | Fallback für fehlende Hostname-Info |
| 4.2 | `restore_manager.py` | "Unknown" Machine-Handling |
| 4.3 | `backup_manager.py` | Optional: Expliziter Hostname-Tag |
| 4.4 | Integration-Tests | Tests mit Legacy-Backups |

**Commit 4:** "feat: Handle legacy backups without hostname metadata"

### Phase 5: Advanced Features (Optional, Week 3)

**Ziel:** Erweiterte Funktionen

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 5.1 | `types.py` | `MachineAlias` Dataclass |
| 5.2 | `config.py` | Machine-Alias-Konfiguration |
| 5.3 | `restore_manager.py` | Path-Mapping bei Cross-Restore |
| 5.4 | `restore_manager.py` | Conflict-Resolution-Modes |

**Commit 5:** "feat: Add machine aliases and path mapping for advanced restore"

---

## 5. Betroffene Dateien

### Neue Dateien

| Datei | Beschreibung |
|-------|--------------|
| `tests/unit/test_cores/test_machine_discovery.py` | Unit-Tests für Machine-Discovery |
| `tests/integration/test_cross_machine_restore.py` | Integration-Tests |

### Modifizierte Dateien

| Datei | Änderungen |
|-------|------------|
| `kopi_docka/types.py` | Neuer Dataclass `MachineInfo` |
| `kopi_docka/cores/repository_manager.py` | `list_all_snapshots()`, `discover_machines()` |
| `kopi_docka/cores/restore_manager.py` | Advanced-Restore-Logic |
| `kopi_docka/commands/backup_commands.py` | `--advanced` Parameter |
| `kopi_docka/helpers/ui_utils.py` | Machine-List-UI |
| `docs/FEATURES.md` | Dokumentation |

---

## 6. Backward-Compatibility

### 6.1 Alte Backups ohne Hostname

**Problem:** Backups vor v5.x haben möglicherweise keinen `source.host` im Kopia-Output.

**Lösung:**
```python
def _extract_hostname(self, snapshot: Dict[str, Any]) -> str:
    source = snapshot.get("source", {})

    # Kopia liefert immer source.host (außer bei sehr alten Versionen)
    if "host" in source:
        return source["host"]

    # Fallback: Pfad-basierte Heuristik
    path = source.get("path", "")
    if path.startswith("/var/lib/docker"):
        return "unknown (local)"

    return "unknown"
```

### 6.2 Standard-Restore bleibt unverändert

```bash
# Weiterhin nur aktuelle Maschine
sudo kopi-docka restore

# Explizit für Cross-Machine
sudo kopi-docka restore --advanced
```

### 6.3 Versionskompatibilität

| Kopi-Docka | Restore --advanced | Legacy Backups |
|------------|-------------------|----------------|
| < 5.0 | ❌ N/A | ✅ |
| ≥ 5.0 | ✅ | ✅ (als "unknown") |

---

## 7. Advanced-Features (Optional)

### 7.1 Machine-Aliase

**Problem:** Hostname geändert, aber Backups unter altem Namen.

**Config:**
```json
{
  "restore": {
    "machine_aliases": {
      "homeserver1": ["old-server", "nas-2020"],
      "homeserver-new": ["homeserver1"]  // Erbt Backups
    }
  }
}
```

**Implementation:**
```python
def resolve_machine_alias(self, hostname: str) -> str:
    """Resolve machine aliases from config."""
    aliases = self.config.get("restore", "machine_aliases", {})

    for canonical, alias_list in aliases.items():
        if hostname in alias_list:
            return canonical

    return hostname
```

### 7.2 Path-Mapping

**Problem:** Volume-Pfade sind auf neuer Maschine anders.

**Config:**
```json
{
  "restore": {
    "path_mappings": {
      "/var/lib/docker/volumes": "/mnt/data/docker/volumes",
      "/opt/stacks": "/home/user/stacks"
    }
  }
}
```

### 7.3 Conflict-Resolution-Modes

```bash
# Alle Konflikte automatisch skippen
sudo kopi-docka restore --advanced --conflict-mode=skip

# Alle Konflikte umbenennen
sudo kopi-docka restore --advanced --conflict-mode=rename

# Alle Konflikte überschreiben (gefährlich!)
sudo kopi-docka restore --advanced --conflict-mode=overwrite
```

---

## 8. Testing-Strategie

### 8.1 Unit-Tests

```python
class TestMachineDiscovery:
    """Tests for machine discovery functionality."""

    def test_discover_machines_returns_all_hosts(self):
        """discover_machines() returns all unique hosts."""

    def test_discover_machines_aggregates_correctly(self):
        """Machine info is correctly aggregated from snapshots."""

    def test_discover_machines_handles_empty_repo(self):
        """Empty repository returns empty list."""

    def test_discover_machines_sorts_by_last_backup(self):
        """Machines are sorted by most recent backup."""


class TestAdvancedRestore:
    """Tests for advanced restore functionality."""

    def test_advanced_flag_triggers_machine_selection(self):
        """--advanced shows machine selection UI."""

    def test_cross_machine_restore_shows_warning(self):
        """Restoring from different machine shows warning."""

    def test_conflict_detection_finds_existing_resources(self):
        """Conflicting containers/volumes/networks are detected."""
```

### 8.2 Integration-Tests

```python
@pytest.mark.integration
class TestCrossMachineRestore:
    """End-to-end tests for cross-machine restore."""

    def test_restore_from_different_machine(self, multi_machine_repo):
        """Complete restore from different machine works."""

    def test_conflict_handling_skip(self):
        """Conflict mode 'skip' skips conflicting resources."""

    def test_conflict_handling_rename(self):
        """Conflict mode 'rename' renames conflicting resources."""
```

### 8.3 Mock-Setup

```python
@pytest.fixture
def multi_machine_snapshots():
    """Snapshots from multiple machines."""
    return [
        {
            "id": "snap1",
            "source": {"host": "server1", "path": "/..."},
            "tags": {"unit": "wordpress", "type": "volume"},
            "startTime": "2025-01-20T02:00:00Z"
        },
        {
            "id": "snap2",
            "source": {"host": "server2", "path": "/..."},
            "tags": {"unit": "nextcloud", "type": "volume"},
            "startTime": "2025-01-21T02:00:00Z"
        },
    ]
```

---

## 9. Risiko-Assessment

### 9.1 Risiko-Matrix

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Konfligierende Ressourcen | Hoch | Mittel | Konflikt-Detection + UI |
| Performance bei vielen Snapshots | Mittel | Niedrig | Caching, Lazy Loading |
| Falsche Maschinen-Zuordnung | Niedrig | Mittel | Klare UI, Warnings |
| Path-Inkompatibilitäten | Hoch | Mittel | Path-Mapping-Feature |
| Netzwerk-Konflikte | Hoch | Hoch | Explizite Warnings |

### 9.2 Mitigations-Strategien

1. **Konflikte:** Umfangreiche Konflikt-Detection vor Restore
2. **Performance:** Caching + Pagination bei vielen Snapshots
3. **Falscher Host:** Klare Anzeige von Source vs. Target
4. **Paths:** Optionales Path-Mapping in Config
5. **Netzwerke:** Explizite Warnings bei Cross-Restore

---

## 10. Zusammenfassung

### Geschätzter Aufwand

| Phase | Aufwand | Commits |
|-------|---------|---------|
| Foundation | 2-3 Tage | 1 |
| CLI & UI | 3-4 Tage | 1 |
| Cross-Restore-Logic | 3-4 Tage | 1 |
| Backward-Compatibility | 1-2 Tage | 1 |
| Advanced Features (Optional) | 2-3 Tage | 1 |
| Testing & Dokumentation | 2-3 Tage | - |
| **Total (ohne Optional)** | **11-16 Tage** | **4** |
| **Total (mit Optional)** | **13-19 Tage** | **5** |

### Neue Dependencies

Keine neuen Dependencies erforderlich.

### Kritische Entscheidungen

1. **`--advanced` vs. Auto-Detect:** Expliziter Flag für Klarheit
2. **Hostname-Quelle:** Kopia's `source.host` nutzen
3. **Konflikt-Default:** "Ask" für sicherstes Verhalten
4. **Legacy-Backups:** Als "unknown" anzeigen

### CLI-Änderungen

```bash
# Neu:
kopi-docka restore --advanced           # Cross-Machine Wizard
kopi-docka restore --advanced --machine=homeserver1  # Direkte Auswahl

# Optional (Phase 5):
kopi-docka restore --advanced --conflict-mode=skip
kopi-docka restore --advanced --conflict-mode=rename
```

---

## 11. Appendix: Kopia Snapshot-Struktur

### Beispiel: `kopia snapshot list --all --json`

```json
[
  {
    "id": "k1a2b3c4d5e6f7g8h9",
    "source": {
      "host": "homeserver1",
      "userName": "root",
      "path": "/var/lib/docker/volumes/wordpress_data/_data"
    },
    "description": "",
    "startTime": "2025-01-20T02:00:15.123456Z",
    "endTime": "2025-01-20T02:05:30.654321Z",
    "stats": {
      "totalSize": 1073741824,
      "excludedTotalSize": 0,
      "fileCount": 15234,
      "excludedFileCount": 0,
      "dirCount": 423,
      "excludedDirCount": 0,
      "errorCount": 0
    },
    "tags": {
      "tag:backup_id": "550e8400-e29b-41d4-a716-446655440000",
      "tag:timestamp": "2025-01-20T02:00:00Z",
      "tag:type": "volume",
      "tag:unit": "wordpress",
      "tag:volume": "wordpress_data"
    },
    "rootEntry": {
      "name": "wordpress_data",
      "type": "d",
      "mode": "0755",
      "mtime": "2025-01-20T01:58:00Z",
      "obj": "k9z8y7x6w5v4u3t2s1",
      "summ": {
        "size": 1073741824,
        "files": 15234,
        "dirs": 423,
        "maxTime": "2025-01-20T01:58:00Z"
      }
    },
    "retentionReason": ["daily-1", "weekly-1"]
  }
]
```

---

[← Back to README](../README.md)
