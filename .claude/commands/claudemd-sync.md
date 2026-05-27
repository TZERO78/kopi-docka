# /claudemd-sync — CLAUDE.md gegen Realität abgleichen

Prüft, ob die Inhalte in `CLAUDE.md` noch zur tatsächlichen Codebasis passen. Erkennt typische Drift:

- Versionsnummer im Header vs. `pyproject.toml` / `constants.py` / `config_template.json`
- "Active Plans" vs. echte Inhalte in `plan/active/`
- "Completed Plans" vs. Release-Einträge in `CHANGELOG.md`
- Zeilenzahlen in der "Key Files"-Tabelle vs. `wc -l`
- "Known Technical Debt"-Punkte, die längst erledigt sind

Gibt eine Liste von Drift-Findings aus und schlägt konkrete Patches vor. **Schreibt nur nach User-Bestätigung.**

## Usage

```
/claudemd-sync
/claudemd-sync --fix          # nach Bestätigung Patches direkt anwenden
```

`$ARGUMENTS` ist `--fix` (optional) oder leer.

## Instructions

### Step 1 — Ist-Stand einsammeln (parallel)

```bash
grep -E '^version|^VERSION|"version"' pyproject.toml kopi_docka/helpers/constants.py kopi_docka/templates/config_template.json
ls plan/active/
git log --oneline -30 -- CHANGELOG.md
wc -l kopi_docka/cores/repository_manager.py kopi_docka/cores/restore_manager.py kopi_docka/helpers/config.py kopi_docka/cores/backup_manager.py
grep -nE '^##\s*\[[0-9]' CHANGELOG.md | head -20
```

Und `Read` auf `CLAUDE.md` (komplett — die Datei ist klein, < 200 Zeilen).

### Step 2 — Drift-Checks

Für jede dieser Kategorien prüfen und Findings sammeln:

**Versions-Drift**
- Header `- **Version**: X.Y.Z` muss exakt zu `pyproject.toml::version`, `constants.py::VERSION` und `config_template.json::version` passen.
- Wenn eine der vier Stellen abweicht: **Finding mit Severity = HIGH** (zerschießt die Releasecheckliste).

**Active-Plans-Drift**
- Jeder Plan unter `plan/active/plan_NNNN_<slug>.md` muss in der "Active Plans"-Sektion von CLAUDE.md genannt sein.
- Jeder Plan in der CLAUDE.md-"Active Plans"-Sektion muss als Datei in `plan/active/` existieren — sonst ist er entweder archiviert oder nie geschrieben worden.
- Mismatch = **Finding Severity = MEDIUM**.

**Completed-Plans-Drift**
- Jeder Plan in `plan/archive/v*.x/` sollte in "Completed Plans" oder in CHANGELOG.md auftauchen. Wenn ein archivierter Plan nirgends in CLAUDE.md erwähnt ist: Finding LOW (nur wenn ≥ 3 fehlen, sonst rauschend).
- Die letzten Releases in CHANGELOG.md sollten in "Completed Plans" sichtbar werden, falls dort ein Plan dazugehört.

**Key-Files-Zeilenzahlen**
- Für jede Zeile in der "Key Files"-Tabelle mit `(NNNN lines)`-Angabe: ist die Zahl noch korrekt (Toleranz ±20 %)?
- Drift > 20 %: Finding MEDIUM (deutet auf größeren Refactor hin, den niemand in CLAUDE.md vermerkt hat).

**Technical-Debt-Stale**
- Punkte unter "Known Technical Debt" stichprobenartig prüfen:
  - `engine/` directory existiert noch und ist leer?
  - `tests/README.md` ist noch der v2.0-Stand?
  - Coverage-Aussage ("~52 %", "~18 %", "~20 %") plausibel?
- Wo offensichtlich überholt: Finding LOW.

### Step 3 — Bericht

Format:

```
## CLAUDE.md Sync-Report

### HIGH (Releasecheckliste-relevant)
- Version-Drift: pyproject.toml = 7.6.4, CLAUDE.md = 7.5.0  → Vorschlag: Header auf 7.6.4 setzen

### MEDIUM
- Active Plans in CLAUDE.md: nur Plan 0028 genannt — auf Disk: 0031, 0032, 0033, 0034, 0036, 0038
- restore_manager.py: CLAUDE.md sagt 2,279 Zeilen, real 2,294 (Drift OK, < 1 %)
- repository_manager.py: CLAUDE.md sagt 834 Zeilen, real 1,182 (Drift 42 %!) → Hinweis auf nicht-dokumentierten Wuchs

### LOW
- "Coverage ~44 %" in Test Conventions vs. "~52 %" in Tech Debt — inkonsistent

### Vorgeschlagene Patches
1. ...
2. ...
```

### Step 4 — Anwenden (nur wenn `$ARGUMENTS == "--fix"`)

User die Patches einzeln zur Bestätigung vorlegen, dann mit `Edit` anwenden. **Kein Auto-Apply ohne explizites ja pro Patch.**

Bei Active/Completed-Plans-Aktualisierungen den User entscheiden lassen, *welcher* Plan in welche Sektion gehört — Status (`proposed`/`in-progress`/`done`) steht im Plan-Frontmatter, aber die Zuordnung zu Releases ist redaktionell.

### Was dieses Command NICHT macht

- Nicht in `CHANGELOG.md` schreiben (das macht `/changelog-entry`).
- Nicht Versionen bumpen (das macht `/release-bump`).
- Keine Plan-Dateien anlegen (das macht `/plan-new`).
- Keine Archivierung von Plänen (passiert manuell beim Release).
