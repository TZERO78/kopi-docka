# Refactoring-Plan: TAR → Direct Kopia Snapshots

[← Back to README](../README.md)

## Executive Summary

**Problem:** Das aktuelle TAR-basierte Volume-Backup zerstört Kopias Block-Level-Deduplizierung. Jedes Backup ist effektiv ein Full-Backup, unabhängig von der tatsächlichen Datenänderung.

**Impact:** Bei einem 100 GB Volume mit 1 GB Änderungen werden trotzdem 100 GB übertragen und gespeichert.

**Lösung:** Migration zu direktem Kopia-Snapshot auf Volume-Verzeichnisse (`kopia snapshot create /var/lib/docker/volumes/.../_data`).

**Geschätzter Aufwand:** 3-4 Wochen für vollständige Implementation + Testing

---

## 1. Architektur-Analyse

### 1.1 Betroffene Module

#### Primär betroffen (Core-Changes)

| Datei | Funktion | Zeilen | Änderungstyp |
|-------|----------|--------|--------------|
| `kopi_docka/cores/backup_manager.py` | `_backup_volume()` | 582-663 | **Komplett neu** |
| `kopi_docka/cores/backup_manager.py` | `_ensure_policies()` | 679-706 | Anpassung |
| `kopi_docka/cores/repository_manager.py` | `create_snapshot_from_stdin()` | 394-429 | Wird obsolet |
| `kopi_docka/cores/restore_manager.py` | `_execute_volume_restore()` | 709-845 | **Komplett neu** |
| `kopi_docka/cores/restore_manager.py` | `_display_volume_restore_instructions()` | 615-693 | **Komplett neu** |

#### Sekundär betroffen (Type-Updates)

| Datei | Änderung |
|-------|----------|
| `kopi_docka/types.py` | Neues Feld `backup_format: str` in `BackupMetadata` |
| `kopi_docka/helpers/constants.py` | Neue Konstanten für Backup-Format |

#### Tests (Anpassung erforderlich)

| Datei | Änderung |
|-------|----------|
| `tests/unit/test_backup_commands.py` | Mock-Anpassungen |
| `tests/unit/test_cores/` | Neue Testdatei für Backup-Manager |
| `tests/integration/` | Neue Integration-Tests für Backup/Restore |

### 1.2 Aktuelle Implementierung

```python
# backup_manager.py:582-663 (aktuell)
def _backup_volume(self, volume: VolumeInfo, unit: BackupUnit, backup_id: str) -> Optional[str]:
    """Backup a single volume via tar stream → Kopia."""
    tar_cmd = [
        "tar", "-cf", "-",
        "--numeric-owner", "--xattrs", "--acls",
        "--one-file-system", "--mtime=@0", "--clamp-mtime", "--sort=name",
        "-C", volume.mountpoint, "."
    ]

    tar_process = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=stderr_file)

    snap_id = self.repo.create_snapshot_from_stdin(
        tar_process.stdout,
        dest_virtual_path=f"{VOLUME_BACKUP_DIR}/{unit.name}/{volume.name}",
        tags={...}
    )
```

**Probleme mit der aktuellen Implementierung:**
1. TAR erzeugt einen Byte-Stream, den Kopia als einzelne Datei sieht
2. Keine Block-Level-Deduplizierung möglich
3. Kopia kann nur Stream-Level-Deduplizierung anwenden (nahezu nutzlos)
4. Jedes Backup = Full-Backup in Bezug auf Storage

### 1.3 Gewünschte Implementierung

```python
# backup_manager.py (neu)
def _backup_volume(self, volume: VolumeInfo, unit: BackupUnit, backup_id: str) -> Optional[str]:
    """Backup a single volume via direct Kopia snapshot."""

    # Docker-Volume-Verzeichnis
    volume_data_path = Path(volume.mountpoint)  # z.B. /var/lib/docker/volumes/myvolume/_data

    # Direkte Snapshot-Erstellung
    snap_id = self.repo.create_snapshot(
        str(volume_data_path),
        tags={
            "type": "volume",
            "unit": unit.name,
            "volume": volume.name,
            "backup_id": backup_id,
            "timestamp": datetime.now().isoformat(),
            "backup_format": "direct",  # NEU: Format-Marker
        }
    )
    return snap_id
```

