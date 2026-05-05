#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# OpenProxy build script — macOS / Linux
# Produces: dist-electron/OpenProxy-*.dmg  (and .zip)
#
# Usage:
#   ./build.sh          → DMG + ZIP
#   ./build.sh --dir    → unpackaged app (fast, for testing)
# ─────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

MODE="${1:-}"

# Read version from root package.json
VERSION=$(node -p "require('./package.json').version")
echo "Building OpenProxy v${VERSION}"

# ── 1. Vue UI ────────────────────────────────────────────────────
echo ""
echo "→ [1/3] Building Vue UI..."
cd ui && npm install --silent && npm run build && cd ..

# ── 2. Python backend (PyInstaller) ──────────────────────────────
echo ""
echo "→ [2/3] Bundling Python backend..."
[ -f "venv/bin/activate" ] && source venv/bin/activate

rm -rf backend-dist build-pyinstaller
pyinstaller \
  --name "OpenProxy-server" \
  --distpath backend-dist \
  --workpath build-pyinstaller \
  --clean \
  --noconfirm \
  main.py

rm -rf build-pyinstaller OpenProxy-server.spec
chmod +x backend-dist/OpenProxy-server/OpenProxy-server

# ── 3. Electron packaging ─────────────────────────────────────────
echo ""
echo "→ [3/3] Packaging with electron-builder..."
if [ "$MODE" = "--dir" ]; then
  npx electron-builder --dir
else
  npx electron-builder --mac
fi

echo ""
echo "✓ Done! Output in dist-electron/"
ls dist-electron/ 2>/dev/null || true
