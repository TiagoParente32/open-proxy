"""MCP server exposing OpenProxy's traffic history and mocking to agents.

The workflow these tools are shaped around is a three-step loop:

    1. run_mock_scenario(...)      -> returns a `watermark`
    2. trigger the app             (adb, a browser, curl, or ask the human)
    3. wait_for_requests(since=watermark)  -> what the app did about it

Step 3 is the assertion. The most useful signal is usually not a screenshot but
the traffic that *follows* the mock: whether the app retried, refreshed its
token, fell back to a cache, or leaked a credential on the retry.
"""

import json
import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer

from openproxy_mcp import __version__
from openproxy_mcp.client import (
    OpenProxyClient,
    OpenProxyError,
    OpenProxyUnavailable,
)

mcp = MCPServer(
    "openproxy",
    version=__version__,
    instructions=(
        "Inspect and manipulate HTTP(S) traffic captured by the OpenProxy "
        "desktop app. Use this when you need to see what a client actually "
        "sent or received — especially a mobile or native app whose traffic "
        "you cannot otherwise observe — or to mock an endpoint and check how "
        "that client reacts. Requires the OpenProxy app to be running."
    ),
)
_client = OpenProxyClient()


def _describe_error(e: Exception) -> dict:
    if isinstance(e, OpenProxyUnavailable):
        return {"error": str(e), "hint": "Is the OpenProxy desktop app running?"}
    if isinstance(e, OpenProxyError):
        return {"error": str(e)}
    return {"error": f"{type(e).__name__}: {e}"}


