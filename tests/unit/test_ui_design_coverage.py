"""
Lightweight coverage check for UI helper usage.

This test scans interactive modules (commands/cores) and reports which files
use the shared UI helpers from `helpers.ui_utils` (e.g., print_header/print_info).
It does not fail the suite, but it surfaces gaps so we can align the CLI design.
"""

from pathlib import Path

UI_TOKENS = {
    "print_header",
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "print_separator",
}


def _iter_python_files():
    root = Path(__file__).resolve().parents[2] / "kopi_docka"
    for package in ["commands", "cores"]:
        for path in (root / package).rglob("*.py"):
            if path.name.startswith("__"):
                continue
            yield path


def test_ui_design_helper_usage(capsys):
    """Report where UI helper design is (not) used."""
    with_helpers = []
    without_helpers = []

    for path in _iter_python_files():
        content = path.read_text()
        if any(token in content for token in UI_TOKENS):
            with_helpers.append(str(path))
        else:
            without_helpers.append(str(path))

    # Emit a concise report; test intentionally passes to avoid blocking CI.
    print("UI design helpers present in:")
    for p in sorted(with_helpers):
        print(f"  ✓ {p}")

    print("\nUI design helpers missing in:")
    for p in sorted(without_helpers):
        print(f"  - {p}")

    # Ensure at least one module uses the helpers (sanity check)
    assert with_helpers, "Expected at least one module to use UI design helpers."
