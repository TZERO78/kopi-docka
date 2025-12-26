#!/usr/bin/env bash
set -euo pipefail

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required (install node/npm)."
  exit 2
fi

FILES=$(find docs/diagrams -name '*.mmd' -print || true)
if [ -z "$FILES" ]; then
  echo "No .mmd files found in docs/diagrams"
  exit 0
fi

for f in $FILES; do
  echo "Rendering $f -> ${f%.mmd}.svg"
  npx -y @mermaid-js/mermaid-cli -i "$f" -o "${f%.mmd}.svg"
done

echo "Done. Generated SVGs can be found next to the .mmd files."
