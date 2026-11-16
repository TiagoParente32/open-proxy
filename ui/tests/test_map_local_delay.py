#!/usr/bin/env python3
"""UI checks for the Delay (ms) field in the Map Local editor against the
running dev app: the field shows a rule's delay, edits persist and reach the
backend, out-of-range values are clamped, the sidebar badge follows, a mocked
request is really held back, and the field works on an agent's mock as an
override.

    npm run start:debug                                  # in one terminal
    venv/bin/python ui/tests/test_map_local_delay.py     # in another

See cdp.py for what the harness needs and how settings are restored.
"""
import json
import time
import asyncio

from cdp import OpenProxyClient, Page, check, isolate, report, restore, send, tools


def mock(i, label, **extra):
    return {"id": i, "active": True, "label": label, "method": "ANY",
            "pattern": f"*/ui-delay/{label}*", "status": 200, "headers": "", "body": label,
            "body_source": "inline", "file_path": "", **extra}


RULES = [mock(1, "slow", delay_ms=1200), mock(2, "fast")]

DELAY_INPUT = "$$('.pm-delay-input').find(vis)"


async def delay_value(page):
    return await page.h(f"return {DELAY_INPUT}.value;")


async def set_delay(page, value):
    await page.h(f"setVal({DELAY_INPUT}, {json.dumps(value)}); return 1;")
    await asyncio.sleep(0.3)


async def badges(page):
    """The '+N ms' badges in the sidebar, top to bottom, '' for rows without one."""
    return await page.h("""
      return $$('.pm-rule-item').filter(vis).map(e => (e.querySelector('.pm-extra')?.textContent || '').trim());""")


async def rules_in_storage(page):
    return json.loads(await page.get_storage("openproxy_mapLocalRules") or "[]")


async def select_rule(page, label):
    await page.h(f"$$('.pm-rule-item').find(e => vis(e) && e.textContent.includes({json.dumps(label)})).click(); return 1;")
    await asyncio.sleep(0.2)


async def timed_send(c, url):
    t0 = time.monotonic()
    flow, _ = await send(c, url)
    return flow, time.monotonic() - t0


async def main():
    page = Page()
    await page.connect()
    snapshot = await page.snapshot_storage()
    c = OpenProxyClient()
    tools_before = await tools(c)
    try:
        await isolate(page)
        await page.set_storage({"openproxy_mapLocalRules": json.dumps(RULES),
                                "openproxy_enableMapLocal": "false"})
        await page.reload()
        await page.h("pill('Map Local').click(); return 1;")
        await asyncio.sleep(0.4)

        print("\n== the field shows the rule's delay ==")
        check("first rule is selected with its delay in the box", await delay_value(page) == "1200", await delay_value(page))
        check("sidebar badges follow the rules", await badges(page) == ["+1200 ms", ""], str(await badges(page)))
        await select_rule(page, "fast")
        check("a rule without a delay shows an empty box", await delay_value(page) == "", await delay_value(page))

        print("\n== edits persist and reach the backend ==")
        await set_delay(page, "300")
        stored = {r["label"]: r.get("delay_ms") for r in await rules_in_storage(page)}
        check("delay is saved with the rule", stored == {"slow": 1200, "fast": 300}, str(stored))
        await asyncio.sleep(0.5)
        listed = {r["label"]: r.get("delay_ms") for r in (await c.call("AGENT_LIST_RULES"))["map_local"]}
        check("backend sees the new delay", listed == {"slow": 1200, "fast": 300}, str(listed))
        check("badge appears on the edited rule", await badges(page) == ["+1200 ms", "+300 ms"], str(await badges(page)))

        print("\n== out-of-range and empty values ==")
        await set_delay(page, "99999")
        check("values above 60 s are clamped to 60000",
              (await rules_in_storage(page))[1].get("delay_ms") == 60000, str(await rules_in_storage(page)))
        await set_delay(page, "-5")
        check("negative values become 0", (await rules_in_storage(page))[1].get("delay_ms") == 0)
        await set_delay(page, "")
        check("clearing the box stores 0, not a string", (await rules_in_storage(page))[1].get("delay_ms") == 0)
        check("badge goes away again", await badges(page) == ["+1200 ms", ""], str(await badges(page)))

        print("\n== the delay really holds the response ==")
        await c.call("AGENT_SET_TOOLS", {"map_local": True})
        await asyncio.sleep(0.5)
        flow, el = await timed_send(c, "http://example.com/ui-delay/slow")
        check("mock with a 1200 ms delay takes at least that long",
              flow.get("status") == 200 and el >= 1.1, f"{flow.get('status')} in {el:.2f}s")
        flow, el = await timed_send(c, "http://example.com/ui-delay/fast")
        check("mock without a delay is immediate", flow.get("status") == 200 and el < 1.0, f"{flow.get('status')} in {el:.2f}s")

        print("\n== the field works on an agent's mock as an override ==")
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-delay", "map_local": [
            {"active": True, "pattern": "*/ui-delay/agent*", "status": 200, "body": "agent"}]})
        check("scenario installed", (r.get("scenario") or {}).get("name") == "ui-delay", str(r)[:120])
        await asyncio.sleep(0.5)
        await select_rule(page, "ui-delay/agent")
        check("agent mock starts with an empty box", await delay_value(page) == "", await delay_value(page))
        await set_delay(page, "800")
        await asyncio.sleep(1.0)  # the override is debounced before it's sent
        check("the Delay label is marked as yours",
              await page.h("return !!$$('.pm-routing-label').find(e => vis(e) && e.textContent.includes('Delay') && e.querySelector('.pm-owned'));"))
        flow, el = await timed_send(c, "http://example.com/ui-delay/agent")
        check("the agent's mock is now held back", flow.get("status") == 200 and el >= 0.7, f"{flow.get('status')} in {el:.2f}s")
        check("the user's rules are untouched",
              {r["label"]: r.get("delay_ms") for r in await rules_in_storage(page)} == {"slow": 1200, "fast": 0})
    finally:
        await restore(page, c, snapshot, tools_before)
        await page.close()
    return report("Map Local delay")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
