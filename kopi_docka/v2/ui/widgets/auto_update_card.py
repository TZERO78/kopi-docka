"""
Auto-updating card widget for Kopi-Docka v2.1 Setup Wizard.

This module provides a base class for creating cards with dynamic content
that can be easily updated without manual recomposition.
"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static


class AutoUpdateCard(Container):
    """
    A helper class that creates a "card" with a title and a dynamic
    content area that can be easily updated.
    
    This base class handles:
    - Title rendering
    - Content container management
    - Efficient content updates
    
    Usage:
        class MyCard(AutoUpdateCard):
            def __init__(self):
                super().__init__(title="My Card Title", classes="card")
            
            def render_content(self) -> ComposeResult:
                yield Label("Dynamic content here")
                yield Button("Click me")
    """
    
    def __init__(self, title: str, **kwargs):
        """
        Initialize the auto-updating card.
        
        Args:
            title: The title to display at the top of the card
            **kwargs: Additional arguments passed to Container (e.g., classes, id)
        """
        self.widget_title = title
        super().__init__(**kwargs)
    
    def compose(self) -> ComposeResult:
        """
        Creates the static title and the container for dynamic content.
        
        The title is rendered once and never changes.
        The content area is a container that can be efficiently updated.
        """
        yield Static(self.widget_title, classes="section-title")
        yield Container(id="content-area")
    
    def on_mount(self) -> None:
        """Performs the initial render of the content."""
        self.update_content()
    
    def update_content(self) -> None:
        """
        Clears old content and renders new content.
        
        This method efficiently removes all old widgets and mounts
        the new widgets returned by render_content().
        
        Call this method whenever you want to refresh the card's content.
        """
        content_area = self.query_one("#content-area", Container)
        
        # Efficiently remove all old widgets
        content_area.remove_children()
        
        # Mount new widgets one by one (more predictable than unpacking generator)
        for widget in self.render_content():
            content_area.mount(widget)
    
    def render_content(self) -> ComposeResult:
        """
        Override this method in child classes to define card content.
        
        This method should yield all widgets that should be displayed
        in the card's content area.
        
        Returns:
            ComposeResult: An iterator of widgets to display
        
        Example:
            def render_content(self) -> ComposeResult:
                if self.some_condition:
                    yield Label("[green]Success![/]")
                else:
                    yield Label("[red]Error![/]")
        """
        # Default implementation yields nothing
