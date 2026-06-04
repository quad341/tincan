#!/usr/bin/env bash
# i18n-extract.sh — extract translatable strings from tincan_gui into .ts files.
#
# Usage: ./scripts/i18n-extract.sh [LOCALE...]
#   LOCALE: e.g. fr de ja  (default: all existing .ts files)
#
# Requires: pyside6-lupdate (from pyside6-tools or python3-pyside6)
#   Fedora:  sudo dnf install python3-pyside6
#   Ubuntu:  pip install pyside6-tools
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS="$PROJECT_ROOT/tincan_gui/translations"

cd "$PROJECT_ROOT"

if [ "$#" -gt 0 ]; then
    LOCALES=("$@")
else
    # Extract locales from existing .ts file names (e.g. tincan_fr.ts → fr)
    LOCALES=()
    for f in "$TRANSLATIONS"/tincan_*.ts; do
        [ -f "$f" ] || continue
        basename="${f##*/}"        # tincan_fr.ts
        locale="${basename#tincan_}" # fr.ts
        locale="${locale%.ts}"     # fr
        LOCALES+=("$locale")
    done
fi

if [ "${#LOCALES[@]}" -eq 0 ]; then
    echo "No locales found. Pass a locale argument, e.g.: $0 fr" >&2
    exit 1
fi

for locale in "${LOCALES[@]}"; do
    ts_file="$TRANSLATIONS/tincan_${locale}.ts"
    echo "Extracting strings for locale: $locale → $ts_file"
    pyside6-lupdate -recursive tincan_gui -ts "$ts_file" -no-obsolete
done

echo "Done."
