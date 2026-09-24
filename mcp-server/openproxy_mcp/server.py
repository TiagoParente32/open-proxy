"""MCP server exposing OpenProxy's traffic history and mocking to agents.

The workflow these tools are shaped around is a three-step loop:

    1. run_mock_scenario(...)      -> returns a `watermark`
    2. trigger the app             (adb, a browser, curl, or ask the human)
    3. wait_for_requests(since=watermark)  -> what the app did about it

Step 3 is the assertion. The most useful signal is usually not a screenshot but
the traffic that *follows* the mock: whether the app retried, refreshed its
token, fell back to a cache, or leaked a credential on the retry.
"""

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from typing_extensions import NotRequired, TypedDict

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

# Tool annotations let MCP clients decide how much ceremony a call needs: a
# read-only tool can run without a permission prompt, a destructive one
# shouldn't. They are hints, not enforcement.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
MUTATES_PROXY = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True,
                              idempotent_hint=True, open_world_hint=False)
# Replay sends real traffic to whatever host the URL names.
SENDS_TRAFFIC = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                idempotent_hint=False, open_world_hint=True)

ThrottleProfile = Literal["None", "Fast 3G", "Slow 3G"]


class MockResponse(TypedDict, total=False):
    """One step of a mock's `responses` sequence. Fields left out fall back to
    the mock's own status/body/headers."""

    status: Annotated[int, Field(description="HTTP status for this step.", ge=100, le=599)]
    body: Annotated[str, Field(description="Body for this step.")]
    headers: Annotated[dict[str, str], Field(description="Headers merged over the mock's.")]


class MockRule(TypedDict):
    """A canned response served instead of contacting the real server."""

    url_pattern: Annotated[str, Field(description=(
        "ANCHORED glob matched against the full URL, so you almost always want "
        "leading and trailing `*`, e.g. \"*/api/v1/profile*\". A pattern without "
        "`*` must equal the entire URL."
    ))]
    status: NotRequired[Annotated[int, Field(
        description="HTTP status to return.", ge=100, le=599)]]
    body: NotRequired[Annotated[str, Field(
        description='Response body as a string; "" for an empty body.')]]
    headers: NotRequired[Annotated[dict[str, str], Field(
        description='Response headers, e.g. {"Content-Type": "application/json"}.')]]
    method: NotRequired[Annotated[str, Field(
        description='Limit to one verb ("GET", "POST", ...). Default: any method.')]]
    delay_ms: NotRequired[Annotated[int, Field(
        description="Hold the response this long before serving it, to test the "
                    "app's timeout handling. Max 60000.", ge=0, le=60000)]]
    responses: NotRequired[Annotated[list[MockResponse], Field(
        description="Serve a different response on each hit: the Nth request gets "
                    "the Nth entry. Test 'fail twice then recover' with "
                    "[{status: 500}, {status: 500}, {status: 200}]. Fields a step "
                    "omits come from the mock itself.")]]
    sequence_mode: NotRequired[Annotated[Literal["hold", "cycle"], Field(
        description="What happens after the last `responses` entry: 'hold' keeps "
                    "serving it (default), 'cycle' starts over.")]]


class RewriteRule(TypedDict):
    """A map-remote redirect: traffic matching `pattern` is sent to `target`."""

    pattern: Annotated[str, Field(description="Regex matched against the full URL.")]
    target: Annotated[str, Field(
        description='Replacement for the matched part, e.g. "staging.example.com".')]


def _describe_error(e: Exception) -> dict:
    if isinstance(e, OpenProxyUnavailable):
        return {"error": str(e), "hint": "Is the OpenProxy desktop app running?"}
    if isinstance(e, OpenProxyError):
        return {"error": str(e)}
    return {"error": f"{type(e).__name__}: {e}"}


