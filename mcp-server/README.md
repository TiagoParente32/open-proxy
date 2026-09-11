# openproxy-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI agents — Claude Code, Claude Desktop, Cursor, Zed, and anything else that speaks MCP — read access to traffic captured by [OpenProxy](https://github.com/TiagoParente32/open-proxy), plus the ability to mock endpoints and observe how a client reacts.

The point isn't to automate the OpenProxy UI. It's to close a blind spot: an agent can already `curl` an endpoint it controls, but it has no way to see what a **mobile app, native app, or third-party SDK** actually sent. This bridges that.

## What it's for

The workflow the tools are shaped around:

1. **`run_mock_scenario(...)`** — install mocks, get back a `watermark`
2. **Trigger the client** — `adb shell input tap`, a browser, a test suite, or just ask the human to tap through
3. **`wait_for_requests(since_seq=watermark)`** — see what the app did about it

Step 3 is where the value is. The strongest assertion signal usually isn't a screenshot, it's *the traffic that follows the mock*:

- Returned a 401 — did the app refresh its token, or keep sending the stale one?
- Returned an empty list — did it retry in a tight loop?
- Returned a 500 — did it leak the auth header to a third-party host on the retry?

All of that is visible as subsequent requests, with no UI inspection at all.

## Install

Requires Python 3.10+ and the OpenProxy desktop app running.

```bash
pip install -e ./mcp-server     # from a checkout
```

### Claude Code

```bash
claude mcp add openproxy -- openproxy-mcp
```

Add `--scope project` to write `.mcp.json` at the repo root so the whole team picks it up.

### Claude Desktop / Cursor / Zed

Add to the client's MCP config (`claude_desktop_config.json` for Claude Desktop):

```json
{
  "mcpServers": {
    "openproxy": {
      "command": "openproxy-mcp"
    }
  }
}
```

The server talks **stdio**, so there's no port to configure and nothing listening.

## Tools

| Tool | What it does |
|---|---|
| `get_proxy_status` | Is OpenProxy running, on which port, with which scenario active |
| `list_requests` | Captured requests as compact summaries (filter by URL / method / status) |
| `get_request` | One flow in full — headers and bodies |
| `run_mock_scenario` | Install a named set of mocks, returns a `watermark` |
| `clear_mocks` | Remove the active scenario |
| `wait_for_requests` | Block until N matching requests complete; the assertion primitive |
| `replay_request` | Re-send a captured request, optionally modified |
| `clear_history` | Drop captured history between scenarios |

## Example

> Mock `/api/profile` to return a 500 and tell me how the Android app handles it.

```
run_mock_scenario(
  name="profile 500",
  mocks=[{"url_pattern": "*/api/profile*", "status": 500,
          "body": '{"error":"server error"}',
          "headers": {"Content-Type": "application/json"}}]
)
→ {"watermark": 41, ...}

# ... agent taps through the app with adb ...

wait_for_requests(since_seq=41, url_pattern="/api/", count=3, timeout=20)
→ three requests: the mocked 500, then two identical retries 1s apart,
  then a POST to /api/analytics with the error — no user-facing retry backoff.
```

## Behaviour worth knowing

**Scenario rules are isolated from the user's.** Mocks installed here are kept in a separate list from whatever the user built by hand in the OpenProxy UI, and are matched *ahead* of them. Running a scenario never destroys their setup, and clearing one restores it exactly.

**Scenarios replace each other wholesale.** Rules never leak from one scenario into the next — that's the failure mode that makes this kind of testing untrustworthy.

**Mocks are cleared automatically on disconnect.** If the MCP server exits mid-scenario, the backend drops the rules rather than leaving the user with silently mocked traffic. Don't rely on it during a session — call `clear_mocks`.

**`url_pattern` in mocks is an anchored glob.** `*/api/profile*` matches; bare `/api/profile` must match the *entire* URL. (The filter argument on `list_requests` / `wait_for_requests` is more forgiving — a bare substring matches anywhere.)

**Bodies are capped at 32KB** and binary/image payloads are dropped from history. Inspect those in the UI.

**History is bounded** at the last 1000 flows. Requests that arrived while OpenProxy wasn't running, or before the buffer wrapped, aren't there.

## Development

The integration test starts its own backend on free ports (so it won't collide with an installed OpenProxy), drives real traffic through mitmproxy, and checks the agent surface, the mocking path, the UI protocol, and disconnect cleanup:

```bash
venv/bin/python mcp-server/tests/test_agent_api.py
```

To point the MCP server at a dev build running alongside the installed app, set `OPENPROXY_WS_PORT` (or `OPENPROXY_WS_URL`) for both the backend and the MCP server:

```bash
OPENPROXY_WS_PORT=8799 venv/bin/python main.py
OPENPROXY_WS_PORT=8799 openproxy-mcp
```

## Security

The server connects to OpenProxy's WebSocket on `127.0.0.1:8765`, which has **no authentication** — localhost-only binding is the whole security model, and any local process could already drive it. This MCP server adds no network exposure of its own (stdio only). Do not expose port 8765 beyond localhost.

## License

GPL-3.0-or-later, same as OpenProxy.
