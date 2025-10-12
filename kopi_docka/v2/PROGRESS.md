# Kopi-Docka v2.1 - Development Progress

**Branch:** `v2.1-rewrite`  
**Status:** Phase 2 Complete ✅ | Phase 3 Ready  
**Last Updated:** 2025-10-12

---

## 🎉 Completed Work

### Phase 0: Project Setup ✅
- Created v2.1-rewrite branch
- Set up kopi_docka/v2/ directory structure
- Updated dependencies in requirements.txt

### Phase 1: Foundation ✅
**Files Created:**
- `config.py` - Pydantic-based JSON configuration (622 lines)
- `i18n.py` - Internationalization system (82 lines)
- `backends/base.py` - Abstract backend interface (152 lines)
- `backends/__init__.py` - Factory & registry (49 lines)
- `ui/app.py` - Textual TUI framework (144 lines)
- `README.md` - Complete architecture documentation (322 lines)

**Key Features:**
- Type-safe configuration with Pydantic validation
- Bilingual support infrastructure (EN/DE)
- Pluggable backend architecture
- Modern TUI foundation with Textual

### Phase 2.0: System Utilities ✅
**Files Created:**
- `utils/os_detect.py` - Linux distribution detection (234 lines)
  - Debian 11, 12, **13 (Trixie)** 🌟
  - Ubuntu 20.04, 22.04, 24.04
  - Arch, Fedora, RHEL-based
  
- `utils/dependency_installer.py` - Auto-installation (318 lines)
  - Kopia (with proper GPG key handling)
  - Rclone (universal cloud backend)
  - Tailscale (for offsite backups)
  - Docker (if needed)

### Phase 2: Backend Implementations ✅

#### 1. FilesystemBackend (239 lines)
**Purpose:** Local/NAS storage support

**Features:**
- Path validation & permission checks
- Auto-create directories
- Connection testing (write/read/delete test file)
- Recovery instructions for NFS/CIFS mounts

**Example Usage:**
```python
from kopi_docka.v2.backends import create_backend

backend = create_backend("filesystem", {
    "repository_path": "/backup/kopi-docka"
})

# Check dependencies
missing = backend.check_dependencies()  # ['kopia'] if not installed

# Interactive setup
config = backend.setup_interactive()

# Test connection
backend.test_connection()  # Creates .kopi-docka-test file
```

#### 2. RcloneBackend (331 lines)
**Purpose:** Universal cloud storage (70+ providers!)

**Critical Fix:** 
- ✅ Uses `--embed-rclone-config` flag
- ✅ Prevents timeout issues with Kopia + rclone

**Features:**
- List existing remotes
- Create new remote (launches `rclone config`)
- Auto-detect remote type (drive, s3, dropbox, etc.)
- Connection testing with 30s timeout
- Environment variable management

**Supported Providers:**
Google Drive, Dropbox, OneDrive, S3, B2, Azure, GCS, SFTP, FTP, WebDAV, and 60+ more!

**Example Usage:**
```python
backend = create_backend("rclone", {
    "repository_path": "gdrive:kopi-docka-backups",
    "credentials": {
        "remote_name": "gdrive",
        "remote_path": "kopi-docka-backups",
        "rclone_config": "~/.config/rclone/rclone.conf"
    }
})
```

#### 3. TailscaleBackend (🔥 Killer Feature!) (410 lines)
**Purpose:** Secure offsite backups over Tailscale network

**Features:**
- **Peer Discovery:** Lists all peers in Tailnet with `tailscale status --json`
- **Rich Info:** Shows disk space, ping latency, online status for each peer
- **SSH Key Setup:** Auto-generates ED25519 key and copies to remote
- **Passwordless Auth:** Uses SSH keys for secure, automated backups
- **Smart Sorting:** Prioritizes online peers with lowest latency

**Example Output:**
```
Available backup targets:
  1. 🟢 backup-server (100.88.1.5) - 2.4TB free - 12ms
  2. 🟢 home-nas (100.88.1.10) - 8.1TB free - 45ms
  3. 🔴 vps-fra (100.88.1.20) - 200GB free - ?
```

