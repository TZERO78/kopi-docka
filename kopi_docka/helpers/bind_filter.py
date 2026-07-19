"""User-editable host-internal bind-mount filter (Plan 0041).

A container bind mount whose host ``source`` matches one of these prefixes or
basenames is a host observer/controller mount (monitoring, log-shipper,
control-plane) and is never backed up — the container's real data lives in its
named volumes.

Resolution (first hit wins for the user override; defaults otherwise):

1. ``KOPI_DOCKA_BIND_FILTER`` env var → explicit path.
2. ``/etc/kopi-docka.filter.json`` (next to the root config).
3. ``~/.config/kopi-docka/filter.json`` (next to the user config).
4. Shipped ``templates/bind_filter.json`` defaults.
5. Hardcoded fallback (:data:`HOST_INTERNAL_BIND_PREFIXES` /
   :data:`HOST_INTERNAL_BIND_BASENAMES` in ``constants.py``) if the shipped
   template is unreadable — so the filter never fails open due to packaging.

A user file REPLACES the shipped defaults for whichever of ``prefixes`` /
``basenames`` it defines; a missing key keeps the shipped default for that key.

Host root ``/`` is intentionally NOT part of this filter: it is hardcoded in
:meth:`kopi_docka.types.BindMountInfo.is_host_internal` as a non-removable safety
guardrail (a ``/`` source recurses into the backup destination and never
completes).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import (
    DEFAULT_CONFIG_PATHS,
    HOST_INTERNAL_BIND_BASENAMES,
    HOST_INTERNAL_BIND_PREFIXES,
)
from .logging import get_logger

logger = get_logger(__name__)

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "bind_filter.json"
_ENV_VAR = "KOPI_DOCKA_BIND_FILTER"

# Cached resolved filter: (prefixes, basenames). Populated on first access.
_cache: Optional[Tuple[Tuple[str, ...], Tuple[str, ...]]] = None


def _user_filter_path() -> Optional[Path]:
    """Return the first existing user override file, or None."""
    env = os.environ.get(_ENV_VAR)
    candidates: List[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(DEFAULT_CONFIG_PATHS["root"].parent / "kopi-docka.filter.json")
    candidates.append(DEFAULT_CONFIG_PATHS["user"].parent / "filter.json")
    for p in candidates:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def _load_json_lists(path: Path) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """Parse a filter file, returning (prefixes, basenames); None for missing keys.

    Any error (unreadable, invalid JSON, wrong shape) is logged and treated as
    "no lists" so the caller falls back to defaults — the filter never crashes a
    backup over a malformed file.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"Ignoring bind-filter file {path}: {e}")
        return None, None

    def _strlist(key: str) -> Optional[List[str]]:
        if key not in data:
            return None
        val = data.get(key)
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            logger.warning(f"Ignoring '{key}' in {path}: expected a list of strings")
            return None
        return [x.rstrip("/") for x in val if x]

    return _strlist("prefixes"), _strlist("basenames")


def _resolve() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    # Shipped defaults (fall back to constants if the template is unreadable).
    prefixes, basenames = _load_json_lists(_TEMPLATE_PATH)
    if prefixes is None:
        prefixes = list(HOST_INTERNAL_BIND_PREFIXES)
    if basenames is None:
        basenames = list(HOST_INTERNAL_BIND_BASENAMES)

    # Optional user override — replaces defaults per key it defines.
    user = _user_filter_path()
    if user is not None:
        u_prefixes, u_basenames = _load_json_lists(user)
        if u_prefixes is not None:
            prefixes = u_prefixes
        if u_basenames is not None:
            basenames = u_basenames
        logger.debug(f"Loaded bind-mount filter override from {user}")

    return tuple(prefixes), tuple(basenames)


def get_host_internal_filter() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Return the cached ``(prefixes, basenames)`` host-internal filter."""
    global _cache
    if _cache is None:
        _cache = _resolve()
    return _cache


def reset_cache() -> None:
    """Clear the cached filter (tests / after editing the override file)."""
    global _cache
    _cache = None
