#!/usr/bin/env python3
"""Integration test for the OpenProxy agent API and MCP client.

Starts its own backend on free ports (so it won't collide with an installed
OpenProxy), drives real traffic through mitmproxy, and asserts on what the
agent surface reports. No pytest dependency — run it directly:

    python mcp-server/tests/test_agent_api.py

Requires the app's own dependencies (mitmproxy, websockets) on the path; the
repo venv works:

    venv/bin/python mcp-server/tests/test_agent_api.py
"""
import os
import sys
import ssl
import json
import time
import socket
import asyncio
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))

import websockets  # noqa: E402
from openproxy_mcp.client import OpenProxyClient  # noqa: E402

MOCK_URL = "http://mock.openproxy.test/api/profile"
BACKEND_BOOT_TIMEOUT = 40

failures = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_get(url, proxy_port):
    """Send a request through the proxy, returning (status, body)."""
    handler = urllib.request.ProxyHandler({
        "http": f"http://127.0.0.1:{proxy_port}",
        "https": f"http://127.0.0.1:{proxy_port}",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))
    try:
        with opener.open(url, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def http_request(method, url, proxy_port, body=None, headers=None):
    """Like http_get but with a method, body and headers. Returns (status, body)."""
    handler = urllib.request.ProxyHandler({
        "http": f"http://127.0.0.1:{proxy_port}",
        "https": f"http://127.0.0.1:{proxy_port}",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, method=method,
                                 data=body.encode() if body is not None else None)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def wait_for_port(port, timeout=BACKEND_BOOT_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


async def agent_call(ws, msg_type, payload=None, req_id="t"):
    """Minimal agent call for the raw-socket tests (no OpenProxyClient)."""
    msg = {"type": msg_type, "req_id": req_id}
    msg.update(payload or {})
    await ws.send(json.dumps(msg))
    while True:
        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
        if data.get("type") == "AGENT_RESULT" and data.get("req_id") == req_id:
            if not data.get("ok"):
                raise RuntimeError(data.get("error"))
            return data.get("data") or {}


async def test_agent_surface(ws_port):
    c = OpenProxyClient(f"ws://127.0.0.1:{ws_port}")

    print("\n== connection ==")
    status = await c.call("AGENT_STATUS")
    proxy_port = status["proxy_port"]
    check("AGENT_STATUS returns proxy port", isinstance(proxy_port, int), f"port={proxy_port}")
    check("starts with no active scenario", status["scenario"] is None)

    print("\n== scenario install + mocked traffic ==")
    scen = await c.call("AGENT_RUN_SCENARIO", {
        "name": "profile 500",
        "map_local": [{
            "active": True, "pattern": "*/api/profile*", "method": "ANY",
            "status": 500, "headers": {"Content-Type": "application/json"},
            "body": '{"error":"boom"}',
        }],
    })
    watermark = scen["watermark"]
    check("scenario returns a watermark", isinstance(watermark, int), f"watermark={watermark}")

    code, body = await asyncio.to_thread(http_get, MOCK_URL, proxy_port)
    check("mock returns configured status", code == 500, f"got {code}")
    check("mock returns configured body", body == '{"error":"boom"}', f"got {body!r}")

    print("\n== wait_for_flows ==")
    res = await c.call("AGENT_WAIT_FOR_FLOWS", {
        "url_pattern": "/api/profile", "since_seq": watermark,
        "count": 1, "timeout": 10,
    }, timeout=25)
    check("wait matched the mocked request", len(res["matched"]) == 1)
    flow_id = None
    if res["matched"]:
        m = res["matched"][0]
        flow_id = m["id"]
        check("matched flow has mocked status", m["status"] == 500, f"status={m['status']}")
        check("matched flow is flagged as mocked", m["mocked"] is True)
        check("matched flow seq is past watermark", m["seq"] > watermark)

    if flow_id:
        print("\n== get_flow ==")
        detail = (await c.call("AGENT_GET_FLOW", {"id": flow_id}))["flow"]
        check("full flow carries response body", detail["res_body"] == '{"error":"boom"}')
        check("full flow carries request headers", isinstance(detail["req_headers"], dict))

    print("\n== watermark isolation ==")
    later = await c.call("AGENT_WAIT_FOR_FLOWS", {
        "url_pattern": "/api/profile", "since_seq": 10_000,
        "count": 1, "timeout": 1,
    }, timeout=15)
    check("future watermark matches nothing", len(later["matched"]) == 0)
    check("timeout is reported honestly", later["timed_out"] is True)

    print("\n== list + filters ==")
    listing = await c.call("AGENT_LIST_FLOWS", {"url_pattern": "profile", "limit": 10})
    check("list finds the flow by substring", len(listing["flows"]) >= 1)
    check("non-matching glob returns nothing",
          len((await c.call("AGENT_LIST_FLOWS", {"url_pattern": "*/nope/*"}))["flows"]) == 0)
    check("method filter excludes",
          len((await c.call("AGENT_LIST_FLOWS", {"method": "DELETE"}))["flows"]) == 0)

    print("\n== scenario clear ==")
    await c.call("AGENT_CLEAR_SCENARIO")
    check("scenario is gone", (await c.call("AGENT_STATUS"))["scenario"] is None)
    code2, _ = await asyncio.to_thread(http_get, MOCK_URL, proxy_port)
    check("traffic no longer mocked after clear", code2 != 500, f"got {code2}")

    print("\n== error envelope ==")
    try:
        await c.call("AGENT_GET_FLOW", {"id": "does-not-exist"})
        check("unknown flow id raises", False, "no exception")
    except Exception as e:
        check("unknown flow id raises a clear error", "does-not-exist" in str(e))

    print("\n== clear history ==")
    st = await c.call("AGENT_CLEAR_FLOWS")
    check("history emptied", st["stats"]["count"] == 0)
    check("watermark keeps counting after clear", st["stats"]["watermark"] > watermark)

    await c.close()
    return proxy_port


async def test_ui_not_regressed(ws_port):
    """broadcast_to_ui now filters agent sockets, and REPEAT_REQUEST moved into
    AgentApiMixin — both must leave the UI protocol untouched."""
    print("\n== UI client still works ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        first = json.loads(await asyncio.wait_for(ui.recv(), timeout=10))
        check("UI gets SYSTEM_INFO on connect", first.get("type") == "SYSTEM_INFO")
        proxy_port = first["data"]["port"]
        second = json.loads(await asyncio.wait_for(ui.recv(), timeout=10))
        check("UI gets SCRIPTS_LIST on connect", second.get("type") == "SCRIPTS_LIST")

        asyncio.create_task(asyncio.to_thread(http_get, "http://example.com/", proxy_port))
        check("UI still receives NEW_REQUEST broadcasts",
              await _await_message(ui, lambda m: m.get("type") == "NEW_REQUEST"))

        await ui.send(json.dumps({
            "type": "REPEAT_REQUEST",
            "request": {"url": "http://example.com/replayed", "method": "GET", "req_headers": {}},
        }))
        check("REPEAT_REQUEST still replays through the proxy",
              await _await_message(
                  ui,
                  lambda m: m.get("type") == "NEW_REQUEST" and "/replayed" in m["data"].get("url", ""),
              ))


async def test_ui_sees_agent_activity(ws_port):
    """The UI must always be able to show who is driving the proxy and how.

    Agent-mocked traffic that the user can't attribute is the failure mode this
    whole surface exists to avoid — they end up debugging a problem that isn't
    theirs. Every transition below has to reach the UI.
    """
    print("\n== UI sees agent activity ==")
    ui = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    try:
        # Connect handshake now carries agent state so a UI opened mid-session
        # isn't blind to an agent that attached earlier.
        seen = {}
        for _ in range(3):
            msg = json.loads(await asyncio.wait_for(ui.recv(), timeout=10))
            seen[msg["type"]] = msg
        check("UI gets AGENT_STATE on connect", "AGENT_STATE" in seen, str(list(seen)))
        proxy_port = seen["SYSTEM_INFO"]["data"]["port"]
        check("no agent reported before one connects",
              seen.get("AGENT_STATE", {}).get("data", {}).get("connected") is False)

        agent = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
        try:
            await agent_call(agent, "AGENT_HELLO", {"client": "test-agent"}, req_id="u1")
            state = await _await_payload(ui, lambda m: m.get("type") == "AGENT_STATE"
                                         and m["data"]["connected"])
            check("UI is told when an agent connects", state is not None)
            check("UI learns the agent's name",
                  state and "test-agent" in state["data"]["clients"],
                  str(state and state["data"]["clients"]))
            check("connected-but-idle reports no scenario",
                  state and state["data"]["scenario"] is None)

            await agent_call(agent, "AGENT_RUN_SCENARIO", {
                "name": "checkout 503",
                "map_local": [{"active": True, "pattern": "*/api/checkout*",
                               "method": "ANY", "status": 503, "body": "down"}],
                "throttle": "Slow 3G",
            }, req_id="u2")

            state = await _await_payload(ui, lambda m: m.get("type") == "AGENT_STATE"
                                         and m["data"]["scenario"])
            check("UI is told when a scenario starts", state is not None)
            scen = state["data"]["scenario"] if state else {}
            check("UI gets the scenario name", scen.get("name") == "checkout 503")
            check("UI gets the mocked patterns, not just a count",
                  scen.get("mocks") and scen["mocks"][0]["pattern"] == "*/api/checkout*",
                  str(scen.get("mocks")))
            check("UI gets the mocked method", scen.get("mocks", [{}])[0].get("method") == "ANY")
            check("UI gets the mocked status", scen.get("mocks", [{}])[0].get("status") == 503)
            check("UI gets the throttle override", scen.get("throttle") == "Slow 3G")

            # A mocked response must be attributable in the traffic table.
            asyncio.create_task(asyncio.to_thread(
                http_get, "http://mock.test/api/checkout", proxy_port))
            upd = await _await_payload(
                ui, lambda m: m.get("type") == "UPDATE_REQUEST" and m["data"].get("agent_mock"),
                timeout=25)
            check("mocked request is attributed to the agent in the traffic feed",
                  upd is not None and upd["data"]["agent_mock"] == "checkout 503",
                  str(upd and upd["data"].get("agent_mock")))

            # The user must be able to take their proxy back without hunting
            # down the agent.
            await ui.send(json.dumps({"type": "AGENT_CLEAR_SCENARIO", "req_id": "ui-stop"}))
            state = await _await_payload(ui, lambda m: m.get("type") == "AGENT_STATE"
                                         and m["data"]["scenario"] is None)
            check("UI can force-stop an agent scenario", state is not None)
            code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/checkout", proxy_port)
            check("traffic really is unmocked after the UI stops it", code != 503, f"got {code}")
        finally:
            await agent.close()

        state = await _await_payload(ui, lambda m: m.get("type") == "AGENT_STATE"
                                     and not m["data"]["connected"])
        check("UI is told when the agent disconnects", state is not None)
    finally:
        await ui.close()


async def _await_payload(ws, predicate, timeout=20):
    """Like _await_message but returns the matching payload (or None)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except asyncio.TimeoutError:
            return None
        if predicate(msg):
            return msg
    return None


async def _await_message(ws, predicate, timeout=20):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except asyncio.TimeoutError:
            return False
        if predicate(msg):
            return True
    return False


async def test_disconnect_clears_scenario(ws_port):
    """An agent that dies mid-scenario must not strand the user with mocks."""
    print("\n== agent disconnect clears its scenario ==")
    agent = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    await agent_call(agent, "AGENT_HELLO", {"client": "integration-test"}, req_id="d1")
    await agent_call(agent, "AGENT_RUN_SCENARIO", {
        "name": "stranded",
        "map_local": [{"active": True, "pattern": "*/api/orphan*", "status": 418, "body": "teapot"}],
    }, req_id="d2")

    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as probe:
        await probe.recv(); await probe.recv()
        st = await agent_call(probe, "AGENT_STATUS", req_id="d3")
        check("scenario active while agent connected",
              st["scenario"] and st["scenario"]["name"] == "stranded")
        proxy_port = st["proxy_port"]

    code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/orphan", proxy_port)
    check("agent mock is serving", code == 418, f"got {code}")

    await agent.close()          # simulates the MCP server crashing
    await asyncio.sleep(1.5)

    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as probe:
        await probe.recv(); await probe.recv()
        st = await agent_call(probe, "AGENT_STATUS", req_id="d4")
        check("scenario auto-cleared on disconnect", st["scenario"] is None)

    code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/orphan", proxy_port)
    check("traffic no longer mocked after disconnect", code != 418, f"got {code}")


async def test_user_overrides_survive_rerun(ws_port):
    """A hand edit to an agent's mock must outlive the agent's next scenario.

    Scenarios replace each other wholesale, so without overrides the user's edit
    would silently vanish the moment the agent re-ran the same test — the exact
    surprise the agent surface exists to prevent.
    """
    print("\n== user overrides on agent mocks ==")
    RULE = {"active": True, "pattern": "*/api/cart*", "method": "GET",
            "status": 500, "body": "agent body"}

    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "override-test"}, req_id="o1")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO",
                             {"name": "cart v1", "map_local": [RULE]}, req_id="o2")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="o3"))["proxy_port"]

        mock = r["scenario"]["mocks"][0]
        check("UI receives the mock's full body, not just a summary",
              mock.get("body") == "agent body", f"got {mock.get('body')!r}")
        check("mock carries a stable override key", bool(mock.get("key")))
        key = mock["key"]

        code, body = await asyncio.to_thread(http_get, "http://mock.test/api/cart", proxy_port)
        check("agent's version serves first", code == 500 and "agent body" in body,
              f"{code} {body[:40]!r}")

        # The user takes over status and body.
        await ui.send(json.dumps({
            "type": "SET_AGENT_RULE_OVERRIDE", "key": key,
            "fields": {"status": 201, "body": "my body"},
        }))
        await asyncio.sleep(0.8)

        code, body = await asyncio.to_thread(http_get, "http://mock.test/api/cart", proxy_port)
        check("user's edit takes effect immediately", code == 201 and "my body" in body,
              f"{code} {body[:40]!r}")

        # The agent re-runs the same scenario with different values.
        r2 = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "cart v2",
            "map_local": [{**RULE, "status": 503, "body": "agent body v2"}],
        }, req_id="o4")

        code, body = await asyncio.to_thread(http_get, "http://mock.test/api/cart", proxy_port)
        check("user's edit survives the agent's next scenario",
              code == 201 and "my body" in body, f"{code} {body[:40]!r}")
        check("UI is told which fields the user owns",
              sorted(r2["scenario"]["mocks"][0].get("overridden") or []) == ["body", "status"],
              str(r2["scenario"]["mocks"][0].get("overridden")))

        # Handing it back restores whatever the agent last installed.
        await ui.send(json.dumps({"type": "CLEAR_AGENT_RULE_OVERRIDE", "key": key}))
        await asyncio.sleep(0.8)
        code, body = await asyncio.to_thread(http_get, "http://mock.test/api/cart", proxy_port)
        check("reverting restores the agent's latest version",
              code == 503 and "agent body v2" in body, f"{code} {body[:40]!r}")


async def test_disconnect_preserves_rules_for_adoption(ws_port):
    """Rules from a vanished agent are handed to the UI instead of dropped."""
    print("\n== disconnect hands rules over for adoption ==")
    agent = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    await agent_call(agent, "AGENT_HELLO", {"client": "adopt-test"}, req_id="p1")
    await agent_call(agent, "AGENT_RUN_SCENARIO", {
        "name": "keep me",
        "map_local": [{"active": True, "pattern": "*/api/keep*", "status": 402, "body": "pay"}],
        "map_remote": [{"active": True, "pattern": "a\\.com", "target": "localhost:1"}],
    }, req_id="p2")

    ui = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    await ui.recv(); await ui.recv()

    # Drain past the AGENT_STATE sent on connect before arming the wait below —
    # otherwise that queued snapshot is what the predicate matches.
    drained = await _await_payload(
        ui, lambda m: m.get("type") == "AGENT_STATE" and m["data"].get("scenario"))
    check("UI sees the live scenario before the agent dies", drained is not None)

    await agent.close()
    state = await _await_payload(ui, lambda m: m.get("type") == "AGENT_STATE"
                                 and m["data"].get("end_reason") == "disconnect")
    check("UI is told the scenario ended by disconnect", state is not None)
    if state:
        last = state["data"].get("last_scenario") or {}
        check("the vanished scenario's rules come with it",
              len(last.get("mocks") or []) == 1 and len(last.get("rewrites") or []) == 1,
              f"mocks={len(last.get('mocks') or [])} rewrites={len(last.get('rewrites') or [])}")
        check("adoptable rules carry their full body",
              (last.get("mocks") or [{}])[0].get("body") == "pay")

    # A user-initiated stop must NOT be offered for adoption.
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent2:
        await agent_call(agent2, "AGENT_HELLO", {"client": "adopt-test-2"}, req_id="p3")
        await agent_call(agent2, "AGENT_RUN_SCENARIO", {
            "name": "stopped by hand",
            "map_local": [{"active": True, "pattern": "*/api/x*", "status": 400}],
        }, req_id="p4")
        await agent_call(agent2, "AGENT_CLEAR_SCENARIO", req_id="p5")
        st = await agent_call(agent2, "AGENT_STATUS", req_id="p6")
        check("an explicitly cleared scenario is not offered for adoption",
              st.get("last_scenario") is None)
    await ui.close()


async def test_activity_feed(ws_port):
    """The UI gets a per-action feed, so the banner can say what it's doing."""
    print("\n== agent activity feed ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "activity-test"}, req_id="a1")
        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "noisy",
            "map_local": [{"active": True, "pattern": "*/api/n*", "status": 200}],
        }, req_id="a2")

        act = await _await_payload(ui, lambda m: m.get("type") == "AGENT_ACTIVITY")
        check("UI receives an activity event", act is not None)
        if act:
            check("activity names the scenario", "noisy" in act["data"].get("message", ""),
                  act["data"].get("message"))
            check("activity points at the right window",
                  act["data"].get("surface") == "map_local", act["data"].get("surface"))


async def test_full_editor_fields_are_overridable(ws_port):
    """Every field the Map Local editor exposes can be taken over.

    The editor is shared with the user's own rules, so anything it can write has
    to survive the round trip — including `pattern`, which is half the identity
    the override is filed under and the one field most likely to orphan itself.
    """
    print("\n== agent rules are editable in the normal editor ==")
    RULE = {"active": True, "pattern": "*/api/orders*", "method": "GET",
            "status": 500, "body": "agent body", "label": "agent label"}

    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "editor-test"}, req_id="e1")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO",
                             {"name": "orders", "map_local": [RULE]}, req_id="e2")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="e3"))["proxy_port"]

        mock = r["scenario"]["mocks"][0]
        check("mock arrives shaped like a rule the editor can drive",
              {"key", "active", "label", "pattern", "method", "status",
               "headers", "body", "body_source", "file_path",
               "req_headers_mod"} <= set(mock),
              str(sorted(mock)))
        key = mock["key"]

        # Re-point the rule at a different URL, exactly as typing in the omnibar would.
        await ui.send(json.dumps({
            "type": "SET_AGENT_RULE_OVERRIDE", "kind": "local", "key": key,
            "fields": {"pattern": "*/api/invoices*", "label": "my label"},
        }))
        await asyncio.sleep(0.8)

        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/invoices", proxy_port)
        check("a re-pointed rule matches its new URL", code == 500, f"got {code}")
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/orders", proxy_port)
        check("and stops matching the agent's old one", code == 502, f"got {code}")

        # The key must NOT have moved with the pattern, or the next scenario
        # would reinstall the agent's URL and the edit would evaporate.
        r2 = await agent_call(agent, "AGENT_RUN_SCENARIO",
                              {"name": "orders again", "map_local": [RULE]}, req_id="e4")
        check("the override key survives a pattern change",
              r2["scenario"]["mocks"][0]["key"] == key,
              f"{r2['scenario']['mocks'][0]['key']} != {key}")
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/invoices", proxy_port)
        check("the re-pointed URL still matches after the agent re-runs",
              code == 500, f"got {code}")
        check("the label the user typed is theirs now",
              r2["scenario"]["mocks"][0]["label"] == "my label",
              r2["scenario"]["mocks"][0]["label"])

        # The sidebar checkbox: switching an agent's rule off must stop it mocking
        # without tearing down the rest of the scenario.
        await ui.send(json.dumps({
            "type": "SET_AGENT_RULE_OVERRIDE", "kind": "local", "key": key,
            "fields": {"active": False},
        }))
        await asyncio.sleep(0.8)
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/invoices", proxy_port)
        check("unchecking an agent rule stops it mocking", code == 502, f"got {code}")

        state = await agent_call(agent, "AGENT_STATUS", req_id="e5")
        check("the rule stays visible while switched off",
              len(state["scenario"]["mocks"]) == 1)

        await ui.send(json.dumps({
            "type": "CLEAR_AGENT_RULE_OVERRIDE", "kind": "local", "key": key}))
        await asyncio.sleep(0.8)
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/orders", proxy_port)
        check("reverting gives the agent its URL back", code == 500, f"got {code}")


