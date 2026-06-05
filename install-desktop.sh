#!/bin/bash
set -euo pipefail

PYTHON=$(command -v python3 || command -v python)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/data/tincan.desktop"
TARGET="$HOME/.local/share/applications/tincan.desktop"

mkdir -p "$(dirname "$TARGET")"
sed "s|@PYTHON@|$PYTHON|g" "$TEMPLATE" > "$TARGET"
echo "Installed $TARGET"
