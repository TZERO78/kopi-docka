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
            "kopi_docka", localedir=LOCALE_DIR, languages=[lang, DEFAULT_LANG], fallback=True
        )
        _translate = translation.gettext
    except (FileNotFoundError, OSError):
        # Fallback: no translation (return original string)
        _translate = lambda x: x

    return _translate


def _(msg: str) -> str:
    """
    Translation function (underscore convention).

    Usage:
        from kopi_docka.i18n import _
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
        # Welcome
        "welcome.title": "Welcome to Kopi-Docka Setup Wizard",
        "welcome.subtitle": "Let's set up your Docker backup system",
        "welcome.system_info": "System Information",
        "welcome.requirements": "System Requirements",
        "welcome.button_next": "Next",
        # Repository Storage Selection
        "backend_selection.title": "Select Repository Storage",
        "backend_selection.subtitle": "Choose where to store your backups",
        "backend_selection.recommendation": "Recommendation",
        "backend_selection.button_next": "Next",
        # Setup
        "setup.title": "Kopi-Docka Setup Wizard",
        "setup.subtitle": "Configure your repository storage",
        "setup.select_backend": "Select repository storage",
        "setup.success": "Configuration saved successfully!",
        "setup.cancelled": "Setup cancelled",
        # Tailscale
        "tailscale.title": "Tailscale Repository Configuration",
        "tailscale.checking": "Checking Tailscale connection...",
        "tailscale.not_connected": "Not connected to Tailscale",
        "tailscale.connect_prompt": "Would you like to connect now?",
        "tailscale.loading_peers": "Loading peers...",
        "tailscale.no_peers": "No peers found in your Tailnet",
        "tailscale.select_peer": "Select peer",
        "tailscale.test_ssh": "Test SSH connection first?",
        "tailscale.backup_path": "Enter backup path on remote host",
        "tailscale.path_must_be_absolute": "Path must be absolute (start with /)",
        "tailscale.verifying_path": "Verifying remote path...",
        "tailscale.path_writable": "Remote path is writable",
        "tailscale.path_not_writable": "Remote path is not writable",
        "tailscale.confirm_config": "Save this configuration?",
        "tailscale.ssh_user": "SSH user",
        "tailscale.peer_offline": "Warning: Selected peer is offline",
        "tailscale.setup_ssh_key": "Setup SSH key for passwordless access?",
        "tailscale.generating_ssh_key": "Generating SSH key...",
        "tailscale.ssh_key_generated": "SSH key generated",
        "tailscale.copying_ssh_key": "Copying SSH key to",
        "tailscale.ssh_key_copied": "SSH key copied successfully",
        "tailscale.ssh_key_failed": "Failed to setup SSH key",
        "tailscale.connection_successful": "Connection successful",
        "tailscale.connection_failed": "Connection failed",
        "tailscale.connection_timeout": "Connection timeout",
        # Dependency Check
        "dependency_check.title": "Dependency Check",
        "dependency_check.button_next": "Next",
        # Common
        "common.button_back": "Back",
        "common.button_quit": "Quit",
        "common.button_help": "Help",
        "common.yes": "Yes",
        "common.no": "No",
        "common.cancel": "Cancel",
        "common.continue": "Continue",
    },
    "de": {
        # Welcome
        "welcome.title": "Willkommen zum Kopi-Docka Setup-Assistenten",
        "welcome.subtitle": "Richten wir Ihr Docker-Backup-System ein",
        "welcome.system_info": "Systeminformationen",
        "welcome.requirements": "Systemanforderungen",
        "welcome.button_next": "Weiter",
        # Repository-Speicher Auswahl
        "backend_selection.title": "Repository-Speicher auswählen",
        "backend_selection.subtitle": "Wählen Sie, wo Ihre Backups gespeichert werden sollen",
        "backend_selection.recommendation": "Empfehlung",
        "backend_selection.button_next": "Weiter",
        # Setup
        "setup.title": "Kopi-Docka Setup-Assistent",
        "setup.subtitle": "Konfigurieren Sie Ihren Repository-Speicher",
        "setup.select_backend": "Repository-Speicher auswählen",
        "setup.success": "Konfiguration erfolgreich gespeichert!",
        "setup.cancelled": "Setup abgebrochen",
        # Tailscale
        "tailscale.title": "Tailscale Repository-Konfiguration",
        "tailscale.checking": "Überprüfe Tailscale-Verbindung...",
        "tailscale.not_connected": "Nicht mit Tailscale verbunden",
        "tailscale.connect_prompt": "Möchten Sie jetzt verbinden?",
        "tailscale.loading_peers": "Lade Peers...",
        "tailscale.no_peers": "Keine Peers in Ihrem Tailnet gefunden",
        "tailscale.select_peer": "Peer auswählen",
        "tailscale.test_ssh": "SSH-Verbindung zuerst testen?",
        "tailscale.backup_path": "Backup-Pfad auf Remote-Host eingeben",
        "tailscale.path_must_be_absolute": "Pfad muss absolut sein (mit / beginnen)",
        "tailscale.verifying_path": "Überprüfe Remote-Pfad...",
        "tailscale.path_writable": "Remote-Pfad ist beschreibbar",
        "tailscale.path_not_writable": "Remote-Pfad ist nicht beschreibbar",
        "tailscale.confirm_config": "Diese Konfiguration speichern?",
        "tailscale.ssh_user": "SSH-Benutzer",
        "tailscale.peer_offline": "Warnung: Ausgewählter Peer ist offline",
        "tailscale.setup_ssh_key": "SSH-Schlüssel für passwortlosen Zugriff einrichten?",
        "tailscale.generating_ssh_key": "Generiere SSH-Schlüssel...",
        "tailscale.ssh_key_generated": "SSH-Schlüssel generiert",
        "tailscale.copying_ssh_key": "Kopiere SSH-Schlüssel nach",
        "tailscale.ssh_key_copied": "SSH-Schlüssel erfolgreich kopiert",
        "tailscale.ssh_key_failed": "Fehler beim Einrichten des SSH-Schlüssels",
        "tailscale.connection_successful": "Verbindung erfolgreich",
        "tailscale.connection_failed": "Verbindung fehlgeschlagen",
        "tailscale.connection_timeout": "Verbindungs-Timeout",
        # Dependency Check
        "dependency_check.title": "Abhängigkeitsprüfung",
        "dependency_check.button_next": "Weiter",
        # Common
        "common.button_back": "Zurück",
        "common.button_quit": "Beenden",
        "common.button_help": "Hilfe",
        "common.yes": "Ja",
        "common.no": "Nein",
        "common.cancel": "Abbrechen",
        "common.continue": "Weiter",
    },
}


def t(key: str, lang: Optional[str] = None) -> str:
    """
    Translation function with dot-notation keys.

    Usage:
        from kopi_docka.i18n import t
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