async def test_rewrites_are_overridable(ws_port):
    """Map Remote gets the same treatment as Map Local, not a read-only list."""
    print("\n== agent rewrites are editable too ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "rewrite-test"}, req_id="w1")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "reroute",
            "map_remote": [{"active": True, "pattern": "old\\.test", "target": "new.test"}],
        }, req_id="w2")

        rw = r["scenario"]["rewrites"][0]
        check("rewrite carries a stable override key", bool(rw.get("key")), str(rw))
        check("rewrite arrives with its active flag", rw.get("active") is True)
        key = rw["key"]

        await ui.send(json.dumps({
            "type": "SET_AGENT_RULE_OVERRIDE", "kind": "remote", "key": key,
            "fields": {"target": "mine.test"},
        }))
        await asyncio.sleep(0.8)

        r2 = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "reroute v2",
            "map_remote": [{"active": True, "pattern": "old\\.test", "target": "agent2.test"}],
        }, req_id="w3")
        rw2 = r2["scenario"]["rewrites"][0]
        check("a hand-edited rewrite survives the agent's next scenario",
              rw2.get("target") == "mine.test", rw2.get("target"))
        check("UI is told which rewrite fields the user owns",
              rw2.get("overridden") == ["target"], str(rw2.get("overridden")))

        await ui.send(json.dumps({
            "type": "CLEAR_AGENT_RULE_OVERRIDE", "kind": "remote", "key": key}))
        await asyncio.sleep(0.8)
        state = await agent_call(agent, "AGENT_STATUS", req_id="w4")
        check("reverting restores the agent's target",
              state["scenario"]["rewrites"][0]["target"] == "agent2.test",
              state["scenario"]["rewrites"][0]["target"])

        # Two rules can legitimately share a pattern; if they shared a key, an
        # edit to one would silently appear on the other.
        r3 = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "twins",
            "map_local": [
                {"active": True, "pattern": "*/api/twin*", "method": "GET", "status": 201},
                {"active": True, "pattern": "*/api/twin*", "method": "GET", "status": 202},
            ],
        }, req_id="w5")
        keys = [m["key"] for m in r3["scenario"]["mocks"]]
        check("identical rules get distinct override keys",
              len(set(keys)) == 2, str(keys))


