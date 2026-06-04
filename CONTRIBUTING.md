# Contributing to tincan

## Internationalisation (i18n)

tincan uses Qt's `tr()` mechanism for translatable strings. Translations live in
`tincan_gui/translations/`.

### Requirements

```bash
# Fedora
sudo dnf install python3-pyside6

# Ubuntu / Debian
pip install pyside6-tools
```

### Running with a different locale

```bash
TINCAN_LOCALE=fr python -m tincan_gui
```

If no `.qm` file exists for the requested locale, tincan silently falls back to
English source strings.

### Extracting strings

Run from the project root after adding or changing translatable strings:

```bash
./scripts/i18n-extract.sh fr          # update French .ts file
./scripts/i18n-extract.sh fr de ja    # update multiple locales
```

This calls `pyside6-lupdate` in merge mode, adding new source strings without
removing existing translations.

### Compiling translations

After editing a `.ts` file, compile it to a binary `.qm` file:

```bash
./scripts/i18n-compile.sh fr
./scripts/i18n-compile.sh              # compile all existing locales
```

The `.qm` files are committed to `tincan_gui/translations/` so that users do not
need to run `lrelease` themselves.

### Adding a new language

1. Extract strings for the new locale:
   ```bash
   ./scripts/i18n-extract.sh <locale>   # e.g. de, ja, pt_BR
   ```
2. Edit `tincan_gui/translations/tincan_<locale>.ts` and translate each
   `<source>` into `<translation>`.
3. Compile:
   ```bash
   ./scripts/i18n-compile.sh <locale>
   ```
4. Test:
   ```bash
   TINCAN_LOCALE=<locale> python -m tincan_gui
   ```
5. Commit both the `.ts` and `.qm` files.

### Unicode symbols in translations

Strings that start with Unicode symbols (○ U+25CB, ● U+25CF, ⚠ U+26A0) should
keep those symbols at the start of the translated string. They are semantic, not
decorative.

Example translation entry:

```xml
<source>⚠ Message content unavailable</source>
<translation>⚠ Inhalt der Nachricht nicht verfügbar</translation>
```
