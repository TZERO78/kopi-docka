# /release-bump — Version Bump nach Releasecheckliste

Bumpt die Kopi-Docka-Version an **allen 5 Stellen** aus der Releasecheckliste in einem konsistenten Schritt. Eliminiert die häufigste Fehlerquelle des manuellen Bumps (vergessene Datei → freshly generated `kopi-docka.json` zeigt falsche Version, CHANGELOG-Datum bleibt "Unreleased", o. ä.).

## Usage

```
/release-bump X.Y.Z
/release-bump 7.7.0
```

`$ARGUMENTS` = die neue Version (ohne führendes `v`), z. B. `7.7.0`.

## Instructions

Du bist im Repository `kopi-docka`. Ziel: die in `$ARGUMENTS` übergebene Version auf einem Release-Branch in 5 Dateien setzen, sauber committen und einen PR vorbereiten — **ohne** in `main` zu pushen.

### Step 0 — Vorbedingungen prüfen

1. `$ARGUMENTS` muss `X.Y.Z` (SemVer) sein. Wenn leer/ungültig: Abbruch mit kurzer Erklärung.
2. `git status` muss clean sein. Sonst: stoppen und User fragen.
3. Aktuelle Version aus `pyproject.toml` lesen → wenn ≥ `$ARGUMENTS` (SemVer-Vergleich): warnen und User-Bestätigung einholen.
4. Sicherstellen, dass wir auf `main` und up to date sind: `git fetch origin && git checkout main && git pull --ff-only`.

### Step 1 — Release-Branch

```bash
git checkout -b release/v$ARGUMENTS main
```

### Step 2 — Die 5 Dateien aktualisieren

| # | Datei | Was ändern |
|---|---|---|
| 1 | `pyproject.toml` | Zeile mit `version = "..."` → `version = "$ARGUMENTS"` |
| 2 | `kopi_docka/helpers/constants.py` | `VERSION = "..."` → `VERSION = "$ARGUMENTS"` |
| 3 | `kopi_docka/templates/config_template.json` | `"version": "..."` → `"version": "$ARGUMENTS"` |
| 4 | `CLAUDE.md` | Headerzeile `- **Version**: ...` → `- **Version**: $ARGUMENTS` |
| 5 | `CHANGELOG.md` | Erste `## [Unreleased]`-Sektion → `## [$ARGUMENTS] - YYYY-MM-DD` mit heutigem Datum. Wenn keine `[Unreleased]`-Sektion existiert: nach dem Header eine neue `## [$ARGUMENTS] - YYYY-MM-DD`-Sektion einfügen und User darauf hinweisen, dass der Eintrag noch leer ist (Hinweis: `/changelog-entry` benutzen). |

Edit-Tool pro Datei, **kein** `sed`. Jeder Edit muss exakt eine Zeile treffen — sonst stoppen.

### Step 3 — Verifikation

Vor dem Commit:

```bash
grep -n "$ARGUMENTS" pyproject.toml kopi_docka/helpers/constants.py kopi_docka/templates/config_template.json CLAUDE.md CHANGELOG.md
```

Es müssen **5 Treffer** erscheinen (mind. einer pro Datei). Wenn weniger: stoppen und Diff zeigen.

Außerdem:

```bash
git diff --stat
```

Erwartet: genau 5 geänderte Dateien.

### Step 4 — Commit (NUR auf Bestätigung des Users)

Diff zeigen, dann fragen: *"Commit als `release: v$ARGUMENTS` und Push als `release/v$ARGUMENTS`?"*

Nur bei `ja`:

```bash
git add pyproject.toml kopi_docka/helpers/constants.py kopi_docka/templates/config_template.json CLAUDE.md CHANGELOG.md
git commit -m "release: v$ARGUMENTS"
git push -u origin release/v$ARGUMENTS
```

### Step 5 — PR (optional)

User fragen, ob `gh pr create --title "release: v$ARGUMENTS"` jetzt ausgeführt werden soll. Wenn ja: Body auf den CHANGELOG-Eintrag verlinken.

### Was dieses Command NICHT macht

- **Keinen Tag setzen.** Tagging passiert erst nach Merge in `main` (Step 3 der Releasecheckliste in CLAUDE.md). Das ist ein bewusster Sicherheitspuffer, weil `git push origin vX.Y.Z` das PyPI-Publish triggert.
- **Keinen CHANGELOG-Inhalt schreiben.** Dafür ist `/changelog-entry` zuständig.
- **Kein `--force`-Push.** Nie.

### Failure-Modi

- Wenn ein Edit nicht eindeutig matched: stoppen, Diff zeigen, User entscheiden lassen.
- Wenn CI nach dem Push rot wird: nicht "fixen by force-push" — neuen Commit auf demselben Branch oder Branch löschen & neu starten.
