"""Shared harness for the UI tests: drives the OpenProxy window over the Chrome
DevTools Protocol and the backend as an agent.

The tests run against a live dev app started with a debugging port:

    npm run start:debug          # electron . --remote-debugging-port=9223

They change rules and switches through the UI, so every `openproxy*`
localStorage key is snapshotted first and restored exactly at the end (see
snapshot_storage / restore). Point them at the dev app, not at an
installation you care about mid-session.
"""
import os
import sys
import json
import asyncio
import urllib.request
from pathlib import Path

import websockets

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))

from openproxy_mcp.client import OpenProxyClient  # noqa: E402,F401  (re-exported for the tests)

CDP_PORT = int(os.environ.get("OPENPROXY_CDP_PORT", "9223"))
# How long a reload takes to reconnect the UI and receive AGENT_STATE.
RELOAD_SETTLE = 4.0

failures = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def report(suite):
    print("\n" + "=" * 52)
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print(f"All {suite} checks passed.")
    return 0


# Prepended to every Page.h() evaluation. alert/confirm are replaced because a
# native dialog blocks the page, and with it every further CDP call.
HELPERS = """
window.alert = m => console.warn('ALERT: ' + m); window.confirm = () => true;
const $$ = s => [...document.querySelectorAll(s)];
const vis = e => !!e && e.offsetParent !== null;
const byText = (s, t) => $$(s).find(e => vis(e) && e.textContent.trim() === t);
const setVal = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); };
const pill = t => $$('button.secondary-pill').find(b => b.textContent.trim() === t);
const pillState = t => { const b = pill(t); return !b ? 'missing' : b.classList.contains('agent-active') ? 'YELLOW' : b.classList.contains('script-active') ? 'BLUE' : 'plain'; };
const modalOpen = () => $$('.pm-header, .pm-sidebar-header, .modal-header').some(vis);
// A hidden or occluded window renders no frames, so CSS transitions never
// finish and getComputedStyle keeps returning their start value. Cancelling
// the transition jumps the element to its final colours.
const settled = el => { const t = el.style.transition; el.style.transition = 'none';
  const cs = getComputedStyle(el), out = {color: cs.color, bg: cs.backgroundColor};
  el.style.transition = t; return out; };
"""


