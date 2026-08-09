#!/bin/bash
# test-update.sh — End-to-end auto-update test on macOS
#
# What this does:
#   1. Builds the app (always, unless --no-build is passed — main.py and the
#      UI are compiled/bundled at build time, so a stale dist-electron/ zip
#      silently tests old code otherwise)
#   2. Finds the built zip for your architecture (arm64 or x64)
#   3. Starts a local HTTP server serving that zip as the "new version"
#   4. Opens the built .app with OPENPROXY_UPDATE_TEST_URL set so it
#      immediately sees a fake v99.9.9 update pointing at your local server
#
# Usage:
#   ./test-update.sh          → build, then run the test
#   ./test-update.sh --no-build → skip build, use existing dist-electron/ zip
#
# When the app opens:
#   - The update banner should appear within a couple of seconds
#   - Click "Update Now" to test the full download + replace flow
#   - The app will quit and relaunch from /Applications/OpenProxy.app
#   - Check /tmp/openproxy_update_*/update.log if anything goes wrong
set -e
cd "$(dirname "$0")"

PORT=9999
NO_BUILD="${1:-}"

# ── 1. Build (unless skipped) ─────────────────────────────────────────────────
if [ "$NO_BUILD" != "--no-build" ]; then
  echo "→ Building (pass --no-build to reuse the existing dist-electron/ zip)..."
  bash build.sh
fi

# ── 2. Find the right zip for this machine ────────────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  ZIP=$(ls dist-electron/*arm64-mac*.zip 2>/dev/null | head -1)
  [ -z "$ZIP" ] && ZIP=$(ls dist-electron/*-mac*.zip 2>/dev/null | head -1)
else
  ZIP=$(ls dist-electron/*-mac*.zip 2>/dev/null | grep -v arm64 | head -1)
  [ -z "$ZIP" ] && ZIP=$(ls dist-electron/*-mac*.zip 2>/dev/null | head -1)
fi

if [ -z "$ZIP" ]; then
  echo "✗ No mac zip found in dist-electron/. Run ./build.sh first."
  exit 1
fi
echo "✓ Using zip: $ZIP"

# ── 3. Find the built .app ────────────────────────────────────────────────────
if [ "$ARCH" = "arm64" ]; then
  APP=$(ls -d dist-electron/mac-arm64/*.app 2>/dev/null | head -1)
  [ -z "$APP" ] && APP=$(ls -d dist-electron/mac*/*.app 2>/dev/null | head -1)
else
  APP=$(ls -d dist-electron/mac/*.app 2>/dev/null | head -1)
  [ -z "$APP" ] && APP=$(ls -d dist-electron/mac*/*.app 2>/dev/null | grep -v arm64 | head -1)
fi

if [ -z "$APP" ]; then
  echo "✗ No .app found in dist-electron/. Run ./build.sh first."
  exit 1
fi
echo "✓ Using app: $APP"

# Copy the zip to a known filename so the URL is stable
cp "$ZIP" /tmp/openproxy_test_update.zip
echo "✓ Copied zip to /tmp/openproxy_test_update.zip"

# ── 4. Start local HTTP server ────────────────────────────────────────────────
# Kill any previous server on this port
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true

echo "→ Starting HTTP server on port $PORT..."
python3 -m http.server $PORT --directory /tmp &
SERVER_PID=$!
echo "✓ Server running (PID $SERVER_PID)"

# Give the server a moment to start
sleep 1

# ── 5. Launch the app with the test env var ───────────────────────────────────
UPDATE_URL="http://127.0.0.1:$PORT/openproxy_test_update.zip"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Opening: $APP"
echo "  Fake update URL: $UPDATE_URL"
echo ""
echo "  The update banner should appear within a couple of seconds."
echo "  Click 'Update Now' to test the full replace flow."
echo ""
echo "  Logs (if update fails): /tmp/openproxy_update_*/update.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Open the .app with the env var injected via the binary directly
# (macOS 'open' strips env vars, so we launch the binary inside the bundle)
BIN=$(defaults read "$(pwd)/$APP/Contents/Info" CFBundleExecutable 2>/dev/null || ls "$APP/Contents/MacOS/" | head -1)
OPENPROXY_UPDATE_TEST_URL="$UPDATE_URL" "$APP/Contents/MacOS/$BIN" &
APP_PID=$!

# Wait for app to exit, then clean up server
wait $APP_PID 2>/dev/null || true
kill $SERVER_PID 2>/dev/null || true
echo "✓ Done. Server stopped."