async def test_replay_by_flow_id(ws_port):
    """Replay resolves the captured request server-side and refuses corrupted bodies.

    The store caps bodies at 32KB; a client reading one back can't tell a
    truncated body from a complete one, so the check has to live where the
    flag does.
    """
    print("\n== replay by flow id ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "replay-test"}, req_id="r0")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "echo",
            "map_local": [{"active": True, "pattern": "*/api/echo*", "status": 200, "body": "ok"}],
        }, req_id="r1")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="r2"))["proxy_port"]
        wm = r["watermark"]

        code, _ = await asyncio.to_thread(
            http_request, "POST", "http://mock.test/api/echo", proxy_port,
            body="hello", headers={"Content-Type": "text/plain"})
        check("original POST is mocked", code == 200, f"got {code}")
        got = await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
            "url_pattern": "/api/echo", "since_seq": wm, "count": 1, "timeout": 10}, req_id="r3")
        original = got["matched"][0]
        detail = (await agent_call(agent, "AGENT_GET_FLOW", {"id": original["id"]}, req_id="r4"))["flow"]
        check("small body is flagged complete", detail.get("req_body_complete") is True)

        rep = await agent_call(agent, "AGENT_REPLAY_REQUEST", {
            "flow_id": original["id"],
            "overrides": {"req_headers": {"X-Replayed": "1", "Content-Type": "text/plain"}},
        }, req_id="r5")
        check("replay returns a watermark", isinstance(rep.get("watermark"), int))
        check("replay echoes the resolved url", rep.get("request", {}).get("url", "").endswith("/api/echo"))
        got = await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
            "url_pattern": "/api/echo", "since_seq": rep["watermark"], "count": 1, "timeout": 10},
            req_id="r6")
        check("replayed request lands in history", len(got["matched"]) == 1)
        if got["matched"]:
            rd = (await agent_call(agent, "AGENT_GET_FLOW", {"id": got["matched"][0]["id"]},
                                   req_id="r7"))["flow"]
            check("replay keeps the original method", rd["method"] == "POST", rd["method"])
            check("replay keeps the original body", rd["req_body"] == "hello", rd["req_body"][:40])
            check("replay applies header overrides", rd["req_headers"].get("X-Replayed") == "1")

        try:
            await agent_call(agent, "AGENT_REPLAY_REQUEST", {
                "flow_id": original["id"], "overrides": {"bogus": 1}}, req_id="r8")
            check("unknown override is rejected", False, "no error")
        except RuntimeError as e:
            check("unknown override is rejected", "bogus" in str(e), str(e))

        try:
            await agent_call(agent, "AGENT_REPLAY_REQUEST", {}, req_id="r9")
            check("replay without flow_id or request is rejected", False, "no error")
        except RuntimeError as e:
            check("replay without flow_id or request is rejected", "flow_id" in str(e), str(e))

        # A body over the store's 32KB cap must not be resent from the store.
        big = "x" * (40 * 1024)
        wm2 = (await agent_call(agent, "AGENT_STATUS", req_id="r10"))["flows"]["watermark"]
        await asyncio.to_thread(http_request, "POST", "http://mock.test/api/echo/big", proxy_port,
                                body=big, headers={"Content-Type": "text/plain"})
        got = await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
            "url_pattern": "/api/echo/big", "since_seq": wm2, "count": 1, "timeout": 10}, req_id="r11")
        big_id = got["matched"][0]["id"]
        bd = (await agent_call(agent, "AGENT_GET_FLOW", {"id": big_id}, req_id="r12"))["flow"]
        check("oversized body is flagged incomplete", bd.get("req_body_complete") is False)
        check("oversized body carries the truncation marker", "truncated" in bd["req_body"][-60:])
        try:
            await agent_call(agent, "AGENT_REPLAY_REQUEST", {"flow_id": big_id}, req_id="r13")
            check("replaying a truncated body is refused", False, "no error")
        except RuntimeError as e:
            check("replaying a truncated body is refused", "truncated" in str(e), str(e)[:80])
        rep = await agent_call(agent, "AGENT_REPLAY_REQUEST", {
            "flow_id": big_id, "overrides": {"req_body": "replacement"}}, req_id="r14")
        check("supplying a body lifts the refusal", isinstance(rep.get("watermark"), int))

        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="r15")


