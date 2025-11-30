# Migration Guide: Textual TUI → Pure CLI

> ⚠️ **DEPRECATED / VERALTET**
>
> Diese Dokumentation bezieht sich auf eine veraltete v2-Entwicklungsversion.
> Die aktuelle Version (v3.3.0) verwendet bereits die Pure CLI-Architektur.
> Dieses Dokument dient nur zu historischen Referenzzwecken.

---

## 🎯 Was hat sich geändert?

Kopi-Docka v2 wurde von einer **Textual TUI** (Terminal User Interface) zu einer **Pure CLI** (Command Line Interface) mit Rich migriert.

### Entfernt
- ❌ Textual TUI (`kopi_docka/v2/ui/`)
- ❌ `textual` Dependency
- ❌ `babel` Dependency (gettext)
- ❌ `test_wizard.py` (TUI-Version)

### Hinzugefügt
- ✅ Pure CLI mit Typer (`kopi_docka/v2/cli/`)
- ✅ Rich für schöne Terminal-Ausgaben
- ✅ Einfachere, wartbare Code-Struktur
- ✅ Multi-Language Support (en/de) bleibt erhalten

## 📦 Installation

```bash
# Abhängigkeiten installieren
pip install -e .

# Oder nur v2 Dependencies
pip install typer rich pydantic docker
```

## 🚀 Usage

### Vorher (TUI)
```bash
python kopi_docka/v2/test_wizard.py
```

### Nachher (CLI)
```bash
# Development
python kopi_docka/v2/test_cli.py setup backend

# Nach Installation
kopi-docka setup backend

# Mit Sprache
kopi-docka setup backend --language de

# Mit Backend-Argument
kopi-docka setup backend --backend tailscale
```

## 🎨 Neue Features

### 1. **Bessere UX**
- Schöne Rich Tables für Peer-Auswahl
- Farbige Ausgaben mit Icons
- Klare Prompts und Bestätigungen

### 2. **Flexibler**
```bash
# Interaktiv (empfohlen)
kopi-docka setup backend

# Automatisiert (für Scripts)
kopi-docka setup backend --backend tailscale --language en
```

### 3. **Multi-Commands**
```bash
kopi-docka version       # Version anzeigen
kopi-docka info          # System-Info
kopi-docka setup backend # Backend einrichten
```

## 🔧 Für Entwickler

### Neue Struktur
```
kopi_docka/v2/
├── cli/                    # ← NEU: Pure CLI
│   ├── __init__.py
│   ├── main.py            # Entry Point mit Typer
│   ├── setup.py           # Setup Commands
│   └── utils.py           # Rich Helpers
├── backends/              # Bestehend, angepasst
│   └── tailscale.py       # Nutzt jetzt Rich
└── i18n.py                # Vereinfacht (nur Dictionary)
```

### Backend Migration

**Vorher** (mit print):
```python
def setup_interactive(self):
    print("Setup...")
    choice = input("Select: ")
```

**Nachher** (mit Rich):
```python
def setup_interactive(self):
    from kopi_docka.v2.cli import utils
    
    utils.print_info("Setup...")
    choice = utils.prompt_select("Select", options)
```

### Testing

```bash
# CLI testen
python kopi_docka/v2/test_cli.py --help

# Backend testen
python kopi_docka/v2/test_cli.py setup backend --backend local
```

## 📊 Vergleich

| Feature | TUI (Vorher) | CLI (Nachher) |
|---------|-------------|---------------|
| UI Framework | Textual | Typer + Rich |
| Dependencies | textual, babel | typer, rich |
| Complexity | Hoch (Async, Screens) | Niedrig (Sequenziell) |
| Debugging | Schwierig | Einfach |
| Automation | Schwierig | Einfach |
| i18n | gettext (.mo files) | Dictionary (JSON-Style) |
| Multi-Language | ✅ | ✅ |

## 🎯 Vorteile der Migration

1. **KISS Prinzip**: Keep It Simple, Stupid
2. **Weniger Dependencies**: Keine Textual, kein Babel
3. **Einfacheres Debugging**: Kein Async, keine Screen-Verwaltung
4. **Bessere Testbarkeit**: CLI ist einfacher zu testen
5. **Automation-Ready**: Perfekt für Scripts
6. **Schneller Start**: Keine TUI-Initialisierung

## 🔄 Breaking Changes

### Entry Points
```bash
# Alt (v1)
kopi-docka          # Zeigt auf v1

# Neu
kopi-docka          # Zeigt auf v2 CLI
kopi-docka-v1       # Legacy v1
```

### Import Paths
```python
# Alt
from kopi_docka.v2.ui.app import WizardApp

# Neu
from kopi_docka.v2.cli.main import app
```

## 📝 Nächste Schritte

1. ✅ CLI-Basis aufgebaut
2. ✅ Tailscale Backend migriert
3. ⏳ Andere Backends migrieren (filesystem, s3, rclone)
4. ⏳ Tests aktualisieren
5. ⏳ Dokumentation aktualisieren

## 💡 Tipps

### Für Benutzer
- Die CLI ist intuitiver und schneller
- Multi-Language funktioniert weiterhin (en/de)
- Nutze `--help` für alle Commands

### Für Entwickler
- Nutze `cli/utils.py` für konsistente Ausgaben
- Erweitere `i18n.py` für neue Übersetzungen
- Teste mit `test_cli.py` vor dem Commit

## 🐛 Bekannte Issues

- ⚠️ Nur Tailscale Backend vollständig migriert
- ⚠️ Filesystem/S3/Rclone nutzen noch alte print() Ausgaben
- ⚠️ Config-Speicherung noch TODO

## 📚 Weitere Infos

- **Rich Docs**: https://rich.readthedocs.io/
- **Typer Docs**: https://typer.tiangolo.com/
- **Kopi-Docka Repo**: https://github.com/TZERO78/kopi-docka

---

**Migration durchgeführt**: 2025-01-17  
**Branch**: `refactor/cli-migration`  
**Autor**: Cline AI Assistant
