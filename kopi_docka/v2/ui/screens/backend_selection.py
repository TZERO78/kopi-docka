"""
Backend selection screen for Kopi-Docka v2.1 Setup Wizard.

This module provides interactive backend selection with detailed descriptions,
recommendations, and help functionality.
"""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, Label, OptionList
from textual.widgets.option_list import Option
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.utils.dependency_installer import DependencyInstaller
from kopi_docka.v2.ui.base_screen import BaseScreen


class BackendSelectionScreen(BaseScreen):
    """
    Backend selection screen for setup wizard.
    
    Features:
    - Display all available backends with details
    - Show recommendations based on system
    - Provide help and guidance
    - Navigation to dependency check
    - Integrated status footer
    """
    
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("n", "next", "Next", show=True),
        Binding("h", "help", "Help", show=True),
    ]
    
    def __init__(self, language: str = "en", debug: bool = False) -> None:
        """
        Initialize backend selection screen.
        
        Args:
            language: Language code (en or de)
            debug: Enable debug mode
        """
        super().__init__()
        self.language = language
        self.debug = debug
        self.installer = DependencyInstaller(
            debug=debug,
            logger=lambda msg: self._log_status(msg) if debug else None
        )
        self.selected_backend: Optional[str] = None
        self.backends_info = self._get_backends_info()
    
    def _log_status(self, message: str) -> None:
        """Log message to status footer."""
        import re
        clean_msg = re.sub(r'\[/?[^\]]+\]', '', message)
        self.update_status(clean_msg[:80])
        
        if hasattr(self.app, 'log_debug'):
            self.app.log_debug(message)
    
    def compose_content(self) -> ComposeResult:
        """Create the backend selection content."""
        yield Static(
            t("backend_selection.title", self.language),
            classes="title"
        )
        yield Static(
            t("backend_selection.subtitle", self.language),
            classes="subtitle"
        )
        
        # Show recommendation
        yield from self._compose_recommendation()
        
        # Backend options
        yield from self._compose_backend_options()
        
        # Navigation buttons
        with Horizontal(classes="button-row"):
            yield Button(
                t("common.button_back", self.language),
                variant="default",
                id="btn-back"
            )
            yield Button(
                t("common.button_help", self.language),
                variant="default",
                id="btn-help"
            )
            yield Button(
                t("backend_selection.button_next", self.language),
                variant="primary",
                id="btn-next",
                disabled=True
            )
    
    def _get_backends_info(self) -> dict:
        """Get information about all available backends."""
        backends = {}
        
        backends["filesystem"] = {
            "name": "Filesystem / NAS",
            "description": "Lokaler oder Netzwerk-Speicher (NFS, CIFS, SMB)",
            "features": [
                "✓ Einfachste Konfiguration",
                "✓ Perfekt für NAS-Geräte",
                "✓ Schnelle Backups im lokalen Netzwerk"
            ],
            "complexity": 1,
            "setup_time": "1 Min",
            "best_for": "Lokale/NAS Backups"
        }
        
        backends["rclone"] = {
            "name": "Cloud Storage (Rclone)",
            "description": "70+ Cloud-Provider (Google Drive, S3, OneDrive, ...)",
            "features": [
                "✓ Größte Auswahl an Anbietern",
                "✓ Offsite-Backup (sicher)",
                "✓ Oft kostenlose Kontingente"
            ],
            "complexity": 2,
            "setup_time": "5 Min",
            "best_for": "Cloud Backups"
        }
        
        backends["tailscale"] = {
            "name": "Tailscale Offsite",
            "description": "Sicheres Backup zu entfernten Tailscale-Peers",
            "features": [
                "✓ Verschlüsseltes WireGuard",
                "✓ Automatische Peer-Erkennung",
                "✓ Perfekt für Offsite"
            ],
            "complexity": 3,
            "setup_time": "3 Min",
            "best_for": "Sichere Offsite"
        }
        
        return backends
    
    def _compose_recommendation(self) -> ComposeResult:
        """Compose recommendation section."""
        recommendation = self._get_recommendation()
        
        if recommendation:
            with Container(classes="card"):
                yield Label(
                    f"💡 Empfehlung: {recommendation['text']}",
                    classes="section-title"
                )
                yield Label(
                    recommendation['reason'],
                    classes="info-text"
                )
    
    def _get_recommendation(self) -> Optional[dict]:
        """Analyze system and provide backend recommendation."""
        has_tailscale = self.installer.check_installed("tailscale")
        has_rclone = self.installer.check_installed("rclone")
        
        if has_tailscale:
            return {
                "backend": "tailscale",
                "text": "Tailscale Offsite",
                "reason": "Tailscale ist bereits installiert - perfekt für sichere Remote-Backups"
            }
        elif has_rclone:
            return {
                "backend": "rclone",
                "text": "Cloud Storage",
                "reason": "Rclone ist bereits installiert - nutzen Sie über 70 Cloud-Anbieter"
            }
        else:
            return {
                "backend": "filesystem",
                "text": "Filesystem / NAS",
                "reason": "Einfachster Start - weitere Ziele können später hinzugefügt werden"
            }
    
    def _compose_backend_options(self) -> ComposeResult:
        """Compose backend selection options."""
        yield Static("Backend auswählen:", classes="section-title")
        
        recommendation = self._get_recommendation()
        recommended_backend = recommendation["backend"] if recommendation else None
        
        option_list = OptionList(id="backend-list")
        
        for backend_id, info in self.backends_info.items():
            is_recommended = backend_id == recommended_backend
            
            option_text = f"{info['name']}"
            if is_recommended:
                option_text += " ⭐"
            
            complexity = "⭐" * info['complexity']
            option_text += f"\n  Komplexität: {complexity} | Setup: {info['setup_time']}"
            option_text += f"\n  {info['description']}"
            
            option_list.add_option(Option(option_text, id=backend_id))
        
        yield option_list
    
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle backend selection."""
        self.selected_backend = event.option.id
        
        next_button = self.query_one("#btn-next", Button)
        next_button.disabled = False
        
        info = self.backends_info.get(self.selected_backend)
        if info:
            self.update_status(f"Ausgewählt: {info['name']}")
            self.notify(
                f"{info['name']}\nAm besten für: {info['best_for']}",
                title="Backend ausgewählt",
                severity="information"
            )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-help":
            self.action_help()
        elif event.button.id == "btn-next":
            self.action_next()
    
    def action_back(self) -> None:
        """Navigate back to welcome screen."""
        self.update_status("Zurück...")
        self.app.pop_screen()
    
    def action_help(self) -> None:
        """Show help information."""
        help_text = """[bold]Backend-Auswahl Hilfe[/]