**Example Usage:**
```python
backend = create_backend("tailscale", {
    "repository_path": "sftp://root@backup-server.tailnet:/backup/kopia",
    "credentials": {
        "peer_hostname": "backup-server",
        "peer_ip": "100.88.1.5",
        "ssh_user": "root",
        "ssh_key": "~/.ssh/kopi-docka_ed25519",
        "remote_path": "/backup/kopia"
    }
})
```

---

## 📊 Statistics

**Total Code Written:**
- ~2,900 lines of production code
- 20 new files
- 4 git commits
- 100% type-hinted
- Bilingual ready (EN/DE)

**Backend Comparison:**

| Backend    | Lines | Complexity | Setup Time | Best For |
|------------|-------|------------|------------|----------|
| Filesystem | 239   | ⭐ Simple  | 1 min      | Local/NAS backup |
| Rclone     | 331   | ⭐⭐ Medium | 5 min      | Cloud providers |
| Tailscale  | 410   | ⭐⭐⭐ Advanced | 3 min   | Offsite backup |

**Dependencies Covered:**
- ✅ Debian 11 (Bullseye)
- ✅ Debian 12 (Bookworm)  
- ✅ **Debian 13 (Trixie)** 🌟 NEW!
- ✅ Ubuntu 20.04, 22.04, 24.04
- ✅ Arch Linux (AUR support)
- ✅ Fedora/RHEL

---

## 🧪 Testing the Backends

### Quick Test Script
```bash
cd /home/tzeroadmin/projects/opensource/kopi-docka

# Test OS detection
python3 -m kopi_docka.v2.utils.os_detect

# Test dependency checker
python3 -c "
from kopi_docka.v2.utils.dependency_installer import DependencyInstaller
installer = DependencyInstaller()
print('OS:', installer.os_info)
print('Kopia:', installer.check_installed('kopia'))
print('Docker:', installer.check_installed('docker'))
print('Rclone:', installer.check_installed('rclone'))
print('Tailscale:', installer.check_installed('tailscale'))
"

# Test backend factory
python3 -c "
from kopi_docka.v2.backends import list_available_backends, create_backend
print('Available backends:', list_available_backends())

# Create filesystem backend
fs = create_backend('filesystem', {})
print('\\nFilesystem backend:', fs.display_name)
print('Description:', fs.description)
print('Dependencies:', fs.check_dependencies())
"

# Test backend registration
python3 -c "
from kopi_docka.v2.backends import BACKENDS
for name, cls in BACKENDS.items():
    backend = cls({})
    print(f'{name}: {backend.display_name}')
    print(f'  Dependencies: {backend.check_dependencies()}')
    print()
"
```

### Manual Backend Test
```python
# Test FilesystemBackend setup
from kopi_docka.v2.backends.filesystem import FilesystemBackend

backend = FilesystemBackend({})
print("Missing deps:", backend.check_dependencies())

# Run interactive setup (will prompt for path)
config = backend.setup_interactive()
print("Config:", config)

# Validate
is_valid, errors = backend.validate_config()
print("Valid:", is_valid, "Errors:", errors)

# Test connection
success = backend.test_connection()
print("Connection test:", "✓" if success else "✗")
```

---

## 🎯 Next Steps: Phase 3 - Setup Wizard

**Goal:** Create interactive wizard for zero-config setup

### Remaining Work

#### 3.1 Welcome Screen (~150 lines)
- Welcome message (bilingual)
- System requirements check
- Debian Trixie support announcement
- Navigation to backend selection

#### 3.2 Backend Selection Screen (~200 lines)
- Show 3 backends with descriptions
- Recommendation logic
- Help/Guide option
- Fuzzy search support

#### 3.3 Dependency Check Screen (~150 lines)
- Show missing dependencies
- Auto-installation UI
- Progress indicators
- Error handling

#### 3.4 Basic Wizard Flow (~200 lines)
- Screen navigation
- State management
- Back/Next buttons
- Exit handling

### Estimated Work
- **Time:** 2-3 hours
- **Tokens:** ~30K
- **Complexity:** Medium (Textual UI learning curve)

---

## 🚀 Usage Examples

### Example 1: Filesystem Backup Setup
```bash
# Will be available after Phase 3:
kopi-docka setup

# Select: Filesystem Backend
# Path: /backup/kopia-repository
# Auto-creates directory if not exists
# Tests write permissions
# Creates Kopia repository
# Done!
```