async def _call(msg_type: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    try:
        result = await _client.call(msg_type, payload, timeout=timeout)
    except Exception as e:  # surfaced to the model as data, not an exception
        return _describe_error(e)
    if _client.protocol_warning and isinstance(result, dict):
        result.setdefault("warning", _client.protocol_warning)
    return result


@mcp.tool(annotations=READ_ONLY)
async def get_proxy_status() -> dict:
    """Check that OpenProxy is running and see what it is currently doing.

    Call this first in a session, and any time a tool returns a connection
    error. Reports the proxy port, whether recording is on, how many flows are
    in history, and which mock scenario (if any) is active.
    """
    return await _call("AGENT_STATUS")


@mcp.tool(annotations=READ_ONLY)
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


@mcp.tool(annotations=READ_ONLY)
async def get_request(flow_id: str) -> dict:
    """Fetch one captured flow in full: request/response headers and bodies.

    Takes the `id` from a list_requests or wait_for_requests result. Bodies are
    truncated at 32KB and binary/image payloads are omitted; `req_body_complete`
    and `res_body_complete` are false when that happened. If you need those
    bytes, inspect them in the OpenProxy UI instead.
    """
    return await _call("AGENT_GET_FLOW", {"id": flow_id})


@mcp.tool(annotations=READ_ONLY)
async def get_requests(flow_ids: list[str]) -> dict:
    """Fetch several captured flows in full at once (max 20 per call).

    Same content as get_request, for when you've identified a handful of flows
    from list_requests or search_requests and want all of them. Ids that are no
    longer in history come back under `missing` rather than failing the call.
    """
    if not flow_ids:
        return {"error": "flow_ids must not be empty"}
    if len(flow_ids) > 20:
        return {"error": "At most 20 flow_ids per call — page through them"}
    return await _call("AGENT_GET_FLOWS", {"ids": flow_ids})


@mcp.tool(annotations=READ_ONLY)
async def search_requests(
    text: str,
    since_seq: int | None = None,
    url_pattern: str | None = None,
    limit: int = 50,
) -> dict:
    """Find captured requests containing `text` anywhere: URL, request or response
    headers, bodies, or WebSocket frames. Case-insensitive substring match.

    This is the tool for "did the app send this token / user id / email to any
    host?" — one call instead of fetching every flow. Each match is a request
    summary plus `hits`: where the text was found and a snippet around it.
    Follow up with get_request on the ones that matter.

    Only text stored in history is searched: bodies are capped at 32KB and
    binary payloads are not indexed.
    """
    return await _call("AGENT_SEARCH_FLOWS", {
        "text": text,
        "since_seq": since_seq,
        "url_pattern": url_pattern,
        "limit": max(1, min(limit, 200)),
    })


@mcp.tool(annotations=READ_ONLY)
async def summarize_traffic(
    since_seq: int | None = None,
    url_pattern: str | None = None,
    top: int = 15,
) -> dict:
    """Aggregate a window of traffic: counts by host, status and method, the
    most-hit endpoints, error/mocked/pending totals, and latency p50/max.

    Use this right after a scenario (pass its `watermark` as since_seq) to see
    the shape of what the app did — which hosts it contacted, how many calls
    failed, whether anything went to a third party — before drilling into
    individual flows with list_requests or search_requests.
    """
    return await _call("AGENT_SUMMARIZE_FLOWS", {
        "since_seq": since_seq,
        "url_pattern": url_pattern,
        "top": max(1, min(top, 100)),
    })


@mcp.tool(annotations=READ_ONLY)
async def get_websocket_messages(flow_id: str, offset: int = 0, limit: int = 100) -> dict:
    """Read the frames exchanged over a captured WebSocket connection.

    `flow_id` is the id of the HTTP upgrade request (it shows up in
    list_requests with a `ws_messages` count). Frames are returned oldest first
    with `from_client` telling direction; page with `next_offset`. The last 200
    frames per connection are kept, each capped at 8KB.
    """
    return await _call("AGENT_GET_WS_MESSAGES", {
        "id": flow_id, "offset": max(0, offset), "limit": max(1, min(limit, 200)),
    })


@mcp.tool(annotations=MUTATES_PROXY)
async def run_mock_scenario(
    name: str,
    mocks: list[MockRule] | None = None,
    rewrites: list[RewriteRule] | None = None,
    throttle: ThrottleProfile | None = None,
) -> dict:
    """Install a named set of mocks, replacing any scenario already active.

    Returns a `watermark` — pass it to wait_for_requests or list_requests so you
    only see traffic that happened after the mocks went in.

    These rules are kept separate from mocks the user set up by hand in the UI
    and are matched ahead of them, so running a scenario never destroys their
    setup. Scenarios replace each other wholesale, so rules never leak from one
    scenario into the next. Call clear_mocks when you are done.

    `mocks` serve canned responses; `rewrites` redirect traffic to another host.
    A mock can also add latency (`delay_ms`) or serve a sequence of different
    responses across successive hits (`responses`) — that's how you test retry
    and recovery behaviour without writing a script.

    `throttle` pins the network profile for the scenario's duration ("Slow 3G",
    "Fast 3G", or "None" to force it off). Omit it to leave the user's setting
    alone.
    """
    rules = []
    for i, m in enumerate(mocks or []):
        pattern = m.get("url_pattern")
        if not pattern:
            return {"error": f"mocks[{i}] is missing url_pattern"}
        rule = {
            "active": True,
            "pattern": pattern,
            "method": (m.get("method") or "ANY").upper(),
            "status": m.get("status", 200),
            "headers": m.get("headers") or {},
            "body": m.get("body", ""),
            "body_source": "inline",
        }
        for extra in ("delay_ms", "responses", "sequence_mode"):
            if m.get(extra) is not None:
                rule[extra] = m[extra]
        rules.append(rule)

    remote = []
    for i, r in enumerate(rewrites or []):
        if not r.get("pattern") or not r.get("target"):
            return {"error": f"rewrites[{i}] needs both pattern and target"}
        remote.append({"active": True, "pattern": r["pattern"], "target": r["target"]})

    return await _call("AGENT_RUN_SCENARIO", {
        "name": name,
        "map_local": rules,
        "map_remote": remote,
        "throttle": throttle,
    })


@mcp.tool(annotations=MUTATES_PROXY)
async def clear_mocks() -> dict:
    """Remove the active mock scenario and hand control back to the user's rules.

    Always call this when finished with a scenario. It runs automatically if
    this MCP server disconnects, so a crash won't strand the user with mocked
    traffic, but don't rely on that during a session.
    """
    return await _call("AGENT_CLEAR_SCENARIO")


@mcp.tool(annotations=READ_ONLY)
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


@mcp.tool(annotations=SENDS_TRAFFIC)
async def replay_request(
    flow_id: str,
    method: str | None = None,
    url: str | None = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
    wait: bool = True,
    timeout: float = 30.0,
) -> dict:
    """Re-send a captured request through the proxy, optionally modified.

    Useful for probing an endpoint with variations of a real request without
    touching the app. Any argument you pass overrides that part of the original.

    Refuses to replay a request whose body was truncated or omitted in history
    (bodies over 32KB, binary uploads) unless you pass `body` yourself — the
    stored copy is not what went over the wire.

    The replay goes through the proxy like any other traffic, so active mocks
    apply to it and it lands in history. With `wait` (default) the resulting
    flow is returned inline as `flow`, headers and bodies included, or
    `timed_out: true` if nothing came back in `timeout` seconds. With
    wait=false you get a `watermark` and `replay_id` to look it up later.
    """
    overrides: dict[str, Any] = {}
    if method is not None:
        overrides["method"] = method
    if url is not None:
        overrides["url"] = url
    if body is not None:
        overrides["req_body"] = body
    if headers is not None:
        overrides["req_headers"] = headers
    capped = max(1.0, min(timeout, 300.0))
    return await _call("AGENT_REPLAY_REQUEST", {
        "flow_id": flow_id, "overrides": overrides, "wait": wait, "timeout": capped,
    }, timeout=capped + 10.0)


@mcp.tool(annotations=SENDS_TRAFFIC)
async def send_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    wait: bool = True,
    timeout: float = 30.0,
) -> dict:
    """Send a request of your own through the proxy, composed from scratch.

    Use this to probe an endpoint the app hasn't hit yet, or to check what a
    mock returns before pointing the app at it. Unlike a plain curl, the
    request passes through OpenProxy, so active mocks and rewrites apply, it
    is recorded in history, and the user can see it in the traffic table.

    `url` must be absolute (http:// or https://). TLS verification is off, as
    for all proxied traffic. With `wait` (default) the completed flow is
    returned as `flow`; otherwise you get a `watermark` and `replay_id`.
    """
    capped = max(1.0, min(timeout, 300.0))
    return await _call("AGENT_SEND_REQUEST", {
        "url": url, "method": method, "headers": headers or {}, "body": body,
        "wait": wait, "timeout": capped,
    }, timeout=capped + 10.0)


@mcp.tool(annotations=DESTRUCTIVE)
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
