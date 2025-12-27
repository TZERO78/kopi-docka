################################################################################
# KOPI-DOCKA
#
# @file:        __init__.py
# @module:      kopi_docka.commands.advanced
# @description: Advanced administration commands (admin subcommand group)
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
Advanced Administration Commands

This module provides the 'admin' subcommand group with administrative functions:
- admin config  - Configuration management (show, edit, new, reset)
- admin repo    - Repository management (init, maintenance, status)
- admin service - Systemd service management (daemon, write-units)
- admin system  - System dependency management (install-deps, show-deps)
- admin snapshot- Snapshot management (list, estimate-size)
"""

import typer

# Create the admin app
admin_app = typer.Typer(
    name="admin",
    help="Advanced administration tools for power users.",
    no_args_is_help=True,
)

# Import and register subcommand modules
from . import config_commands
from . import repo_commands
from . import service_commands
from . import system_commands
from . import snapshot_commands
from . import notification_commands

# Register subcommand groups
config_commands.register(admin_app)
repo_commands.register(admin_app)
service_commands.register(admin_app)
system_commands.register(admin_app)
snapshot_commands.register(admin_app)
notification_commands.register(admin_app)
