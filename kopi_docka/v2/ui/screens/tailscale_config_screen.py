"""
Tailscale Configuration Screen for Kopi-Docka v2.1 Setup Wizard
PRODUCTION-READY VERSION - Thread-safe, robust, secure, version-safe
"""

import asyncio
import json
import os
import shlex
import subprocess
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Button, Label, Input, Log, RadioButton, RadioSet
from textual.binding import Binding

from kopi_docka.v2.i18n import t
from kopi_docka.v2.backends.tailscale import TailscalePeer
from kopi_docka.v2.ui.base_screen import BaseScreen


class TailscaleConfigScreen(BaseScreen):
    """Tailscale configuration screen - PRODUCTION-READY"""
    
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("c", "connect", "Connect", show=True),
        Binding("r", "reload", "Reload", show=True),
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
    
    # ========================================================================
    # Helper: Thread-safe UI calls
    # ========================================================================
    
    def _ui(self, fn, *args, **kwargs):
        """
        UI-Aufruf sicher aus Worker-Threads/Coroutines.
        
        Robust wrapper for UI calls from async workers or thread workers.
        Detects whether we're in the same thread (async worker) or different thread.
        """
        import threading
        
        # Check if we're in the same thread as the app (async worker)
        if hasattr(self.app, '_thread_id') and self.app._thread_id == threading.get_ident():
            # Same thread - async worker - call directly!
            try:
                fn(*args, **kwargs)
            except Exception:
                # If direct call fails for some reason, schedule it
                self.call_after_refresh(lambda: fn(*args, **kwargs))
        else:
            # Different thread - use call_from_thread if available
            call_from_thread = getattr(self.app, "call_from_thread", None)
            if call_from_thread:
                call_from_thread(fn, *args, **kwargs)
            else:
                # Fallback for older Textual versions
                self.call_after_refresh(lambda: fn(*args, **kwargs))
    
    # ========================================================================
    # UI Composition
    # ========================================================================
    
    def compose_content(self) -> ComposeResult:
        """Initial composition - wird nur einmal aufgerufen"""
        
        # Header
        yield Static("Tailscale Backend Configuration", classes="title")
        yield Static("🔥 Secure offsite backups via your private Tailnet", classes="subtitle")
        
        # Status Section
        yield Static("Connection Status", classes="section-title")
        with Container(classes="card", id="status-card"):
            # WICHTIG: Status-Zeilen als Static, damit Rich-Markup sicher gerendert wird
            yield Static("⏳ Checking Tailscale...", id="status-label")
            yield Static("[dim]Please wait...[/]", id="status-detail")
        
        # Content Section (wird dynamisch gefüllt)
        yield Static("Configuration", classes="section-title", id="config-title")
        with Container(classes="card", id="config-card"):
            yield Static("[dim]Loading...[/]", id="config-placeholder")
        
        # Action Log
        yield Static("Actions", classes="section-title")
        with Container(classes="card"):
            yield Log(id="action-log", auto_scroll=True)
        
        # Button Row (wird dynamisch gefüllt) - Container braucht ID, Buttons NICHT!
        with Horizontal(classes="button-row", id="button-row"):
            # Initial buttons - NO IDs to avoid conflicts later!
            yield Button(t("common.button_back", self.language), variant="default", name="back")
            yield Button("🔄 Checking...", variant="default", name="reload", disabled=True)
    
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
            result = subprocess.run(
                ["tailscale", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.connected = True
                self._ui(self.update_status, "Connected - Loading peers...")
                await self._load_peers()
                
                if self.peers:
                    online_count = sum(1 for p in self.peers if p.online)
                    self._ui(self.update_status, f"Found {len(self.peers)} peer(s) ({online_count} online)")
                else:
                    self._ui(self.update_status, "No peers found")
            else:
                self.connected = False
                self._ui(self.update_status, "Not connected")
        
        except FileNotFoundError:
            self.connected = False
            self._ui(self.update_status, "Tailscale not installed")
            self._ui(self.notify, "Tailscale is not installed!", severity="error")
        
        except Exception as e:
            self.connected = False
            self._ui(self.update_status, f"Error: {e}")
            self._ui(self.notify, f"Error: {e}", severity="error")
        
        finally:
            self.checking = False
            self.call_after_refresh(self._update_ui)
    
    async def _load_peers(self) -> None:
        """Load peer information from Tailscale - DEFENSIVE PARSING"""
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
            
            peers_dict = data.get("Peer") or data.get("Peers") or {}
            self_node = (data.get("Self") or {}).get("ID")
            
            for peer_id, info in peers_dict.items():
                if self_node and peer_id == self_node:
                    continue
                
                hostname = info.get("HostName") or info.get("DNSName") or "unknown"
                ips = info.get("TailscaleIPs") or []
                ip = ips[0] if ips else None
                online = info.get("Online", False)
                os_type = info.get("OS", "unknown")
                
                if not ip:
                    continue
                
                peer = TailscalePeer(hostname=hostname, ip=ip, online=online, os=os_type)
                
                if online:
                    peer.disk_free_gb = await self._get_disk_space(ip, hostname)
                    peer.ping_ms = await self._ping_peer(hostname, ip)
                
                self.peers.append(peer)
            
            self.peers.sort(key=lambda p: (not p.online, p.ping_ms or 9999))
        
        except Exception as e:
            self._ui(self.notify, f"Error loading peers: {e}", severity="warning")
    
    async def _get_disk_space(self, ip: str, hostname: str) -> Optional[float]:
        """Get disk space via SSH - WITH FALLBACK for BusyBox/minimal systems"""
        target = ip or hostname
        ssh_user = os.getenv("KOPI_DOCKA_SSH_USER", "root")
        ssh_strict = os.getenv("KOPI_DOCKA_SSH_STRICT", "0") == "1"
        ssh_opts = [] if ssh_strict else ["-o", "StrictHostKeyChecking=no"]
        
        cmds = [
            ["ssh"] + ssh_opts + ["-o", "ConnectTimeout=2", f"{ssh_user}@{target}", 
             "df", "/", "--output=avail", "--block-size=G"],
            ["ssh"] + ssh_opts + ["-o", "ConnectTimeout=2", f"{ssh_user}@{target}", 
             "sh", "-c", "df -BG / | tail -1 | awk '{print $4}' | tr -d 'G'"]
        ]
        
        for cmd in cmds:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                if result.returncode == 0:
                    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
                    if lines:
                        return float(lines[-1].strip().rstrip("G"))
            except Exception:
                continue
        
        return None
    
    async def _ping_peer(self, hostname: str, ip: Optional[str] = None) -> Optional[int]:
        """Ping peer and return latency - USE IP to avoid MagicDNS issues"""
        target = ip or hostname
        
        try:
            result = subprocess.run(
                ["tailscale", "ping", "-c", "1", target],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "time=" in line:
                        return int(float(line.split("time=")[1].split()[0].rstrip("ms")))
        except Exception:
            pass
        return None
    
    # ========================================================================
    # UI Updates (Manual)
    # ========================================================================
    
    def _update_ui(self) -> None:
        """Update UI after status check"""
        # WICHTIG: Status-Widgets jetzt als Static holen
        status_label = self.query_one("#status-label", Static)
        status_detail = self.query_one("#status-detail", Static)
        
        if self.connected:
            status_label.update("[green]🟢 Tailscale is connected[/]")
            if self.peers:
                online_count = sum(1 for p in self.peers if p.online)
                status_detail.update(f"[cyan]Found {len(self.peers)} peer(s) ({online_count} online)[/]")
            else:
                status_detail.update("[yellow]⚠ No peers found in your Tailnet[/]")
        else:
            status_label.update("[red]🔴 Not connected to Tailscale[/]")
            status_detail.update("[dim]Click 'Connect' to start[/]")
        
        self._update_config_section()
        self._update_buttons()
    
    def _update_config_section(self) -> None:
        """Update configuration section content"""
        config_card = self.query_one("#config-card", Container)
        config_card.remove_children()
        
        if self.connected and self.peers:
            config_card.mount(Static("Select Backup Target", classes="section-subtitle"))
            
            radio_set = RadioSet(id="peer-selection")
            for idx, peer in enumerate(self.peers):
                icon = "🟢" if peer.online else "🔴"
                disk = f"{peer.disk_free_gb:.1f}GB" if peer.disk_free_gb else "?"
                ping = f"{peer.ping_ms}ms" if peer.ping_ms else "?"
                status = "Online" if peer.online else "Offline"
                
                radio_set.mount(RadioButton(
                    f"{icon} {peer.hostname} ({peer.ip}) | {disk} | {ping} | {status}",
                    id=f"peer-{idx}"
                ))
            
            config_card.mount(radio_set)
            
            # Auto-select first peer
            if self.peers:
                def select_first():
                    try:
                        first_button = self.query_one("#peer-0", RadioButton)
                        if first_button:
                            first_button.value = True
                    except Exception:
                        pass
                self.call_after_refresh(select_first)
            
            config_card.mount(Static("Backup Path on Remote Host:", classes="section-subtitle"))
            config_card.mount(Input(placeholder="/backup/kopi-docka", value="/backup/kopi-docka", id="backup-path"))
            config_card.mount(Label("[dim]Must be an absolute path starting with /[/]", classes="hint"))
        
        elif self.connected and not self.peers:
            config_card.mount(Label("[yellow]⚠ No peers found in your Tailnet[/]"))
            config_card.mount(Label("[dim]Make sure other devices are connected to Tailscale[/]"))
        
        else:
            config_card.mount(Label("[yellow]You must connect to Tailscale to continue[/]"))
            config_card.mount(Label("[dim]Tip: Use --operator flag to avoid sudo in future[/]"))
    
    def _update_buttons(self) -> None:
        """Update button row based on state"""
        button_row = self.query_one("#button-row", Horizontal)
        button_row.remove_children()
        
        if self.connected and self.peers:
            button_row.mount(Button(t("common.button_back", self.language), variant="default", name="back"))
            button_row.mount(Button("Test Connection", variant="default", name="test"))
            button_row.mount(Button("Save & Continue", variant="primary", name="save"))
        else:
            button_row.mount(Button(t("common.button_back", self.language), variant="default", name="back"))
            if not self.connected:
                button_row.mount(Button("🔗 Connect", variant="primary", name="connect"))
                button_row.mount(Button("⚙️ Setup Operator", variant="default", name="operator"))
            button_row.mount(Button("🔄 Reload", variant="default", name="reload"))
    
    # ========================================================================
    # Helpers
    # ========================================================================
    
    def _run_tailscale(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run tailscale command with sudo fallback"""
        result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Failed to run tailscale")
        
        for cmd in (["tailscale", *args], ["sudo", "tailscale", *args]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if result.returncode == 0 or "https://login.tailscale.com" in (result.stdout + result.stderr):
                    return result
            except Exception:
                continue
        
        return result
    
    # ========================================================================
    # Actions
    # ========================================================================
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle all button presses"""
        button_name = event.button.name
        
        if button_name == "back":
            self.action_back()
        elif button_name == "connect":
            self.action_connect()
        elif button_name == "operator":
            self.action_setup_operator()
        elif button_name == "reload":
            self.action_reload()
        elif button_name == "test":
            self.action_test()
        elif button_name == "save":
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
        self._ui(log.clear)
        self._ui(log.write_line, "[cyan]→ Running 'tailscale up'...[/]")
        
        try:
            result = self._run_tailscale("up", timeout=30)
            output = (result.stdout + "\n" + result.stderr).strip()
            
            auth_url = None
            for line in output.split('\n'):
                if 'https://login.tailscale.com' in line:
                    url_start = line.find('https://')
                    if url_start >= 0:
                        auth_url = line[url_start:].strip()
                        break
            
            if auth_url:
                self._ui(log.write_line, "")
                self._ui(log.write_line, "[bold yellow]╔════════════════════════════════════════╗[/]")
                self._ui(log.write_line, "[bold yellow]║  🔐 AUTHENTICATION REQUIRED           ║[/]")
                self._ui(log.write_line, "[bold yellow]╚════════════════════════════════════════╝[/]")
                self._ui(log.write_line, "")
                self._ui(log.write_line, "[bold cyan]Open this link in your browser:[/]")
                self._ui(log.write_line, "")
                self._ui(log.write_line, f"[bold green]{auth_url}[/]")
                self._ui(log.write_line, "")
                self._ui(log.write_line, "[white]Steps:[/]")
                self._ui(log.write_line, "[dim]1. Copy link (mark with mouse, Ctrl+Shift+C)[/]")
                self._ui(log.write_line, "[dim]2. Open in browser on any device[/]")
                self._ui(log.write_line, "[dim]3. Sign in to Tailscale[/]")
                self._ui(log.write_line, "[dim]4. Click 'Reload' here when done[/]")
                self._ui(self.notify, "🔐 Auth required - see log!", severity="warning", timeout=10)
                self._ui(self.update_status, "⏳ Waiting for auth...")
            else:
                if output:
                    self._ui(log.write_line, "[cyan]Output:[/]")
                    for line in output.split('\n'):
                        if line.strip():
                            self._ui(log.write_line, f"  {line}")
            
            if result.returncode == 0:
                self._ui(log.write_line, "\n[green]✓ Connected successfully![/]")
                await asyncio.sleep(2)
                await self._check_tailscale()
            else:
                if not auth_url:
                    self._ui(log.write_line, "\n[red]✗ Connection failed[/]")
        
        except subprocess.TimeoutExpired:
            self._ui(log.write_line, "\n[yellow]⚠ Timeout - auth in progress[/]")
            self._ui(self.notify, "Auth in progress - check browser", severity="information")
        except Exception as e:
            self._ui(log.write_line, f"\n[red]✗ Error: {e}[/]")
            self._ui(self.notify, f"Error: {e}", severity="error")
    
    def action_setup_operator(self) -> None:
        """Setup Tailscale operator"""
        username = os.getenv("USER", "unknown")
        log = self.query_one("#action-log", Log)
        log.clear()
        log.write_line(f"[cyan]→ Setting up operator for: {username}[/]")
        
        try:
            result = subprocess.run(
                ["sudo", "tailscale", "set", f"--operator={username}"],
                capture_output=True, text=True, timeout=10
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
        if not self.connected or not self.peers:
            self.notify("Connect to Tailscale first!", severity="warning")
            return
        
        try:
            radio_set = self.query_one("#peer-selection", RadioSet)
            if not radio_set.pressed_button:
                self.notify("Select a peer first", severity="warning")
                return
            
            idx = int(radio_set.pressed_button.id.removeprefix("peer-"))
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
        self._ui(log.clear)
        self._ui(log.write_line, f"[cyan]→ Testing {self.selected_peer.hostname} ({self.selected_peer.ip})...[/]")
        
        target = self.selected_peer.ip or self.selected_peer.hostname
        ssh_strict = os.getenv("KOPI_DOCKA_SSH_STRICT", "0") == "1"
        ssh_opts = [] if ssh_strict else ["-o", "StrictHostKeyChecking=no"]
        
        try:
            ssh_user = os.getenv("KOPI_DOCKA_SSH_USER", "root")
            result = subprocess.run(
                ["ssh"] + ssh_opts + ["-o", "ConnectTimeout=5", f"{ssh_user}@{target}", "echo", "test"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                self._ui(log.write_line, "[green]✓ SSH connection successful![/]")
                self._ui(self.notify, "Test successful!", severity="information")
            else:
                self._ui(log.write_line, "[red]✗ SSH connection failed[/]")
                if result.stderr:
                    self._ui(log.write_line, f"[dim]{result.stderr}[/]")
                self._ui(self.notify, "Test failed", severity="error")
        except Exception as e:
            self._ui(log.write_line, f"[red]✗ Error: {e}[/]")
            self._ui(self.notify, f"Error: {e}", severity="error")
    
    def action_save(self) -> None:
        """Save configuration and continue"""
        if not self.connected or not self.peers:
            self.notify("Connect first!", severity="error")
            return
        
        try:
            radio_set = self.query_one("#peer-selection", RadioSet)
            if not radio_set.pressed_button:
                self.notify("Select a peer", severity="error")
                return
            
            idx = int(radio_set.pressed_button.id.removeprefix("peer-"))
            peer = self.peers[idx]
            backup_path = self.query_one("#backup-path", Input).value.strip()
            
            if not backup_path:
                self.notify("Enter backup path", severity="error")
                return
            
            if not backup_path.startswith("/"):
                self.notify("Backup path must be absolute (start with /)", severity="error")
                return
            
            ssh_user = os.getenv("KOPI_DOCKA_SSH_USER", "root")
            host = peer.ip or peer.hostname
            ssh_strict = os.getenv("KOPI_DOCKA_SSH_STRICT", "0") == "1"
            ssh_opts = [] if ssh_strict else ["-o", "StrictHostKeyChecking=no"]
            
            log = self.query_one("#action-log", Log)
            log.clear()
            log.write_line(f"[cyan]→ Checking remote path {backup_path}...[/]")
            
            qpath = shlex.quote(backup_path)
            check = subprocess.run(
                ["ssh"] + ssh_opts + ["-o", "ConnectTimeout=5", f"{ssh_user}@{host}", 
                 "sh", "-c", f"mkdir -p {qpath} && test -w {qpath}"],
                capture_output=True, text=True, timeout=10
            )
            
            if check.returncode != 0:
                log.write_line("[red]✗ Remote path not writable![/]")
                log.write_line(f"[dim]Error: {check.stderr}[/]")
                self.notify("Remote path check failed - not writable?", severity="error")
                return
            
            log.write_line("[green]✓ Remote path is writable[/]")
            repo_path = f"sftp://{ssh_user}@{host}//{backup_path.lstrip('/')}"
            
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
            
            log.write_line("[green]✓ Configuration validated![/]")
            self.notify("Configuration saved!", severity="information")
            
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
    