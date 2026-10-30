#!/usr/bin/env python3
"""Broad UI regression sweep against the running dev app.

Covers the user-facing surface that doesn't reach outside the app (OS proxy,
certificate trust, VPN mode and updates are left alone): toolbar windows,
traffic table, inspector, search, filter chips, Map Local / Map Remote /
Breakpoint rules built through the UI, the agent banner, user overrides of an
agent's rule, adoption of a departed agent's rules, the agent highlight in
every theme, and toolbar toggles reaching the backend. Uncaught exceptions in
the page fail the run.

    npm run start:debug                          # in one terminal
    venv/bin/python ui/tests/test_ui_sweep.py    # in another

Example.com is used as a real upstream for the traffic and rewrite checks, so
they need network access. See cdp.py for how settings are restored.
"""
import json
import time
import asyncio

from cdp import REPO_ROOT, OpenProxyClient, Page, check, isolate, report, restore, send, tools

MOCK_AGENT = [{"active": True, "pattern": "*mock.openproxy.test/api/ui-sweep*", "method": "ANY",
               "status": 418, "body": "ui-sweep"}]
THEMES = sorted(p.stem for p in (REPO_ROOT / "ui" / "src" / "themes").glob("*.json"))


async def close_modal(page):
    await page.h("""
      const b = $$('.pm-close-btn, .close-btn, .modal-close').find(vis);
      if (b) b.click(); else document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
      return true;""")
    await asyncio.sleep(0.4)
    if await page.h("return modalOpen();"):
        await page.h("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1;")
        await asyncio.sleep(0.3)


async def delete_rule(page, pill_label, pattern):
    """Delete one of the user's rules through its window. False if not listed."""
    await page.h(f"pill({json.dumps(pill_label)}).click(); return 1;")
    await asyncio.sleep(0.5)
    ok = await page.h(f"""
      const item = $$('.pm-rule-item:not(.pm-rule-item--agent)').find(e => e.textContent.includes({json.dumps(pattern)}));
      if (!item) return false;
      item.querySelector('.pm-rule-del').click(); return true;""")
    await asyncio.sleep(0.3)
    await close_modal(page)
    return ok


async def save_rule(page):
    await page.h("byText('.pm-btn-execute', 'Save & Apply').click(); return 1;")
    await asyncio.sleep(0.6)
    if await page.h("return modalOpen();"):
        await close_modal(page)


