# Kopi-Docka v2.1 - Complete Rewrite

**Status:** 🚧 In Development (Phase 1 Complete)

## 🎯 Mission

Transform Kopi-Docka from a technical CLI tool into a **user-friendly backup solution** with:
- **Zero-Config Setup**: Interactive wizard handles everything
- **Smart Automation**: Auto-install dependencies, validate configs, test connections
- **Safety First**: Never lose data, always create disaster recovery bundles
- **Modern UX**: Beautiful TUI with Textual + Rich
- **Bilingual**: Complete UI in English & German
- **Fresh Start**: No backwards compatibility, clean architecture

## 🏗️ Architecture Overview

```
kopi_docka/v2/
├── config.py           # 🌟 Pydantic models (type-safe JSON config)
├── i18n.py             # 🌟 Internationalization (EN/DE)
├── backends/           # 🌟 Pluggable storage backends
│   ├── base.py         # Abstract base class
│   ├── __init__.py     # Factory & registry
│   ├── filesystem.py   # Local/NAS storage (TODO)
│   ├── rclone.py       # Universal cloud (TODO)
│   ├── tailscale.py    # 🔥 Killer feature! (TODO)
│   ├── s3.py           # AWS S3 (TODO)
│   ├── b2.py           # Backblaze B2 (TODO)
│   └── webdav.py       # Nextcloud/OwnCloud (TODO)
├── ui/                 # 🌟 Textual TUI
│   ├── app.py          # Main application
│   ├── screens/        # Wizard screens (TODO)
│   └── widgets/        # Custom widgets (TODO)
└── locales/            # Translation files (TODO)
    ├── en/
    └── de/
```

## ✅ Phase 1: Foundation (COMPLETE!)

### 1. Pydantic Config Models (`config.py`)

**Type-safe JSON configuration** replacing the old INI system:

```python
from kopi_docka.v2.config import KopiDockaConfig, BackendConfig

# Create config
config = KopiDockaConfig(
    backend=BackendConfig(
        type="tailscale",
        repository_path="sftp://backup-nas.tailnet:/backup/kopia",
        credentials={"ssh_key": "~/.ssh/kopi-docka"}
    )
)

# Save to JSON
config.save(Path("~/.config/kopi-docka/config.json"))

# Load from JSON
config = KopiDockaConfig.load(Path("~/.config/kopi-docka/config.json"))

# Type-safe access with autocomplete!
backend_type = config.backend.type
retention_days = config.retention.daily
```

**Features:**
- ✅ Auto-validation (Pydantic validators)
- ✅ Type hints (IDE autocomplete)
- ✅ Schema documentation (docstrings on all fields)
- ✅ Secure password handling (file or direct)
- ✅ Path normalization (expanduser, resolve)

### 2. Internationalization (`i18n.py`)

**Bilingual support** (English/German) using gettext:

```python
from kopi_docka.v2.i18n import _

# Auto-detects language from environment
print(_("Welcome to Kopi-Docka!"))
# EN: "Welcome to Kopi-Docka!"
# DE: "Willkommen bei Kopi-Docka!"

# Manual language switch
from kopi_docka.v2.i18n import set_language
set_language("de")
```

**Features:**
- ✅ Auto-detection from `LANG`, `LANGUAGE`, `LC_ALL`
- ✅ Fallback to English
- ✅ Runtime language switching
- 📝 TODO: Create `.po` translation files

### 3. Backend Plugin System (`backends/`)

**Pluggable architecture** for different storage backends:

```python
from kopi_docka.v2.backends import create_backend, list_available_backends

# List available backends
backends = list_available_backends()
# ['filesystem', 'rclone', 'tailscale', 's3', 'b2', 'webdav']

# Create backend instance
backend = create_backend("tailscale", {
    "repository_path": "sftp://nas:/backup",
    "credentials": {...}
})

# Use backend
missing_deps = backend.check_dependencies()  # ['tailscale']
backend.install_dependencies()  # Auto-install
config = backend.setup_interactive()  # Guided setup
is_valid, errors = backend.validate_config()
backend.test_connection()
kopia_args = backend.get_kopia_args()
```

**Backend Interface:**
- `check_dependencies()` - Check for missing tools
- `install_dependencies()` - Auto-install (OS-aware)
- `setup_interactive()` - Guided wizard
- `validate_config()` - Validate settings
- `test_connection()` - Test connectivity
- `get_kopia_args()` - Generate Kopia CLI args

### 4. Textual TUI (`ui/app.py`)

**Modern terminal UI** with Textual framework:

```python
from kopi_docka.v2.ui.app import run_setup_wizard

# Launch interactive setup
run_setup_wizard()
```

**Features:**
- ✅ Beautiful TUI with CSS-like styling
- ✅ Keyboard shortcuts (q=quit, ?=help, l=language)
- ✅ Responsive layout
- 📝 TODO: Add wizard screens

## 📋 Next Steps

