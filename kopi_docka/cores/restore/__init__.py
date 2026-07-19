################################################################################
# KOPI-DOCKA
#
# @file:        __init__.py
# @module:      kopi_docka.cores.restore
# @description: Role-based restore components (first slice of Plan 0033 split).
# @author:      Markus F. (TZERO78) & KI-Assistenten
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Hinweise:
# - This package starts the role-based decomposition of restore_manager.py.
#   New restore roles land here; the monolith split itself is Plan 0033.
################################################################################

from .bind_restore import BindRestoreEngine

__all__ = ["BindRestoreEngine"]