async def test_rewrite_redirects_traffic(ws_port):
    """A map_remote rule really re-routes the request, not just shows up in state."""
    print("\n== rewrites redirect traffic ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "rewrite-traffic"}, req_id="x0")
        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "reroute",
            # Only the *landed* host is mocked; start.test reaching it proves the rewrite ran.
            "map_local": [{"active": True, "pattern": "*landed.test/api/target*",
                           "status": 299, "body": "landed"}],
            "map_remote": [{"active": True, "pattern": r"start\.test", "target": "landed.test"}],
        }, req_id="x1")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="x2"))["proxy_port"]
        code, body = await asyncio.to_thread(http_get, "http://start.test/api/target", proxy_port)
        check("request to the original host is served by the rewritten host's mock",
              code == 299 and body == "landed", f"{code} {body[:30]!r}")
        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="x3")
        code, _ = await asyncio.to_thread(http_get, "http://start.test/api/target", proxy_port)
        check("rewrite gone after clear", code != 299, f"got {code}")


async def test_throttle(ws_port):
    """Throttle names are validated, and a valid one actually slows traffic."""
    print("\n== throttle ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "throttle-test"}, req_id="t0")
        try:
            await agent_call(agent, "AGENT_RUN_SCENARIO", {"name": "typo", "throttle": "slow 3g"},
                             req_id="t1")
            check("unknown throttle profile is rejected", False, "no error")
        except RuntimeError as e:
            check("unknown throttle profile is rejected", "throttle" in str(e).lower(), str(e)[:80])
        check("a rejected scenario installs nothing",
              (await agent_call(agent, "AGENT_STATUS", req_id="t2"))["scenario"] is None)

        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "slow",
            "map_local": [{"active": True, "pattern": "*/api/slow*", "status": 200, "body": "s"}],
            "throttle": "Slow 3G",
        }, req_id="t3")
        st = await agent_call(agent, "AGENT_STATUS", req_id="t4")
        proxy_port = st["proxy_port"]
        check("status reports the effective throttle", st["throttle"] == "Slow 3G", st["throttle"])
        t0 = time.monotonic()
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/slow", proxy_port)
        elapsed = time.monotonic() - t0
        check("Slow 3G delays the request", code == 200 and elapsed >= 1.9, f"{code} in {elapsed:.2f}s")

        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="t5")
        st = await agent_call(agent, "AGENT_STATUS", req_id="t6")
        check("clearing hands throttle back to the user's setting", st["throttle"] == "None",
              st["throttle"])


