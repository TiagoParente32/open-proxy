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


async def main():
    ws_port = free_port()
    env = {**os.environ, "OPENPROXY_WS_PORT": str(ws_port), "PYTHONUNBUFFERED": "1"}
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
        await test_disconnect_clears_scenario(ws_port)
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
