import json
import asyncio

from server.scripting import ScriptsManager


class BridgeCore:
    """Shared state + infra used by every other ProxyUIBridge mixin: init,
    UI broadcast, and the tiny script-list notify helper."""

    def __init__(self, proxy_port):
        self.proxy_port = proxy_port
        self.connected_clients = set()
        self.bg_tasks = set()

        self.is_recording = True
        self.disable_cache = False
        self.throttle_profile = "None"

        self.map_local_enabled = True
        self.map_local_rules = []
        self.map_remote_enabled = True
        self.map_remote_rules = []
        self.breakpoints_enabled = True
        self.breakpoint_rules = []
        self.paused_flows = {}

        self.wg_enabled = False
        self.wg_port = 51820
        self._master = None     # set by run_proxy_forever; used for WG restart + inject
        self._last_startup_error = ""   # captured from mitmproxy's log on startup failure
        self.pending_update_info = None  # cached until a client connects

        # macOS system proxy state — tracked so the SIGTERM handler can auto-unset on quit
        self.is_mac_proxy_set = False
        self.mac_proxy_services = []

        self.scripts_manager = ScriptsManager()
        self.scripts_manager.load_all()

    def add_log(self, entry) -> None:
        """Capture mitmproxy ERROR log entries so we can surface them in the UI."""
        if getattr(entry, 'level', None) == "error":
            self._last_startup_error = getattr(entry, 'msg', str(entry))

    async def broadcast_to_ui(self, msg_type, data):
        if not self.connected_clients: return
        message = json.dumps({"type": msg_type, "data": data})
        await asyncio.gather(*(client.send(message) for client in self.connected_clients), return_exceptions=True)

    async def _broadcast_scripts_list(self):
        await self.broadcast_to_ui("SCRIPTS_LIST", {"scripts": self.scripts_manager.state_list()})
