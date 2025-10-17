#!/usr/bin/env python3
"""
Test script for Kopi-Docka v2.1 Setup Wizard

Run this to test the interactive setup wizard.

IMPORTANT: When using sudo, make sure dependencies are available:
  Option 1: Use sudo -E to preserve environment
    $ sudo -E /path/to/venv/bin/python3 kopi_docka/v2/test_wizard.py
  
  Option 2: Install dependencies system-wide
    $ sudo pip3 install textual pydantic babel docker rich
    $ sudo python3 kopi_docka/v2/test_wizard.py
  
  Option 3: Activate venv, then use sudo with full python path
    $ source .venv/bin/activate
    $ sudo $(which python3) kopi_docka/v2/test_wizard.py
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kopi_docka.v2.ui.app import run_setup_wizard


def main():
    """Run the setup wizard"""
    parser = argparse.ArgumentParser(description="Kopi-Docka v2.1 Setup Wizard")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose output"
    )
    args = parser.parse_args()
    
    # Check for sudo/root privileges
    import os
    if os.geteuid() != 0:
        print("╔═══════════════════════════════════════════════════════════════╗")
        print("║  ⚠️  WARNUNG: Kopi-Docka Setup benötigt sudo-Rechte          ║")
        print("╚═══════════════════════════════════════════════════════════════╝")
        print("")
        print("Der Setup-Wizard benötigt root-Rechte für:")
        print("  • Installation von Dependencies (rclone, tailscale, etc.)")
        print("  • Kopia Repository-Operationen")
        print("  • Docker-Verwaltung")
        print("")
        print("Bitte starten Sie den Wizard erneut mit sudo:")
        print("")
        print("Falls Sie eine venv verwenden:")
        print(f"  $ source .venv/bin/activate")
        print(f"  $ sudo $(which python3) {' '.join(sys.argv)}")
        print("")
        print("Oder installieren Sie Dependencies system-weit:")
        print("  $ sudo pip3 install textual pydantic babel docker rich")
        print(f"  $ sudo python3 {' '.join(sys.argv)}")
        print("")
        response = input("Trotzdem fortfahren (eingeschränkte Features)? (j/N): ")
        if response.lower() not in ['j', 'ja', 'y', 'yes']:
            print("Setup abgebrochen.")
            sys.exit(1)
        print("")
    
    # Don't print anything - TUI will handle all output
    try:
        run_setup_wizard(debug=args.debug)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