**Vorteile:**
1. Kopia sieht alle Dateien einzeln
2. Block-Level-Deduplizierung funktioniert
3. Nur geänderte Blöcke werden übertragen
4. 100 GB Volume mit 1 GB Änderung = ~1 GB Upload

### 1.4 Abhängigkeiten zwischen Modulen

```
backup_commands.py
       ↓
BackupManager.backup_unit()
       ↓
BackupManager._backup_volume()  ← ÄNDERUNG
       ↓
KopiaRepository.create_snapshot()  ← Bestehend, wird genutzt
                      (statt create_snapshot_from_stdin)
```

---

## 2. Backward-Compatibility-Strategie

### 2.1 Das Problem

Existierende Backups sind TAR-basiert:
- Snapshot-Type: `type=volume`
- Snapshot-Inhalt: Eine einzige TAR-Datei
- Restore-Prozess: TAR-Extraktion erforderlich

Neue Backups sind direkte Verzeichnis-Snapshots:
- Snapshot-Type: `type=volume`
- Snapshot-Inhalt: Verzeichnisstruktur mit Dateien
- Restore-Prozess: Direkte Kopie

**Kritisches Problem:** Der Restore-Code muss beide Formate erkennen und korrekt behandeln.

### 2.2 Format-Detection-Strategie

```python
# Neues Feld in Backup-Tags
tags = {
    ...
    "backup_format": "direct"  # oder "tar" (legacy, implizit wenn fehlt)
}
```

**Detection-Logik:**
```python
def _detect_backup_format(self, snapshot_tags: Dict[str, str]) -> str:
    """Detect backup format from snapshot tags."""
    # Neues Format hat expliziten Marker
    if snapshot_tags.get("backup_format") == "direct":
        return "direct"

    # Legacy-Format (vor v5.0.0)
    return "tar"
```

### 2.3 Legacy-Mode-Strategie

**Option A: Automatische Detection (Empfohlen)**
- Restore erkennt automatisch das Format
- Kein User-Eingriff erforderlich
- Beide Formate werden unbegrenzt unterstützt

**Option B: Migration-Tool**
- Einmaliges Tool konvertiert TAR → Direct
- Komplexer zu implementieren
- Nicht empfohlen (Storage-intensiv)

**Entscheidung: Option A**

### 2.4 Versioning-Strategie

| Version | Backup-Format | Restore-Support |
|---------|---------------|-----------------|
| ≤ 4.x | TAR only | TAR only |
| 5.0.0 | Direct only | TAR + Direct |
| 5.1.0+ | Direct only | TAR + Direct |

**Breaking Change: Ja → v5.0.0**

Grund: Alte Kopi-Docka-Versionen (< 5.0) können Direct-Format nicht restoren.

### 2.5 Migration-Pfad für Benutzer

