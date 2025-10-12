"""
Main Textual Application for Kopi-Docka Setup Wizard

Modern Terminal User Interface using Textual framework.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from ..i18n import _, get_current_language


class KopiDockaApp(App):
    """Main Kopi-Docka TUI Application"""
    
    TITLE = "Kopi-Docka Setup Wizard"
    SUB_TITLE = f"v2.1 | {_('Language')}: {get_current_language().upper()}"
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    Header {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    
    Footer {
        background: $panel;
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
    """
    
    BINDINGS = [
        Binding("q", "quit", _("Quit"), show=True),
        Binding("?", "help", _("Help"), show=True),
        Binding("l", "toggle_lang", _("Language"), show=False),
    ]
    
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Footer()
    
    def action_quit(self) -> None:
        """Quit the application"""
        self.exit()
    
    def action_help(self) -> None:
        """Show help screen"""
        self.push_screen("help")
    
    def action_toggle_lang(self) -> None:
        """Toggle between EN/DE"""
        from ..i18n import get_current_language, set_language
        
        current = get_current_language()
        new_lang = "de" if current == "en" else "en"
        set_language(new_lang)
        
        # Update title
        self.sub_title = f"v2.1 | {_('Language')}: {new_lang.upper()}"
        self.refresh()


def run_setup_wizard() -> None:
    """
    Run the interactive setup wizard.
    
    This is the main entry point for the new v2.1 setup experience.
    """
    app = KopiDockaApp()
    app.run()


if __name__ == "__main__":
    run_setup_wizard()
