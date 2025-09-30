# Makefile for Kopi-Docka

# Explicitly define the Python interpreter from our virtual environment.
# This makes sure 'make' always uses the right tools from the right workbench.
PYTHON := .venv/bin/python3

.PHONY: all clean install install-dev check-style format test build

# Default command when running 'make'
all: build

# Clean up build artifacts
clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache

# Install the package for production
install:
	pip install .

# Install for development, including test tools
install-dev:
	pip install -e ".[dev]"

# Run style and format checks
check-style:
	$(PYTHON) -m flake8 kopi_docka/
	$(PYTHON) -m black --check kopi_docka/

# Auto-format the code
format:
	$(PYTHON) -m black kopi_docka/

# Run tests
test:
	$(PYTHON) -m pytest

# Build the standalone executable
build:
	$(PYTHON) -m pyinstaller --onefile --name kopi-docka kopi_docka/__main__.py
	@echo "Build complete. The executable is located in the 'dist' directory."
# Note: Ensure that PyInstaller is properly configured to include all necessary files and dependencies.
# You may need to create a spec file for more complex setups.