async def test_rule_validation(ws_port):
    """Malformed rules fail at install time, not as a 500 at match time."""
    print("\n== rule validation ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "validation-test"}, req_id="v0")
        for label, payload, needle in [
            ("empty mock pattern", {"map_local": [{"pattern": ""}]}, "pattern"),
            ("non-numeric status", {"map_local": [{"pattern": "*/x*", "status": "abc"}]}, "status"),
            ("out-of-range status", {"map_local": [{"pattern": "*/x*", "status": 999}]}, "100-599"),
            ("empty rewrite pattern", {"map_remote": [{"pattern": "", "target": "a"}]}, "pattern"),
        ]:
            try:
                await agent_call(agent, "AGENT_RUN_SCENARIO", {"name": label, **payload}, req_id="v1")
                check(f"{label} is rejected", False, "no error")
            except RuntimeError as e:
                check(f"{label} is rejected", needle in str(e), str(e)[:80])
        check("nothing installed after rejections",
              (await agent_call(agent, "AGENT_STATUS", req_id="v2"))["scenario"] is None)


async def test_list_since_seq(ws_port):
    """since_seq on list returns exactly the traffic after the watermark."""
    print("\n== list since_seq ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "since-test"}, req_id="s0")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "since",
            "map_local": [{"active": True, "pattern": "*/api/since*", "status": 200, "body": "s"}],
        }, req_id="s1")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="s2"))["proxy_port"]
        await asyncio.to_thread(http_get, "http://mock.test/api/since/before", proxy_port)
        wm = (await agent_call(agent, "AGENT_STATUS", req_id="s3"))["flows"]["watermark"]
        await asyncio.to_thread(http_get, "http://mock.test/api/since/after1", proxy_port)
        await asyncio.to_thread(http_get, "http://mock.test/api/since/after2", proxy_port)
        await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
            "url_pattern": "/api/since/after", "since_seq": wm, "count": 2, "timeout": 10}, req_id="s4")
        listing = await agent_call(agent, "AGENT_LIST_FLOWS", {
            "url_pattern": "/api/since", "since_seq": wm}, req_id="s5")
        urls = [f["url"] for f in listing["flows"]]
        check("only flows after the watermark are listed",
              len(urls) == 2 and all("/after" in u for u in urls), str(urls))
        check("listing is oldest-first", urls == sorted(urls), str(urls))
        check("every listed seq is past the watermark",
              all(f["seq"] > wm for f in listing["flows"]))
        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="s6")


async def test_scenario_ownership(ws_port):
    """The agent that installed a scenario takes it with it; bystanders don't."""
    print("\n== scenario ownership ==")
    owner = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    bystander = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    await agent_call(owner, "AGENT_HELLO", {"client": "owner"}, req_id="w0")
    await agent_call(bystander, "AGENT_HELLO", {"client": "bystander"}, req_id="w1")
    await agent_call(owner, "AGENT_RUN_SCENARIO", {
        "name": "owned",
        "map_local": [{"active": True, "pattern": "*/api/owned*", "status": 200}],
    }, req_id="w2")
    await owner.close()
    await asyncio.sleep(1.0)
    st = await agent_call(bystander, "AGENT_STATUS", req_id="w3")
    check("owner leaving clears its scenario even with another agent attached",
          st["scenario"] is None, str(st["scenario"] and st["scenario"]["name"]))

    await agent_call(bystander, "AGENT_RUN_SCENARIO", {
        "name": "mine",
        "map_local": [{"active": True, "pattern": "*/api/mine*", "status": 200}],
    }, req_id="w4")
    passerby = await websockets.connect(f"ws://127.0.0.1:{ws_port}")
    await agent_call(passerby, "AGENT_HELLO", {"client": "passerby"}, req_id="w5")
    await passerby.close()
    await asyncio.sleep(1.0)
    st = await agent_call(bystander, "AGENT_STATUS", req_id="w6")
    check("an unrelated agent leaving does not clear someone else's scenario",
          st["scenario"] is not None and st["scenario"]["name"] == "mine")
    await agent_call(bystander, "AGENT_CLEAR_SCENARIO", req_id="w7")
    await bystander.close()


async def test_ui_stop_is_attributed_to_user(ws_port):
    """The activity feed must not credit the agent for the user's stop button."""
    print("\n== UI stop attribution ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "attrib-test"}, req_id="b0")
        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "attrib",
            "map_local": [{"active": True, "pattern": "*/api/a*", "status": 200}],
        }, req_id="b1")
        await _await_payload(ui, lambda m: m.get("type") == "AGENT_ACTIVITY")
        await ui.send(json.dumps({"type": "AGENT_CLEAR_SCENARIO", "req_id": "ui-stop"}))
        act = await _await_payload(ui, lambda m: m.get("type") == "AGENT_ACTIVITY"
                                   and m["data"].get("kind") == "scenario"
                                   and "Started" not in m["data"].get("message", ""))
        check("a UI-initiated stop is worded as the user's action",
              act is not None and act["data"]["message"].startswith("You "),
              str(act and act["data"].get("message")))


