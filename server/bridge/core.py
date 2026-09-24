import json
import asyncio

from server.scripting import ScriptsManager
from server.bridge.flow_store import FlowStore


class BridgeCore:
    """Shared state + infra used by every other ProxyUIBridge mixin: init,
    UI broadcast, and the tiny script-list notify helper."""

    def __init__(self, proxy_port):
        self.proxy_port = proxy_port
        self.connected_clients = set()
        # Subset of connected_clients that identified as automation clients and
        # are therefore excluded from UI broadcasts (see broadcast_to_ui).
        self.agent_clients = set()
        self.agent_client_names = {}    # websocket -> client name, for the UI banner
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

        # --- Automation surface (MCP / CLI clients) ---------------------
        # Traffic history the UI never needed: the Vue store holds the live
        # list, but an agent connects after the fact and has to ask what
        # already happened. See flow_store.py.
        self.flow_store = FlowStore()

        # Agent scenario rules are kept *separate* from the rules above rather
        # than overwriting them. An agent running a mock scenario must not wipe
        # the mocks a user built by hand in the UI, and clearing a scenario has
        # to restore the user's setup exactly — only possible if we never
        # touched it. Matched ahead of the UI rules.
        self.agent_scenario = None      # {"name", "started_seq", "started_at"}
        # The socket that installed the scenario. Its disconnect clears the
        # scenario even if other agents are still attached — they didn't ask
        # for those mocks and shouldn't inherit them.
        self.agent_scenario_owner = None
        # Per-rule hit counters for mocks with a `responses` sequence
        # ("500, 500, then 200"). Keyed by the rule's override key; reset on
        # every scenario install so a re-run starts the sequence over.
        self.agent_rule_hits = {}
        self.agent_map_local_rules = []
        self.agent_map_remote_rules = []
        self.agent_throttle_profile = None   # None = inherit the UI's setting

        # Fields the user has taken over on an agent's rules, keyed by
        # method|pattern (mocks) or pattern (rewrites). Re-applied on every
        # scenario install so an agent re-running the same test can't silently
        # undo a hand edit. `_order` keeps the key each live rule was installed
        # under, so an override that rewrites the pattern still resolves.
        self.agent_rule_overrides = {}
        self.agent_rule_originals = {}   # key -> the agent's untouched mock
        self.agent_rule_order = []       # keys, in the order the agent sent them
        self.agent_remote_overrides = {}
        self.agent_remote_originals = {}
        self.agent_remote_order = []
        self.agent_last_scenario = None  # kept when an agent disconnects mid-run
        self.agent_end_reason = None
        self.agent_activity = []        # recent agent actions, for the UI strip
        self.mcp_shim_path = None       # set by main.py once the launcher is written

        self.wg_enabled = False
        self.wg_port = 51820
        self._master = None     # set by run_proxy_forever; used for WG restart + inject
        self._ip_onboarding_addon = None  # set by run_proxy_forever; serves mitm cert page on LOCAL_IP
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
        # Automation clients opt out via AGENT_HELLO: they query history on
        # demand, so shipping them every NEW_REQUEST (bodies and all) would be
        # pure serialisation cost for something they immediately discard.
        targets = [c for c in self.connected_clients if c not in self.agent_clients]
        if not targets: return
        message = json.dumps({"type": msg_type, "data": data})
        await asyncio.gather(*(client.send(message) for client in targets), return_exceptions=True)

    async def _broadcast_scripts_list(self):
        await self.broadcast_to_ui("SCRIPTS_LIST", {"scripts": self.scripts_manager.state_list()})
