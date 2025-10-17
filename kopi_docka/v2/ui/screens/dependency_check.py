"""
Dependency check and installation screen for Kopi-Docka v2.1 Setup Wizard.

This module handles checking and installing required dependencies for the
selected backend with progress indicators and error handling.
"""

from typing import Optional
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, Label, ProgressBar, Log
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.backends import create_backend
from kopi_docka.v2.utils.dependency_installer import DependencyInstaller, InstallStatus, InstallResult
from kopi_docka.v2.ui.base_screen import BaseScreen


class DependencyItem(Container):
    """Widget to display a single dependency with status."""
    
    def __init__(self, name: str, installed: bool, required: bool = True) -> None:
        super().__init__()
        self.dep_name = name
        self.installed = installed
        self.required = required
    
    def compose(self) -> ComposeResult:
        if self.installed:
            status = "[green]✓ Installiert[/]"
        else:
            status = "[red]✗ Fehlt[/]" if self.required else "[yellow]⚠ Optional[/]"
        
        req_label = " (Erforderlich)" if self.required else " (Optional)"
        yield Label(f"{status} {self.dep_name}{req_label}")


class DependencyCheckScreen(BaseScreen):
    """Dependency check and installation screen with integrated status footer."""
    
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("i", "install", "Install", show=True),
        Binding("s", "skip", "Skip", show=True),
    ]
    
    def __init__(self, language: str = "en", backend_id: str = "filesystem", debug: bool = False) -> None:
        super().__init__()
        self.language = language
        self.backend_id = backend_id
        self.debug = debug
        self.installer = DependencyInstaller(
            debug=debug,
            logger=lambda msg: self._log_status(msg) if debug else None
        )
        self.backend = create_backend(backend_id, {})
        
        # WICHTIG: Dependencies früh prüfen, BEVOR compose() aufgerufen wird
        self.missing_deps = self._check_dependencies()
        self.installing = False
    
    def _check_dependencies(self) -> list[str]:
        """Check and return missing dependencies"""
        all_deps = self.backend.check_dependencies()
        missing = []
        
        for dep in all_deps:
            if not self.installer.check_installed(dep):
                missing.append(dep)
        
        return missing
    
    def _log_status(self, message: str) -> None:
        import re
        clean_msg = re.sub(r'\[/?[^\]]+\]', '', message)
        self.update_status(clean_msg[:80])
        if hasattr(self.app, 'log_debug'):
            self.app.log_debug(message)
    
    def compose_content(self) -> ComposeResult:
        yield Static(t("dependency_check.title", self.language), classes="title")
        yield Static(f"Backend: {self.backend.display_name}", classes="subtitle")
        
        yield from self._compose_dependencies()
        yield from self._compose_progress_section()
        yield from self._compose_buttons()
    
    def _compose_dependencies(self) -> ComposeResult:
        yield Static("Abhängigkeitsstatus", classes="section-title")
        
        with Container(classes="card"):
            all_deps = self.backend.check_dependencies()
            
            for dep in all_deps:
                # Nutze self.missing_deps aus __init__
                installed = dep not in self.missing_deps
                yield DependencyItem(dep, installed, required=True)
            
            if not self.missing_deps:
                yield Label("[green]✓ Alle Abhängigkeiten installiert![/]")
            else:
                yield Label(f"[yellow]⚠ {len(self.missing_deps)} Abhängigkeit(en) fehlen[/]")
    
    def _compose_progress_section(self) -> ComposeResult:
        # Nur erstellen wenn Dependencies fehlen
        if not self.missing_deps:
            return  # Keine Komponenten erstellen!
        
        # Container initial versteckt, wird bei Installation sichtbar
        with Container(id="progress-section", classes="card hidden"):
            yield Static("Installation", classes="section-title")
            yield ProgressBar(id="install-progress", total=100, show_eta=False)
            yield Log(id="install-log", auto_scroll=True, classes="install-log")
    
    def _compose_buttons(self) -> ComposeResult:
        with Horizontal(classes="button-row"):
            yield Button(t("common.button_back", self.language), variant="default", id="btn-back")
            
            if self.missing_deps:
                yield Button("Installieren", variant="primary", id="btn-install")
                yield Button("Überspringen", variant="default", id="btn-skip")
            else:
                yield Button(t("dependency_check.button_next", self.language), variant="primary", id="btn-next")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-install":
            self.action_install()
        elif event.button.id == "btn-skip":
            self.action_skip()
        elif event.button.id == "btn-next":
            self.action_next()
    
    def action_back(self) -> None:
        self.update_status("Zurück...")
        self.app.pop_screen()
    
    def action_install(self) -> None:
        if self.installing:
            return
        
        self.installing = True
        self.update_status("Starte Installation...")
        
        # Progress-Section sichtbar machen
        progress_section = self.query_one("#progress-section")
        progress_section.remove_class("hidden")
        
        self.query_one("#btn-install", Button).disabled = True
        self.query_one("#btn-skip", Button).disabled = True
        self.query_one("#btn-back", Button).disabled = True
        
        self.run_worker(self._install_dependencies(), exclusive=True)
    
    async def _install_dependencies(self) -> None:
        log = self.query_one("#install-log", Log)
        progress = self.query_one("#install-progress", ProgressBar)
        
        total_deps = len(self.missing_deps)
        success_count = 0
        
        for idx, dep in enumerate(self.missing_deps):
            # Fix: Progress sollte (idx+1) sein, nicht idx
            progress.update(progress=((idx + 1) / total_deps) * 100)
            
            # Install with rich result
            log.write_line(f"[cyan]Installiere {dep}...[/]")
            self.update_status(f"Installiere {dep}...")
            
            result: InstallResult = self.installer.install(dep)
            
            # Show command output if available and in debug mode
            if result.command_output and self.debug:
                for line in result.command_output.split('\n')[:5]:  # First 5 lines only
                    if line.strip():
                        log.write_line(f"[dim]  {line}[/]")
            
            # Handle different statuses
            if result.status == InstallStatus.SUCCESS:
                # Verify installation
                if self.installer.check_installed(dep):
                    log.write_line(f"[green]✓ {dep} verifiziert[/]")
                    success_count += 1
                    
                    # Post-install hook for Tailscale
                    if dep == "tailscale":
                        await self._handle_tailscale_post_install(log)
                else:
                    log.write_line(f"[red]✗ {dep} Verifikation fehlgeschlagen![/]")
                    log.write_line(f"[dim]  Installation meldete Erfolg aber Befehl nicht gefunden[/]")
                    log.write_line(f"[dim]  Versuchen Sie: which {dep}[/]")
            
            elif result.status == InstallStatus.ALREADY_INSTALLED:
                log.write_line(f"[yellow]○ {dep} bereits installiert[/]")
                success_count += 1
                
                # Post-install hook auch bei bereits installiert (wichtig für Tailscale!)
                if dep == "tailscale":
                    await self._handle_tailscale_post_install(log)
            
            elif result.status == InstallStatus.UNSUPPORTED_OS:
                log.write_line(f"[yellow]⚠ {result.message}[/]")
                if result.error_details:
                    log.write_line(f"[dim]  {result.error_details}[/]")
            
            else:
                # FAILED, TIMEOUT, PERMISSION_ERROR, etc.
                log.write_line(f"[red]✗ {result.message}[/]")
                if result.error_details:
                    for line in result.error_details.split('\n')[:10]:  # First 10 lines
                        if line.strip():
                            log.write_line(f"[dim]  {line}[/]")
        
        progress.update(progress=100)
        
        # Final summary
        if success_count == total_deps:
            log.write_line(f"\n[green]✓ Alle {total_deps} Abhängigkeiten bereit![/]")
            self.update_status("Installation erfolgreich")
            await asyncio.sleep(1)
            self._show_next_button()
        else:
            log.write_line(f"\n[yellow]⚠ {success_count}/{total_deps} bereit[/]")
            self.update_status(f"{success_count}/{total_deps} installiert")
            self.query_one("#btn-back", Button).disabled = False
            self.query_one("#btn-skip", Button).disabled = False
        
        self.installing = False
    
    async def _handle_tailscale_post_install(self, log: Log) -> None:
        """Post-install hook for Tailscale: Check connection and start if needed"""
        import subprocess
        import json
        
        log.write_line("\n[cyan]→ Prüfe Tailscale-Verbindung...[/]")
        await asyncio.sleep(0.5)  # Brief pause for UI
        
        try:
            # Check if Tailscale is running
            result = subprocess.run(
                ["tailscale", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Already connected
                log.write_line("[green]  ✓ Tailscale ist bereits verbunden![/]")
                
                # Try to show peer count
                try:
                    status_json = subprocess.run(
                        ["tailscale", "status", "--json"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if status_json.returncode == 0:
                        data = json.loads(status_json.stdout)
                        peer_count = len(data.get("Peer", {}))
                        if peer_count > 0:
                            log.write_line(f"[cyan]  → {peer_count} Peer(s) im Tailnet gefunden[/]")
                except Exception:
                    pass  # Nicht kritisch
            else:
                # Not connected - start Tailscale
                log.write_line("[yellow]  ⚠ Tailscale noch nicht verbunden[/]")
                log.write_line("[cyan]  → Führe 'tailscale up' aus...[/]")
                log.write_line("[dim]  (Authentifizierungs-Link erscheint unten)[/]")
                
                # Start Tailscale WITHOUT capturing output so user sees the auth link
                try:
                    result = subprocess.run(
                        ["sudo", "tailscale", "up"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    # Show the output (contains auth URL)
                    if result.stdout:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                log.write_line(f"[cyan]  {line}[/]")
                    
                    if result.returncode == 0:
                        log.write_line("[green]  ✓ Tailscale verbunden![/]")
                    else:
                        log.write_line("[yellow]  ⚠ Authentifizierung ausstehend[/]")
                        if result.stderr:
                            for line in result.stderr.strip().split('\n')[:5]:
                                if line.strip():
                                    log.write_line(f"[dim]  {line}[/]")
                
                except subprocess.TimeoutExpired:
                    log.write_line("[yellow]  ⚠ Tailscale-Start läuft...[/]")
                    log.write_line("[cyan]  → Öffnen Sie den Browser und authentifizieren Sie sich[/]")
                except Exception as e:
                    log.write_line(f"[red]  ✗ Fehler beim Starten: {str(e)}[/]")
        
        except FileNotFoundError:
            log.write_line("[red]  ✗ Tailscale-Befehl nicht gefunden[/]")
        except Exception as e:
            log.write_line(f"[red]  ✗ Fehler bei Tailscale-Check: {str(e)}[/]")
    
    def _show_next_button(self) -> None:
        button_container = self.query_one(".button-row")
        button_container.query("#btn-install").remove()
        button_container.query("#btn-skip").remove()
        button_container.mount(
            Button(t("dependency_check.button_next", self.language), variant="primary", id="btn-next")
        )
    
    def action_skip(self) -> None:
        self.notify("Abhängigkeiten übersprungen", severity="warning")
        self.action_next()
    
    def action_next(self) -> None:
        self.update_status("Zur Konfiguration...")
        
        # Spezialbehandlung für Tailscale - direkt zum spezialisierten Screen
        if self.backend_id == "tailscale":
            from kopi_docka.v2.ui.screens.tailscale_config_screen import TailscaleConfigScreen
            self.app.push_screen(TailscaleConfigScreen(
                language=self.language,
                backend_id=self.backend_id,
                debug=self.debug
            ))
        else:
            # Für alle anderen Backends normaler Config Screen
            from kopi_docka.v2.ui.screens.backend_config import BackendConfigScreen
            self.app.push_screen(BackendConfigScreen(
                language=self.language,
                backend_id=self.backend_id,
                debug=self.debug
            ))
    
    def on_mount(self) -> None:
        super().on_mount()
        self.update_status("Prüfe Abhängigkeiten...")