async def _call(msg_type: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        return await _client.call(msg_type, payload, timeout=timeout)
    except Exception as e:  # surfaced to the model as data, not an exception
        return _describe_error(e)


@mcp.tool()
async def get_proxy_status() -> dict:
    """Check that OpenProxy is running and see what it is currently doing.

    Call this first in a session, and any time a tool returns a connection
    error. Reports the proxy port, whether recording is on, how many flows are
    in history, and which mock scenario (if any) is active.
    """
    return await _call("AGENT_STATUS")


@mcp.tool()
async def list_requests(
    url_pattern: str | None = None,
    method: str | None = None,
    status: int | None = None,
    since_seq: int | None = None,
    only_completed: bool = False,
    limit: int = 50,
) -> dict:
    """List captured requests, newest last. Returns compact summaries, no bodies.

    Use this to see what traffic the proxy has observed. Fetch a single flow's
    headers and bodies with get_request once you know which one you want.

    url_pattern matches the full URL: a bare substring ("/api/login") matches
    anywhere, while a pattern containing `*` is anchored and globbed
    ("https://api.example.com/v1/*"). Matching is case-insensitive.

    since_seq limits results to flows recorded after that sequence number — pass
    the `watermark` from run_mock_scenario to see only traffic that followed it.
    """
    return await _call("AGENT_LIST_FLOWS", {
        "url_pattern": url_pattern,
        "method": method,
        "status": status,
        "since_seq": since_seq,
        "only_completed": only_completed,
        "limit": max(1, min(limit, 200)),
    })


@mcp.tool()
async def get_request(flow_id: str) -> dict:
    """Fetch one captured flow in full: request/response headers and bodies.

    Takes the `id` from a list_requests or wait_for_requests result. Bodies are
    truncated at 32KB and binary/image payloads are omitted — if you need those
    bytes, inspect them in the OpenProxy UI instead.
    """
    return await _call("AGENT_GET_FLOW", {"id": flow_id})


@mcp.tool()
async def run_mock_scenario(
    name: str,
    mocks: list[dict[str, Any]] | None = None,
    rewrites: list[dict[str, Any]] | None = None,
    throttle: str | None = None,
) -> dict:
    """Install a named set of mocks, replacing any scenario already active.

    Returns a `watermark` — pass it to wait_for_requests or list_requests so you
    only see traffic that happened after the mocks went in.

    These rules are kept separate from mocks the user set up by hand in the UI
    and are matched ahead of them, so running a scenario never destroys their
    setup. Scenarios replace each other wholesale, so rules never leak from one
    scenario into the next. Call clear_mocks when you are done.

    Each entry in `mocks` accepts:
      url_pattern  required. ANCHORED glob against the full URL, so you almost
                   always want leading and trailing `*`, e.g.
                   "*/api/v1/profile*". A pattern without `*` must match the
                   entire URL exactly.
      status       HTTP status to return (default 200)
      body         response body as a string (use "" for an empty body)
      headers      dict of response headers, e.g. {"Content-Type": "application/json"}
      method       limit to one verb ("GET", "POST", ...); defaults to any

    Each entry in `rewrites` (map-remote) accepts `pattern` (a regex) and
    `target` (its replacement) to redirect traffic to another host.

    `throttle` pins the network profile for the scenario's duration: "Slow 3G",
    "Fast 3G", or "None". Omit it to leave the user's setting alone.
    """
    rules = []
    for m in mocks or []:
        pattern = m.get("url_pattern") or m.get("pattern")
        if not pattern:
            return {"error": f"Mock entry missing url_pattern: {json.dumps(m)[:200]}"}
        headers = m.get("headers")
        rules.append({
            "active": True,
            "pattern": pattern,
            "method": (m.get("method") or "ANY").upper(),
            "status": m.get("status", 200),
            "headers": headers if headers is not None else {},
            "body": m.get("body", ""),
            "body_source": "inline",
        })

    remote = [
        {"active": True, "pattern": r.get("pattern", ""), "target": r.get("target", "")}
        for r in (rewrites or [])
    ]

    return await _call("AGENT_RUN_SCENARIO", {
        "name": name,
        "map_local": rules,
        "map_remote": remote,
        "throttle": throttle,
    })


@mcp.tool()
async def clear_mocks() -> dict:
    """Remove the active mock scenario and hand control back to the user's rules.

    Always call this when finished with a scenario. It runs automatically if
    this MCP server disconnects, so a crash won't strand the user with mocked
    traffic, but don't rely on that during a session.
    """
    return await _call("AGENT_CLEAR_SCENARIO")


@mcp.tool()
async def wait_for_requests(
    url_pattern: str | None = None,
    method: str | None = None,
    status: int | None = None,
    since_seq: int | None = None,
    count: int = 1,
    timeout: float = 30.0,
) -> dict:
    """Block until `count` matching requests complete, then return them.

    This is the assertion half of a mock scenario: install mocks, trigger the
    app, then wait here to see what it actually sent. Pass the `watermark` from
    run_mock_scenario as since_seq so earlier traffic can't satisfy the wait.

    Never raises on timeout — it returns whatever matched plus
    `timed_out: true`. A partial result is itself a finding: "the app retried
    once, not the three times expected" is the answer, not a failure.

    timeout is capped at 300 seconds. Use a generous value when a human has to
    tap through something, a short one when you are driving the client yourself.
    """
    # Give the backend a little longer than the wait itself so the call doesn't
    # time out client-side just as the server is about to answer.
    capped = max(1.0, min(timeout, 300.0))
    return await _call("AGENT_WAIT_FOR_FLOWS", {
        "url_pattern": url_pattern,
        "method": method,
        "status": status,
        "since_seq": since_seq,
        "count": max(1, count),
        "timeout": capped,
    }, timeout=capped + 10.0)


@mcp.tool()
async def replay_request(
    flow_id: str,
    method: str | None = None,
    url: str | None = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    """Re-send a captured request through the proxy, optionally modified.

    Useful for probing an endpoint with variations of a real request without
    touching the app. Any argument you pass overrides that part of the original.

    The replay is proxied like any other traffic, so the result shows up in
    history rather than being returned here: this returns a `watermark`, and you
    read the outcome with wait_for_requests(since_seq=watermark).
    """
    original = await _call("AGENT_GET_FLOW", {"id": flow_id})
    if "error" in original:
        return original

    flow = original.get("flow", {})
    request = {
        "url": url or flow.get("url"),
        "method": (method or flow.get("method") or "GET").upper(),
        "req_headers": headers if headers is not None else flow.get("req_headers", {}),
        "req_body": body if body is not None else flow.get("req_body", ""),
    }
    return await _call("AGENT_REPLAY_REQUEST", {"request": request})


@mcp.tool()
async def clear_history() -> dict:
    """Drop captured flow history.

    Worth doing between scenarios so list_requests stays readable. Sequence
    numbers keep counting, so a watermark taken before a clear never starts
    matching unrelated traffic afterwards.
    """
    return await _call("AGENT_CLEAR_FLOWS")


def main():
    """Entry point for the `openproxy-mcp` console script (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
