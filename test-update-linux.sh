#!/bin/bash
# test-update-linux.sh — End-to-end auto-update test on Linux (AppImage)
#
# What this does:
#   1. Builds the app (always, unless --no-build is passed — main.py and the
#      UI are compiled/bundled at build time, so a stale dist-electron/
#      AppImage silently tests old code otherwise)
#   2. Copies the newest AppImage to a user-writable "install" location, so
#      the swap runs without pkexec and never touches dist-electron/
#   3. Starts a local HTTP server serving that AppImage as the "new version"
#      (the URL must end in .AppImage: the updater picks its swap strategy
#      from the downloaded file's extension)
#   4. Launches the installed AppImage with OPENPROXY_UPDATE_TEST_URL set so
#      it immediately sees a fake v99.9.9 update pointing at your local server
#
# Usage:
#   ./test-update-linux.sh            → build, then run the test
#   ./test-update-linux.sh --no-build → skip build, use existing AppImage
#
# When the app opens:
#   - The update banner should appear within a couple of seconds
#   - Click "Update Now" to test the full download + replace flow
#   - The app quits; unlike macOS, the Linux swap script doesn't relaunch it,
#     so this script relaunches it once the swap is done
#   - Check /tmp/openproxy_update_*/update.log if anything goes wrong
#   - Once it's back, the script checks the MCP launcher in ~/.openproxy/bin
#     points at the installed AppImage and still answers an MCP initialize
set -e
cd "$(dirname "$0")"

PORT=9999
NO_BUILD="${1:-}"
TEST_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/openproxy-update-test"
INSTALLED="$TEST_DIR/OpenProxy.AppImage"
SERVE_DIR="$TEST_DIR/serve"

# ── 1. Build (unless skipped) ─────────────────────────────────────────────────
if [ "$NO_BUILD" != "--no-build" ]; then
  # A past `sudo` build leaves root-owned files all over the tree (ui/dist,
  # backend-dist, dist-electron, node_modules), and the build then dies on
  # whichever it tries to replace first.
  NOT_MINE=$(find . -path ./venv -prune -o -not -user "$(id -un)" -print -quit 2>/dev/null)
  if [ -n "$NOT_MINE" ]; then
    echo "✗ Some files here aren't owned by you (e.g. $NOT_MINE), so the build can't replace them. Fix with:"
    echo "    sudo chown -R $(id -un): $(pwd)"
    exit 1
  fi
  echo "→ Building (pass --no-build to reuse the existing AppImage)..."
  bash build-linux.sh
fi

