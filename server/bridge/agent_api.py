"""WebSocket surface for automation clients (the MCP server, CLI tooling).

Kept apart from WsHandlerMixin for two reasons: the UI protocol is a long
if/elif chain that doesn't need to grow, and these messages follow a different
convention from the UI's fire-and-forget ones — every request carries a
`req_id` and gets exactly one `AGENT_RESULT` back.

That correlation matters. The UI protocol replies by message *type*, which is
fine for a single client but races as soon as the UI and an agent ask the same
question at once. New messages all go through the envelope below instead.
"""

import ssl
import json
import time
import uuid
import asyncio
import threading
import urllib.request

from server import system_helpers

# Upper bound on a single wait_for_flows call. A wedged waiter would otherwise
# pin a future until the client disconnects.
MAX_WAIT_TIMEOUT = 300.0

# Bump when a message changes shape incompatibly. The MCP server ships inside
# the app, so the two only drift in the window between an app update and the
# agent restarting its MCP process — the handshake names the mismatch so the
# user gets "restart your agent" instead of a puzzling failure.
AGENT_PROTOCOL_VERSION = 1

# Fields of an agent-owned rule the user is allowed to take over — i.e. every
# field the normal Map Local / Map Remote editors expose, so an agent's rule can
# be edited in the same window as the user's own with nothing greyed out.
#
# `pattern` and `method` are in here even though they form the rule's identity:
# the override key is derived from the *agent's* untouched rule and stored
# alongside it (see `agent_rule_order`), never recomputed from the merged
# result, so re-pointing a rule at a different URL can't orphan the override.
OVERRIDABLE_FIELDS = {
    "active", "label", "pattern", "method", "status",
    "headers", "body", "body_source", "file_path", "req_headers_mod",
}

# Same, for Map Remote rewrites — a rewrite is only ever these three fields.
OVERRIDABLE_REMOTE_FIELDS = {"active", "pattern", "target"}

# How many agent actions to keep for the UI's activity strip.
ACTIVITY_LOG_LIMIT = 50

# Network profiles the proxy knows how to simulate — must match the labels the
# UI's throttle menu offers. Anything else is rejected at scenario install
# rather than silently meaning "no throttle", so a typo can't produce a test
# that passed without ever throttling.
THROTTLE_PROFILES = {"None", "Fast 3G", "Slow 3G"}

# Replay parameters an agent may override on a captured request.
REPLAY_OVERRIDES = {"method", "url", "req_headers", "req_body"}

# Header send/replay stamps on injected requests so the caller can find the
# resulting flow. Stripped in the request hook before going upstream.
REPLAY_ID_HEADER = "X-OpenProxy-Replay-Id"

# Longest per-mock artificial latency. Anything an app would wait on is well
# under this; the cap stops a typo pinning a request for an hour.
MAX_MOCK_DELAY_MS = 60_000

SEQUENCE_MODES = {"hold", "cycle"}

AGENT_MESSAGE_TYPES = {
    "AGENT_HELLO",
    "AGENT_STATUS",
    "AGENT_LIST_FLOWS",
    "AGENT_GET_FLOW",
    "AGENT_GET_FLOWS",
    "AGENT_SEARCH_FLOWS",
    "AGENT_SUMMARIZE_FLOWS",
    "AGENT_GET_WS_MESSAGES",
    "AGENT_CLEAR_FLOWS",
    "AGENT_WAIT_FOR_FLOWS",
    "AGENT_RUN_SCENARIO",
    "AGENT_CLEAR_SCENARIO",
    "AGENT_REPLAY_REQUEST",
    "AGENT_SEND_REQUEST",
}

# Messages that may block for as long as the caller asked. They run detached
# so the connection keeps serving other messages meanwhile.
_INJECT_TYPES = {"AGENT_REPLAY_REQUEST", "AGENT_SEND_REQUEST"}


def _is_long_running(msg_type, payload) -> bool:
    if msg_type == "AGENT_WAIT_FOR_FLOWS":
        return True
    return msg_type in _INJECT_TYPES and bool(payload.get("wait"))


