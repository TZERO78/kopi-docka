## Plan: Upgrade auf v6.0.0 mit Dokumentationsprüfung

Das Projekt wird von v5.6.0 auf v6.0.0 angehoben. Die Dokumentation muss auf Konsistenz geprüft und mit den Änderungen zwischen `main` und `dev` Branch synchronisiert werden. Der CHANGELOG fehlt für v5.6.0 und muss für v6.0.0 ergänzt werden. Schreibe es in Englisch.
Starte auch eine inhaltliche Prüfung der Dokumentation gegen die aktuellen Features im Code. Prüfe auch die test coverage für neue Features. Des Weiteren passe die Versionsnummern in den relevanten Dateien an. die (docs/ARCHITECTURE.md) biete dir eine Übersicht über die Architektur, die du für die Prüfung nutzen kannst diese solltes du mit den Code abgleichen.

---

## Todo List

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Git-Diff analysieren | ✅ Done | 55 files changed, +6470/-1286 lines |
| 2 | Versionen auf 6.0.0 aktualisieren | ✅ Done | pyproject.toml + constants.py |
| 3 | CHANGELOG.md ergänzen | ✅ Done | [6.0.0] - 2025-12-31 entry added |
| 4 | Docs Versionsreferenzen aktualisieren | ✅ Done | USAGE.md, FEATURES.md, INSTALLATION.md |
| 5 | Inhaltliche Docs-Prüfung | ✅ Done | ~85% complete, gaps identified |
| 6 | Test Coverage prüfen | ✅ Done | 18,234 lines total, SafeExitManager well covered |
| 7 | Deprecated Code entfernen | ⏸️ HOLD | Kept in v6.0.0, removal planned for v7.0.0 |
| 8 | ARCHITECTURE.md Lücken schließen | ✅ Done | 6 modules + helpers added |
| 9 | FEATURES.md Lücken schließen | ✅ Done | Notification + Dry-Run sections added |
| 10 | README.md aktualisieren | ✅ Done | Graceful Shutdown + Notifications features |

---

## Documentation Gaps - RESOLVED ✅

### ARCHITECTURE.md - Missing modules:
- [x] `dependency_manager.py` - Hard/Soft Gate System
- [x] `dry_run_manager.py` - Backup Simulation  
- [x] `notification_manager.py` - Apprise Integration
- [x] `service_helper.py` - systemctl/journalctl Wrapper
- [x] `repo_helper.py` - Repository Detection
- [x] `dependency_helper.py` - CLI Tool Detection
- [ ] `commands/advanced/` - Entire folder not documented (low priority)

### FEATURES.md - Missing sections:
- [x] Notifications as standalone section (currently only link to NOTIFICATIONS.md)
- [x] Dry-Run explanation (what gets simulated)
- [x] `advanced notification` commands in CLI table

---

## ⏸️ Deprecated Code Analysis (ON HOLD)

**Status:** `create_snapshot_from_stdin()` was marked deprecated in v5.0.0 with planned removal in v6.0.0

**Current State:**
- Function EXISTS in `backup_manager.py` (lines 434-480)
- Raises `DeprecationWarning` when called
- Used by `restore_manager.py` line 856 (`_restore_from_stdin`)
- Has test coverage in `test_backup_manager.py`

**⚠️ RISK ASSESSMENT:**
1. **Breaking Change:** Removing it would break any external code using this method
2. **Internal Usage:** `_restore_from_stdin` in RestoreManager still references it
3. **Test Dependencies:** Tests exist for deprecated behavior

**Recommendation:** 
- Keep function in v6.0.0 with deprecation warning
- Plan removal for v7.0.0 after verifying no internal/external usage
- Update CHANGELOG to reflect "deprecated, NOT removed"

---

### Steps (Original Reference)

1. **Git-Diff analysieren**: `git log main..dev --oneline` und `git diff main dev --stat` ausführen, um alle Änderungen zwischen Branches zu identifizieren.

2. **Versionen auf 6.0.0 aktualisieren** in:
   - [pyproject.toml](pyproject.toml) → `version = "6.0.0"`
   - [kopi_docka/helpers/constants.py](kopi_docka/helpers/constants.py) → `VERSION = "6.0.0"` und Header-Kommentar `@version: 6.0.0`

3. **CHANGELOG.md ergänzen**: Neuen `## [6.0.0]` Eintrag in [CHANGELOG.md](CHANGELOG.md) mit allen Änderungen seit v5.5.1 basierend auf Git-Commits hinzufügen.

4. **Dokumentation aktualisieren**: Versionsreferenzen in [docs/INSTALLATION.md](docs/INSTALLATION.md#L121-L137), [docs/CONFIGURATION.md](docs/CONFIGURATION.md#L196), und [docs/FEATURES.md](docs/FEATURES.md#L5) auf `v6.0.0` ändern.

5. **Inhaltliche Prüfung** aller Docs: [ARCHITECTURE.md](docs/ARCHITECTURE.md), [FEATURES.md](docs/FEATURES.md), [USAGE.md](docs/USAGE.md), [CONFIGURATION.md](docs/CONFIGURATION.md), [HOOKS.md](docs/HOOKS.md), [NOTIFICATIONS.md](docs/NOTIFICATIONS.md) gegen die aktuellen Features im Code validieren.

6. ~~**Deprecated Code entfernen**~~: `create_snapshot_from_stdin()` - **OBSOLET** - bleibt in v6.0.0, Entfernung für v7.0.0 geplant.

### Further Considerations

1. ~~**Git-Diff erforderlich**~~ ✅ Erledigt
2. **Major Version Begründung**: SafeExitManager + Pydantic Validation + Breaking Change Warning rechtfertigen v6.0.0
3. **README.md**: Die Haupt-README sollte ebenfalls auf aktuelle Features geprüft werden
