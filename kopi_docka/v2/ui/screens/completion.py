"""
Completion screen for Kopi-Docka v2.1 Setup Wizard.

This module displays the final setup summary and next steps.
"""

from typing import Dict, Any
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Button, Label
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.backends import create_backend
from kopi_docka.v2.ui.base_screen import BaseScreen


class CompletionScreen(BaseScreen):
    """Completion screen with setup summary and integrated status footer."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]
    
    def __init__(
        self,
        language: str = "en",
        backend_id: str = "filesystem",
        config: Dict[str, Any] = None,
        debug: bool = False
    ) -> None:
        super().__init__()
        self.language = language
        self.backend_id = backend_id
        self.config = config or {}
        self.debug = debug
        self.backend = create_backend(backend_id, self.config)
    
    def compose_content(self) -> ComposeResult:
        yield Static("🎉 Setup Abgeschlossen!", classes="title")
        yield Static(
            "Kopi-Docka wurde erfolgreich konfiguriert",
            classes="subtitle"
        )
        
        yield from self._compose_summary()
        yield from self._compose_next_steps()
        
        with Horizontal(classes="button-row"):
            yield Button("Beenden", variant="primary", id="btn-quit")
    
    def _compose_summary(self) -> ComposeResult:
        """Compose setup summary."""
        yield Static("Setup-Zusammenfassung:", classes="section-title")
        
        with Container(classes="card"):
            yield Label(f"✓ Backend: {self.backend.display_name}")
            
            # Show configuration details
            if self.backend_id == "filesystem":
                yield Label(f"✓ Backup-Pfad: {self.config.get('path', 'N/A')}")
            elif self.backend_id == "rclone":
                yield Label(f"✓ Remote: {self.config.get('remote', 'N/A')}")
                yield Label(f"✓ Pfad: {self.config.get('path', 'backups')}")
            elif self.backend_id == "tailscale":
                yield Label(f"✓ Host: {self.config.get('host', 'N/A')}")
                yield Label(f"✓ Pfad: {self.config.get('path', 'N/A')}")
            
            yield Label("\n✓ Abhängigkeiten installiert")
            yield Label("✓ Konfiguration gespeichert")
    
    def _compose_next_steps(self) -> ComposeResult:
        """Compose next steps information."""
        yield Static("Nächste Schritte:", classes="section-title")
        
        with Container(classes="card"):
            yield Label("1. Repository initialisieren:")
            yield Label("   [cyan]kopi-docka repository init[/]", classes="info-text")
            
            yield Label("\n2. Docker-Container entdecken:")
            yield Label("   [cyan]kopi-docka backup discover[/]", classes="info-text")
            
            yield Label("\n3. Erstes Backup erstellen:")
            yield Label("   [cyan]kopi-docka backup run[/]", classes="info-text")
            
            yield Label("\n4. Automatische Backups einrichten:")
            yield Label("   [cyan]kopi-docka service enable[/]", classes="info-text")
            
            yield Label("\n[dim]Dokumentation: https://docs.kopi-docka.io[/]")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-quit":
            self.action_quit()
    
    def action_quit(self) -> None:
        """Exit the wizard."""
        self.update_status("Setup abgeschlossen")
        self.app.exit()
    
    def on_mount(self) -> None:
        super().on_mount()
        self.update_status("Setup erfolgreich abgeschlossen! 🎉")