```
┌─────────────────────────────────────────────────────────────┐
│                    UPGRADE GUIDE v4.x → v5.0                │
├─────────────────────────────────────────────────────────────┤
│ 1. Upgrade: pip install --upgrade kopi-docka               │
│                                                             │
│ 2. Verify: kopi-docka doctor                               │
│    → Shows "Backup format: direct (v5.0+)"                 │
│                                                             │
│ 3. First backup creates new-format snapshots               │
│    → Old backups remain accessible                         │
│                                                             │
│ 4. Restore works with both formats automatically           │
│                                                             │
│ NO MIGRATION REQUIRED - old backups stay compatible        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Implementierungs-Roadmap

### Phase 1: Foundation (Week 1)

**Ziel:** Infrastruktur für Format-Detection und neue Backup-Methode

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 1.1 | `constants.py` | Neue Konstanten `BACKUP_FORMAT_TAR`, `BACKUP_FORMAT_DIRECT` |
| 1.2 | `types.py` | Feld `backup_format` in `BackupMetadata` |
| 1.3 | `backup_manager.py` | Neue Methode `_backup_volume_direct()` |
| 1.4 | `backup_manager.py` | Alte Methode umbenennen zu `_backup_volume_tar()` |
| 1.5 | `backup_manager.py` | Dispatcher `_backup_volume()` mit Format-Switch |

**Commit 1:** "feat: Add backup format infrastructure for direct Kopia snapshots"

### Phase 2: Backup-Implementation (Week 1-2)

**Ziel:** Neue Direct-Backup-Methode vollständig implementieren

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 2.1 | `backup_manager.py` | `_backup_volume_direct()` implementieren |
| 2.2 | `backup_manager.py` | Exclude-Patterns für Direct-Modus |
| 2.3 | `backup_manager.py` | Permission-Handling für Docker-Volumes |
| 2.4 | `backup_manager.py` | Error-Handling und Logging |
| 2.5 | Unit-Tests | Tests für neue Backup-Methode |

**Commit 2:** "feat: Implement direct Kopia snapshot backup for volumes"

### Phase 3: Restore-Implementation (Week 2-3)

**Ziel:** Restore für beide Formate

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 3.1 | `restore_manager.py` | `_detect_backup_format()` implementieren |
| 3.2 | `restore_manager.py` | `_restore_volume_direct()` implementieren |
| 3.3 | `restore_manager.py` | `_restore_volume_tar()` (bestehend, Refactoring) |
| 3.4 | `restore_manager.py` | Dispatcher mit Format-Detection |
| 3.5 | `restore_manager.py` | Manual-Instructions für beide Formate |
| 3.6 | Unit-Tests | Tests für Restore beider Formate |

**Commit 3:** "feat: Implement dual-format restore (TAR legacy + direct)"

### Phase 4: Migration & Cleanup (Week 3-4)

**Ziel:** Default-Switch und Dokumentation

| Task | Datei | Beschreibung |
|------|-------|--------------|
| 4.1 | `backup_manager.py` | Direct als Default setzen |
| 4.2 | `repository_manager.py` | `create_snapshot_from_stdin()` als deprecated markieren |
| 4.3 | `FEATURES.md` | Dokumentation aktualisieren |
| 4.4 | `CHANGELOG.md` | Breaking-Change dokumentieren |
| 4.5 | Integration-Tests | End-to-End-Tests |

**Commit 4:** "feat!: Switch to direct Kopia snapshots as default (BREAKING)"

### Abhängigkeiten zwischen Phasen

```
Phase 1: Foundation
    ↓ (blocked by)
Phase 2: Backup-Implementation
    ↓ (blocked by)
Phase 3: Restore-Implementation
    ↓ (blocked by)
Phase 4: Migration & Cleanup
```

---

## 4. Edge-Cases & Risiken

### 4.1 Docker-Volume-Struktur

**Problem:** Docker-Volumes haben unterschiedliche Strukturen je nach Driver:

| Driver | Mountpoint-Struktur |
|--------|---------------------|
| `local` | `/var/lib/docker/volumes/<name>/_data` |
| `nfs` | Remote-Mount, kein lokaler Pfad |
| `cifs` | Remote-Mount, kein lokaler Pfad |
| `bind` | Beliebiger Host-Pfad |

**Lösung:**
```python
def _get_volume_path(self, volume: VolumeInfo) -> Path:
    """Get the actual data path for a volume."""

    # Local driver: Standard-Pfad
    if volume.driver == "local":
        return Path(volume.mountpoint)

    # Named volumes mit explizitem Mountpoint
    if volume.mountpoint:
        return Path(volume.mountpoint)

    # Fallback: docker inspect für Mount-Info
    # ...
