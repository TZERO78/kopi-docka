"""
Backend configuration screen for Kopi-Docka v2.1 Setup Wizard.

This module provides backend-specific configuration with validation.
"""

from typing import Optional, Dict, Any
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Button, Label, Input
from textual.binding import Binding
from textual.validation import Function

from kopi_docka.v2.i18n import t
from kopi_docka.v2.backends import create_backend
from kopi_docka.v2.ui.base_screen import BaseScreen


class BackendConfigScreen(BaseScreen):
    """Backend configuration screen with integrated status footer."""
    
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
    ]
    
    def __init__(self, language: str = "en", backend_id: str = "filesystem", debug: bool = False) -> None:
        super().__init__()
        self.language = language
        self.backend_id = backend_id
        self.debug = debug
        self.backend = create_backend(backend_id, {})
        self.config_values: Dict[str, Any] = {}
    
    def compose_content(self) -> ComposeResult:
        yield Static("Backend-Konfiguration", classes="title")
        yield Static(f"{self.backend.display_name}", classes="subtitle")
        
        yield Static(
            "Konfigurieren Sie Ihr Backend mit den erforderlichen Parametern",
            classes="info-text"
        )
        
        yield from self._compose_config_fields()
        
        with Horizontal(classes="button-row"):
            yield Button(t("common.button_back", self.language), variant="default", id="btn-back")
            yield Button("Speichern & Weiter", variant="primary", id="btn-save")
    
    def _compose_config_fields(self) -> ComposeResult:
        """Compose backend-specific configuration fields."""
        yield Static("Konfiguration:", classes="section-title")
        
        with Container(classes="card"):
            # Backend-specific fields
            if self.backend_id == "filesystem":
                yield Label("Backup-Pfad:")
                yield Input(
                    placeholder="/mnt/backup oder /path/to/nas",
                    id="backup_path",
                    classes="config-input"
                )
                
            elif self.backend_id == "rclone":
                yield Label("Rclone Remote Name:")
                yield Input(
                    placeholder="z.B. 'gdrive' oder 'dropbox'",
                    id="remote_name",
                    classes="config-input"
                )
                yield Label("\nRemote Pfad:")
                yield Input(
                    placeholder="z.B. 'backups' oder 'kopi-docka'",
                    id="remote_path",
                    classes="config-input"
                )
                
            elif self.backend_id == "tailscale":
                yield Label("Tailscale Host:")
                yield Input(
                    placeholder="hostname oder 100.x.x.x",
                    id="tailscale_host",
                    classes="config-input"
                )
                yield Label("\nBackup-Pfad auf Remote:")
                yield Input(
                    placeholder="/mnt/backup",
                    id="backup_path",
                    classes="config-input"
                )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-save":
            self.action_save()
    
    def action_back(self) -> None:
        self.update_status("Zurück...")
        self.app.pop_screen()
    
    def action_save(self) -> None:
        """Validate and save configuration."""
        self.update_status("Validiere Konfiguration...")
        
        # Collect configuration values
        if self.backend_id == "filesystem":
            backup_path = self.query_one("#backup_path", Input).value
            if not backup_path:
                self.notify("Bitte geben Sie einen Backup-Pfad an", severity="error")
                return
            self.config_values["path"] = backup_path
            
        elif self.backend_id == "rclone":
            remote_name = self.query_one("#remote_name", Input).value
            remote_path = self.query_one("#remote_path", Input).value
            if not remote_name:
                self.notify("Bitte geben Sie einen Remote-Namen an", severity="error")
                return
            self.config_values["remote"] = remote_name
            self.config_values["path"] = remote_path or "backups"
            
        elif self.backend_id == "tailscale":
            host = self.query_one("#tailscale_host", Input).value
            path = self.query_one("#backup_path", Input).value
            if not host or not path:
                self.notify("Bitte füllen Sie alle Felder aus", severity="error")
                return
            self.config_values["host"] = host
            self.config_values["path"] = path
        
        self.update_status("Konfiguration gespeichert")
        self.notify("Konfiguration erfolgreich gespeichert!", severity="information")
        
        # Navigate to completion
        from kopi_docka.v2.ui.screens.completion import CompletionScreen
        self.app.push_screen(
            CompletionScreen(
                language=self.language,
                backend_id=self.backend_id,
                config=self.config_values,
                debug=self.debug
            )
        )
    
    def on_mount(self) -> None:
        super().on_mount()
        self.update_status(f"Konfiguriere {self.backend.display_name}...")
