import os
import sys
import threading
import signal

# Force-imported (not referenced directly below) so PyInstaller's static
# analysis bundles them — mitmproxy needs mitmproxy_rs's native extension at
# runtime, and Pillow is pulled in transitively without an explicit import
# reaching it from anywhere else in the dependency graph.
import mitmproxy_rs
from PIL import Image

from server.bridge import ProxyUIBridge
from server.system_helpers import get_free_port
from server.runners import run_async_loop
from server.macos_proxy import unset_macos_proxy
from server.windows_proxy import unset_windows_proxy
from server.linux_proxy import unset_linux_proxy


if __name__ == "__main__":
    ACTIVE_PROXY_PORT = get_free_port(9090)
    print(f"Starting OpenProxy on port {ACTIVE_PROXY_PORT}", flush=True)

    bridge = ProxyUIBridge(proxy_port=ACTIVE_PROXY_PORT)

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
