#!/bin/bash
set -e

# ─────────────────────────────────────────────
# OpenProxy build script (Linux)
# Usage:
#   ./build_linux.sh            → interactive menu
#   ./build_linux.sh app        → build binary folder only
#   ./build_linux.sh tar        → build binary folder + package as tar.gz
#   ./build_linux.sh appimage   → build binary folder + package as AppImage
# ─────────────────────────────────────────────

APP_NAME="OpenProxy"
PYINSTALLER_ARGS=(
  --name "$APP_NAME"
  --windowed
  --icon=icon.png
  --add-data "ui/dist:ui/dist"
  --add-data "icon.png:."
  main.py
)

# ── Resolve mode ──────────────────────────────
MODE="${1:-}"
if [ -z "$MODE" ]; then
  echo ""
  echo "What do you want to build?"
  echo "  1) App only   (dist/$APP_NAME/ folder with binary)"
  echo "  2) tar.gz     (binary folder packaged as tar.gz)"
  echo "  3) AppImage   (single portable .AppImage file)"
  echo ""
  read -rp "Choice [1/2/3]: " CHOICE
  case "$CHOICE" in
    2) MODE="tar" ;;
    3) MODE="appimage" ;;
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
echo "✓ App built → dist/$APP_NAME/"

VERSION=$(python3 -c "import re; print(re.search(r'APP_VERSION\s*=\s*[\"\'](.*?)[\"\']', open('main.py').read()).group(1))")

# ── tar.gz ────────────────────────────────────
if [ "$MODE" = "tar" ]; then
  TAR_NAME="${APP_NAME}-${VERSION}-linux.tar.gz"
  echo "▶ Creating tar.gz: $TAR_NAME..."
  tar -czf "dist/$TAR_NAME" -C dist "$APP_NAME"
  echo ""
  echo "✓ Archive built → dist/$TAR_NAME"
fi

# ── AppImage ──────────────────────────────────
if [ "$MODE" = "appimage" ]; then
  if ! command -v appimagetool &>/dev/null; then
    echo ""
    echo "  appimagetool not found. Download it from:"
    echo "    https://github.com/AppImage/AppImageKit/releases"
    echo "  Then place it in your PATH and re-run."
    exit 1
  fi

  APPDIR="dist/${APP_NAME}.AppDir"
  echo "▶ Creating AppImage..."

  # Build AppDir structure
  mkdir -p "$APPDIR/usr/bin"
  cp -r "dist/$APP_NAME/." "$APPDIR/usr/bin/"
  cp icon.png "$APPDIR/${APP_NAME}.png"

  cat > "$APPDIR/${APP_NAME}.desktop" <<EOF
[Desktop Entry]
Name=$APP_NAME
Exec=$APP_NAME
Icon=$APP_NAME
Type=Application
Categories=Development;
EOF

  cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/$APP_NAME" "\$@"
EOF
  chmod +x "$APPDIR/AppRun"

  APPIMAGE_NAME="${APP_NAME}-${VERSION}-linux.AppImage"
  appimagetool "$APPDIR" "dist/$APPIMAGE_NAME"
  rm -rf "$APPDIR"

  echo ""
  echo "✓ AppImage built → dist/$APPIMAGE_NAME"
fi

echo ""
echo "Done!"