async def test_send_request_and_wait(ws_port):
    """send_request composes from scratch and, with wait, returns its own flow."""
    print("\n== send_request ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "send-test"}, req_id="n0")
        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "send",
            "map_local": [{"active": True, "pattern": "*/api/send*", "status": 202,
                           "body": "accepted", "headers": {"Content-Type": "text/plain"}}],
        }, req_id="n1")
        for bad, needle in [({"url": "not-a-url"}, "absolute"),
                            ({"url": "http://mock.test/x", "headers": "nope"}, "headers")]:
            try:
                await agent_call(agent, "AGENT_SEND_REQUEST", bad, req_id="n2")
                check(f"send rejects {bad}", False, "no error")
            except RuntimeError as e:
                check(f"send rejects {list(bad)[-1]} misuse", needle in str(e), str(e)[:60])

        r = await agent_call(agent, "AGENT_SEND_REQUEST", {
            "url": "http://mock.test/api/send", "method": "post",
            "headers": {"X-From": "agent", "Content-Type": "application/json"},
            "body": '{"a":1}', "wait": True, "timeout": 10,
        }, req_id="n3")
        check("send returns a replay_id", bool(r.get("replay_id")))
        check("send with wait returns the flow", r.get("flow") is not None and r.get("timed_out") is False,
              str({k: r.get(k) for k in ("timed_out", "hint")}))
        f = r.get("flow") or {}
        check("sent flow was mocked", f.get("status") == 202 and f.get("res_body") == "accepted",
              f"{f.get('status')} {f.get('res_body')!r}")
        check("method is upper-cased", f.get("method") == "POST", f.get("method"))
        check("body went through", f.get("req_body") == '{"a":1}', f.get("req_body"))
        check("flow records its replay_id", f.get("replay_id") == r["replay_id"])
        check("correlation header is stripped from the recorded request",
              "X-OpenProxy-Replay-Id" not in f.get("req_headers", {}), str(list(f.get("req_headers", {}))))
        check("custom header went through", f.get("req_headers", {}).get("X-From") == "agent")

        # The UI must be able to tell an agent-injected row from app traffic.
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
            await ui.recv(); await ui.recv(); await ui.recv()
            asyncio.ensure_future(agent_call(agent, "AGENT_SEND_REQUEST", {
                "url": "http://mock.test/api/send/ui", "wait": False}, req_id="n3b"))
            nr = await _await_payload(ui, lambda m: m.get("type") == "NEW_REQUEST"
                                      and "/api/send/ui" in m["data"].get("url", ""))
            check("UI's NEW_REQUEST marks agent-sent rows",
                  nr is not None and bool(nr["data"].get("agent_sent")),
                  str(nr and nr["data"].get("agent_sent")))
            check("agent-sent row does not leak the correlation header to the UI",
                  nr is not None and "X-OpenProxy-Replay-Id" not in nr["data"].get("req_headers", {}))

        # Without wait: fire-and-forget, then find it by replay_id via the list filter.
        r2 = await agent_call(agent, "AGENT_SEND_REQUEST", {
            "url": "http://mock.test/api/send/2", "wait": False}, req_id="n4")
        check("send without wait returns no flow", "flow" not in r2 and "watermark" in r2)
        got = await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
            "url_pattern": "/api/send/2", "since_seq": r2["watermark"], "count": 1, "timeout": 10},
            req_id="n5")
        check("fire-and-forget send lands in history",
              len(got["matched"]) == 1 and got["matched"][0]["replay_id"] == r2["replay_id"])

        # Two concurrent sends to the same URL must each get their own flow back.
        # (agent_call can't multiplex on one socket, so the second uses its own.)
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent2:
            await agent_call(agent2, "AGENT_HELLO", {"client": "send-test-2"}, req_id="n6h")
            a, b = await asyncio.gather(
                agent_call(agent, "AGENT_SEND_REQUEST", {"url": "http://mock.test/api/send/same",
                                                         "headers": {"X-Which": "a"}, "wait": True}, req_id="n6"),
                agent_call(agent2, "AGENT_SEND_REQUEST", {"url": "http://mock.test/api/send/same",
                                                          "headers": {"X-Which": "b"}, "wait": True}, req_id="n7"),
            )
        check("concurrent sends to one URL are correlated correctly",
              (a.get("flow") or {}).get("req_headers", {}).get("X-Which") == "a"
              and (b.get("flow") or {}).get("req_headers", {}).get("X-Which") == "b")

        # replay with wait returns the flow too
        rep = await agent_call(agent, "AGENT_REPLAY_REQUEST", {
            "flow_id": f["id"], "overrides": {"req_headers": {"X-From": "replay"}},
            "wait": True, "timeout": 10}, req_id="n8")
        check("replay with wait returns the replayed flow",
              (rep.get("flow") or {}).get("req_headers", {}).get("X-From") == "replay",
              str(rep.get("flow", {}).get("req_headers")))
        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="n9")