class AgentApiMixin:
    """Handles the AGENT_* message family. Mixed into ProxyUIBridge."""

    async def handle_agent_message(self, websocket, payload) -> bool:
        """Dispatch an AGENT_* message. False if this isn't one of ours.

        The caller (websocket_handler) uses the return value to decide whether
        to fall through to the UI protocol.
        """
        msg_type = payload.get("type")
        if msg_type not in AGENT_MESSAGE_TYPES:
            return False

        req_id = payload.get("req_id")

        if msg_type == "AGENT_HELLO":
            # Mark this socket as automation so it stops receiving the UI
            # broadcast stream. Done here rather than at connect time
            # because the server can't tell a UI from an agent until asked.
            self.agent_clients.add(websocket)
            client = payload.get("client", "unknown")
            self.agent_client_names[websocket] = client
            print(f"[Agent] '{client}' connected", flush=True)
            await self.broadcast_agent_state()
            data = self._agent_status()
            theirs = payload.get("protocol")
            if theirs is not None and theirs != AGENT_PROTOCOL_VERSION:
                data["warning"] = (
                    f"This MCP server speaks agent protocol {theirs} but OpenProxy "
                    f"{data['version']} speaks {AGENT_PROTOCOL_VERSION}. One of them was "
                    "updated while the other kept running — restart the MCP server "
                    "(or the agent using it) so both come from the same build."
                )
            await self._agent_reply(websocket, req_id, data=data)
            return True

        # Waiting blocks for as long as the caller asked for, so it runs
        # detached — otherwise this connection would process no other message
        # until the wait resolved.
        if _is_long_running(msg_type, payload):
            task = asyncio.create_task(self._agent_process(websocket, req_id, msg_type, payload))
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)
        else:
            await self._agent_process(websocket, req_id, msg_type, payload)
        return True

    async def _agent_process(self, websocket, req_id, msg_type, payload):
        """Dispatch one message, reply, and narrate it to the UI."""
        try:
            data = await self._dispatch_agent(msg_type, payload, websocket)
            await self._agent_reply(websocket, req_id, data=data)

            # The UI can send AGENT_* too (its "stop the agent" button), and
            # the feed must not credit the agent for what the user did.
            by_agent = websocket in self.agent_clients
            activity = self._activity_for(msg_type, payload, data, by_agent=by_agent)
            if activity:
                kind, message, surface = activity
                await self.log_agent_activity(kind, message, surface=surface)
        except Exception as e:
            await self._agent_reply(websocket, req_id, error=f"{type(e).__name__}: {e}")

    async def _dispatch_agent(self, msg_type, payload, websocket=None):
        if msg_type == "AGENT_STATUS":
            return self._agent_status()

        if msg_type == "AGENT_LIST_FLOWS":
            flows = self.flow_store.list(
                url_pattern=payload.get("url_pattern"),
                method=payload.get("method"),
                status=payload.get("status"),
                since_seq=payload.get("since_seq"),
                only_completed=bool(payload.get("only_completed", False)),
                limit=int(payload.get("limit", 50)),
            )
            return {"flows": flows, "stats": self.flow_store.stats()}

        if msg_type == "AGENT_GET_FLOW":
            entry = self.flow_store.get(payload.get("id", ""))
            if entry is None:
                raise KeyError(
                    f"No flow {payload.get('id')!r} in history "
                    f"(buffer holds the last {self.flow_store.stats()['capacity']})"
                )
            return {"flow": self.flow_store.detail(entry)}

        if msg_type == "AGENT_GET_FLOWS":
            ids = payload.get("ids")
            if not isinstance(ids, list) or not ids:
                raise ValueError("ids must be a non-empty list of flow ids")
            found, missing = self.flow_store.get_many([str(i) for i in ids])
            return {"flows": found, "missing": missing}

        if msg_type == "AGENT_SEARCH_FLOWS":
            text = payload.get("text")
            if not text or not isinstance(text, str):
                raise ValueError("text must be a non-empty string")
            return {
                "matches": self.flow_store.search(
                    text,
                    since_seq=payload.get("since_seq"),
                    url_pattern=payload.get("url_pattern"),
                    limit=int(payload.get("limit", 50)),
                ),
                "stats": self.flow_store.stats(),
            }

        if msg_type == "AGENT_SUMMARIZE_FLOWS":
            return self.flow_store.summarize(
                since_seq=payload.get("since_seq"),
                url_pattern=payload.get("url_pattern"),
                top=int(payload.get("top", 15)),
            )

        if msg_type == "AGENT_GET_WS_MESSAGES":
            result = self.flow_store.ws_messages(
                payload.get("id", ""),
                offset=int(payload.get("offset", 0)),
                limit=int(payload.get("limit", 100)),
            )
            if result is None:
                raise KeyError(f"No flow {payload.get('id')!r} in history")
            return result

        if msg_type == "AGENT_WAIT_FOR_FLOWS":
            timeout = min(float(payload.get("timeout", 30.0)), MAX_WAIT_TIMEOUT)
            result = await self.flow_store.wait_for(
                url_pattern=payload.get("url_pattern"),
                method=payload.get("method"),
                status=payload.get("status"),
                since_seq=payload.get("since_seq"),
                count=int(payload.get("count", 1)),
                timeout=timeout,
            )
            return {
                "matched": result["matched"],
                "timed_out": result["timed_out"],
                "watermark": self.flow_store.watermark(),
            }

        if msg_type == "AGENT_CLEAR_FLOWS":
            self.flow_store.clear()
            return {"stats": self.flow_store.stats()}

        if msg_type == "AGENT_RUN_SCENARIO":
            return await self._agent_run_scenario(payload, owner=websocket)

        if msg_type == "AGENT_CLEAR_SCENARIO":
            return await self._agent_clear_scenario()

        if msg_type == "AGENT_REPLAY_REQUEST":
            return await self._agent_inject(self._agent_build_replay(payload), payload)

        if msg_type == "AGENT_SEND_REQUEST":
            return await self._agent_inject(self._agent_build_send(payload), payload)

        raise ValueError(f"Unhandled agent message {msg_type}")

    async def _agent_inject(self, request, payload):
        """Fire a request through our own proxy and, if asked, wait for its flow.

        The request is stamped with a correlation id so the wait finds *this*
        request even when the app under test hits the same URL concurrently.
        """
        replay_id = uuid.uuid4().hex[:12]
        headers = request.get("req_headers") or {}
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                headers = {}
        headers = dict(headers)
        headers[REPLAY_ID_HEADER] = replay_id
        request["req_headers"] = headers

        watermark = self.flow_store.watermark()
        self.replay_request(request)
        result = {
            "watermark": watermark,
            "replay_id": replay_id,
            "request": {"method": request.get("method"), "url": request.get("url")},
        }
        if not payload.get("wait"):
            # The caller reads the outcome with wait_for(since_seq=watermark).
            return result

        timeout = min(float(payload.get("timeout", 30.0)), MAX_WAIT_TIMEOUT)
        res = await self.flow_store.wait_for(
            replay_id=replay_id, since_seq=watermark, count=1, timeout=timeout,
        )
        result["timed_out"] = res["timed_out"]
        if res["matched"]:
            result["flow"] = self.flow_store.detail(self.flow_store.get(res["matched"][0]["id"]))
        else:
            result["flow"] = None
            result["hint"] = (
                "No response within the timeout. Either the server is slow, or "
                "the request never reached the proxy (malformed URL, proxy port "
                "closed) — check the backend log."
            )
        return result

    @staticmethod
    def _agent_build_send(payload):
        """A request composed from scratch, not derived from a captured flow."""
        url = payload.get("url")
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            raise ValueError("url must be an absolute http:// or https:// URL")
        headers = payload.get("headers") or {}
        if not isinstance(headers, dict):
            raise TypeError("headers must be an object")
        body = payload.get("body")
        if body is not None and not isinstance(body, str):
            raise TypeError("body must be a string")
        return {
            "url": url,
            "method": str(payload.get("method") or "GET").upper(),
            "req_headers": {str(k): str(v) for k, v in headers.items()},
            "req_body": body or "",
        }

    async def _agent_reply(self, websocket, req_id, data=None, error=None):
        try:
            await websocket.send(json.dumps({
                "type": "AGENT_RESULT",
                "req_id": req_id,
                "ok": error is None,
                "data": data if data is not None else {},
                "error": error,
            }))
        except Exception as e:
            print(f"[Agent] Failed to reply to {req_id}: {e}", flush=True)

    def _agent_build_replay(self, payload):
        """Resolve a replay payload to the request dict `replay_request` wants.

        Two shapes are accepted: `flow_id` (+ optional `overrides`), where the
        captured request is looked up here, or a fully-specified `request`
        for callers that already have one (the UI's composer, older clients).

        Looking the flow up server-side is what makes the truncation check
        possible: the store caps bodies at 32KB and marks the rest, so a body
        read back through the wire looks complete when it isn't. Replaying it
        would send a corrupted payload — refuse unless the caller supplies
        their own body.
        """
        flow_id = payload.get("flow_id")
        if not flow_id:
            request = payload.get("request")
            if not isinstance(request, dict) or not request.get("url"):
                raise ValueError("Replay needs either flow_id or a request with a url")
            return dict(request)

        entry = self.flow_store.get(flow_id)
        if entry is None:
            raise KeyError(
                f"No flow {flow_id!r} in history "
                f"(buffer holds the last {self.flow_store.stats()['capacity']})"
            )

        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise TypeError("overrides must be an object")
        unknown = set(overrides) - REPLAY_OVERRIDES
        if unknown:
            raise ValueError(
                f"Unknown replay override(s) {sorted(unknown)}; "
                f"allowed: {sorted(REPLAY_OVERRIDES)}"
            )

        request = {
            "url": entry["url"],
            "method": entry["method"],
            "req_headers": dict(entry["req_headers"]),
            "req_body": entry["req_body"],
        }
        for field, value in overrides.items():
            if value is not None:
                request[field] = value
        request["method"] = str(request["method"] or "GET").upper()

        body_overridden = overrides.get("req_body") is not None
        if entry["req_body"] and not entry["req_body_complete"] and not body_overridden:
            raise ValueError(
                f"Refusing to replay {flow_id}: its request body was truncated or "
                f"omitted in history ({entry['req_bytes']} bytes on the wire), so "
                "resending it would send a corrupted payload. Pass req_body to "
                "supply one yourself."
            )
        return request

    def _agent_status(self):
        return {
            "version": self._agent_app_version(),
            "protocol": AGENT_PROTOCOL_VERSION,
            "mcp_command": self.mcp_shim_path,
            "proxy_port": self.proxy_port,
            "local_ip": system_helpers.LOCAL_IP,
            "recording": self.is_recording,
            "throttle": self._effective_throttle(),
            "map_local_enabled": self.map_local_enabled,
            "map_remote_enabled": self.map_remote_enabled,
            "user_rule_counts": {
                "map_local": len(self.map_local_rules),
                "map_remote": len(self.map_remote_rules),
            },
            "scenario": self.agent_scenario,
            "flows": self.flow_store.stats(),
            "ui_clients": len(self.connected_clients),
        }

    @staticmethod
    def _agent_app_version():
        from server.constants import APP_VERSION
        return APP_VERSION

    async def _agent_run_scenario(self, payload, owner=None):
        """Install a named set of agent-owned rules, replacing any previous one.

        Replacing rather than merging is deliberate: scenarios are run in
        sequence and rules leaking from scenario N into N+1 is the failure mode
        that makes this whole workflow untrustworthy.
        """
        name = payload.get("name") or "unnamed scenario"
        map_local = payload.get("map_local") or []
        map_remote = payload.get("map_remote") or []
        throttle = payload.get("throttle")

        if not isinstance(map_local, list) or not isinstance(map_remote, list):
            raise TypeError("map_local and map_remote must be lists of rules")
        if throttle is not None and throttle not in THROTTLE_PROFILES:
            raise ValueError(
                f"Unknown throttle profile {throttle!r}; "
                f"expected one of {sorted(THROTTLE_PROFILES)}"
            )
        for i, rule in enumerate(map_local):
            if not isinstance(rule, dict) or not rule.get("pattern"):
                raise ValueError(f"map_local[{i}] needs a non-empty pattern")
            try:
                status = int(rule.get("status", 200))
            except (TypeError, ValueError):
                raise ValueError(f"map_local[{i}] status {rule.get('status')!r} is not an integer")
            if not 100 <= status <= 599:
                raise ValueError(f"map_local[{i}] status {status} is outside 100-599")
            delay = rule.get("delay_ms") or 0
            if not isinstance(delay, (int, float)) or not 0 <= delay <= MAX_MOCK_DELAY_MS:
                raise ValueError(f"map_local[{i}] delay_ms must be 0-{MAX_MOCK_DELAY_MS}")
            responses = rule.get("responses")
            if responses is not None:
                if not isinstance(responses, list) or not responses:
                    raise ValueError(f"map_local[{i}] responses must be a non-empty list")
                for j, step in enumerate(responses):
                    if not isinstance(step, dict):
                        raise ValueError(f"map_local[{i}].responses[{j}] must be an object")
                    if "status" in step:
                        try:
                            st = int(step["status"])
                        except (TypeError, ValueError):
                            raise ValueError(f"map_local[{i}].responses[{j}] status is not an integer")
                        if not 100 <= st <= 599:
                            raise ValueError(f"map_local[{i}].responses[{j}] status {st} is outside 100-599")
            mode = rule.get("sequence_mode")
            if mode is not None and mode not in SEQUENCE_MODES:
                raise ValueError(f"map_local[{i}] sequence_mode must be one of {sorted(SEQUENCE_MODES)}")
        for i, rule in enumerate(map_remote):
            if not isinstance(rule, dict) or not rule.get("pattern"):
                raise ValueError(f"map_remote[{i}] needs a non-empty pattern")

        # Rules arrive from an agent, so default the fields the matcher relies
        # on rather than trusting every key to be present.
        normalised_local = [self._normalise_local_rule(r) for r in map_local]
        normalised_remote = [
            {"active": r.get("active", True),
             "pattern": r.get("pattern", ""),
             "target": r.get("target", "")}
            for r in map_remote
        ]

        # Keep the agent's untouched version so clearing an override can restore
        # it, then re-apply anything the user has taken over. Scenarios replace
        # each other wholesale, so without this the user's edit would silently
        # vanish on the agent's next run — precisely the surprise this whole
        # surface exists to avoid.
        # A fresh scenario supersedes any pending "an agent vanished, want its
        # rules?" offer — otherwise the UI could adopt rules from a dead agent
        # while a live one is already running something else.
        self.agent_last_scenario = None
        self.agent_end_reason = None

        self.agent_rule_order, self.agent_rule_originals = self._index_rules(
            normalised_local, self.rule_key
        )
        self.agent_remote_order, self.agent_remote_originals = self._index_rules(
            normalised_remote, self.remote_key
        )

        self.agent_throttle_profile = throttle
        self.agent_scenario_owner = owner
        self.agent_rule_hits = {}
        self.agent_scenario = {
            "name": name,
            "started_seq": self.flow_store.watermark(),
            "started_at": time.time(),
            "throttle": throttle,
        }
        # Builds the live rule lists and the broadcast snapshot from the
        # originals just indexed, so installing a scenario and editing one go
        # through exactly the same path.
        self._reapply_overrides()

        print(f"[Agent] Scenario '{name}': {len(normalised_local)} mock(s), "
              f"{len(normalised_remote)} rewrite(s), throttle={throttle}", flush=True)

        await self.broadcast_agent_state()

        return {"scenario": self.agent_scenario, "watermark": self.agent_scenario["started_seq"]}

    # ---- user overrides over agent rules ---------------------------------

    @staticmethod
    def rule_key(rule):
        """Identity an override on a mock is filed under.

        Pattern plus method, because that pair is what actually decides which
        requests a rule catches — an agent re-running the same scenario with a
        different body still matches the same traffic, and that's the case the
        user's edit needs to survive.

        Only ever called on a rule as the *agent* sent it. The result is stored
        in `agent_rule_order` and carried from there, so a user override that
        changes the pattern doesn't move the rule out from under its own key.
        """
        return f"{(rule.get('method') or 'ANY').upper()}|{rule.get('pattern', '')}"

    @staticmethod
    def remote_key(rule):
        """Identity an override on a rewrite is filed under. Pattern only —
        that's the whole of a rewrite's matching half."""
        return f"REWRITE|{rule.get('pattern', '')}"

    @staticmethod
    def _index_rules(rules, key_fn):
        """Freeze the agent's rules as (ordered keys, key -> untouched rule).

        Two rules can legitimately share a pattern and method, so identical
        keys get a suffix. Without it the second rule would inherit the first's
        overrides and the user would watch an edit they made to one rule appear
        on another.
        """
        order, originals = [], {}
        for rule in rules:
            key = key_fn(rule)
            if key in originals:
                n = 2
                while f"{key}#{n}" in originals:
                    n += 1
                key = f"{key}#{n}"
            order.append(key)
            originals[key] = dict(rule)
        return order, originals

    def _overrides_for(self, kind):
        return (
            (self.agent_remote_overrides, OVERRIDABLE_REMOTE_FIELDS)
            if kind == "remote"
            else (self.agent_rule_overrides, OVERRIDABLE_FIELDS)
        )

    def _apply_override(self, key, rule, kind="local"):
        """Overlay the fields the user has taken over onto an agent's rule."""
        table, allowed = self._overrides_for(kind)
        override = table.get(key)
        if not override:
            return dict(rule)
        merged = dict(rule)
        for field, value in override.items():
            if field in allowed:
                merged[field] = value
        return merged

    def _describe_rule(self, key, rule, kind="local"):
        """One agent-owned rule as the UI needs it: full content, plus which
        fields the user has taken over so the editor can mark them.

        Shaped exactly like a rule in the user's own list (with `key` standing
        in for `id`) so the Map Local / Map Remote editors can drive it without
        a second code path.
        """
        table, allowed = self._overrides_for(kind)
        override = table.get(key) or {}
        # Field names, not a boolean: the UI marks the individual inputs the
        # user owns, so it's obvious what the agent no longer controls.
        overridden = sorted(f for f in override if f in allowed)

        if kind == "remote":
            return {
                "key": key,
                "active": rule.get("active", True),
                "pattern": rule.get("pattern", ""),
                "target": rule.get("target", ""),
                "overridden": overridden,
            }
        return {
            "key": key,
            "active": rule.get("active", True),
            "label": rule.get("label", ""),
            "pattern": rule.get("pattern", ""),
            "method": rule.get("method", "ANY"),
            "status": rule.get("status", 200),
            "headers": rule.get("headers", ""),
            "body": rule.get("body", ""),
            "body_source": rule.get("body_source", "inline"),
            "file_path": rule.get("file_path", ""),
            "req_headers_mod": rule.get("req_headers_mod", {}),
            # Agent-only extras; the UI editor shows but doesn't edit these.
            "delay_ms": rule.get("delay_ms") or 0,
            "responses": rule.get("responses") or None,
            "sequence_mode": rule.get("sequence_mode") or "hold",
            "overridden": overridden,
        }

    async def set_agent_rule_override(self, key, fields, kind="local"):
        """Record a user edit to an agent-owned rule and apply it immediately."""
        if not key:
            return
        table, allowed = self._overrides_for(kind)
        current = dict(table.get(key) or {})
        for field, value in (fields or {}).items():
            if field in allowed:
                current[field] = value
        if not current:
            table.pop(key, None)
        else:
            table[key] = current

        self._reapply_overrides()
        await self.log_agent_activity(
            "override",
            f"You took over {key.split('|', 1)[-1]}",
            surface="map_remote" if kind == "remote" else "map_local",
        )
        await self.broadcast_agent_state()

    async def clear_agent_rule_override(self, key, kind="local"):
        """Hand a rule back to the agent, restoring whatever it last installed."""
        table, _ = self._overrides_for(kind)
        if key is None:
            table.clear()
        else:
            table.pop(key, None)
        self._reapply_overrides()
        await self.broadcast_agent_state()

    def _reapply_overrides(self):
        """Recompute live rules and the broadcast snapshot from current overrides.

        Everything is rebuilt from `agent_rule_originals` / `agent_remote_originals`
        rather than from the currently-installed rules, so clearing an override
        restores the agent's value instead of leaving the user's stuck in place.
        """
        self.agent_map_local_rules = [
            {**self._apply_override(k, self.agent_rule_originals.get(k, {}), "local"), "_key": k}
            for k in self.agent_rule_order
        ]
        self.agent_map_remote_rules = [
            self._apply_override(k, self.agent_remote_originals.get(k, {}), "remote")
            for k in self.agent_remote_order
        ]
        if self.agent_scenario:
            # Full rules, not summaries: the user has to be able to read the
            # body an agent is serving to tell a mock apart from a real bug,
            # and to adopt the rule as their own once the agent goes away.
            self.agent_scenario["mocks"] = [
                self._describe_rule(k, r, "local")
                for k, r in zip(self.agent_rule_order, self.agent_map_local_rules)
            ]
            self.agent_scenario["rewrites"] = [
                self._describe_rule(k, r, "remote")
                for k, r in zip(self.agent_remote_order, self.agent_map_remote_rules)
            ]

    @staticmethod
    def _normalise_local_rule(rule):
        headers = rule.get("headers", "")
        # The matcher expects `headers` as a JSON *string* (that's what the UI
        # stores); accept a dict too since it's the natural thing for a client.
        if isinstance(headers, dict):
            headers = json.dumps(headers)
        return {
            "active": rule.get("active", True),
            "label": rule.get("label", ""),
            "pattern": rule.get("pattern", ""),
            "method": rule.get("method", "ANY"),
            "status": rule.get("status", 200),
            "headers": headers,
            "body": rule.get("body", ""),
            "body_source": rule.get("body_source", "inline"),
            "file_path": rule.get("file_path", ""),
            "req_headers_mod": rule.get("req_headers_mod", {}),
            "delay_ms": rule.get("delay_ms") or 0,
            "responses": rule.get("responses") or None,
            "sequence_mode": rule.get("sequence_mode") or "hold",
        }

    async def _agent_clear_scenario(self, reason="agent_cleared"):
        """Tear down the active scenario.

        `reason` rides along on the broadcast because the UI treats the cases
        differently: rules from an agent that *vanished* are worth keeping
        around for the user to adopt, rules the user themselves stopped are not.
        """
        previous = self.agent_scenario
        self.agent_map_local_rules = []
        self.agent_map_remote_rules = []
        self.agent_rule_originals = {}
        self.agent_rule_order = []
        self.agent_remote_originals = {}
        self.agent_remote_order = []
        self.agent_throttle_profile = None
        self.agent_scenario = None
        self.agent_scenario_owner = None
        self.agent_rule_hits = {}
        self.agent_last_scenario = previous if reason == "disconnect" else None
        self.agent_end_reason = reason if previous else None
        await self.broadcast_agent_state()
        return {"cleared": previous}

    # ---- activity feed ---------------------------------------------------

    async def log_agent_activity(self, kind, message, surface=None):
        """Record one agent action for the UI's activity strip.

        `surface` names the window the action belongs to ("map_local",
        "map_remote", "traffic"), so the UI can offer to open the right one
        instead of duplicating the detail in the banner.
        """
        entry = {
            "kind": kind,
            "message": message,
            "surface": surface,
            "at": time.time(),
        }
        self.agent_activity.append(entry)
        if len(self.agent_activity) > ACTIVITY_LOG_LIMIT:
            del self.agent_activity[:-ACTIVITY_LOG_LIMIT]
        await self.broadcast_to_ui("AGENT_ACTIVITY", entry)

    def _activity_for(self, msg_type, payload, result, by_agent=True):
        """Human-readable description of an agent call, or None to stay quiet.

        Reads are deliberately low-noise: an agent listing traffic is not
        something the user needs narrated, but anything that *changes* what the
        proxy serves is. `by_agent` is False when the UI sent the message.
        """
        if not by_agent:
            if msg_type == "AGENT_CLEAR_SCENARIO":
                return "scenario", "You stopped the agent's mocks", None
            return None

        if msg_type == "AGENT_RUN_SCENARIO":
            sc = (result or {}).get("scenario") or {}
            n_mock, n_rw = len(sc.get("mocks") or []), len(sc.get("rewrites") or [])
            bits = []
            if n_mock:
                bits.append(f"{n_mock} mock{'' if n_mock == 1 else 's'}")
            if n_rw:
                bits.append(f"{n_rw} rewrite{'' if n_rw == 1 else 's'}")
            detail = " and ".join(bits) if bits else "no rules"
            surface = "map_local" if n_mock else ("map_remote" if n_rw else None)
            return "scenario", f"Started “{sc.get('name')}” — {detail}", surface

        if msg_type == "AGENT_CLEAR_SCENARIO":
            return "scenario", "Cleared its mocks", None
        if msg_type == "AGENT_REPLAY_REQUEST":
            url = ((result or {}).get("request") or {}).get("url", "")
            return "replay", f"Replayed {url}", "traffic"
        if msg_type == "AGENT_SEND_REQUEST":
            req = (result or {}).get("request") or {}
            return "replay", f"Sent {req.get('method', '')} {req.get('url', '')}", "traffic"
        if msg_type == "AGENT_GET_FLOWS":
            n = len((result or {}).get("flows") or [])
            return "read", f"Inspected {n} request{'' if n == 1 else 's'}", "traffic"
        if msg_type == "AGENT_CLEAR_FLOWS":
            return "history", "Cleared captured history", "traffic"
        if msg_type == "AGENT_GET_FLOW":
            return "read", "Inspected a request", "traffic"
        return None

    # ---- UI visibility ---------------------------------------------------

    def agent_state(self):
        """What the UI needs to show who is driving the proxy and how.

        Sent on UI connect and re-broadcast on every change, so a user can
        always see that an agent is attached and which endpoints it has taken
        over. Without this, agent-mocked traffic looks like a bug in the app
        under test.
        """
        return {
            "connected": len(self.agent_clients) > 0,
            "clients": sorted(self.agent_client_names.values()),
            "scenario": self.agent_scenario,
            # Set only when an agent disconnected mid-scenario. The UI adopts
            # these into the user's own rules (switched off) so the work isn't
            # lost, without leaving traffic mocked by an agent that's gone.
            "last_scenario": self.agent_last_scenario,
            "end_reason": self.agent_end_reason,
            "activity": self.agent_activity[-20:],
        }

    async def broadcast_agent_state(self):
        await self.broadcast_to_ui("AGENT_STATE", self.agent_state())

    # ---- shared replay ---------------------------------------------------

    def replay_request(self, req_data):
        """Re-send a request through our own proxy, off the event loop.

        Shared by the UI's REPEAT_REQUEST (composer / "repeat" button) and the
        agent's replay tool so both produce identical traffic.
        """
        def _replay():
            try:
                url = req_data.get("url")
                if not url or url == "https://":
                    print("[WARNING] Invalid URL in composer.")
                    return

                method = req_data.get("method", "GET").upper()
                req = urllib.request.Request(url, method=method)

                raw_headers = req_data.get("req_headers", {})
                if isinstance(raw_headers, str):
                    try:
                        raw_headers = json.loads(raw_headers)
                    except Exception:
                        raw_headers = {}

                for k, v in raw_headers.items():
                    if k.lower() not in ["host", "content-length", "accept-encoding"]:
                        req.add_header(k, str(v))

                body = req_data.get("req_body")
                # Any method may carry a body except the two where it's
                # meaningless; DELETE-with-body APIs exist and agents probe them.
                if body and method not in ("GET", "HEAD"):
                    if not req_data.get("req_is_image") and not str(body).startswith("//"):
                        req.data = body.encode('utf-8')
                        req.add_header('Content-Length', str(len(req.data)))

                proxy_handler = urllib.request.ProxyHandler({
                    'http': f'http://127.0.0.1:{self.proxy_port}',
                    'https': f'http://127.0.0.1:{self.proxy_port}'
                })

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                opener = urllib.request.build_opener(
                    proxy_handler, urllib.request.HTTPSHandler(context=ctx)
                )
                opener.open(req, timeout=300)
                print(f"[INFO] Successfully injected {method} to {url}")

            except Exception as e:
                print(f"[ERROR] Replay failed: {e}")

        threading.Thread(target=_replay, daemon=True).start()
