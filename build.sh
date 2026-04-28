#!/bin/bash
set -e

# ─────────────────────────────────────────────
# OpenProxy build script
# Usage:
#   ./build.sh          → interactive menu
#   ./build.sh app      → build .app + folder only
#   ./build.sh dmg      → build .app + package as DMG
# ─────────────────────────────────────────────

APP_NAME="OpenProxy"
PYINSTALLER_ARGS=(
  --name "$APP_NAME"
  --windowed
  --icon=icon.icns
  --add-data "ui/dist:ui/dist"
  --add-data "icon.png:."
  main.py
)

# ── Resolve mode ──────────────────────────────
MODE="${1:-}"
if [ -z "$MODE" ]; then
  echo ""
  echo "What do you want to build?"
  echo "  1) App only  (.app + folder in dist/)"
  echo "  2) DMG       (.app packaged as a macOS installer)"
  echo ""
  read -rp "Choice [1/2]: " CHOICE
  case "$CHOICE" in
    2) MODE="dmg" ;;
    *) MODE="app" ;;
  esac
fi

# ── Build UI ──────────────────────────────────
echo ""
echo "▶ Building UI..."
cd ui && npm run build && cd ..

# ── Clean previous dist ───────────────────────
echo "▶ Cleaning dist/..."
rm -rf dist/

# ── PyInstaller ───────────────────────────────
echo "▶ Running PyInstaller..."
pyinstaller "${PYINSTALLER_ARGS[@]}"

echo ""
echo "✓ App built → dist/$APP_NAME.app"

# ── DMG ───────────────────────────────────────
if [ "$MODE" = "dmg" ]; then
  if ! command -v create-dmg &>/dev/null; then
    echo ""
    echo "  create-dmg not found. Install it with:"
    echo "    brew install create-dmg"
    exit 1
  fi

  VERSION=$(python3 -c "import re; print(re.search(r'APP_VERSION\s*=\s*[\"\'](.*?)[\"\']', open('main.py').read()).group(1))")
  DMG_NAME="${APP_NAME}-${VERSION}.dmg"

  echo "▶ Creating DMG: $DMG_NAME..."
  create-dmg \
    --volname "$APP_NAME" \
    --volicon "icon.icns" \
    --window-pos 200 120 \
    --window-size 660 400 \
    --icon-size 128 \
    --icon "${APP_NAME}.app" 180 170 \
    --app-drop-link 480 170 \
    --hide-extension "${APP_NAME}.app" \
    "dist/$DMG_NAME" \
    "dist/${APP_NAME}.app"

  echo ""
  echo "✓ DMG built → dist/$DMG_NAME"
fi

echo ""
echo "Done!"