# ── 2. Find the AppImage and "install" it ─────────────────────────────────────
# Newest first (-t): dist-electron/ accumulates builds from earlier versions.
SRC=$(ls -t dist-electron/*.AppImage 2>/dev/null | head -1)
if [ -z "$SRC" ]; then
  echo "✗ No AppImage found in dist-electron/. Run ./build-linux.sh first."
  exit 1
fi
echo "✓ Using AppImage: $SRC ($(date -r "$SRC" '+%Y-%m-%d %H:%M'))"

mkdir -p "$SERVE_DIR"
cp "$SRC" "$INSTALLED" && chmod +x "$INSTALLED"
cp "$SRC" "$SERVE_DIR/openproxy_test_update.AppImage"
echo "✓ Installed test copy at $INSTALLED"
# mv -f in the swap script gives the file a new inode; that's how we tell the
# swap actually happened when old and new are byte-identical builds.
INODE_BEFORE=$(stat -c %i "$INSTALLED")

# The build has to contain the MCP server, or every MCP check below is moot.
# (An AppImage packaged around a stale backend-dist/ silently lacks it.)
# Asked of the backend itself: PyInstaller keeps pure-Python packages in its
# PYZ archive, so there's no mcp/ folder to look for. Extracting avoids FUSE.
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test-update","version":"0"}}}'
PROBE_DIR=$(mktemp -d)
( cd "$PROBE_DIR" && "$INSTALLED" --appimage-extract 'resources/backend/*' >/dev/null 2>&1 )
if ! printf '%s\n' "$INIT" | timeout 30 "$PROBE_DIR/squashfs-root/resources/backend/OpenProxy-server/OpenProxy-server" --mcp 2>/dev/null \
     | head -c 4000 | grep -q '"serverInfo"'; then
  rm -rf "$PROBE_DIR"
  echo "✗ $SRC's backend doesn't answer MCP (stale backend-dist/?). Rebuild without --no-build."
  exit 1
fi
rm -rf "$PROBE_DIR"
echo "✓ Bundled backend answers MCP initialize"

# The AppImage runtime mounts itself with libfuse2, which fails on distros
# where fusermount is fusermount3 ("Cannot mount AppImage"). Extract-and-run
# sidesteps FUSE; $APPIMAGE is still set, so the updater and shim behave the
# same. Exported so the fake agent and the shim check below inherit it.
if timeout 5 "$INSTALLED" --appimage-mount 2>&1 | grep -q "Cannot mount AppImage"; then
  echo "! FUSE can't mount AppImages here; using APPIMAGE_EXTRACT_AND_RUN=1"
  export APPIMAGE_EXTRACT_AND_RUN=1
fi

# ── 3. Start local HTTP server ────────────────────────────────────────────────
if command -v fuser >/dev/null; then fuser -k $PORT/tcp 2>/dev/null || true; fi

echo "→ Starting HTTP server on port $PORT..."
python3 -m http.server $PORT --bind 127.0.0.1 --directory "$SERVE_DIR" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
echo "✓ Server running (PID $SERVER_PID)"
sleep 1

# ── 4. Launch the app with the test env var ───────────────────────────────────
UPDATE_URL="http://127.0.0.1:$PORT/openproxy_test_update.AppImage"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Opening: $INSTALLED"
echo "  Fake update URL: $UPDATE_URL"
echo ""
echo "  The update banner should appear within a couple of seconds."
echo "  Click 'Update Now' to test the full replace flow."
echo ""
echo "  Logs (if update fails): /tmp/openproxy_update_*/update.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

START_MARK=$(date +%s)
OPENPROXY_UPDATE_TEST_URL="$UPDATE_URL" "$INSTALLED" &
APP_PID=$!

# Stand in for a connected agent: an MCP server launched through the shim the
# app writes on startup, exactly as a client launches it, with stdin held open
# like a client keeps it. The update must stop it before the swap.
SHIM="$HOME/.openproxy/bin/openproxy-mcp"
SHIM_MARK="APPIMAGE='$INSTALLED'"
for i in $(seq 1 60); do
  grep -qF "$SHIM_MARK" "$SHIM" 2>/dev/null && break
  sleep 1
done
if ! grep -qF "$SHIM_MARK" "$SHIM" 2>/dev/null; then
  echo "✗ The app didn't write an MCP launcher for $INSTALLED at $SHIM"
  kill $APP_PID 2>/dev/null; exit 1
fi
sleep 100000 | "$SHIM" >/dev/null 2>&1 &
MCP_PID=$!
echo "✓ Fake agent MCP server running (PID $MCP_PID)"

wait $APP_PID 2>/dev/null || true
echo "✓ App exited."

# ── 5. Wait for the detached swap script to finish ────────────────────────────
LOG=""
for i in $(seq 1 40); do
  LOG=$(find /tmp -maxdepth 2 -path '/tmp/openproxy_update_*/update.log' -newermt "@$START_MARK" 2>/dev/null | head -1)
  if [ -n "$LOG" ] && grep -q "AppImage updated successfully" "$LOG"; then break; fi
  sleep 1
done
if [ -z "$LOG" ] || ! grep -q "AppImage updated successfully" "$LOG"; then
  echo "✗ The swap didn't complete (did you click 'Update Now'?)"
  [ -n "$LOG" ] && { echo "  Log: $LOG"; tail -20 "$LOG"; }
  kill $MCP_PID 2>/dev/null; exit 1
fi
if [ "$(stat -c %i "$INSTALLED")" = "$INODE_BEFORE" ]; then
  echo "✗ Swap log says success but $INSTALLED wasn't replaced"; exit 1
fi
echo "✓ AppImage replaced ($LOG)"

# `$MCP_PID` is the pipeline's last process: the shim, which execs the backend.
if kill -0 $MCP_PID 2>/dev/null; then
  echo "✗ The update left the agent's MCP server running (PID $MCP_PID)"
  kill $MCP_PID 2>/dev/null; exit 1
fi
pkill -f "^sleep 100000$" 2>/dev/null || true
echo "✓ The update stopped the agent's MCP server"

# ── 6. Relaunch and check the MCP launcher ────────────────────────────────────
echo ""
echo "→ Relaunching the updated app..."
"$INSTALLED" >/dev/null 2>&1 &
disown
for i in $(seq 1 90); do
  if (exec 3<>/dev/tcp/127.0.0.1/8765) 2>/dev/null; then break; fi
  sleep 1
done
sleep 2
if [ ! -x "$SHIM" ]; then
  echo "✗ MCP launcher missing: $SHIM"; exit 1
fi
if ! grep -qF "$SHIM_MARK" "$SHIM"; then
  echo "✗ MCP launcher does not point at the installed AppImage:"; grep '^APPIMAGE=' "$SHIM"; exit 1
fi
echo "✓ Launcher points at the installed AppImage"
if printf '%s\n' "$INIT" | timeout 30 "$SHIM" 2>/dev/null | head -c 4000 | grep -q '"serverInfo"'; then
  echo "✓ MCP launcher answers initialize from the updated app"
else
  echo "✗ MCP launcher did not answer initialize"; exit 1
fi
echo ""
echo "✓ All checks passed. The relaunched app is still running; quit it from the tray."
