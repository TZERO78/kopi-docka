"""
Kopi-Docka v2.1 Setup Wizard Screens.

This package contains all screen components for the interactive setup wizard.
"""

from kopi_docka.v2.ui.screens.welcome import WelcomeScreen
from kopi_docka.v2.ui.screens.backend_selection import BackendSelectionScreen
from kopi_docka.v2.ui.screens.dependency_check import DependencyCheckScreen
from kopi_docka.v2.ui.screens.backend_config import BackendConfigScreen
from kopi_docka.v2.ui.screens.tailscale_config_screen import TailscaleConfigScreen
from kopi_docka.v2.ui.screens.completion import CompletionScreen

__all__ = [
    "WelcomeScreen",
    "BackendSelectionScreen",
    "DependencyCheckScreen",
    "BackendConfigScreen",
    "TailscaleConfigScreen",
    "CompletionScreen",
]
