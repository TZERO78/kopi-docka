#!/usr/bin/env python3
"""
Generate a machine-readable JSON summary mapping components -> classes -> public methods
and extract Mermaid code blocks from `docs/ARCHITECTURE.md` into `docs/diagrams/*.mmd`.
"""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'kopi_docka'
OUT_JSON = ROOT / 'docs' / 'architecture_components.json'
MD = ROOT / 'docs' / 'ARCHITECTURE.md'
DIAG_DIR = ROOT / 'docs' / 'diagrams'
DIAG_DIR.mkdir(parents=True, exist_ok=True)

# Walk selected python modules and parse classes & methods
modules = []
for p in (SRC / 'cores').glob('*.py'):
    modules.append(p)
for p in (SRC / 'backends').glob('*.py'):
    modules.append(p)
for p in (SRC / 'helpers').glob('*.py'):
    modules.append(p)
# include top-level modules as well
for p in (SRC).glob('*.py'):
    modules.append(p)

components = {}

for mod in modules:
    try:
        src = mod.read_text()
        tree = ast.parse(src)
    except Exception:
        continue

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            name = node.name
            # public methods: functions defined on the class without leading underscore
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    mname = item.name
                    if not mname.startswith('_'):
                        methods.append(mname)
            classes.append({'name': name, 'methods': sorted(methods)})

    if classes:
        # map module path to a component key
        rel = mod.relative_to(SRC)
        components[str(rel)] = classes

# Additionally create a small index mapping known component names to files (heuristic)
component_name_map = {
    'BackupManager': 'cores/backup_manager.py',
    'KopiaRepository': 'cores/repository_manager.py',
    'RestoreManager': 'cores/restore_manager.py',
    'DockerDiscovery': 'cores/docker_discovery.py',
    'HooksManager': 'cores/hooks_manager.py',
    'KopiaPolicyManager': 'cores/kopia_policy_manager.py',
    'BackendBase': 'backends/base.py',
}

out = {'components': {}}
for comp, path in component_name_map.items():
    p = Path(path)
    key = str(p)
    cls = components.get(key) or []
    out['components'][comp] = cls

# Also include raw components discovered by module path
out['by_module'] = components

OUT_JSON.write_text(json.dumps(out, indent=2))
print('Wrote', OUT_JSON)

# Extract mermaid blocks from ARCHITECTURE.md
md_text = MD.read_text()
# regex for ```mermaid ... ```
pattern = re.compile(r"```mermaid\n([\s\S]*?)\n```", re.MULTILINE)
found = pattern.findall(md_text)
for i, block in enumerate(found, 1):
    # create reasonable name by looking at first line
    first_line = block.strip().splitlines()[0] if block.strip() else f'diagram_{i}'
    # sanitize a file name
    fname = re.sub(r"[^0-9a-zA-Z_-]", '_', first_line)[:60]
    if not fname:
        fname = f'diagram_{i}'
    mmd_path = DIAG_DIR / f'{i:02d}_{fname}.mmd'
    mmd_path.write_text(block)
    print('Wrote', mmd_path)

print('Done')