### Example 2: Cloud Backup with Rclone
```bash
kopi-docka setup

# Select: Rclone Backend
# Existing remotes: gdrive (drive), dropbox (dropbox)
# Select: gdrive
# Path in remote: kopi-docka-backups
# Tests connection
# Creates Kopia repository with --embed-rclone-config
# Done!
```

### Example 3: Tailscale Offsite Backup
```bash
kopi-docka setup

# Select: Tailscale Backend
# Discovers peers in Tailnet...
# Available targets:
#   1. backup-server (2.4TB free, 12ms)
#   2. home-nas (8.1TB free, 45ms)
# Select: 1
# Setup SSH key? Yes
# Generates ED25519 key
# Copies to backup-server
# Tests connection
# Creates Kopia repository
# Done!
```

---

## 📝 Architecture Highlights

### Why This Design?

**1. Pydantic Configuration**
- Type-safe: IDE autocomplete works!
- Validated: Catches errors before they happen
- JSON: Machine-readable for DR scripts
- Future-proof: Easy to add new fields

**2. Plugin Backend System**
- Extensible: Add new backends easily
- Isolated: Each backend is self-contained
- Testable: Unit test each backend separately
- Documented: Recovery instructions built-in

**3. Auto-Dependency Management**
- OS-aware: Detects Debian, Ubuntu, Arch, etc.
- Smart: Installs only what's missing
- Safe: Asks permission before installing
- Modern: Uses new GPG keyring methods

**4. Tailscale Integration** 🔥
- Zero-config: Auto-discovers peers
- Secure: Encrypted over WireGuard
- Smart: Shows disk space & latency
- Easy: One-click SSH key setup

---

## 🐛 Known Limitations

### Current Version
1. **No Textual UI yet** - Backends use simple input() prompts
   - Will be replaced with beautiful Textual screens in Phase 3

2. **No password setup** - Hardcoded for testing
   - Phase 3 will add password validation & storage

3. **No container discovery** - Manual selection required
   - Phase 3 will add Docker container auto-discovery

4. **No systemd timer** - No automatic backups yet
   - Phase 3 will add schedule configuration

### Future Phases
- **Phase 3:** Complete wizard with Textual UI
- **Phase 4:** Enhanced DR system with Taildrop
- **Phase 5:** Polish, i18n completion, integration testing

---

## 💾 Git History

```bash
658bce0 (HEAD -> v2.1-rewrite) feat(v2): Implement three backend systems
19531db feat(v2): Add OS detection and dependency installer utilities
de0811c docs: Add comprehensive v2.1 README with architecture and examples
27e2162 feat: v2.1 foundation - Pydantic config, i18n, backend system, Textual UI base
```

**Branch is 4 commits ahead of develop**

---

## 🎓 Lessons Learned

### Python Patterns
1. **Dataclasses:** Perfect for configuration objects
2. **Abstract Base Classes:** Force interface compliance
3. **Factory Pattern:** Clean backend instantiation
4. **Type Hints:** Essential for maintainability
5. **Pydantic:** Game-changer for validation

### System Integration
1. **OS Detection:** `/etc/os-release` is standard
2. **Package Managers:** Debian's GPG keyring method changed
3. **Tailscale API:** `tailscale status --json` is powerful
4. **Rclone:** `--embed-rclone-config` prevents timeouts
5. **Kopia:** SFTP backend works perfectly with Tailscale

---

## 📚 References

- **Pydantic:** https://docs.pydantic.dev/
- **Textual:** https://textual.textualize.io/
- **Kopia:** https://kopia.io/docs/
- **Rclone:** https://rclone.org/docs/
- **Tailscale:** https://tailscale.com/kb/

---

## ✅ Success Criteria

**Phase 2 Goals:** ✅ ALL ACHIEVED!
- [x] Three functional backends
- [x] OS detection (Debian 13 Trixie!)
- [x] Auto-dependency installation
- [x] Type-safe configuration
- [x] Bilingual infrastructure
- [x] Comprehensive documentation
- [x] Recovery instructions

**Next Milestone:** Phase 3 - Interactive wizard that normal users can use!

---

*Built with ❤️ for the Kopi-Docka v2.1 rewrite*
