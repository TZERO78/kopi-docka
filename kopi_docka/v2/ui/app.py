"""
Main Textual Application for Kopi-Docka Setup Wizard

Modern Terminal User Interface using Textual framework.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, RichLog, Static
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen
from textual.reactive import reactive

from ..i18n import _, get_current_language
from .screens import WelcomeScreen


class DebugFooter(Static):
    """Custom Footer showing debug messages."""
    
    debug_text = reactive("")
    
    def __init__(self) -> None:
        """Initialize debug footer."""
        super().__init__()
        self.debug_text = "[Debug] Ready..."
    
    def render(self) -> str:
        """Render the debug footer."""
        return self.debug_text
    
    def update_messages(self, messages: list[str]) -> None:
        """Update with new debug messages."""
        import re
        
        def strip_markup(text: str) -> str:
            """Remove Rich markup tags from text."""
            return re.sub(r'\[/?[^\]]+\]', '', text)
        
        # Show last 3 messages (truncated, without markup)
        footer_text = " | ".join([
            (strip_markup(msg)[:50] + "...") if len(strip_markup(msg)) > 50 else strip_markup(msg)
            for msg in messages[-3:]
        ])
        
        self.debug_text = f"[Debug] {footer_text}"


class DebugScreen(Screen):
    """Full-screen debug log viewer."""
    
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Close", show=True),
        Binding("q", "app.pop_screen", "Close", show=False),
    ]
    
    def __init__(self, debug_messages: list[str]) -> None:
        """Initialize with existing debug messages."""
        super().__init__()
        self.debug_messages = debug_messages
    
    def compose(self) -> ComposeResult:
        """Create the debug screen layout."""
        with Vertical():
            yield Static("[bold cyan]Debug Log[/] (Press ESC to close)", id="debug-title")
            debug_log = RichLog(id="full-debug-log", wrap=True, highlight=True)
            yield debug_log
    
    def on_mount(self) -> None:
        """Load all debug messages when screen mounts."""
        debug_log = self.query_one("#full-debug-log", RichLog)
        for msg in self.debug_messages:
            debug_log.write(msg)


class KopiDockaApp(App):
    """Main Kopi-Docka TUI Application"""
    
    TITLE = "Kopi-Docka Setup Wizard"
    SUB_TITLE = f"v2.1 | {_('Language')}: {get_current_language().upper()}"
    
    def __init__(self, debug: bool = False, **kwargs):
        """
        Initialize the app.
        
        Args:
            debug: Enable debug mode
            **kwargs: Additional arguments for App
        """
        super().__init__(**kwargs)
        self.debug_mode = debug  # Use debug_mode to avoid conflict with App.debug property
        self.debug_messages = []  # Store all debug messages
        self.footer_messages = []  # Last 3 messages for footer
    
    CSS = """
    /* Apple-inspired dark theme */
    Screen {
        background: #1a1a1a;
    }
    
    Header {
        background: #2a2a2a;
        color: #ffffff;
        text-style: bold;
    }
    
    Footer {
        background: #2a2a2a;
        color: #a0a0a0;
    }
    
    /* Horizontal button layout */
    .button-row {
        layout: horizontal;
        align: center middle;
        height: auto;
        margin-top: 2;
    }
    
    .step-header {
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }
    
    .description {
        color: $text-muted;
        margin-left: 4;
        margin-bottom: 1;
    }
    
    #main {
        padding: 2 4;
        height: 100%;
    }
    
    #actions {
        layout: horizontal;
        height: auto;
        margin-top: 2;
        align: center middle;
    }
    
    #actions Button {
        margin: 0 1;
    }
    
    .backend-option {
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
        background: $surface;
    }
    
    .backend-option:hover {
        background: $boost;
        border: solid $accent;
    }
    
    .backend-option.selected {
        background: $primary;
        color: $text;
        border: solid $accent;
    }
    
    DebugScreen {
        background: $surface;
    }
    
    DebugScreen #debug-title {
        background: $primary;
        color: $text;
        text-align: center;
        padding: 1;
        text-style: bold;
    }
    
    DebugScreen #full-debug-log {
        border: solid $primary;
        background: $surface-darken-1;
        height: 100%;
    }
    
    DebugFooter {
        dock: bottom;
        background: $boost;
        color: $text;
        height: 1;
        padding: 0 1;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", _("Quit"), show=True),
        Binding("?", "help", _("Help"), show=True),
        Binding("d", "show_debug", "Debug", show=True, key_display="D"),
        Binding("l", "toggle_lang", _("Language"), show=False),
    ]
    
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        
        # Use either DebugFooter or standard Footer
        if self.debug_mode:
            yield DebugFooter()
        else:
            yield Footer()
    
    def log_debug(self, message: str) -> None:
        """
        Log a debug message.
        
        Args:
            message: The debug message to log
        """
        if self.debug_mode:
            # Store in full history
            self.debug_messages.append(message)
            
            # Keep last 3 for footer
            self.footer_messages.append(message)
            if len(self.footer_messages) > 3:
                self.footer_messages.pop(0)
            
            # Update footer with last 3 messages
            self._update_footer()
    
    def _update_footer(self) -> None:
        """Update footer with recent debug messages."""
        if not self.debug_mode or not self.footer_messages:
            return
        
        # Update the DebugFooter widget
        try:
            debug_footer = self.query_one(DebugFooter)
            debug_footer.update_messages(self.footer_messages)
        except Exception:
            # DebugFooter not found, ignore
            pass
    
    def on_mount(self) -> None:
        """Called when app starts - show welcome screen"""
        if self.debug_mode:
            self.log_debug("[bold cyan]Debug Mode Enabled[/]")
            self.log_debug(f"Starting Kopi-Docka v2.1 Setup Wizard")
        
        self.push_screen(WelcomeScreen(
            language=get_current_language(),
            debug=self.debug_mode
        ))
    
    def action_quit(self) -> None:
        """Quit the application"""
        self.exit()
    
    def action_help(self) -> None:
        """Show help screen"""
        self.push_screen("help")
    
    def action_show_debug(self) -> None:
        """Show full debug log screen."""
        if self.debug_mode:
            self.push_screen(DebugScreen(self.debug_messages))
    
    def action_toggle_lang(self) -> None:
        """Toggle between EN/DE"""
        from ..i18n import get_current_language, set_language
        
        current = get_current_language()
        new_lang = "de" if current == "en" else "en"
        set_language(new_lang)
        
        # Update title
        if not self.debug_mode:
            self.sub_title = f"v2.1 | {_('Language')}: {new_lang.upper()}"
        self.refresh()


def run_setup_wizard(debug: bool = False) -> None:
    """
    Run the interactive setup wizard.
    
    This is the main entry point for the new v2.1 setup experience.
    
    Args:
        debug: Enable debug mode with verbose output
    """
    app = KopiDockaApp(debug=debug)
    app.run()


if __name__ == "__main__":
    run_setup_wizard()