[cyan]Filesystem / NAS:[/]
• Lokale Backups oder NAS-Geräte
• Schnellste Option
• Keine Internet-Verbindung nötig

[cyan]Cloud Storage:[/]
• Offsite-Backups in die Cloud
• 70+ Anbieter verfügbar
• Sicher bei lokalen Problemen

[cyan]Tailscale Offsite:[/]
• Verschlüsselte Remote-Backups
• Nutzt Ihr Tailscale-Netzwerk
• Sehr sicher durch WireGuard

[yellow]💡 Tipp:[/] Mehrere Backends möglich!"""
        
        self.notify(help_text, title="Hilfe", timeout=20)
    
    def action_next(self) -> None:
        """Navigate to dependency check screen."""
        if not self.selected_backend:
            self.notify("Bitte wählen Sie zuerst ein Backend aus.", severity="warning")
            return
        
        self.update_status("Prüfe Dependencies...")
        from kopi_docka.v2.ui.screens.dependency_check import DependencyCheckScreen
        self.app.push_screen(
            DependencyCheckScreen(
                language=self.language,
                backend_id=self.selected_backend,
                debug=self.debug
            )
        )
    
    def on_mount(self) -> None:
        """Called when screen is mounted."""
        super().on_mount()
        self.update_status("Backend auswählen...")