class Page:
    """The app window. Records console errors and uncaught exceptions as it goes."""

    def __init__(self):
        self.ws = None
        self.n = 0
        self.errors = []

    async def connect(self):
        try:
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5))
        except Exception as e:
            raise SystemExit(
                f"No debugging port on {CDP_PORT} ({type(e).__name__}). "
                "Start the dev app with `npm run start:debug` first."
            )
        url = next(t for t in targets if t.get("type") == "page")["webSocketDebuggerUrl"]
        # No keepalive: the socket is only read during a call, so a quiet
        # stretch (a long request, a sleep) would fail the ping and drop it.
        self.ws = await websockets.connect(url, max_size=None, ping_interval=None)
        await self._send("Runtime.enable")
        self.errors.clear()   # only what happens during the run counts

    async def close(self):
        await self.ws.close()

    async def _send(self, method, params=None):
        self.n += 1
        mine = self.n
        await self.ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            event = msg.get("method")
            if event == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.errors.append("exception: " + ((d.get("exception") or {}).get("description") or d.get("text", ""))[:200])
            elif event == "Runtime.consoleAPICalled" and msg["params"]["type"] in ("error", "assert"):
                args = msg["params"].get("args", [])
                self.errors.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in args)[:200])
            if msg.get("id") == mine:
                return msg

    async def js(self, expr):
        r = await self._send("Runtime.evaluate",
                             {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = r.get("result", {})
        if "exceptionDetails" in res:
            raise RuntimeError(json.dumps(res["exceptionDetails"])[:300])
        return res.get("result", {}).get("value")

    async def h(self, body):
        """Run `body` (statements ending in a return) with HELPERS in scope."""
        return await self.js(f"(async () => {{ {HELPERS} {body} }})()")

    async def reload(self):
        await self._send("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(RELOAD_SETTLE)

    async def toolbar(self):
        return await self.h("""
          const thr = $$('button.secondary-pill').find(b => /Throttle|3G/.test(b.textContent));
          return {mapLocal: pillState('Map Local'), mapRemote: pillState('Map Remote'),
                  throttle: thr ? thr.textContent.trim() : null,
                  recording: document.querySelector('[title*=Intercepting]')?.title,
                  banner: (document.querySelector('.agent-bar')?.innerText || '').replace(/\\s+/g, ' ')};""")

    async def get_storage(self, key):
        return await self.js(f"localStorage.getItem({json.dumps(key)})")

    async def set_storage(self, values):
        """Set localStorage keys; a None value removes the key."""
        await self.js(f"""(() => {{ const v = {json.dumps(values)};
          for (const [k, x] of Object.entries(v)) {{ if (x === null) localStorage.removeItem(k); else localStorage.setItem(k, x); }} }})()""")

    async def snapshot_storage(self):
        return await self.js("Object.fromEntries(Object.keys(localStorage).filter(k => k.startsWith('openproxy')).map(k => [k, localStorage.getItem(k)]))")


async def send(c, url, wait=True, timeout=15):
    """Send a request through the proxy as the agent; returns (flow, raw result)."""
    r = await c.call("AGENT_SEND_REQUEST", {"url": url, "wait": wait, "timeout": timeout}, timeout=timeout + 15)
    return r.get("flow") or {}, r


async def tools(c):
    return (await c.call("AGENT_STATUS"))["tools"]


async def isolate(page):
    """Load empty rule lists with their switches off, so none of the user's own
    mocks, rewrites or breakpoints is live while the tests flip switches. A
    live breakpoint would pause real traffic with no timeout, and a reload
    drops the paused flow from the UI, so the request would hang."""
    await page.set_storage({"openproxy_mapLocalRules": "[]", "openproxy_mapRemoteRules": "[]",
                            "openproxy_breakpointRules": "[]", "openproxy_enableMapLocal": "false",
                            "openproxy_enableMapRemote": "false", "openproxy_breakpointsEnabled": "false"})
    await page.reload()


async def restore(page, c, snapshot, tools_before):
    """Put the user's settings back and close `c`: clear any scenario, restore
    the exact localStorage snapshot, reload so the UI re-pushes it, then check
    both from a fresh connection once `c` is gone."""
    print("\n== restore ==")
    await c.call("AGENT_CLEAR_SCENARIO")
    check("scenario cleared", (await c.call("AGENT_STATUS"))["scenario"] is None)
    # Anything a test agent switched off is queued to come back on when it
    # disconnects, which would land after the checks below. Turning those
    # switches on voids the restores; the reload then re-applies the user's
    # real values from the snapshot. Only the switches the tests turn off,
    # and only with the rule lists still empty: breakpoints and recording are
    # never forced on.
    await isolate(page)
    now = await tools(c)
    off = {name: True for name in ("map_local", "map_remote", "no_cache") if not now[name]}
    if off:
        await c.call("AGENT_SET_TOOLS", off)
    # Let the UI apply the AGENT_STATE / TOOL_STATE that just went out: its
    # watchers persist to localStorage and would overwrite the restore.
    await asyncio.sleep(1.5)
    await page.js(f"""(() => {{ const snap = {json.dumps(snapshot)};
        Object.keys(localStorage).filter(k => k.startsWith('openproxy') && !(k in snap)).forEach(k => localStorage.removeItem(k));
        for (const [k, v] of Object.entries(snap)) localStorage.setItem(k, v); }})()""")
    await page.reload()
    # Recording isn't persisted by the UI, so it isn't re-pushed on reload. Flip
    # it with the record button, as the user would: done by this agent, an
    # "off" would be undone again when it disconnects.
    if (await tools(c))["recording"] != tools_before["recording"]:
        await page.h("document.querySelector('[title*=Intercepting]').click(); return 1;")
        await asyncio.sleep(0.5)
    await c.close()
    await asyncio.sleep(1.0)
    after = await page.snapshot_storage()
    diff = sorted(k for k in set(snapshot) | set(after) if snapshot.get(k) != after.get(k))
    check("localStorage restored exactly", not diff, str(diff))
    probe = OpenProxyClient()
    now = await tools(probe)
    await probe.close()
    check("backend switches back to their starting values", now == tools_before,
          json.dumps({k: (tools_before[k], now[k]) for k in tools_before if tools_before[k] != now[k]}))
