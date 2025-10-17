"""
Internationalization (i18n) System for Kopi-Docka v2.1

Provides bilingual support (English/German) using gettext.
"""

from __future__ import annotations

import gettext
import os
from pathlib import Path
from typing import Callable, Optional

# Locale directory (relative to this file)
LOCALE_DIR = Path(__file__).parent / "locales"
DEFAULT_LANG = "en"
SUPPORTED_LANGUAGES = {"en", "de"}

# Global translation function
_translate: Optional[Callable[[str], str]] = None


def setup_i18n(lang: Optional[str] = None) -> Callable[[str], str]:
    """
    Setup internationalization system.
    
    Args:
        lang: Language code ('en' or 'de'). If None, auto-detect from environment.
    
    Returns:
        Translation function
    """
    global _translate
    
    # Auto-detect language from environment
    if lang is None:
        # Check LANGUAGE, LANG, LC_ALL environment variables
        for env_var in ["LANGUAGE", "LANG", "LC_ALL"]:
            env_value = os.getenv(env_var, "")
            if env_value:
                # Extract language code (e.g., 'de_DE.UTF-8' -> 'de')
                lang = env_value.split("_")[0].split(".")[0].lower()
                break
        
        # Fallback to default
        if not lang or lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANG
    
    # Validate language
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANG
    
    try:
        # Load translation catalog
        translation = gettext.translation(
            "kopi_docka",
            localedir=LOCALE_DIR,
            languages=[lang, DEFAULT_LANG],
            fallback=True
        )
        _translate = translation.gettext
    except (FileNotFoundError, OSError):
        # Fallback: no translation (return original string)
        _translate = lambda x: x
    
    return _translate


def _( msg: str) -> str:
    """
    Translation function (underscore convention).
    
    Usage:
        from kopi_docka.v2.i18n import _
        print(_("Welcome to Kopi-Docka!"))
    
    Args:
        msg: Message to translate
    
    Returns:
        Translated message
    """
    global _translate
    if _translate is None:
        setup_i18n()
    return _translate(msg) if _translate else msg


def get_current_language() -> str:
    """Get currently active language code"""
    # Try to detect from environment
    for env_var in ["LANGUAGE", "LANG", "LC_ALL"]:
        env_value = os.getenv(env_var, "")
        if env_value:
            lang = env_value.split("_")[0].split(".")[0].lower()
            if lang in SUPPORTED_LANGUAGES:
                return lang
    return DEFAULT_LANG


def set_language(lang: str) -> None:
    """
    Manually set language.
    
    Args:
        lang: Language code ('en' or 'de')
    """
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {lang}. Must be one of {SUPPORTED_LANGUAGES}")
    setup_i18n(lang)


# Translation dictionary (fallback when .mo files are not available)
_TRANSLATIONS = {
    "en": {
        "welcome.title": "Welcome to Kopi-Docka Setup Wizard",
        "welcome.subtitle": "Let's set up your Docker backup system",
        "welcome.system_info": "System Information",
        "welcome.requirements": "System Requirements",
        "welcome.button_next": "Next",
        "backend_selection.title": "Select Backup Backend",
        "backend_selection.subtitle": "Choose where to store your backups",
        "backend_selection.recommendation": "Recommendation",
        "backend_selection.button_next": "Next",
        "dependency_check.title": "Dependency Check",
        "dependency_check.button_next": "Next",
        "common.button_back": "Back",
        "common.button_quit": "Quit",
        "common.button_help": "Help",
    },
    "de": {
        "welcome.title": "Willkommen zum Kopi-Docka Setup-Assistenten",
        "welcome.subtitle": "Richten wir Ihr Docker-Backup-System ein",
        "welcome.system_info": "Systeminformationen",
        "welcome.requirements": "Systemanforderungen",
        "welcome.button_next": "Weiter",
        "backend_selection.title": "Backup-Backend auswählen",
        "backend_selection.subtitle": "Wählen Sie, wo Ihre Backups gespeichert werden sollen",
        "backend_selection.recommendation": "Empfehlung",
        "backend_selection.button_next": "Weiter",
        "dependency_check.title": "Abhängigkeitsprüfung",
        "dependency_check.button_next": "Weiter",
        "common.button_back": "Zurück",
        "common.button_quit": "Beenden",
        "common.button_help": "Hilfe",
    }
}


def t(key: str, lang: Optional[str] = None) -> str:
    """
    Translation function with dot-notation keys.
    
    Usage:
        from kopi_docka.v2.i18n import t
        print(t("welcome.title", "de"))
    
    Args:
        key: Translation key (e.g., "welcome.title")
        lang: Language code. If None, uses current language.
    
    Returns:
        Translated string or key if not found
    """
    if lang is None:
        lang = get_current_language()
    
    # Try fallback dictionary first
    if lang in _TRANSLATIONS and key in _TRANSLATIONS[lang]:
        return _TRANSLATIONS[lang][key]
    
    # Fallback to English
    if "en" in _TRANSLATIONS and key in _TRANSLATIONS["en"]:
        return _TRANSLATIONS["en"][key]
    
    # Last resort: return key itself
    return key


# Initialize on import
setup_i18n()
