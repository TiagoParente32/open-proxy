#!/bin/bash
# build-linux.sh — Build for Linux (Ubuntu)
# Usage: ./build-linux.sh [--dir]
set -e
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
MODE="${1:-}"

VERSION=$(node -p "require('./package.json').version")
echo "Building OpenProxy (linux) v${VERSION}"

# 1. Build UI
echo "\n→ [1/3] Building Vue UI..."
cd ui && npm install --silent && npm run build && cd ..

# 2. Bundle Python backend
echo "\n→ [2/3] Bundling Python backend..."
[ -f "venv/bin/activate" ] && source venv/bin/activate
rm -rf backend-dist build-pyinstaller
pyinstaller \
  --name "OpenProxy-server" \
  --distpath backend-dist \
  --workpath build-pyinstaller \
  --clean \
  --noconfirm \
  "$ROOT_DIR/main.py"
rm -rf build-pyinstaller OpenProxy-server.spec
chmod +x backend-dist/OpenProxy-server/OpenProxy-server

# 3. Package with electron-builder for Linux
echo "\n→ [3/3] Packaging with electron-builder (linux)..."
# ensure root node_modules exist
if [ ! -d "$ROOT_DIR/node_modules" ]; then
  echo "Root node_modules missing; installing..."
  npm install --silent
fi

# make sure native helper binaries are executable (fixes EACCES during packaging)
if [ -f "$ROOT_DIR/node_modules/app-builder-bin/linux/x64/app-builder" ]; then
  chmod +x "$ROOT_DIR/node_modules/app-builder-bin/linux/x64/app-builder" || true
fi
if [ -f "$ROOT_DIR/node_modules/7zip-bin/linux/x64/7za" ]; then
  chmod +x "$ROOT_DIR/node_modules/7zip-bin/linux/x64/7za" || true
fi

if [ "$MODE" = "--dir" ]; then
  npx electron-builder --projectDir "$ROOT_DIR" --dir
else
  npx electron-builder --projectDir "$ROOT_DIR" --linux
fi

echo "\n✓ Done! Output in dist-electron/"
ls dist-electron/ 2>/dev/null || true