async def test_sequenced_and_delayed_mocks(ws_port):
    """`responses` serves a different answer per hit; `delay_ms` adds latency."""
    print("\n== sequenced + delayed mocks ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent, \
               websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        await ui.recv(); await ui.recv(); await ui.recv()
        await agent_call(agent, "AGENT_HELLO", {"client": "seq-test"}, req_id="q0")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "flaky",
            "map_local": [
                {"active": True, "pattern": "*/api/flaky*", "status": 200, "body": "base",
                 "responses": [{"status": 500, "body": "down"}, {"status": 503}, {"status": 200}]},
                {"active": True, "pattern": "*/api/cycle*", "status": 200,
                 "responses": [{"status": 201}, {"status": 202}], "sequence_mode": "cycle"},
                {"active": True, "pattern": "*/api/slow*", "status": 200, "body": "z", "delay_ms": 1200},
            ],
        }, req_id="q1")
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="q2"))["proxy_port"]
        mocks = r["scenario"]["mocks"]
        check("UI-facing rule carries the sequence", len(mocks[0].get("responses") or []) == 3)
        check("UI-facing rule carries the delay", mocks[2].get("delay_ms") == 1200)

        seen = []
        for _ in range(4):
            code, body = await asyncio.to_thread(http_get, "http://mock.test/api/flaky", proxy_port)
            seen.append((code, body))
        check("hold sequence: 500, 503, 200, then stays 200",
              [c for c, _ in seen] == [500, 503, 200, 200], str([c for c, _ in seen]))
        check("step body overrides the mock body", seen[0][1] == "down", seen[0][1])
        check("step without body falls back to the mock body", seen[1][1] == "base", seen[1][1])

        cyc = [(await asyncio.to_thread(http_get, "http://mock.test/api/cycle", proxy_port))[0]
               for _ in range(3)]
        check("cycle sequence wraps around", cyc == [201, 202, 201], str(cyc))

        t0 = time.monotonic()
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/slow", proxy_port)
        el = time.monotonic() - t0
        check("delay_ms holds the response", code == 200 and el >= 1.1, f"{code} in {el:.2f}s")

        # Re-installing restarts the sequence.
        await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "flaky again",
            "map_local": [{"active": True, "pattern": "*/api/flaky*", "status": 200,
                           "responses": [{"status": 500}, {"status": 200}]}],
        }, req_id="q3")
        code, _ = await asyncio.to_thread(http_get, "http://mock.test/api/flaky", proxy_port)
        check("a new scenario restarts the sequence", code == 500, f"got {code}")

        # A user override on `status` beats the sequence.
        key = (await agent_call(agent, "AGENT_STATUS", req_id="q4"))["scenario"]["mocks"][0]["key"]
        await ui.send(json.dumps({"type": "SET_AGENT_RULE_OVERRIDE", "key": key,
                                  "fields": {"status": 418}}))
        await asyncio.sleep(0.8)
        codes = [(await asyncio.to_thread(http_get, "http://mock.test/api/flaky", proxy_port))[0]
                 for _ in range(2)]
        check("user's status override wins over the sequence", codes == [418, 418], str(codes))
        await ui.send(json.dumps({"type": "CLEAR_AGENT_RULE_OVERRIDE", "key": key}))
        await asyncio.sleep(0.5)

        for label, rule, needle in [
            ("bad delay", {"pattern": "*/x*", "delay_ms": 999999}, "delay_ms"),
            ("empty responses", {"pattern": "*/x*", "responses": []}, "responses"),
            ("bad step status", {"pattern": "*/x*", "responses": [{"status": 42}]}, "100-599"),
            ("bad mode", {"pattern": "*/x*", "responses": [{"status": 200}], "sequence_mode": "loop"},
             "sequence_mode"),
        ]:
            try:
                await agent_call(agent, "AGENT_RUN_SCENARIO", {"name": label, "map_local": [rule]},
                                 req_id="q5")
                check(f"{label} is rejected", False, "no error")
            except RuntimeError as e:
                check(f"{label} is rejected", needle in str(e), str(e)[:70])
        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="q6")


async def test_search_summary_batch(ws_port):
    """search / summarize / get_many read back a window of traffic."""
    print("\n== search, summarize, batch get ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        await agent_call(agent, "AGENT_HELLO", {"client": "search-test"}, req_id="g0")
        r = await agent_call(agent, "AGENT_RUN_SCENARIO", {
            "name": "search",
            "map_local": [
                {"active": True, "pattern": "*one.test/api/*", "status": 200,
                 "body": '{"token":"SECRET-abc123"}', "headers": {"Content-Type": "application/json"}},
                {"active": True, "pattern": "*two.test/*", "status": 404, "body": "nope"},
            ],
        }, req_id="g1")
        wm = r["watermark"]
        proxy_port = (await agent_call(agent, "AGENT_STATUS", req_id="g2"))["proxy_port"]
        await asyncio.to_thread(http_request, "GET", "http://one.test/api/login", proxy_port,
                                headers={"Authorization": "Bearer SECRET-abc123"})
        await asyncio.to_thread(http_get, "http://one.test/api/profile", proxy_port)
        await asyncio.to_thread(http_get, "http://two.test/track?u=secret-ABC123", proxy_port)
        await asyncio.to_thread(http_get, "http://two.test/other", proxy_port)
        await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {"since_seq": wm, "count": 4, "timeout": 10},
                         req_id="g3")

        sr = await agent_call(agent, "AGENT_SEARCH_FLOWS", {"text": "secret-abc123", "since_seq": wm},
                              req_id="g4")
        matches = sr["matches"]
        check("search is case-insensitive and finds every carrier", len(matches) == 3, str(len(matches)))
        where = {m["url"].split("//")[1].split("?")[0]: sorted(h["in"] for h in m["hits"]) for m in matches}
        check("search reports where the text was found",
              where.get("one.test/api/login") == ["req_headers.Authorization", "res_body"]
              and where.get("two.test/track") == ["url"], str(where))
        check("hits carry a snippet", all(h["snippet"] for m in matches for h in m["hits"]))
        check("search honours url_pattern",
              len((await agent_call(agent, "AGENT_SEARCH_FLOWS",
                                    {"text": "secret", "since_seq": wm, "url_pattern": "two.test"},
                                    req_id="g5"))["matches"]) == 1)
        try:
            await agent_call(agent, "AGENT_SEARCH_FLOWS", {"text": ""}, req_id="g6")
            check("empty search text is rejected", False, "no error")
        except RuntimeError as e:
            check("empty search text is rejected", "text" in str(e))

        sm = await agent_call(agent, "AGENT_SUMMARIZE_FLOWS", {"since_seq": wm}, req_id="g7")
        check("summary counts the window", sm["total"] == 4 and sm["completed"] == 4, str(sm["total"]))
        check("summary groups by host",
              sm["by_host"].get("one.test", {}).get("count") == 2
              and sm["by_host"].get("two.test", {}).get("statuses") == {"404": 2}, str(sm["by_host"]))
        check("summary tallies statuses", sm["by_status"] == {"200": 2, "404": 2}, str(sm["by_status"]))
        check("summary counts mocked flows", sm["mocked"] == 4, str(sm["mocked"]))
        check("summary lists top endpoints", any("two.test/track" in e["endpoint"]
                                                 for e in sm["top_endpoints"]))
        check("summary reports latency", sm["duration_ms"]["p50"] is not None)

        ids = [m["id"] for m in matches]
        gm = await agent_call(agent, "AGENT_GET_FLOWS", {"ids": ids + ["ghost"]}, req_id="g8")
        check("batch get returns every known flow in full",
              len(gm["flows"]) == 3 and all("res_body" in f for f in gm["flows"]))
        check("batch get reports unknown ids", gm["missing"] == ["ghost"], str(gm["missing"]))
        try:
            await agent_call(agent, "AGENT_GET_FLOWS", {"ids": []}, req_id="g9")
            check("batch get rejects an empty list", False, "no error")
        except RuntimeError as e:
            check("batch get rejects an empty list", "ids" in str(e))
        await agent_call(agent, "AGENT_CLEAR_SCENARIO", req_id="g10")


