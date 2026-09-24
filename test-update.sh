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
#   - Once it's back, the script checks the MCP launcher in ~/.openproxy/bin
#     points at the updated bundle and still answers an MCP initialize
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
# Newest first (-t): dist-electron/ accumulates zips from earlier versions, and
# alphabetical order would quietly serve the oldest one as the "update".
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  ZIP=$(ls -t dist-electron/*arm64-mac*.zip 2>/dev/null | head -1)
  [ -z "$ZIP" ] && ZIP=$(ls -t dist-electron/*-mac*.zip 2>/dev/null | head -1)
else
  ZIP=$(ls -t dist-electron/*-mac*.zip 2>/dev/null | grep -v arm64 | head -1)
  [ -z "$ZIP" ] && ZIP=$(ls -t dist-electron/*-mac*.zip 2>/dev/null | head -1)
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

# ── 6. MCP launcher check against the relaunched app ─────────────────────────
# The update swapped the bundle; the launcher the backend writes on startup
# must now point into the new one and still serve MCP. This is the "register
# once, keep updating" contract for agents, so it's checked here rather than
# left to the user to notice.
SHIM="$HOME/.openproxy/bin/openproxy-mcp"
echo ""
echo "→ Waiting for the relaunched app (up to 90s)..."
for i in $(seq 1 90); do
  if nc -z 127.0.0.1 8765 2>/dev/null; then break; fi
  sleep 1
done
sleep 2
if [ ! -x "$SHIM" ]; then
  echo "✗ MCP launcher missing: $SHIM"; exit 1
fi
if ! grep -q "$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")" "$SHIM"; then
  echo "✗ MCP launcher does not point at the relaunched app:"; tail -1 "$SHIM"; exit 1
fi
echo "✓ Launcher points at the relaunched bundle: $(tail -1 "$SHIM")"
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test-update","version":"0"}}}'
if printf '%s\n' "$INIT" | "$SHIM" 2>/dev/null | head -c 4000 | grep -q '"serverInfo"'; then
  echo "✓ MCP launcher answers initialize from the updated app"
else
  echo "✗ MCP launcher did not answer initialize"; exit 1
fi
