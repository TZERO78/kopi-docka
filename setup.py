################################################################################
# KOPI-DOCKA
#
# @file:        setup.py
# @module:      setup
# @description: Setuptools configuration and CLI packaging for Kopi-Docka.
# @author:      Markus F. (TZERO78) & Contributors
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     2.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT-Lizenz: siehe LICENSE oder https://opensource.org/licenses/MIT
# ==============================================================================
# Changes in v2.0.0:
# - Updated version to 2.0.0 to reflect major restructuring
# - Package data now includes templates directory
# - CLI entry points unchanged for backward compatibility
################################################################################

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description (optional)
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    long_description = readme_file.read_text(encoding="utf-8")

setup(
    name="kopi-docka",
    version="2.0.0",
    description="Robust cold backups for Docker environments using Kopia",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Markus F. (TZERO78) & Contributors",
    author_email="",
    url="https://github.com/TZERO78/kopi-docka",
    project_urls={
        "Source": "https://github.com/TZERO78/kopi-docka",
        "Issues": "https://github.com/TZERO78/kopi-docka/issues",
        "Documentation": "https://github.com/TZERO78/kopi-docka#readme",
    },
    license="MIT",
    license_files=("LICENSE",),

    packages=find_packages(exclude=("tests*", "docs*", "examples*")),
    
    # Include template files
    package_data={
        "kopi_docka": [
            "templates/*.json",
        ],
    },
    
    include_package_data=True,
    zip_safe=False,

    python_requires=">=3.10",

    install_requires=[
        "psutil>=5.9.0",
        "typer>=0.12.0",
        "rich>=13.0.0",
        "pydantic>=2.0.0",
        "docker>=7.0.0",
        "jsonschema>=4.21.0",
    ],

    extras_require={
        "systemd": [
            # Optional: nur auf Linux sinnvoll verfügbar
            "systemd-python>=234",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.950",
        ],
    },

    entry_points={
        "console_scripts": [
            # CLI (Pure CLI with Rich)
            "kopi-docka=kopi_docka.cli.main:cli_main",
            # Legacy v1 CLI (kept for compatibility)
            "kopi-docka-v1=kopi_docka.__main__:main",
            # Service/Daemon-Helper
            "kopi-docka-service=kopi_docka.cores.service_manager:main",
        ],
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],

    keywords="docker backup kopia volumes cold-backup systemd restore disaster-recovery",
)
