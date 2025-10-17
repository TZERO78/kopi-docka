"""
Welcome screen for Kopi-Docka v2.1 Setup Wizard.

Displays system information and requirements check.
"""

import os
import sys
import shutil
import platform
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, Button, Label
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.utils.os_detect import detect_os_info, get_package_manager
from kopi_docka.v2.utils.dependency_installer import DependencyInstaller
from kopi_docka.v2.ui.base_screen import BaseScreen
from textual.containers import Horizontal


class RequirementItem(Static):
    """Widget to display a single requirement with status."""
    
    def __init__(self, label: str, status: str, description: str = "") -> None:
        """
        Initialize requirement item.
        
        Args:
            label: Requirement name
            status: Status icon (✓, ✗, ⚠)
            description: Optional description
        """
        super().__init__()
        self.label = label
        self.status = status
        self.description = description
    
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        status_color = "green" if self.status == "✓" else "red" if self.status == "✗" else "yellow"
        yield Label(f"[{status_color}]{self.status}[/] {self.label}")
        if self.description:
            yield Label(f"  [dim]{self.description}[/]")


class WelcomeScreen(BaseScreen):
    """
    Welcome screen for setup wizard.
    
    Features:
    - Bilingual welcome message
    - System requirements check
    - OS detection display
    - Navigation to backend selection
    - Integrated status footer
    """
    
    BINDINGS = [
        Binding("escape", "app.quit", "Quit", show=True),
        Binding("n", "next", "Next", show=True),
    ]
    
    def __init__(self, language: str = "en", debug: bool = False) -> None:
        """
        Initialize welcome screen.
        
        Args:
            language: Language code (en or de)
            debug: Enable debug mode
        """
        super().__init__()
        self.language = language
        self.debug = debug
        self.os_info = detect_os_info()
        # Pass logger callback to installer
        self.installer = DependencyInstaller(
            debug=debug,
            logger=lambda msg: self._log_status(msg) if debug else None
        )
    
    def _log_status(self, message: str) -> None:
        """Log message to both app and status footer."""
        # Remove Rich markup for footer
        import re
        clean_msg = re.sub(r'\[/?[^\]]+\]', '', message)
        self.update_status(clean_msg[:80])  # Truncate for footer
        
        # Also log to app if available
        if hasattr(self.app, 'log_debug'):
            self.app.log_debug(message)
    
    def compose_content(self) -> ComposeResult:
        """Create the welcome screen content."""
        yield Static(
            t("welcome.title", self.language),
            classes="title"
        )
        yield Static(
            t("welcome.subtitle", self.language),
            classes="subtitle"
        )
        
        # Sudo warning if not root
        if os.geteuid() != 0:
            yield from self._compose_sudo_warning()
        
        # System information
        yield from self._compose_system_info()
        
        # Requirements check
        yield from self._compose_requirements()
        
        # Navigation buttons
        with Horizontal(classes="button-row"):
            yield Button(
                t("welcome.button_next", self.language),
                variant="primary",
                id="btn-next"
            )
            yield Button(
                t("common.button_quit", self.language),
                variant="default",
                id="btn-quit"
            )
    
    def _compose_sudo_warning(self) -> ComposeResult:
        """Compose sudo warning card if not running as root."""
        yield Static("⚠️ Sudo-Rechte benötigt", classes="section-title")
        
        with Container(classes="card warning-card"):
            yield Label("[yellow]⚠ Kopi-Docka benötigt sudo-Rechte für:[/]")
            yield Label("  • Installation von Dependencies (rclone, tailscale, etc.)")
            yield Label("  • Kopia Repository-Operationen")
            yield Label("  • Docker-Verwaltung (Container stoppen, Volumes)")
            yield Label("  • Systemd-Timer Konfiguration")
            yield Label("")
            yield Label("[cyan]Empfehlung:[/] Wizard als sudo starten:")
            yield Label(f"[dim]$ sudo python3 {' '.join(sys.argv)}[/]")
            yield Label("")
            yield Label("[yellow]Sie können fortfahren, aber einige Features sind eingeschränkt.[/]")
    
    def _compose_system_info(self) -> ComposeResult:
        """Compose system information section."""
        yield Static(
            t("welcome.system_info", self.language),
            classes="section-title"
        )
        
        with Container(classes="card"):
            if self.os_info:
                os_line = f"{self.os_info.name} {self.os_info.version}"
                if self.os_info.version_codename:
                    os_line += f" ({self.os_info.version_codename})"
                
                yield Label(f"🐧 OS: {os_line}", classes="info-text")
                
                pkg_mgr = get_package_manager()
                if pkg_mgr:
                    yield Label(f"📦 Package Manager: {pkg_mgr}", classes="info-text")
            else:
                yield Label("⚠ Could not detect OS", classes="info-text")
    
    def _compose_requirements(self) -> ComposeResult:
        """Compose requirements check section."""
        yield Static(
            t("welcome.requirements", self.language),
            classes="section-title"
        )
        
        with Container(classes="card"):
            # Check core dependencies
            requirements = self._check_requirements()
            
            for req in requirements:
                yield RequirementItem(
                    req["label"],
                    req["status"],
                    req.get("description", "")
                )
            
            # Summary
            total = len(requirements)
            met = sum(1 for r in requirements if r["status"] == "✓")
            missing = total - met
            
            if missing == 0:
                yield Label(f"[green]✓ All requirements met[/]")
            else:
                yield Label(f"[yellow]⚠ {missing} requirement(s) need attention[/]")
    
    def _check_requirements(self) -> list[dict]:
        """
        Check system requirements.
        
        Returns:
            List of requirement dictionaries with status
        """
        self.update_status("Checking system requirements...")
        requirements = []
        
        # Check sudo/root privileges
        is_root = os.geteuid() == 0
        if is_root:
            requirements.append({
                "label": "Sudo/Root Rechte",
                "status": "✓",
                "description": "Benötigt für Installation & Docker"
            })
        else:
            requirements.append({
                "label": "Sudo/Root Rechte",
                "status": "⚠",
                "description": "WARNUNG: Einige Features benötigen sudo"
            })
        
        # Check Python version
        py_version = sys.version_info
        if py_version >= (3, 9):
            requirements.append({
                "label": f"Python {py_version.major}.{py_version.minor}",
                "status": "✓",
                "description": "Required: Python 3.9+"
            })
        else:
            requirements.append({
                "label": f"Python {py_version.major}.{py_version.minor}",
                "status": "✗",
                "description": "Required: Python 3.9+"
            })
        
        # Check Docker
        docker_installed = self.installer.check_installed("docker")
        if docker_installed:
            requirements.append({
                "label": "Docker",
                "status": "✓",
                "description": "Container backup support"
            })
        else:
            requirements.append({
                "label": "Docker",
                "status": "⚠",
                "description": "Optional"
            })
        
        # Check Kopia
        kopia_installed = self.installer.check_installed("kopia")
        if kopia_installed:
            requirements.append({
                "label": "Kopia",
                "status": "✓",
                "description": "Backup engine"
            })
        else:
            requirements.append({
                "label": "Kopia",
                "status": "⚠",
                "description": "Will be installed"
            })
        
        # Check disk space
        import shutil
        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024**3)
            if free_gb > 10:
                requirements.append({
                    "label": f"Disk Space ({free_gb:.1f} GB free)",
                    "status": "✓"
                })
            else:
                requirements.append({
                    "label": f"Disk Space ({free_gb:.1f} GB free)",
                    "status": "⚠",
                    "description": "Low space"
                })
        except Exception:
            pass
        
        self.update_status("System check complete")
        return requirements
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-quit":
            self.app.exit()
    
    def action_next(self) -> None:
        """Navigate to backend selection screen."""
        self.update_status("Loading backend selection...")
        from kopi_docka.v2.ui.screens.backend_selection import BackendSelectionScreen
        self.app.push_screen(BackendSelectionScreen(
            language=self.language,
            debug=self.debug
        ))
    
    def on_mount(self) -> None:
        """Called when screen is mounted."""
        super().on_mount()
        self.update_status("Welcome to Kopi-Docka Setup Wizard")