async def test_websocket_messages(ws_port):
    """Frames over a proxied WebSocket are readable per flow."""
    print("\n== websocket messages ==")
    # A tiny echo server the proxy can reach.
    async def echo(ws):
        async for m in ws:
            await ws.send(f"echo:{m}")
    echo_server = await websockets.serve(echo, "127.0.0.1", 0)
    echo_port = echo_server.sockets[0].getsockname()[1]
    try:
        async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
            await agent_call(agent, "AGENT_HELLO", {"client": "ws-test"}, req_id="k0")
            st = await agent_call(agent, "AGENT_STATUS", req_id="k1")
            proxy_port, wm = st["proxy_port"], st["flows"]["watermark"]

            try:
                from websockets.asyncio.client import connect as ws_connect
            except ImportError:
                check("websockets client supports proxies (skipped)", True); return

            # websockets >= 14 takes the proxy as a URL string.
            async with ws_connect(f"ws://127.0.0.1:{echo_port}/socket",
                                  proxy=f"http://127.0.0.1:{proxy_port}") as c:
                await c.send("hello"); await c.recv()
                await c.send("world"); await c.recv()

            got = await agent_call(agent, "AGENT_WAIT_FOR_FLOWS", {
                "url_pattern": "/socket", "since_seq": wm, "count": 1, "timeout": 10}, req_id="k2")
            check("the upgrade request is in history", len(got["matched"]) == 1)
            if not got["matched"]:
                return
            fid = got["matched"][0]["id"]
            await asyncio.sleep(0.5)
            listing = await agent_call(agent, "AGENT_LIST_FLOWS", {"url_pattern": "/socket",
                                                                    "since_seq": wm}, req_id="k3")
            check("summary carries the frame count", listing["flows"][0]["ws_messages"] == 4,
                  str(listing["flows"][0]["ws_messages"]))
            msgs = await agent_call(agent, "AGENT_GET_WS_MESSAGES", {"id": fid}, req_id="k4")
            seq = [(m["from_client"], m["content"]) for m in msgs["messages"]]
            check("frames come back in order with direction",
                  seq == [(True, "hello"), (False, "echo:hello"), (True, "world"), (False, "echo:world")],
                  str(seq))
            page = await agent_call(agent, "AGENT_GET_WS_MESSAGES", {"id": fid, "offset": 2, "limit": 1},
                                    req_id="k5")
            check("frame paging works", [m["content"] for m in page["messages"]] == ["world"]
                  and page["next_offset"] == 3, str(page))
            detail = (await agent_call(agent, "AGENT_GET_FLOW", {"id": fid}, req_id="k6"))["flow"]
            check("get_flow reports a count, not the frame log", detail["ws_messages"] == 4)
            sr = await agent_call(agent, "AGENT_SEARCH_FLOWS", {"text": "echo:world", "since_seq": wm},
                                  req_id="k7")
            check("search covers websocket frames",
                  len(sr["matches"]) == 1 and sr["matches"][0]["hits"][0]["in"].startswith("ws_messages["),
                  str(sr["matches"] and sr["matches"][0]["hits"]))
    finally:
        echo_server.close()
        await echo_server.wait_closed()


async def test_bundled_mcp_entry(ws_port, home):
    """`main.py --mcp` is a working MCP server, and the backend wrote a launcher for it.

    This is the "install once" contract: the app refreshes ~/.openproxy/bin/
    openproxy-mcp on every start, SYSTEM_INFO reports where it is, and running
    that file speaks MCP over stdio against this backend.
    """
    print("\n== bundled MCP entry point + launcher ==")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as ui:
        info = json.loads(await asyncio.wait_for(ui.recv(), timeout=10))
    shim = info["data"].get("mcp_command")
    check("SYSTEM_INFO reports the launcher path", bool(shim), str(shim))
    expected_dir = os.path.join(home, ".openproxy", "bin")
    check("launcher lives under the app's data dir",
          bool(shim) and os.path.dirname(shim) == expected_dir, f"{shim} vs {expected_dir}")
    check("launcher exists and is executable",
          bool(shim) and os.path.isfile(shim) and os.access(shim, os.X_OK))
    if shim:
        text = open(shim).read()
        check("launcher runs main.py --mcp with the venv interpreter",
              "main.py" in text and "--mcp" in text and sys.executable in text, text[-120:])

    async def probe(cmd, args, label):
        params = StdioServerParameters(command=cmd, args=args,
                                       env={**os.environ, "OPENPROXY_WS_PORT": str(ws_port)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                tools = await session.list_tools()
                names = sorted(t.name for t in tools.tools)
                check(f"{label}: serves the tool list", "get_proxy_status" in names and len(names) >= 13,
                      str(len(names)))
                res = await session.call_tool("get_proxy_status", {})
                data = json.loads(res.content[0].text) if res.content else {}
                check(f"{label}: get_proxy_status reaches this backend",
                      data.get("proxy_port") is not None and data.get("protocol") == 1, str(data)[:120])
                check(f"{label}: status carries the launcher path", data.get("mcp_command") == shim)

    await probe(sys.executable, [str(REPO_ROOT / "main.py"), "--mcp"], "main.py --mcp")
    if shim and sys.platform != "win32":
        await probe(shim, [], "launcher")


async def test_protocol_skew_is_reported(ws_port):
    """An MCP process from another build gets told, in-band, to restart."""
    print("\n== protocol skew ==")
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        r = await agent_call(agent, "AGENT_HELLO", {"client": "old-build", "protocol": 0}, req_id="pv1")
        check("mismatched protocol gets a warning", "restart" in (r.get("warning") or "").lower(),
              str(r.get("warning"))[:80])
    async with websockets.connect(f"ws://127.0.0.1:{ws_port}") as agent:
        r = await agent_call(agent, "AGENT_HELLO", {"client": "same-build", "protocol": 1}, req_id="pv2")
        check("matching protocol gets no warning", "warning" not in r)
        check("status reports the protocol version", r.get("protocol") == 1)


async def main():
    ws_port = free_port()
    # Isolated HOME so the backend's ~/.openproxy (scripts, MCP launcher) is
    # this run's own, not the developer's.
    import tempfile
    home = tempfile.mkdtemp(prefix="openproxy-test-home-")
    env = {**os.environ, "OPENPROXY_WS_PORT": str(ws_port), "PYTHONUNBUFFERED": "1",
           "HOME": home, "USERPROFILE": home}
    print(f"Starting backend (ws={ws_port})...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not wait_for_port(ws_port):
            print("Backend failed to start within "
                  f"{BACKEND_BOOT_TIMEOUT}s; output:\n{proc.stdout.read()[:2000]}")
            return 1

        await test_agent_surface(ws_port)
        await test_ui_not_regressed(ws_port)
        await test_ui_sees_agent_activity(ws_port)
        await test_disconnect_clears_scenario(ws_port)
        await test_user_overrides_survive_rerun(ws_port)
        await test_full_editor_fields_are_overridable(ws_port)
        await test_rewrites_are_overridable(ws_port)
        await test_disconnect_preserves_rules_for_adoption(ws_port)
        await test_activity_feed(ws_port)
        await test_replay_by_flow_id(ws_port)
        await test_rewrite_redirects_traffic(ws_port)
        await test_throttle(ws_port)
        await test_rule_validation(ws_port)
        await test_list_since_seq(ws_port)
        await test_scenario_ownership(ws_port)
        await test_ui_stop_is_attributed_to_user(ws_port)
        await test_send_request_and_wait(ws_port)
        await test_sequenced_and_delayed_mocks(ws_port)
        await test_search_summary_batch(ws_port)
        await test_websocket_messages(ws_port)
        await test_bundled_mcp_entry(ws_port, home)
        await test_protocol_skew_is_reported(ws_port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n" + "=" * 52)
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