async def main():
    page = Page()
    await page.connect()
    snapshot = await page.snapshot_storage()
    c = OpenProxyClient()
    tools_before = await tools(c)
    t0 = int(time.time())
    try:
        await isolate(page)

        print("\n== toolbar modals open and close ==")
        labels = await page.h("return $$('button.secondary-pill').filter(vis).map(b => b.textContent.trim());")
        print("     pills:", labels)
        for label in ("Breakpoints", "Map Local", "Map Remote", "Highlight"):
            if label not in labels:
                check(f"{label} pill present", False, "hidden by toolbar settings?")
                continue
            await page.h(f"pill({json.dumps(label)}).click(); return 1;")
            await asyncio.sleep(0.5)
            check(f"{label} modal opens", await page.h("return modalOpen();"))
            await close_modal(page)
            check(f"{label} modal closes", not await page.h("return modalOpen();"))
        opened = await page.h("""const b = $$('button').find(e => vis(e) && /^Script/.test(e.textContent.trim()));
                                 if (!b) return 'missing'; b.click(); return 'clicked';""")
        if opened == "clicked":
            await asyncio.sleep(0.5)
            check("Scripting modal opens", await page.h("return modalOpen();"))
            await close_modal(page)
            check("Scripting modal closes", not await page.h("return modalOpen();"))
        await page.h("$$('button[title=\"Compose New Request\"]')[0].click(); return 1;")
        await asyncio.sleep(0.5)
        check("Compose modal opens", await page.h("return $$('.pm-header, .modal-header, .compose-modal, [class*=compose]').some(vis);"))
        await close_modal(page)

        print("\n== traffic table, inspector, search, status chips ==")
        token = f"uisweep{t0}"
        url = f"http://example.com/?{token}=1"
        flow, _ = await send(c, url, timeout=30)
        check("request through proxy completes", flow.get("status") == 200, str(flow.get("status")))
        await asyncio.sleep(1.0)
        row = await page.h(f"return $$('tbody tr').some(r => r.textContent.includes({json.dumps(token)}));")
        check("request appears in the traffic table", row)
        await page.h(f"$$('tbody tr').find(r => r.textContent.includes({json.dumps(token)})).click(); return 1;")
        await asyncio.sleep(0.5)
        check("clicking the row opens it in the inspector",
              await page.h(f"return ($$('.inspector-url-bar')[0]?.textContent || '').includes({json.dumps(token)});"))
        await page.h(f"setVal($$('input[placeholder^=\"Search\"]').find(vis), {json.dumps(token)}); return 1;")
        await asyncio.sleep(0.6)
        rows = await page.h("return $$('tbody tr').filter(r => !r.hasAttribute('aria-hidden') && r.textContent.trim()).map(r => r.textContent);")
        check("search narrows the table to the matching request",
              len(rows) >= 1 and all(token in r for r in rows), f"{len(rows)} rows")
        await page.h("setVal($$('input[placeholder^=\"Search\"]').find(vis), ''); return 1;")
        await asyncio.sleep(0.4)
        await page.h("byText('.chip', '4xx').click(); return 1;")
        await asyncio.sleep(0.5)
        check("4xx chip hides the 200 request",
              not await page.h(f"return $$('tbody tr').some(r => r.textContent.includes({json.dumps(token)}));"))
        await page.h("const g = byText('.chip', '4xx').closest('.chip-group'); [...g.querySelectorAll('.chip')].find(e => e.textContent.trim() === 'All').click(); return 1;")
        await asyncio.sleep(0.5)
        check("All chip brings it back",
              await page.h(f"return $$('tbody tr').some(r => r.textContent.includes({json.dumps(token)}));"))

        print("\n== user Map Local rule built in the UI ==")
        await page.h("pill('Map Local').click(); return 1;")
        await asyncio.sleep(0.5)
        await page.h("$$('.pm-add-btn').find(vis).click(); return 1;")
        await asyncio.sleep(0.4)
        await page.h("setVal($$('.pm-url-input').find(vis), '*sweep-user-mock*'); setVal($$('.pm-status-input').find(vis), '207'); return 1;")
        await asyncio.sleep(0.3)
        await save_rule(page)
        saved = await page.js("JSON.parse(localStorage.getItem('openproxy_mapLocalRules') || '[]').map(r => [r.pattern, r.status, r.active])")
        check("rule saved", any(p == "*sweep-user-mock*" for p, *_ in saved), str(saved))
        check("Map Local pill blue for an active user rule", await page.h("return pillState('Map Local');") == "BLUE")
        flow, _ = await send(c, "http://mock.openproxy.test/sweep-user-mock")
        check("user mock serves 207", flow.get("status") == 207 and flow.get("mocked"), str(flow.get("status")))
        check("user mock isn't attributed to an agent", "X-OpenProxy-Agent" not in (flow.get("res_headers") or {}))
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-sweep C", "map_local": MOCK_AGENT})
        await asyncio.sleep(0.5)
        check("Map Local switch already on → no enabled_tools", not r.get("enabled_tools"))
        check("agent mock on top of a user rule → pill yellow", await page.h("return pillState('Map Local');") == "YELLOW")
        f1, _ = await send(c, "http://mock.openproxy.test/api/ui-sweep")
        f2, _ = await send(c, "http://mock.openproxy.test/sweep-user-mock")
        check("agent mock and user mock both serve", (f1.get("status"), f2.get("status")) == (418, 207),
              f"{f1.get('status')}, {f2.get('status')}")
        await c.call("AGENT_CLEAR_SCENARIO")
        await asyncio.sleep(0.4)
        check("scenario cleared → back to blue", await page.h("return pillState('Map Local');") == "BLUE")
        check("rule deleted through the UI", await delete_rule(page, "Map Local", "*sweep-user-mock*"))
        await asyncio.sleep(0.4)
        check("no user rules left → pill plain", await page.h("return pillState('Map Local');") == "plain")
        flow, _ = await send(c, "http://mock.openproxy.test/sweep-user-mock")
        check("deleted rule no longer serves", not flow.get("mocked"))

        print("\n== user Map Remote rule built in the UI ==")
        await page.h("pill('Map Remote').click(); return 1;")
        await asyncio.sleep(0.5)
        await page.h("$$('.pm-add-btn').find(vis).click(); return 1;")
        await asyncio.sleep(0.4)
        await page.h(r"""const ins = $$('.pm-routing-input').filter(vis);
                         setVal(ins.find(e => !e.classList.contains('target-input')), 'sweep-remote\\.openproxy\\.test');
                         setVal($$('.target-input').find(vis), 'example.com'); return 1;""")
        await asyncio.sleep(0.3)
        await save_rule(page)
        check("Map Remote pill blue for an active user rule", await page.h("return pillState('Map Remote');") == "BLUE")
        # example.com's own latency varies by seconds; give it room.
        flow, raw = await send(c, "http://sweep-remote.openproxy.test/", timeout=30)
        check("user rewrite reaches example.com", flow.get("status") == 200,
              json.dumps({k: raw.get(k) for k in ("timed_out", "hint")} | {"status": flow.get("status"), "error": flow.get("error"), "ms": flow.get("duration_ms")}))
        check("rewrite deleted through the UI", await delete_rule(page, "Map Remote", "sweep-remote"))
        await asyncio.sleep(0.4)
        check("Map Remote pill plain after delete", await page.h("return pillState('Map Remote');") == "plain")

        print("\n== breakpoint built in the UI pauses and drops a request ==")
        await page.h("pill('Breakpoints').click(); return 1;")
        await asyncio.sleep(0.5)
        await page.h("$$('.pm-add-btn').find(vis).click(); return 1;")
        await asyncio.sleep(0.4)
        await page.h("setVal($$('.pm-routing-input').find(vis), '*sweep-bp.openproxy.test*'); return 1;")
        await asyncio.sleep(0.3)
        await save_rule(page)
        check("backend has breakpoints on", (await tools(c))["breakpoints"] is True)
        _, r = await send(c, "http://sweep-bp.openproxy.test/x", wait=False)
        await asyncio.sleep(1.5)
        check("breakpoint hit shows in the UI", await page.h("return !!$$('.pm-btn-drop').find(vis);"))
        await page.h("$$('.pm-btn-drop').find(vis).click(); return 1;")
        await asyncio.sleep(1.0)
        check("dropping closes the breakpoint view", not await page.h("return !!$$('.pm-btn-drop').find(vis);"))
        res = await c.call("AGENT_WAIT_FOR_FLOWS", {"url_pattern": "sweep-bp.openproxy.test",
                                                     "since_seq": r["watermark"], "count": 1, "timeout": 5}, timeout=15)
        check("dropped request ends without a response",
              bool(res["matched"]) and res["matched"][0].get("status") in (None, 0) or res.get("timed_out"),
              str(res["matched"][:1])[:120])
        check("breakpoint deleted through the UI", await delete_rule(page, "Breakpoints", "sweep-bp"))
        await asyncio.sleep(0.4)
        check("no breakpoint rules → backend breakpoints off", (await tools(c))["breakpoints"] is False)

        print("\n== agent banner controls ==")
        await c.call("AGENT_RUN_SCENARIO", {"name": "ui-sweep F", "map_local": MOCK_AGENT})
        await asyncio.sleep(0.5)
        await page.h("byText('button', 'Show rules').click(); return 1;")
        await asyncio.sleep(0.5)
        check("Show rules opens Map Local with the agent's rule",
              await page.h("return modalOpen() && $$('.pm-rule-item--agent').some(e => e.textContent.includes('api/ui-sweep'));"))

        print("\n== user takes over an agent rule ==")
        await page.h("$$('.pm-rule-item--agent').find(vis).click(); return 1;")
        await asyncio.sleep(0.4)
        await page.h("setVal($$('.pm-status-input').find(vis), '299'); return 1;")
        await asyncio.sleep(1.0)
        await close_modal(page)
        flow, _ = await send(c, "http://mock.openproxy.test/api/ui-sweep")
        check("override applied to the agent's mock", flow.get("status") == 299, str(flow.get("status")))
        sc = (await c.call("AGENT_STATUS"))["scenario"]
        check("backend marks status as user-owned",
              sc and "status" in (sc["mocks"][0].get("overridden") or []), str(sc and sc["mocks"][0].get("overridden")))

        await page.h("byText('button', 'History').click(); return 1;")
        await asyncio.sleep(0.4)
        check("History shows the agent's actions",
              await page.h("return document.body.innerText.includes('Started “ui-sweep F”');"))
        await page.h("byText('button', 'History').click(); return 1;")
        await page.h("byText('button', 'Stop').click(); return 1;")
        await asyncio.sleep(0.8)
        check("Stop clears the agent's scenario", (await c.call("AGENT_STATUS"))["scenario"] is None)
        check("banner no longer says mocking", not await page.h("return document.body.innerText.includes('is mocking');"))

        print("\n== rules of an agent that vanished are adopted, switched off ==")
        gone = OpenProxyClient()
        await gone.call("AGENT_RUN_SCENARIO", {"name": "ui-sweep H", "map_local": [
            {"active": True, "pattern": "*sweep-adopt*", "status": 202, "body": "a"}]})
        await gone.close()
        await asyncio.sleep(1.5)
        adopted = await page.js("JSON.parse(localStorage.getItem('openproxy_mapLocalRules') || '[]').filter(r => r.pattern === '*sweep-adopt*').map(r => r.active)")
        check("rule adopted into the user's list, inactive", adopted == [False], str(adopted))
        check("inactive adopted rule → pill plain (not blue)", await page.h("return pillState('Map Local');") == "plain")
        flow, _ = await send(c, "http://mock.openproxy.test/sweep-adopt")
        check("adopted rule doesn't serve", not flow.get("mocked"))
        check("adopted rule deleted through the UI", await delete_rule(page, "Map Local", "*sweep-adopt*"))

        print("\n== agent highlight in every theme ==")
        await c.call("AGENT_RUN_SCENARIO", {"name": "ui-sweep I", "map_local": MOCK_AGENT})
        await asyncio.sleep(0.5)
        for theme in THEMES:
            await page.set_storage({"openproxy-theme": theme})
            await page.reload()
            res = await page.h("""
              const probe = document.createElement('span'); probe.style.color = 'var(--warning)'; document.body.appendChild(probe);
              const warn = getComputedStyle(probe).color; probe.remove();
              const p = pill('Map Local'), plain = pill('Highlight') || pill('Breakpoints');
              return {state: pillState('Map Local'), color: settled(p).color, warn,
                      bg: settled(p).bg, plainBg: settled(plain).bg,
                      mocks: $$('.agent-bar').some(e => e.innerText.includes('mocking'))};""")
            st = await c.call("AGENT_STATUS")
            check(f"{theme}: pill yellow in the theme's --warning",
                  res["state"] == "YELLOW" and res["color"] == res["warn"] and res["bg"] != res["plainBg"],
                  f"{res['state']} color {res['color']} warn {res['warn']} · backend map_local "
                  f"{st['tools']['map_local']}, scenario {'on' if st['scenario'] else 'off'}, banner mocking {res['mocks']}")
        await c.call("AGENT_CLEAR_SCENARIO")

        print("\n== toolbar toggles driven from the UI reach the backend ==")
        nc0 = (await tools(c))["no_cache"]
        await page.h("$$('[title=\"Disable caching for all requests\"]').find(vis).click(); return 1;")
        await asyncio.sleep(0.5)
        check("No Cache click flips the backend", (await tools(c))["no_cache"] is (not nc0))
        await page.h("$$('[title=\"Disable caching for all requests\"]').find(vis).click(); return 1;")
        await asyncio.sleep(0.5)
        check("second click flips it back", (await tools(c))["no_cache"] is nc0)
        await page.h("$$('[title=\"Network Throttling\"]').find(vis).click(); await new Promise(r => setTimeout(r, 300)); $$('.throttle-wrapper .dropdown-item').filter(vis).find(e => e.textContent.trim().startsWith('Slow 3G')).click(); return 1;")
        await asyncio.sleep(0.5)
        check("throttle menu sets Slow 3G on the backend", (await tools(c))["throttle"] == "Slow 3G")
        await page.h("$$('[title=\"Network Throttling\"]').find(vis).click(); await new Promise(r => setTimeout(r, 300)); $$('.throttle-wrapper .dropdown-item').filter(vis).find(e => e.textContent.trim().startsWith('None')).click(); return 1;")
        await asyncio.sleep(0.5)
        check("throttle menu sets None", (await tools(c))["throttle"] == "None")
        await page.h("$$('[title*=Intercepting]')[0].click(); return 1;")
        await asyncio.sleep(0.5)
        check("record button pauses the backend", (await tools(c))["recording"] is False)
        await page.h("$$('[title*=Intercepting]')[0].click(); return 1;")
        await asyncio.sleep(0.5)
        check("record button resumes it", (await tools(c))["recording"] is True)
    finally:
        await restore(page, c, snapshot, tools_before)
        print("\n== console errors / exceptions during the sweep ==")
        for e in page.errors:
            print("   ", e)
        exceptions = [e for e in page.errors if e.startswith("exception")]
        check("no uncaught exceptions in the page", not exceptions, f"{len(exceptions)} exceptions")
        await page.close()
    return report("UI sweep")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
