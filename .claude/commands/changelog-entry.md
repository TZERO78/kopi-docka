# /changelog-entry — Neuer CHANGELOG-Eintrag im Hausstil

Erzeugt einen `CHANGELOG.md`-Eintrag im Kopi-Docka-Format (`### Emoji Titel` → **Why** → **Changes** → **Upgrade notes**) aus dem aktuellen Diff oder einer User-Beschreibung. Konsistent mit dem Stil seit v7.x.

## Usage

```
/changelog-entry
/changelog-entry <freitext was wir gemacht haben>
```

`$ARGUMENTS` ist optional. Wenn leer: aus `git diff main...HEAD` ableiten. Wenn gefüllt: als Leitfaden für das *Why* nehmen.

## Instructions

### Step 1 — Kontext einsammeln

Parallel ausführen:

```bash
git rev-parse --abbrev-ref HEAD          # Branch
git log main..HEAD --oneline             # Commits auf diesem Branch
git diff main...HEAD --stat              # Geänderte Files
```

Und einmal `Read` auf den Kopf von `CHANGELOG.md` (erste ~80 Zeilen), um den genauen Stil und das Versions-Header-Format zu sehen.

### Step 2 — Eintrag entwerfen

Format (so wie die letzten Einträge in CHANGELOG.md, z. B. v7.6.4, v7.6.3, v7.6.2):

```
## [Unreleased]

### <Emoji> <Kurztitel — was ist die User-spürbare Änderung>

**Why:** <2–4 Sätze. Was war kaputt / was hat ein User gemeldet / welcher
Bug oder welche Lücke wird geschlossen. Konkret, nicht abstrakt.>

**Changes:**
- `<file>` <was sich geändert hat — als Stichpunkt>
- ...

**Upgrade notes:** <1–2 Sätze: muss der User etwas tun? `pip install --upgrade`
reicht meistens. Config-Migrationen, Repo-Format-Änderungen, Breaking
Changes hier erwähnen — sonst "No config or repo-format changes".>

---
```

Emoji-Konvention (aus den letzten Einträgen):
- 🐛 Bugfix
- ✨ / 🆕 Feature
- 📚 Docs
- 🔧 Refactor / internals
- 🔒 Security
- ⚠️ Breaking change

### Step 3 — Einfügen

- Wenn `## [Unreleased]` bereits existiert und dort schon Einträge stehen: **anhängen** (neuen `### ...`-Block unten in der Sektion, vor dem `---`).
- Wenn `## [Unreleased]` leer/nicht existiert: oben unter dem Header und über dem letzten Release-Eintrag eine neue `## [Unreleased]`-Sektion anlegen.
- **Keinesfalls** ein konkretes Datum oder eine Versionsnummer schon setzen — das macht `/release-bump` beim Release.

### Step 4 — Verifikation

Dem User den fertigen Block zeigen und fragen: *"So einfügen, oder anpassen?"* Erst nach Bestätigung schreiben.

### Hausstil-Regeln (Memory: Docs in English)

- **CHANGELOG.md bleibt englisch**, auch wenn der Chat deutsch ist. Das *Why* schreibt sich oft auf Englisch besser, weil es für den PyPI-Reader gedacht ist.
- Konkrete Datei-/Method-Namen in Backticks (siehe v7.6.3-Eintrag mit `commands/disaster_recovery_commands.py::cmd_disaster_recovery_export`).
- Keine Marketing-Sprache. Wenn ein Bug gefixt wurde, sagen wie er sich gezeigt hat (Symptom + Root cause).
