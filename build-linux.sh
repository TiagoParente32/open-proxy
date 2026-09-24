#!/bin/bash
# build-linux.sh — Build for Linux
# Usage:
#   ./build-linux.sh           → x64 AppImage + tar.gz (default, run on x64 machine)
#   ./build-linux.sh --arm64   → arm64 AppImage + tar.gz (run on arm64 machine)
#   ./build-linux.sh --dir     → unpacked dir only (fastest, for quick testing)
#
# NOTE: arm64 builds MUST be run on an arm64 machine. PyInstaller compiles native
# binaries and cannot cross-compile, so the Python backend arch must match the target.
# NOTE: .deb target requires fakeroot and dpkg to be installed on the build machine.
#   sudo apt install fakeroot dpkg rpm
set -e
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
MODE="${1:-}"

VERSION=$(node -p "require('./package.json').version")

# Generate version.json so the packaged app can read its own version at
# runtime (see main.py::_read_app_version). Named distinctly from
# package.json to avoid electron-builder's special-cased handling of that
# filename when copied via extraResources.
node -e "require('fs').writeFileSync('version.json', JSON.stringify({ version: require('./package.json').version }))"

# Determine target arch
if [ "$MODE" = "--arm64" ]; then
  TARGET_ARCH="arm64"
  EB_ARCH_FLAG="--arm64"
else
  TARGET_ARCH="x64"
  EB_ARCH_FLAG="--x64"
fi

echo "Building OpenProxy (linux/${TARGET_ARCH}) v${VERSION}"

# 1. Build UI
echo "\n→ [1/3] Building Vue UI..."
(cd ui && npm install --silent && npm run build)

# 2. Bundle Python backend
echo "\n→ [2/3] Bundling Python backend..."
[ -f "venv/bin/activate" ] && source venv/bin/activate
rm -rf backend-dist build-pyinstaller
# --paths/--hidden-import/--collect-submodules bundle the MCP server (see
# mcp-server/) so `OpenProxy-server --mcp` works from the packaged app. Only the
# subpackages we use: `mcp.cli` needs typer, which isn't installed.
# Fail here, not at the user's first tool call: the MCP server is bundled from
# this interpreter's site-packages, so `mcp` must be importable by it. Invoking
# PyInstaller as a module (not the `pyinstaller` script) guarantees the bundle is
# built from the same interpreter — a stale console script can point elsewhere.
python -c "import mcp, sys; sys.path.insert(0, '$ROOT_DIR/mcp-server'); import openproxy_mcp.server" \
  || { echo "ERROR: 'mcp' is not installed for $(which python) — run: pip install -r requirements.txt"; exit 1; }
python -m PyInstaller \
  --name "OpenProxy-server" \
  --distpath backend-dist \
  --workpath build-pyinstaller \
  --clean \
  --noconfirm \
  --paths "$ROOT_DIR/mcp-server" \
  --hidden-import openproxy_mcp.server \
  --collect-submodules mcp.server \
  --collect-submodules mcp.shared \
  "$ROOT_DIR/main.py"
rm -rf build-pyinstaller OpenProxy-server.spec
chmod +x backend-dist/OpenProxy-server/OpenProxy-server

# 3. Package with electron-builder for Linux
echo "\n→ [3/3] Packaging with electron-builder (linux/${TARGET_ARCH})..."
if [ ! -d "$ROOT_DIR/node_modules" ]; then
  echo "Root node_modules missing; installing..."
  npm install --silent
fi

# Make sure native helper binaries are executable
if [ -f "$ROOT_DIR/node_modules/app-builder-bin/linux/x64/app-builder" ]; then
  chmod +x "$ROOT_DIR/node_modules/app-builder-bin/linux/x64/app-builder" || true
fi
if [ -f "$ROOT_DIR/node_modules/7zip-bin/linux/x64/7za" ]; then
  chmod +x "$ROOT_DIR/node_modules/7zip-bin/linux/x64/7za" || true
fi

if [ "$MODE" = "--dir" ]; then
  npx electron-builder --projectDir "$ROOT_DIR" --dir
else
  npx electron-builder --projectDir "$ROOT_DIR" --linux $EB_ARCH_FLAG
fi

echo "\n✓ Done! Output in dist-electron/"
ls dist-electron/ 2>/dev/null || true
