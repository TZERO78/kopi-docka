"""
Tailscale Configuration Screen for Kopi-Docka v2.1 Setup Wizard - ULTRA SIMPLE VERSION

NO custom widgets - only pure Textual standard widgets
Everything inline in compose_content()
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Static, Button, Label, Input, Log, RadioButton, RadioSet
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.backends.tailscale import TailscalePeer
from kopi_docka.v2.ui.base_screen import BaseScreen


class TailscaleConfigScreen(BaseScreen):
    """Tailscale configuration screen - ultra simplified"""
    
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("c", "connect", "Connect", show=True),
        Binding("r", "reload", "Reload", show=True),
        Binding("t", "test", "Test", show=False),
    ]
    
    def __init__(self, language: str = "en", backend_id: str = "tailscale", debug: bool = False):
        super().__init__()
        self.language = language
        self.backend_id = backend_id
        self.debug = debug
        
        # State
        self.connected = False
        self.peers: List[TailscalePeer] = []
        self.selected_peer: Optional[TailscalePeer] = None
        self.checking = False
    
    def compose_content(self) -> ComposeResult:
        """Main composition - everything inline, no custom widgets"""
        
        # Header
        yield Static("Tailscale Backend Configuration", classes="title")
        yield Static("🔥 Secure offsite backups via your private Tailnet", classes="subtitle")
        
        # ===== STATUS SECTION =====
        yield Static("Connection Status", classes="section-title")
        with Container(classes="card"):
            if self.connected:
                yield Label("[green]🟢 Tailscale is connected[/]")
                if self.peers:
                    yield Label(f"[cyan]Found {len(self.peers)} peer(s) in your Tailnet[/]")
                else:
                    yield Label("[yellow]⚠ No peers found[/]")
            else:
                yield Label("[red]🔴 Not connected to Tailscale[/]")
                yield Label("[dim]Click 'Connect' to start[/]")
        
        # ===== MAIN CONTENT =====
        if self.connected and self.peers:
            # Peer selection
            yield Static("Select Backup Target", classes="section-title")
            with ScrollableContainer(classes="card"):
                with RadioSet(id="peer-selection"):
                    for idx, peer in enumerate(self.peers):
                        # Peer info
                        icon = "🟢" if peer.online else "🔴"
                        disk = f"{peer.disk_free_gb:.1f}GB" if peer.disk_free_gb else "?"
                        ping = f"{peer.ping_ms}ms" if peer.ping_ms else "?"
                        status = "Online" if peer.online else "Offline"
                        
                        with Vertical(classes="peer-item"):
                            yield RadioButton(
                                f"{icon} {peer.hostname} ({peer.ip})",
                                value=str(idx),
                                id=f"peer-{idx}"
                            )
                            yield Label(f"[dim]  {disk} free | {ping} | {status}[/]")
            
            # Backup path
            yield Static("Backup Path on Remote Host", classes="section-title")
            with Container(classes="card"):
                yield Label("Path:")
                yield Input(
                    placeholder="/backup/kopi-docka",
                    value="/backup/kopi-docka",
                    id="backup-path"
                )
        
        elif self.connected and not self.peers:
            # Connected but no peers
            yield Static("No Peers Found", classes="section-title")
            with Container(classes="card"):
                yield Label("[yellow]⚠ No peers found in your Tailnet[/]")
                yield Label("[dim]Make sure other devices are connected[/]")
        
        else:
            # Not connected
            yield Static("Connection Required", classes="section-title")
            with Container(classes="card"):
                yield Label("[yellow]You must connect to Tailscale to continue[/]")
                yield Label("[dim]Tip: Use --operator flag to avoid sudo in future[/]")
        
        # ===== ACTION LOG (always present) =====
        yield Static("Actions", classes="section-title")
        with Container(classes="card"):
            yield Log(id="action-log", auto_scroll=True)
        
        # ===== BUTTONS =====
        with Horizontal(classes="button-row"):
            yield Button(t("common.button_back", self.language), variant="default", id="btn-back")
            
            if self.connected and self.peers:
                # Connected with peers - show test and save
                yield Button("Test Connection", variant="default", id="btn-test")
                yield Button("Save & Continue", variant="primary", id="btn-save")
            else:
                # Not connected or no peers - show connect/reload
                if not self.connected:
                    yield Button("🔗 Connect", variant="primary", id="btn-connect")
                    yield Button("⚙️ Setup Operator", variant="default", id="btn-operator")
                
                yield Button("🔄 Reload", variant="success" if not self.connected else "default", id="btn-reload")
    
    # ========================================================================
    # Lifecycle
    # ========================================================================
    
    def on_mount(self) -> None:
        """Called when screen is first mounted"""
        super().on_mount()
        self.update_status("Checking Tailscale...")
        self.run_worker(self._check_tailscale(), exclusive=True)
    
    async def _check_tailscale(self) -> None:
        """Check if Tailscale is connected and load peers"""
        self.checking = True
        
        try:
            # Run tailscale status
            result = subprocess.run(
                ["tailscale", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.connected = True
                self.update_status("Connected - Loading peers...")
                
                # Load peers
                await self._load_peers()
                
                if self.peers:
                    self.update_status(f"Found {len(self.peers)} peer(s)")
                else:
                    self.update_status("No peers found")
            else:
                self.connected = False
                self.update_status("Not connected")
        
        except FileNotFoundError:
            self.connected = False
            self.update_status("Tailscale not installed")
            self.notify("Tailscale is not installed!", severity="error")
        
        except Exception as e:
            self.connected = False
            self.update_status(f"Error: {e}")
            self.notify(f"Error: {e}", severity="error")
        
        finally:
            self.checking = False
            # Refresh UI
            await self.recompose()
    
    async def _load_peers(self) -> None:
        """Load peer information from Tailscale"""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return
            
            data = json.loads(result.stdout)
            self.peers = []
            
            # Parse peers
            for peer_id, info in data.get("Peer", {}).items():
                hostname = info.get("HostName", "unknown")
                ips = info.get("TailscaleIPs", [])
                ip = ips[0] if ips else "unknown"
                online = info.get("Online", False)
                os_type = info.get("OS", "unknown")
                
                peer = TailscalePeer(
                    hostname=hostname,
                    ip=ip,
                    online=online,
                    os=os_type
                )
                
                # Get disk space and ping for online peers
                if online:
                    peer.disk_free_gb = await self._get_disk_space(hostname)
                    peer.ping_ms = await self._ping_peer(hostname)
                
                self.peers.append(peer)
            
            # Sort: online first, then by ping
            self.peers.sort(key=lambda p: (not p.online, p.ping_ms or 9999))
        
        except Exception as e:
            self.notify(f"Error loading peers: {e}", severity="warning")
    
    async def _get_disk_space(self, hostname: str) -> Optional[float]:
        """Get disk space via SSH"""
        try:
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=2",
                 f"root@{hostname}", "df", "/", "--output=avail", "--block-size=G"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    return float(lines[1].rstrip('G'))
        except Exception:
            pass
        return None
    
    async def _ping_peer(self, hostname: str) -> Optional[int]:
        """Ping peer and return latency"""
        try:
            result = subprocess.run(
                ["tailscale", "ping", "-c", "1", hostname],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if "time=" in line:
                        time_str = line.split("time=")[1].split()[0]
                        return int(float(time_str.rstrip('ms')))
        except Exception:
            pass
        return None
    
    # ========================================================================
    # Actions
    # ========================================================================
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle all button presses"""
        button_id = event.button.id
        
        if button_id == "btn-back":
            self.action_back()
        elif button_id == "btn-connect":
            self.action_connect()
        elif button_id == "btn-operator":
            self.action_setup_operator()
        elif button_id == "btn-reload":
            self.action_reload()
        elif button_id == "btn-test":
            self.action_test()
        elif button_id == "btn-save":
            self.action_save()
    
    def action_back(self) -> None:
        """Go back"""
        self.update_status("Going back...")
        self.app.pop_screen()
    
    def action_connect(self) -> None:
        """Start Tailscale connection"""
        if self.checking:
            return
        
        self.update_status("Connecting...")
        self.run_worker(self._connect_tailscale(), exclusive=True)
    
    async def _connect_tailscale(self) -> None:
        """Run tailscale up and show auth link"""
        log = self.query_one("#action-log", Log)
        log.clear()
        
        log.write_line("[cyan]→ Running 'tailscale up'...[/]")
        
        try:
            result = subprocess.run(
                ["sudo", "tailscale", "up"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Combine stdout and stderr
            output = (result.stdout + "\n" + result.stderr).strip()
            
            # Extract auth URL
            auth_url = None
            for line in output.split('\n'):
                if 'https://login.tailscale.com' in line:
                    url_start = line.find('https://')
                    if url_start >= 0:
                        auth_url = line[url_start:].strip()
                        break
            
            # Show auth link if found
            if auth_url:
                log.write_line("")
                log.write_line("[bold yellow]╔════════════════════════════════════════╗[/]")
                log.write_line("[bold yellow]║  🔐 AUTHENTICATION REQUIRED           ║[/]")
                log.write_line("[bold yellow]╚════════════════════════════════════════╝[/]")
                log.write_line("")
                log.write_line("[bold cyan]Open this link in your browser:[/]")
                log.write_line("")
                log.write_line(f"[bold green]{auth_url}[/]")
                log.write_line("")
                log.write_line("[white]Steps:[/]")
                log.write_line("[dim]1. Copy link (mark with mouse, Ctrl+Shift+C)[/]")
                log.write_line("[dim]2. Open in browser on any device[/]")
                log.write_line("[dim]3. Sign in to Tailscale[/]")
                log.write_line("[dim]4. Click 'Reload' here when done[/]")
                
                self.notify("🔐 Auth required - see log!", severity="warning", timeout=10)
                self.update_status("⏳ Waiting for auth...")
            else:
                # Show output
                if output:
                    log.write_line("[cyan]Output:[/]")
                    for line in output.split('\n'):
                        if line.strip():
                            log.write_line(f"  {line}")
            
            # Check if successful
            if result.returncode == 0:
                log.write_line("\n[green]✓ Connected successfully![/]")
                await asyncio.sleep(2)
                await self._check_tailscale()
            else:
                if not auth_url:
                    log.write_line("\n[red]✗ Connection failed[/]")
        
        except subprocess.TimeoutExpired:
            log.write_line("\n[yellow]⚠ Timeout - auth in progress[/]")
            self.notify("Auth in progress - check browser", severity="information")
        except Exception as e:
            log.write_line(f"\n[red]✗ Error: {e}[/]")
            self.notify(f"Error: {e}", severity="error")
    
    def action_setup_operator(self) -> None:
        """Setup Tailscale operator"""
        import os
        username = os.getenv("USER", "unknown")
        
        log = self.query_one("#action-log", Log)
        log.clear()
        log.write_line(f"[cyan]→ Setting up operator for: {username}[/]")
        
        try:
            result = subprocess.run(
                ["sudo", "tailscale", "set", f"--operator={username}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                log.write_line("[green]✓ Operator configured![/]")
                log.write_line("[dim]  'tailscale' now works without sudo[/]")
                self.notify("Operator configured!", severity="information")
            else:
                log.write_line(f"[red]✗ Failed: {result.stderr}[/]")
                self.notify("Setup failed", severity="error")
        except Exception as e:
            log.write_line(f"[red]✗ Error: {e}[/]")
            self.notify(f"Error: {e}", severity="error")
    
    def action_reload(self) -> None:
        """Reload connection status"""
        self.update_status("Reloading...")
        self.run_worker(self._check_tailscale(), exclusive=True)
    
    def action_test(self) -> None:
        """Test connection to selected peer"""
        # Guards
        if not self.connected or not self.peers:
            self.notify("Connect to Tailscale first!", severity="warning")
            return
        
        try:
            radio_set = self.query_one("#peer-selection", RadioSet)
            if not radio_set.pressed_button:
                self.notify("Select a peer first", severity="warning")
                return
            
            idx = int(radio_set.pressed_button.value)
            self.selected_peer = self.peers[idx]
            
            self.update_status(f"Testing {self.selected_peer.hostname}...")
            self.run_worker(self._test_connection(), exclusive=True)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
    
    async def _test_connection(self) -> None:
        """Test SSH to selected peer"""
        if not self.selected_peer:
            return
        
        log = self.query_one("#action-log", Log)
        log.clear()
        log.write_line(f"[cyan]→ Testing {self.selected_peer.hostname}...[/]")
        
        try:
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                 f"root@{self.selected_peer.hostname}", "echo", "test"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                log.write_line("[green]✓ SSH connection successful![/]")
                self.notify("Test successful!", severity="information")
            else:
                log.write_line("[red]✗ SSH connection failed[/]")
                if result.stderr:
                    log.write_line(f"[dim]{result.stderr}[/]")
                self.notify("Test failed", severity="error")
        except Exception as e:
            log.write_line(f"[red]✗ Error: {e}[/]")
            self.notify(f"Error: {e}", severity="error")
    
    def action_save(self) -> None:
        """Save configuration and continue"""
        # Guards
        if not self.connected or not self.peers:
            self.notify("Connect first!", severity="error")
            return
        
        try:
            # Get selected peer
            radio_set = self.query_one("#peer-selection", RadioSet)
            if not radio_set.pressed_button:
                self.notify("Select a peer", severity="error")
                return
            
            idx = int(radio_set.pressed_button.value)
            peer = self.peers[idx]
            
            # Get backup path
            backup_path = self.query_one("#backup-path", Input).value
            if not backup_path:
                self.notify("Enter backup path", severity="error")
                return
            
            # Build config
            ssh_user = "root"  # TODO: Make configurable
            repo_path = f"sftp://{ssh_user}@{peer.hostname}:{backup_path}"
            
            config = {
                "type": "sftp",
                "repository_path": repo_path,
                "credentials": {
                    "peer_hostname": peer.hostname,
                    "peer_ip": peer.ip,
                    "ssh_user": ssh_user,
                    "remote_path": backup_path
                }
            }
            
            self.notify("Configuration saved!", severity="information")
            
            # Navigate to completion
            from kopi_docka.v2.ui.screens.completion import CompletionScreen
            self.app.push_screen(
                CompletionScreen(
                    language=self.language,
                    backend_id=self.backend_id,
                    config=config,
                    debug=self.debug
                )
            )
        
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")