```

### 4.2 Permission-Probleme

**Problem:** Docker-Volumes gehören oft `root:root` oder speziellen UIDs.

**Risiko:** Kopia läuft als root (via sudo), sollte kein Problem sein.

**Edge-Case:** Volumes mit speziellen ACLs oder SELinux-Labels.

**Lösung:**
```python
# Kopia-Parameter für Permission-Erhaltung
snapshot_args = [
    "--ignore-permission-errors",  # Warnung statt Abbruch
    "--parallel", str(self.max_workers),
]
```

### 4.3 Symlinks und Hardlinks

**Problem:** Docker-Volumes können Symlinks enthalten (z.B. für Logs).

**Aktuell (TAR):** `--dereference` folgt Symlinks.

**Direkt (Kopia):** Standard-Verhalten erhält Symlinks.

**Entscheidung:** Kopia-Standard beibehalten (Symlinks erhalten).

### 4.4 Sehr große Dateien

**Problem:** Single Files > 10 GB (z.B. Datenbank-Files).

**TAR:** Streaming, kein RAM-Problem.

**Kopia:** Chunking mit konfigurierbarer Chunk-Size.

**Lösung:** Kopia-Policy für große Dateien:
```bash
kopia policy set --max-file-size 100GB /path
```

### 4.5 Sparse Files

**Problem:** Sparse Files (z.B. VM-Images) können durch Kopia "aufgebläht" werden.

**TAR:** Erhält Sparse-Struktur mit `--sparse`.

**Kopia:** Seit v0.13+ Sparse-File-Support.

**Lösung:** Kopia-Version ≥ 0.13 dokumentieren als Requirement.

### 4.6 Laufende Prozesse (trotz Cold-Backup)

**Problem:** Obwohl Container gestoppt werden, könnten andere Prozesse auf Volumes zugreifen.

**Risiko:** Inkonsistente Snapshots wenn Dateien während Backup geändert werden.

**Lösung:**
- Docker-Container-Stop ist ausreichend für Container-Daten
- Warnung wenn Volume von Nicht-Container-Prozessen gemountet

### 4.7 Volume-Driver-Kompatibilität

| Driver | Direct-Backup Support |
|--------|----------------------|
| `local` | ✅ Vollständig |
| `nfs` | ⚠️ Wenn lokal gemountet |
| `cifs` | ⚠️ Wenn lokal gemountet |
| `overlay2` | ✅ Vollständig |
| `btrfs` | ✅ Vollständig |
| `zfs` | ✅ Vollständig |

**Fallback:** Für nicht-lokale Volumes weiterhin TAR-Methode.

---

## 5. Testing-Strategie

### 5.1 Unit-Tests

**Neue Test-Datei:** `tests/unit/test_cores/test_backup_manager.py`

```python
class TestBackupVolumeFormats:
    """Tests for backup format handling."""

    def test_backup_volume_direct_creates_snapshot(self):
        """Direct backup creates Kopia snapshot of volume path."""

    def test_backup_volume_direct_includes_format_tag(self):
        """Direct backup includes backup_format=direct in tags."""

    def test_backup_volume_tar_legacy_still_works(self):
        """TAR backup still works for compatibility."""

    def test_backup_volume_excludes_patterns(self):
        """Exclude patterns are applied correctly."""
```

**Neue Test-Datei:** `tests/unit/test_cores/test_restore_manager.py`

```python
class TestRestoreFormatDetection:
    """Tests for backup format detection in restore."""

    def test_detect_format_direct_from_tag(self):
        """Detects direct format from backup_format tag."""

    def test_detect_format_tar_when_no_tag(self):
        """Assumes TAR format when no backup_format tag."""

    def test_restore_volume_direct_copies_files(self):
        """Direct restore copies files without TAR extraction."""

    def test_restore_volume_tar_extracts_archive(self):
        """TAR restore extracts archive correctly."""
```

### 5.2 Integration-Tests

**Neue Test-Datei:** `tests/integration/test_backup_restore_formats.py`

```python
@pytest.mark.integration
class TestBackupRestoreRoundtrip:
    """End-to-end tests for backup and restore."""

    def test_backup_restore_direct_format(self, docker_volume):
        """Complete backup/restore cycle with direct format."""

    def test_backup_restore_tar_format(self, docker_volume):
        """Complete backup/restore cycle with TAR format."""

    def test_restore_old_backup_with_new_version(self, legacy_snapshot):
        """New version can restore old TAR-format backups."""
```

### 5.3 Test-Matrix

| Szenario | Backup v4.x | Backup v5.x |
|----------|-------------|-------------|
| Restore v4.x | ✅ TAR | ❌ N/A |
| Restore v5.x | ✅ TAR-Compat | ✅ Direct |

### 5.4 Performance-Tests

```python
@pytest.mark.slow
class TestBackupPerformance:
    """Performance comparison tests."""

    def test_direct_backup_faster_than_tar(self, large_volume):
        """Direct backup is faster than TAR for large volumes."""

    def test_incremental_backup_size_reduction(self, volume_with_changes):
        """Second backup is significantly smaller than first."""
