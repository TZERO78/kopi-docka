# /plan-new — Neuen Plan in `plan/active/` anlegen

Legt eine neue Plan-Datei mit Standard-Frontmatter unter `plan/active/plan_NNNN_<slug>.md` an. Vergibt automatisch die nächste freie Nummer (durchsucht `plan/active/` **und** `plan/archive/**` — Nummern werden nie wiederverwendet).

## Usage

```
/plan-new <kebab-slug>
/plan-new <kebab-slug>: <einzeiler-titel>
/plan-new restore-helper-extraction
/plan-new restore-helper-extraction: Restore-Wizard Helper aus restore_manager ziehen
```

`$ARGUMENTS` = entweder nur ein kebab-case-Slug, oder `<slug>: <Titel-Einzeiler>`.

## Instructions

### Step 1 — Eingabe parsen

- `$ARGUMENTS` aufteilen am ersten `:`. Vor dem `:` ist der **Slug**, danach (optional) der **Titel**.
- Slug validieren: nur `[a-z0-9-]`, keine Leerzeichen, keine Versalien. Sonst Abbruch mit Korrekturvorschlag.
- Wenn kein Titel angegeben: Titel = Slug mit `-` → ` ` und erstem Buchstaben groß.

### Step 2 — Nächste Plan-Nummer finden

```bash
ls plan/active/ plan/archive/**/*.md 2>/dev/null \
  | grep -oE 'plan_[0-9]{4}_' \
  | grep -oE '[0-9]{4}' \
  | sort -n | tail -1
```

Nächste Nummer = `max + 1`, vierstellig zero-padded. Wenn keine Pläne existieren: `0001`.

> Hinweis: Die Nummerierung ist **monoton steigend, ohne Lücken-Recycling**. Plan 0035 fehlt z. B. im Repo — das ist Absicht (übersprungen / nie gestartet). Nicht auffüllen.

### Step 3 — Datei schreiben

Pfad: `plan/active/plan_<NNNN>_<slug>.md`

Inhalt (genau dieses Template, Datum = heute im Format `YYYY-MM-DD`):

```markdown
---
name: plan_<NNNN>_<slug>
status: proposed
priority: nice-to-have
target_release: tbd
created: <YYYY-MM-DD>
---

# Plan <NNNN>: <Titel>

**Branch (when picked up):** `<feature|refactor|fix>/<slug>`

---

## Context

<Warum existiert dieser Plan? Welches Problem / welche Schmerzpunkte?
Konkret, mit Datei-/Methodennamen. Wenn aus Code-Review oder User-
Feedback entstanden: kurz zitieren.>

---

## Scope

- [ ] <konkreter Schritt 1>
- [ ] <konkreter Schritt 2>
- [ ] Tests aktualisiert / neu
- [ ] CHANGELOG-Eintrag (`/changelog-entry`)

## Out of Scope

<Was bewusst NICHT in diesem Plan ist, um Scope Creep zu vermeiden.>

---

## Acceptance Criteria

- <messbares Kriterium 1>
- <messbares Kriterium 2>

---

## Notes

<Optional: bekannte Risiken, offene Fragen, Verweise auf Issues/PRs.>
```

### Step 4 — Bestätigung

- Pfad und vollständigen Inhalt zeigen.
- Hinweis: `plan/` ist in `.gitignore`, der Plan wird **nicht** in Git committed (siehe CLAUDE.md → Plan System).
- Vorschlag fürs Branchnamen-Setup zeigen (aber **nicht** automatisch erzeugen):
  ```bash
  git checkout -b <feature|refactor|fix>/<slug>
  ```

### Was dieses Command NICHT macht

- Keinen Branch erzeugen (User entscheidet, wann er den Plan picked-up).
- Keinen Pull Request anlegen.
- Keinen leeren Plan committen (Pläne sind ohnehin gitignored).
- Keine Datei in `plan/archive/` schreiben — Archiv passiert nur beim Release.