### Phase 2: Backend Implementations (Week 2-3)

Priority order:

1. **FilesystemBackend** (easiest, test the pattern)
2. **RcloneBackend** (universal cloud, 70+ providers)
   - **Critical**: Use `--embed-rclone-config` to avoid timeout issues!
3. **TailscaleBackend** (🔥 killer feature!)
   - Peer discovery
   - SSH key setup
   - Passwordless auth
4. **S3Backend** (AWS S3 + compatible)
5. **B2Backend** (Backblaze B2)
6. **WebDAVBackend** (Nextcloud, OwnCloud)

### Phase 3: Setup Wizard (Week 3-4)

Build complete wizard flow:

1. Welcome screen
2. Backend selection (with recommendations)
3. Dependency check + auto-install
4. Backend-specific setup
5. Password setup (strong validation)
6. Container discovery
7. Schedule configuration
8. Test backup
9. DR bundle creation
10. Summary

### Phase 4: Enhanced DR System (Week 4)

Improve disaster recovery:

- Collect all credentials (SSH keys, rclone.conf, etc.)
- Backend-specific recovery scripts
- Taildrop integration (send bundle to phone!)
- Test on fresh VM

### Phase 5: Polish & Integration (Week 5)

- Complete i18n (translate ALL strings)
- Adapt existing `cores/` modules to new config
- Testing (unit + integration)
- Documentation (README, guides, screenshots)
- Cleanup old structure

## 🚀 Quick Start (For Developers)

### Install Dependencies

```bash
# From project root
pip install -e .

# Or install v2.1 dependencies directly
pip install textual pydantic babel docker rich
```

### ⚠️ Important: Sudo Requirements

**Kopi-Docka requires root privileges for:**
- Installing system dependencies (rclone, tailscale, etc.)
- Kopia repository operations
- Docker management (stopping containers, volume access)
- Systemd timer configuration

**Always run the wizard with sudo:**
```bash
sudo python3 kopi_docka/v2/test_wizard.py
```

If you start without sudo, you'll see a warning and can choose to continue with limited functionality.

### Test Current Implementation

```bash
# Test Pydantic config
python3 -c "
from kopi_docka.v2.config import KopiDockaConfig, BackendConfig
from pathlib import Path

config = KopiDockaConfig(
    backend=BackendConfig(
        type='filesystem',
        repository_path='/backup/kopia'
    )
)
print(config.model_dump_json(indent=2))
"

# Test i18n
python3 -c "
from kopi_docka.v2.i18n import _, set_language
print(_('Welcome'))  # Auto-detect language
set_language('de')
print(_('Welcome'))  # Should show German if .po exists
"

# Test Textual app (basic) - REQUIRES SUDO!
sudo python3 kopi_docka/v2/test_wizard.py

# Or with debug output
sudo python3 kopi_docka/v2/test_wizard.py --debug
```

## 📖 Design Principles

### KISS (Keep It Simple, Stupid)
- One command: `kopi-docka setup`
- Sensible defaults everywhere
- User can't make mistakes (validation)
- Automate everything possible

### User-First
- Never assume knowledge
- Offer help at every decision
- Show progress, don't leave user waiting
- Errors are learning opportunities

### Safety
- Always create DR bundles
- Warn about password importance
- Test connections before committing
- Never delete data without triple-confirm

### Modularity
- Each backend is a plugin
- Easy to add new backends
- Config format supports future features
- Clean separation of concerns

## 🔧 Development Notes

### Python Concepts (For C# Developers)

```python
# 1. Properties (like C# properties)
@property
def backend_type(self) -> str:
    return self.data["backend"]["type"]

# 2. Abstract Base Classes (like C# interfaces)
from abc import ABC, abstractmethod

class BackendBase(ABC):
    @abstractmethod
    def setup(self): pass

# 3. Pydantic (like C# records + FluentValidation)
from pydantic import BaseModel, Field

class Config(BaseModel):
    name: str = Field(..., min_length=1)
    age: int = Field(ge=0, le=150)

# 4. Type Hints (like C# types)
def process(items: List[str]) -> Dict[str, int]:
    return {item: len(item) for item in items}
```

### Testing

```bash
# Run tests
pytest tests/unit/v2/

# Test specific backend
pytest tests/unit/v2/backends/test_filesystem.py -v

# Coverage
pytest --cov=kopi_docka.v2 tests/unit/v2/
```

## 📚 Resources

- **Textual Docs**: https://textual.textualize.io/
- **Pydantic Docs**: https://docs.pydantic.dev/
- **Kopia Docs**: https://kopia.io/docs/
- **Tailscale Docs**: https://tailscale.com/kb/

## 🤝 Contributing

This is a complete rewrite, so we're building from scratch. Follow the backend plugin pattern and use Textual for all UI.

**Current Focus:** Implementing backend plugins (Phase 2)

## 📝 License

MIT License - see LICENSE file
