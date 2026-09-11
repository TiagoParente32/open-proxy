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
import asyncio
import threading
import urllib.request

from server import system_helpers

# Upper bound on a single wait_for_flows call. A wedged waiter would otherwise
# pin a future until the client disconnects.
MAX_WAIT_TIMEOUT = 300.0

AGENT_MESSAGE_TYPES = {
    "AGENT_HELLO",
    "AGENT_STATUS",
    "AGENT_LIST_FLOWS",
    "AGENT_GET_FLOW",
    "AGENT_CLEAR_FLOWS",
    "AGENT_WAIT_FOR_FLOWS",
    "AGENT_RUN_SCENARIO",
    "AGENT_CLEAR_SCENARIO",
    "AGENT_REPLAY_REQUEST",
}


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

        # Waiting blocks for as long as the caller asked for, so it runs
        # detached — otherwise this connection would process no other message
        # until the wait resolved.
        if msg_type == "AGENT_WAIT_FOR_FLOWS":
            task = asyncio.create_task(self._agent_wait_for_flows(websocket, req_id, payload))
            self.bg_tasks.add(task)
            task.add_done_callback(self.bg_tasks.discard)
            return True

        try:
            if msg_type == "AGENT_HELLO":
                # Mark this socket as automation so it stops receiving the UI
                # broadcast stream. Done here rather than at connect time
                # because the server can't tell a UI from an agent until asked.
                self.agent_clients.add(websocket)
                client = payload.get("client", "unknown")
                print(f"[Agent] '{client}' connected", flush=True)
                await self._agent_reply(websocket, req_id, data=self._agent_status())
                return True

            data = await self._dispatch_agent(msg_type, payload)
            await self._agent_reply(websocket, req_id, data=data)
        except Exception as e:
            await self._agent_reply(websocket, req_id, error=f"{type(e).__name__}: {e}")
        return True

    async def _dispatch_agent(self, msg_type, payload):
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
            return {"flow": entry}

        if msg_type == "AGENT_CLEAR_FLOWS":
            self.flow_store.clear()
            return {"stats": self.flow_store.stats()}

        if msg_type == "AGENT_RUN_SCENARIO":
            return await self._agent_run_scenario(payload)

        if msg_type == "AGENT_CLEAR_SCENARIO":
            return await self._agent_clear_scenario()

        if msg_type == "AGENT_REPLAY_REQUEST":
            watermark = self.flow_store.watermark()
            self.replay_request(payload.get("request", {}))
            # The replay is proxied, so it lands in the store like any other
            # request — the caller polls from this watermark for the result.
            return {"watermark": watermark}

        raise ValueError(f"Unhandled agent message {msg_type}")

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

    def _agent_status(self):
        return {
            "version": self._agent_app_version(),
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

    async def _agent_run_scenario(self, payload):
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

        # Rules arrive from an agent, so default the fields the matcher relies
        # on rather than trusting every key to be present.
        normalised_local = [self._normalise_local_rule(r) for r in map_local]
        normalised_remote = [
            {"active": r.get("active", True),
             "pattern": r.get("pattern", ""),
             "target": r.get("target", "")}
            for r in map_remote
        ]

        self.agent_map_local_rules = normalised_local
        self.agent_map_remote_rules = normalised_remote
        self.agent_throttle_profile = throttle
        self.agent_scenario = {
            "name": name,
            "started_seq": self.flow_store.watermark(),
            "started_at": time.time(),
            "map_local": len(normalised_local),
            "map_remote": len(normalised_remote),
            "throttle": throttle,
        }

        print(f"[Agent] Scenario '{name}': {len(normalised_local)} mock(s), "
              f"{len(normalised_remote)} rewrite(s), throttle={throttle}", flush=True)

        # Surface it to any connected UI. The Vue store ignores message types it
        # doesn't know, so this is safe ahead of UI support landing.
        await self.broadcast_to_ui("AGENT_SCENARIO", self.agent_scenario)

        return {"scenario": self.agent_scenario, "watermark": self.agent_scenario["started_seq"]}

    @staticmethod
    def _normalise_local_rule(rule):
        headers = rule.get("headers", "")
        # The matcher expects `headers` as a JSON *string* (that's what the UI
        # stores); accept a dict too since it's the natural thing for a client.
        if isinstance(headers, dict):
            headers = json.dumps(headers)
        return {
            "active": rule.get("active", True),
            "pattern": rule.get("pattern", ""),
            "method": rule.get("method", "ANY"),
            "status": rule.get("status", 200),
            "headers": headers,
            "body": rule.get("body", ""),
            "body_source": rule.get("body_source", "inline"),
            "file_path": rule.get("file_path", ""),
            "req_headers_mod": rule.get("req_headers_mod", {}),
        }

    async def _agent_clear_scenario(self):
        previous = self.agent_scenario
        self.agent_map_local_rules = []
        self.agent_map_remote_rules = []
        self.agent_throttle_profile = None
        self.agent_scenario = None
        await self.broadcast_to_ui("AGENT_SCENARIO", None)
        return {"cleared": previous}

    async def _agent_wait_for_flows(self, websocket, req_id, payload):
        try:
            timeout = min(float(payload.get("timeout", 30.0)), MAX_WAIT_TIMEOUT)
            result = await self.flow_store.wait_for(
                url_pattern=payload.get("url_pattern"),
                method=payload.get("method"),
                status=payload.get("status"),
                since_seq=payload.get("since_seq"),
                count=int(payload.get("count", 1)),
                timeout=timeout,
            )
            await self._agent_reply(websocket, req_id, data={
                "matched": result["matched"],
                "timed_out": result["timed_out"],
                "watermark": self.flow_store.watermark(),
            })
        except Exception as e:
            await self._agent_reply(websocket, req_id, error=f"{type(e).__name__}: {e}")

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
                if body and method in ["POST", "PUT", "PATCH"]:
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
