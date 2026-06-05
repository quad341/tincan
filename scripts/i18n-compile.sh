#!/usr/bin/env bash
# i18n-compile.sh — compile .ts translation files to binary .qm files.
#
# Usage: ./scripts/i18n-compile.sh [LOCALE...]
#   LOCALE: e.g. fr de ja  (default: all existing .ts files)
#
# Requires: lrelease (from pyside6-tools or python3-pyside6)
#   Fedora:  sudo dnf install python3-pyside6
#   Ubuntu:  pip install pyside6-tools
#
# Output: tincan_gui/translations/tincan_{locale}.qm
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS="$PROJECT_ROOT/tincan_gui/translations"

cd "$PROJECT_ROOT"

if [ "$#" -gt 0 ]; then
    LOCALES=("$@")
else
    LOCALES=()
    for f in "$TRANSLATIONS"/tincan_*.ts; do
        [ -f "$f" ] || continue
        basename="${f##*/}"
        locale="${basename#tincan_}"
        locale="${locale%.ts}"
        LOCALES+=("$locale")
    done
fi

if [ "${#LOCALES[@]}" -eq 0 ]; then
    echo "No .ts files found. Run i18n-extract.sh first." >&2
    exit 1
fi

for locale in "${LOCALES[@]}"; do
    ts_file="$TRANSLATIONS/tincan_${locale}.ts"
    qm_file="$TRANSLATIONS/tincan_${locale}.qm"
    if [ ! -f "$ts_file" ]; then
        echo "Warning: $ts_file not found — skipping $locale" >&2
        continue
    fi
    echo "Compiling $ts_file → $qm_file"
    pyside6-lrelease "$ts_file" -qm "$qm_file"
done

echo "Done."
