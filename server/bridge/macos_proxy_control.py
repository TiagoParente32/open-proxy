import sys
import json
import asyncio

from server.macos_proxy import set_macos_proxy, unset_macos_proxy, _sudoers_ok


class MacProxyControlMixin:
    """WebSocket-driven macOS system proxy toggle."""

    async def _toggle_macos_proxy(self, websocket, enable: bool):
        if sys.platform != "darwin":
            await websocket.send(json.dumps({
                "type": "MACOS_PROXY_STATUS",
                "active": False,
                "services": [],
                "error": "System proxy toggle is macOS-only.",
            }))
            return

        # Notify the UI if this will require a one-time admin password prompt
        # to install the passwordless sudoers entry.
        if not _sudoers_ok():
            await self.broadcast_to_ui("MACOS_PROXY_FIRST_TIME_SETUP", {})

        # set/unset_macos_proxy() may block on the osascript admin dialog
        # (first run only), so run them off the asyncio loop.
        loop = asyncio.get_running_loop()
        if enable:
            result = await loop.run_in_executor(None, set_macos_proxy, self.proxy_port)
        else:
            result = await loop.run_in_executor(None, unset_macos_proxy)

        if result.get("ok"):
            self.is_mac_proxy_set = enable
            self.mac_proxy_services = result.get("services", []) if enable else []

        await self.broadcast_to_ui("MACOS_PROXY_STATUS", {
            "active": self.is_mac_proxy_set,
            "services": result.get("services", []),
            "error": result.get("error"),
        })
