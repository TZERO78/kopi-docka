################################################################################
# KOPI-DOCKA
#
# @file:        system_commands.py
# @module:      kopi_docka.commands.advanced
# @description: System dependency commands (admin system subgroup) - WRAPPER
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     3.4.1
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
################################################################################

"""
System dependency management commands under 'admin system'.

This module previously provided install-deps and show-deps commands,
but these were removed in v5.5.0 as part of the Hard/Soft Gate refactoring.
Users should install dependencies manually.
"""

import typer


def register(app: typer.Typer):
    """Register system commands under 'admin system'.

    Note: install-deps and show-deps commands were removed in v5.5.0.
    This function is kept for compatibility but no longer registers any commands.
    """
    pass
