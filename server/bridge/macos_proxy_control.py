import sys
import json
import asyncio

from server.macos_proxy import (
    set_macos_proxy, unset_macos_proxy, _sudoers_ok,
    is_cert_trusted_macos, trust_cert_macos,
)
from server.windows_proxy import (
    set_windows_proxy, unset_windows_proxy,
    is_cert_trusted_windows, trust_cert_windows,
)
from server.linux_proxy import (
    set_linux_proxy, unset_linux_proxy,
    is_cert_trusted_linux, trust_cert_linux,
)


class MacProxyControlMixin:
    """WebSocket-driven OS system proxy toggle (macOS/Windows/Linux) and
    mitmproxy CA trust-store checks."""

    async def _toggle_macos_proxy(self, websocket, enable: bool):
        loop = asyncio.get_running_loop()

        if sys.platform == "darwin":
            # Notify the UI if this will require a one-time admin password prompt
            # to install the passwordless sudoers entry.
            if not _sudoers_ok():
                await self.broadcast_to_ui("MACOS_PROXY_FIRST_TIME_SETUP", {})
            # set/unset_macos_proxy() may block on the osascript admin dialog
            # (first run only), so run them off the asyncio loop.
            if enable:
                result = await loop.run_in_executor(None, set_macos_proxy, self.proxy_port)
            else:
                result = await loop.run_in_executor(None, unset_macos_proxy)
        elif sys.platform == "win32":
            fn = set_windows_proxy if enable else unset_windows_proxy
            result = await loop.run_in_executor(None, fn, self.proxy_port) if enable \
                else await loop.run_in_executor(None, fn)
        elif sys.platform.startswith("linux"):
            fn = set_linux_proxy if enable else unset_linux_proxy
            result = await loop.run_in_executor(None, fn, self.proxy_port) if enable \
                else await loop.run_in_executor(None, fn)
        else:
            result = {"ok": False, "error": f"Unsupported platform: {sys.platform}"}

        if result.get("ok"):
            self.is_mac_proxy_set = enable
            self.mac_proxy_services = result.get("services", []) if enable else []

        await self.broadcast_to_ui("MACOS_PROXY_STATUS", {
            "active": self.is_mac_proxy_set,
            "services": result.get("services", []),
            "error": result.get("error"),
        })

    async def handle_check_cert_trust(self, ws):
        """Reports whether the mitmproxy CA is already trusted on this machine."""
        loop = asyncio.get_running_loop()
        if sys.platform == "darwin":
            trusted = await loop.run_in_executor(None, is_cert_trusted_macos)
        elif sys.platform == "win32":
            trusted = await loop.run_in_executor(None, is_cert_trusted_windows)
        elif sys.platform.startswith("linux"):
            trusted = await loop.run_in_executor(None, is_cert_trusted_linux)
        else:
            trusted = False
        await ws.send(json.dumps({"type": "CERT_TRUST_STATUS", "trusted": trusted}))

    async def handle_trust_cert(self, ws):
        """Trusts the mitmproxy CA in this machine's OS cert store (Chrome/Edge/curl on
        all platforms, plus Safari on macOS). Firefox keeps its own separate store."""
        loop = asyncio.get_running_loop()
        if sys.platform == "darwin":
            result = await loop.run_in_executor(None, trust_cert_macos)
        elif sys.platform == "win32":
            result = await loop.run_in_executor(None, trust_cert_windows)
        elif sys.platform.startswith("linux"):
            result = await loop.run_in_executor(None, trust_cert_linux)
        else:
            result = {"ok": False, "error": f"Unsupported platform: {sys.platform}"}
        await ws.send(json.dumps({"type": "CERT_TRUST_RESULT", "ok": result["ok"], "error": result["error"]}))