```

### 5.5 Edge-Case-Tests

```python
class TestEdgeCases:
    """Edge case tests for backup/restore."""

    def test_backup_volume_with_symlinks(self):
    def test_backup_volume_with_hardlinks(self):
    def test_backup_volume_with_special_permissions(self):
    def test_backup_volume_with_acls(self):
    def test_backup_volume_with_xattrs(self):
    def test_backup_empty_volume(self):
    def test_backup_volume_with_unicode_filenames(self):
    def test_restore_to_non_empty_volume(self):
```

---

## 6. Risiko-Assessment

### 6.1 Risiko-Matrix

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Alte Backups nicht mehr lesbar | Niedrig | Hoch | Format-Detection, Legacy-Support |
| Performance-Regression | Niedrig | Mittel | Benchmark-Tests vor Release |
| Permission-Verlust bei Restore | Mittel | Hoch | Extensive Testing, `--preserve-permissions` |
| Inkompatibilität mit Volume-Drivers | Mittel | Mittel | Driver-Detection, Fallback zu TAR |
| Breaking Change für Automation | Hoch | Mittel | Klare Dokumentation, Deprecation-Warnings |

### 6.2 Rollback-Plan

Falls kritische Probleme nach Release:

1. **Hotfix v5.0.1:** Bug-Fixes ohne Format-Änderung
2. **Feature-Flag:** `--backup-format=tar` für Rollback zu altem Verhalten
3. **v5.1.0:** Beide Formate als wählbare Option

---

## 7. Dokumentations-Änderungen

### 7.1 FEATURES.md Updates

```markdown
## Backup-Format: Direct Kopia Snapshots (v5.0+)

Ab v5.0.0 nutzt Kopi-Docka **direkte Kopia-Snapshots** für Volume-Backups.

### Vorteile
- **Block-Level-Deduplizierung:** Nur geänderte Blöcke werden gespeichert
- **Schnellere Backups:** Inkrementelle Backups deutlich kleiner
- **Bessere Kompression:** Kopia komprimiert auf Dateiebene

### Migration von v4.x
- Keine Migration erforderlich
- Alte Backups bleiben lesbar
- Neue Backups nutzen automatisch neues Format
```

### 7.2 CHANGELOG.md

```markdown
## [5.0.0] - YYYY-MM-DD

### BREAKING CHANGES
- Volume-Backups nutzen jetzt direkte Kopia-Snapshots statt TAR-Streams
- Alte Kopi-Docka-Versionen (< 5.0) können neue Backups nicht restoren
- Kopia ≥ 0.13 ist jetzt Voraussetzung

### Changed
- `_backup_volume()` nutzt `create_snapshot()` statt `create_snapshot_from_stdin()`
- Backup-Tags enthalten jetzt `backup_format: direct`

### Deprecated
- `create_snapshot_from_stdin()` ist deprecated (wird in v6.0 entfernt)
```

---

## 8. Zusammenfassung

### Geschätzter Aufwand

| Phase | Aufwand | Commits |
|-------|---------|---------|
| Foundation | 2-3 Tage | 1 |
| Backup-Implementation | 3-4 Tage | 1 |
| Restore-Implementation | 4-5 Tage | 1 |
| Migration & Cleanup | 2-3 Tage | 1 |
| Testing & Dokumentation | 3-4 Tage | - |
| **Total** | **14-19 Tage** | **4** |

### Neue Dependencies

Keine neuen Dependencies erforderlich.

### Voraussetzungen

- Kopia ≥ 0.13 (für Sparse-File-Support)
- Python ≥ 3.10 (bestehend)

### Kritische Entscheidungen

1. **Breaking Change:** Ja, v5.0.0
2. **Legacy-Support:** Unbegrenzt für Restore
3. **Fallback:** TAR-Methode für inkompatible Volume-Drivers
4. **Default:** Direct-Format ab v5.0.0

---

[← Back to README](../README.md)
