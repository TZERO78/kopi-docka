"""
Base Screen with integrated status footer for all wizard screens.

Provides consistent layout and Apple-inspired design.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive


class StatusFooter(Static):
    """Status footer showing debug/status messages."""
    
    status_text = reactive("Ready")
    
    def render(self) -> str:
        """Render the status text."""
        return f"⬩ {self.status_text}"
    
    def update_status(self, message: str) -> None:
        """
        Update the status message.
        
        Args:
            message: New status message (without Rich markup)
        """
        self.status_text = message


class BaseScreen(Screen):
    """
    Base screen for all wizard screens with integrated status footer.
    
    Features:
    - Automatic status footer
    - Apple-inspired design
    - Consistent layout
    """
    
    DEFAULT_CSS = """
    BaseScreen {
        background: #1a1a1a;
        color: #e8e8e8;
    }
    
    BaseScreen Container {
        background: transparent;
    }
    
    BaseScreen #content-area {
        height: 1fr;
        padding: 2 4;
        background: transparent;
    }
    
    BaseScreen StatusFooter {
        dock: bottom;
        height: 1;
        background: #2a2a2a;
        color: #a0a0a0;
        padding: 0 2;
        text-style: none;
    }
    
    /* Apple-inspired styling */
    BaseScreen Static {
        background: transparent;
    }
    
    BaseScreen .card {
        background: #242424;
        border: round #3a3a3a;
        padding: 2 3;
        margin: 1 0;
    }
    
    BaseScreen .card:hover {
        background: #2a2a2a;
        border: round #4a4a4a;
    }
    
    BaseScreen .card.selected {
        background: #0a84ff;
        border: round #0a84ff;
        color: white;
    }
    
    BaseScreen .title {
        text-style: bold;
        color: #ffffff;
        text-align: center;
        padding: 1 0;
    }
    
    BaseScreen .subtitle {
        color: #a0a0a0;
        text-align: center;
        padding: 0 0 2 0;
    }
    
    BaseScreen .section-title {
        text-style: bold;
        color: #e8e8e8;
        padding: 2 0 1 0;
    }
    
    BaseScreen .info-text {
        color: #b0b0b0;
        padding: 0 2;
    }
    
    BaseScreen Button {
        min-width: 16;
        background: #0a84ff;
        color: white;
        border: none;
        margin: 0 1;
    }
    
    BaseScreen Button:hover {
        background: #0066cc;
    }
    
    BaseScreen Button:focus {
        text-style: bold;
    }
    
    BaseScreen Button.-default {
        background: #3a3a3a;
        color: #e8e8e8;
    }
    
    BaseScreen Button.-default:hover {
        background: #4a4a4a;
    }
    """
    
    def __init__(self, **kwargs):
        """Initialize base screen."""
        super().__init__(**kwargs)
        self.status_footer = None
    
    def compose(self) -> ComposeResult:
        """
        Create the base layout with content area and status footer.
        
        Subclasses should override compose_content() instead of this method.
        """
        with Vertical():
            with Container(id="content-area"):
                yield from self.compose_content()
            
            # Add status footer
            self.status_footer = StatusFooter()
            yield self.status_footer
    
    def compose_content(self) -> ComposeResult:
        """
        Override this method in subclasses to provide screen content.
        
        This will be placed in the content area above the status footer.
        """
        yield Static("Override compose_content() in subclass")
    
    def update_status(self, message: str) -> None:
        """
        Update the status footer message.
        
        Args:
            message: Status message to display
        """
        if self.status_footer:
            self.status_footer.update_status(message)
    
    def on_mount(self) -> None:
        """Called when screen is mounted."""
        # Set initial status
        self.update_status("Ready")
