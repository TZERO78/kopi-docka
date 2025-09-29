"""
Setup script for Kopi-Docka.

This script configures the package for installation via pip.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / 'README.md'
long_description = ''
if readme_file.exists():
    with open(readme_file, 'r', encoding='utf-8') as f:
        long_description = f.read()

setup(
    name='kopi-docka',
    version='1.0.0',
    description='A robust backup solution for Docker environments using Kopia',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Kopi-Docka Development Team',
    author_email='admin@example.com',
    url='https://github.com/yourusername/kopi-docka',
    license='MIT',
    
    packages=find_packages(),
    include_package_data=True,
    
    python_requires='>=3.8',
    
    install_requires=[
        'psutil>=5.9.0',
    ],
    
    extras_require={
        'systemd': [
            'systemd-python>=234',
        ],
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=3.0.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
            'mypy>=0.950',
        ],
    },
    
    entry_points={
        'console_scripts': [
            'kopi-docka=kopi_docka.__main__:main',
        ],
    },
    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: System :: Archiving :: Backup',
        'Topic :: System :: Systems Administration',
    ],
    
    keywords='docker backup kopia containers volumes database',
)