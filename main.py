import os
import sys
import threading
import signal

# `--mcp` turns this same binary into the MCP server (stdio). Handled before
# the imports below: mitmproxy is heavy, and nothing may print to stdout once
# an MCP client owns it. See server/mcp_shim.py for why one binary does both.
if "--mcp" in sys.argv[1:]:
    from server.mcp_shim import run_mcp_server
    run_mcp_server()
    sys.exit(0)

# Force-imported (not referenced directly below) so PyInstaller's static
# analysis bundles them — mitmproxy needs mitmproxy_rs's native extension at
# runtime, and Pillow is pulled in transitively without an explicit import
# reaching it from anywhere else in the dependency graph.
import mitmproxy_rs
from PIL import Image

from server.bridge import ProxyUIBridge
from server.system_helpers import get_free_port
from server.runners import run_async_loop
from server.mcp_shim import ensure_mcp_shim
from server.macos_proxy import unset_macos_proxy
from server.windows_proxy import unset_windows_proxy
from server.linux_proxy import unset_linux_proxy


if __name__ == "__main__":
    ACTIVE_PROXY_PORT = get_free_port(9090)
    print(f"Starting OpenProxy on port {ACTIVE_PROXY_PORT}", flush=True)

    bridge = ProxyUIBridge(proxy_port=ACTIVE_PROXY_PORT)

    # Refresh the agent launcher so it points at *this* build. Runs on every
    # start so updates and moved installs never break a registered agent.
    bridge.mcp_shim_path = ensure_mcp_shim()

    t = threading.Thread(target=run_async_loop, args=(bridge, ACTIVE_PROXY_PORT), daemon=True)
    t.start()

    def _shutdown(*_args):
        # If the user set the OS-level system proxy this session, unset it on quit
        # — otherwise their entire machine keeps routing through OpenProxy after
        # we exit. On macOS this will pop the admin password dialog one more time.
        if bridge.is_mac_proxy_set:
            try:
                if sys.platform == "darwin":
                    unset_macos_proxy()
                elif sys.platform == "win32":
                    unset_windows_proxy()
                elif sys.platform.startswith("linux"):
                    unset_linux_proxy()
            except Exception as e:
                print(f"[QUIT] Failed to unset OS proxy: {e}", flush=True)
        os._exit(0)

    # Electron sends SIGTERM via pythonProcess.kill() on before-quit; SIGINT
    # covers Ctrl-C in dev. Both must run cleanup before we exit.
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    try:
        t.join()
    except KeyboardInterrupt:
        _shutdown()
