# /kopia-bypass-check — Architektur-Guardrail für KopiaRepository

Findet direkte Aufrufe der `kopia`-CLI, die **nicht** durch `KopiaRepository._run()` in [cores/repository_manager.py](../../kopi_docka/cores/repository_manager.py) gehen. Die Regel steht seit Plan 0020 in CLAUDE.md — dieses Command erzwingt sie maschinell.

## Usage

```
/kopia-bypass-check
/kopia-bypass-check --diff       # nur die in HEAD geänderten Files prüfen
```

`$ARGUMENTS` ist `--diff` (optional) oder leer (= ganze Codebasis).

## Instructions

### Step 1 — Whitelist laden

Bekannte und dokumentierte Bypässe (aus CLAUDE.md → "Known bypass points") — diese sind **erlaubt**:

| Datei | Funktion / Stelle | Grund |
|---|---|---|
| `kopi_docka/helpers/repo_helper.py` | `kopia repository connect` (Pre-Init) | Chicken-and-egg: noch keine `KopiaRepository`-Instanz |
| `kopi_docka/helpers/repo_helper.py` | `kopia repository disconnect` (Pre-Init) | dito |
| `kopi_docka/cores/repository_manager.py` | `create_snapshot_from_stdin()` | `_run()` hat keinen stdin-Stream-Mode |
| `kopi_docka/cores/repository_manager.py` | `_run()` selbst | das **ist** der erlaubte Weg |

### Step 2 — Scope bestimmen

- Ohne Argument: **alle** Python-Files unter `kopi_docka/`.
- Mit `--diff`: nur die Files aus `git diff main...HEAD --name-only -- 'kopi_docka/**/*.py'`.

### Step 3 — Bypass-Pattern grepen

Verdächtige Patterns (Reihenfolge nach Trefferwahrscheinlichkeit):

```bash
# A: Direkte subprocess-Aufrufe auf "kopia"
grep -nE 'subprocess\.(run|Popen|check_output|check_call|call)\b' kopi_docka/**/*.py \
  | grep -v -E '(_run\(|repository_manager\.py.*_run)' \
  | xargs -I{} bash -c 'echo {}; grep -B1 -A5 "kopia" {} 2>/dev/null' 2>/dev/null

# B: run_command()-Aufrufe (ui_utils-Wrapper), die "kopia" als argv[0] haben
grep -nE 'run_command\(\s*\[?\s*["\x27]kopia["\x27]' kopi_docka/**/*.py

# C: shell=True mit "kopia" im String
grep -nE 'shell\s*=\s*True' kopi_docka/**/*.py | xargs -I{} grep -l "kopia" {} 2>/dev/null
```

Praktisch: jedes File mit `import subprocess` UND `kopia` als String prüfen.

### Step 4 — Whitelist abziehen

Treffer aus Step 3 gegen die Whitelist aus Step 1 abgleichen.

**Match-Kriterien:** Datei **und** Funktionsname/Kontext müssen übereinstimmen. Ein neuer `subprocess.run([..., "kopia", ...])` in `repo_helper.py`, der **nicht** in `_connect_kopia()` / `_disconnect_kopia()` (oder den dokumentierten Pre-Init-Helpern) liegt, ist **kein** erlaubter Bypass — nur die zwei bestehenden Stellen sind whitelistet, nicht das ganze File.

### Step 5 — Bericht

Format:

```
## Kopia-Bypass-Check

✅ 2 bekannte Bypässe gefunden (whitelisted):
   - helpers/repo_helper.py:128 — kopia repository connect (Pre-Init)
   - helpers/repo_helper.py:201 — kopia repository disconnect (Pre-Init)
   - cores/repository_manager.py:415 — create_snapshot_from_stdin()

❌ 1 NEUER, nicht-dokumentierter Bypass:
   - cores/restore_manager.py:887 — subprocess.run(["kopia", "snapshot", "verify", ...])
     Empfehlung: Methode in KopiaRepository hinzufügen (z. B. verify_snapshot(snapshot_id))
     und von hier aus self.kopia.verify_snapshot(...) aufrufen.
```

- **0 neue Funde** → Exit-Status "clean", einzeiliger Status.
- **≥ 1 neue Funde** → jedes mit Datei:Zeile, Argv-Auszug und konkretem Refactor-Vorschlag (welche `KopiaRepository`-Methode wäre der richtige Ort).

### Step 6 — Optional: Plan-Entwurf

Wenn ≥ 2 neue Bypässe gefunden werden, fragen: *"Soll ich einen Plan-Entwurf via `/plan-new bypass-cleanup-vN` anlegen?"* — analog zu Plan 0020. **Nicht** automatisch erstellen.

### Was dieses Command NICHT macht

- Keinen Code automatisch refactoren.
- Keine Whitelist erweitern. Wenn ein neuer Bypass strukturell unvermeidbar ist (wie damals stdin-streaming), muss das in CLAUDE.md unter "Known bypass points" dokumentiert werden — manueller redaktioneller Schritt, kein Auto-Edit.
- Kein Lint-Plugin / kein Pre-Commit-Hook setzen — wenn das gewünscht ist, ist `/update-config` der richtige Pfad.
