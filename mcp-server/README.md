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

There is nothing to install: the MCP server ships inside the OpenProxy app as `OpenProxy-server --mcp`. On every start the app refreshes a small launcher at

| Platform | Launcher |
|---|---|
| macOS / Linux | `~/.openproxy/bin/openproxy-mcp` |
| Windows | `%USERPROFILE%\.openproxy\bin\openproxy-mcp.cmd` |

that runs the currently installed build. Register **that path** with your agent. It never changes, so a config written once survives app updates, a moved install, and Linux AppImage remounts. The app's **Tools → Connect an AI Agent (MCP)…** window shows the exact path with copy buttons and whether an agent is connected right now.

### Claude Code

```bash
claude mcp add openproxy --scope user -- ~/.openproxy/bin/openproxy-mcp
```

`--scope user` makes it available in every project; `--scope project` writes `.mcp.json` at the repo root so the whole team picks it up (everyone still needs OpenProxy installed).

### Claude Desktop / Cursor / Zed

Use the absolute launcher path; desktop apps start with the system PATH, not your shell's. For Claude Desktop, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openproxy": {
      "command": "/Users/you/.openproxy/bin/openproxy-mcp"
    }
  }
}
```

Cursor takes the same shape in `~/.cursor/mcp.json`; Zed uses `context_servers` in its `settings.json`.

The server talks **stdio**, so there's no port to configure and nothing listening.

### Updates

An update replaces the whole app bundle, MCP server included, and the launcher is rewritten on the next start to point at it. An MCP process that an agent started *before* the update keeps running the old build until that agent restarts it; the handshake detects the version skew and every tool result carries a warning saying so.

### Running from a checkout (development)

`python main.py --mcp` runs the same server from the repo venv, and the backend writes the launcher pointed at it, so the app's setup window works in development too. To use the package on its own — for tests, or to run the server on another machine than the app — install it into any Python 3.10+ environment:

```bash
uv tool install ./mcp-server     # or: pip install -e ./mcp-server
```

## Tools

| Tool | What it does |
|---|---|
| `get_proxy_status` | Is OpenProxy running, on which port, with which scenario active |
| `list_requests` | Captured requests as compact summaries (filter by URL / method / status / watermark) |
| `get_request` | One flow in full — headers and bodies |
| `get_requests` | Up to 20 flows in full, in one call |
| `search_requests` | Find flows containing a string anywhere: URL, headers, bodies, WebSocket frames |
| `summarize_traffic` | Counts by host / status / method, top endpoints, latency — the shape of a window of traffic |
| `get_websocket_messages` | Frames exchanged over a captured WebSocket connection |
| `run_mock_scenario` | Install a named set of mocks (with optional latency and response sequences), returns a `watermark` |
| `clear_mocks` | Remove the active scenario |
| `wait_for_requests` | Block until N matching requests complete; the assertion primitive |
| `replay_request` | Re-send a captured request, optionally modified; returns the resulting flow |
| `send_request` | Send a request composed from scratch through the proxy; returns the resulting flow |
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

**Mocks are cleared automatically on disconnect.** If the MCP server exits mid-scenario, the backend drops the rules rather than leaving the user with silently mocked traffic. The scenario belongs to the connection that installed it, so another agent staying attached doesn't keep it alive. Don't rely on it during a session — call `clear_mocks`.

**Mocks can fail-then-recover.** A mock's `responses` list serves a different response on each hit (`[{status: 500}, {status: 500}, {status: 200}]`), holding on the last entry by default or cycling with `sequence_mode: "cycle"`. `delay_ms` adds per-endpoint latency on top of any throttle. Both are agent-only fields; the UI shows them on the rule but doesn't edit them.

**Injected requests are tagged.** `send_request` and `replay_request` stamp an `X-OpenProxy-Replay-Id` header so they can return *their* flow even if the app hits the same URL at the same moment. The header is stripped before the request leaves the proxy; the flow's `replay_id` field records it.

**Bad rules fail at install time.** An unknown `throttle` name, an empty pattern, or a status outside 100–599 is rejected by `run_mock_scenario` with nothing installed, rather than silently doing nothing or serving a 500 when matched.

**`url_pattern` in mocks is an anchored glob.** `*/api/profile*` matches; bare `/api/profile` must match the *entire* URL. (The filter argument on `list_requests` / `wait_for_requests` is more forgiving — a bare substring matches anywhere.)

**Bodies are capped at 32KB** and binary/image payloads are dropped from history. `get_request` reports `req_body_complete` / `res_body_complete` so you can tell. Inspect those in the UI.

**`replay_request` refuses a request whose stored body is incomplete** (over the cap, or binary), because resending the stored copy would send a corrupted payload. Pass `body` yourself to replay it anyway.

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
