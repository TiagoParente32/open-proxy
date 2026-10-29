#!/usr/bin/env python3
"""UI checks for agent-driven toolbar switches (set_proxy_tools, scenario
auto-enable, restore on disconnect) against the running dev app.

    npm run start:debug                               # in one terminal
    venv/bin/python ui/tests/test_agent_switches.py   # in another

See cdp.py for what the harness needs and how settings are restored.
"""
import json
import asyncio

from cdp import OpenProxyClient, Page, check, report, restore, send, tools

MOCK = "http://mock.openproxy.test/api/ui-test"
MOCKS = [{"active": True, "pattern": "*mock.openproxy.test/api/ui-test*", "method": "ANY",
          "status": 418, "body": "ui-test"}]
USER_RULE = {"id": "ui-test-rule", "label": "ui test rule", "pattern": "*/ui-test-user-only*",
             "method": "ANY", "status": 200, "headers": "", "body": "", "body_source": "inline",
             "file_path": "", "req_headers_mod": {}}


async def hit(c, url=MOCK):
    flow, _ = await send(c, url)
    return flow.get("status"), flow.get("mocked")


async def set_user_rules(page, rules, enabled):
    await page.set_storage({"openproxy_mapLocalRules": json.dumps(rules),
                            "openproxy_enableMapLocal": json.dumps(enabled)})
    await page.reload()


async def main():
    page = Page()
    await page.connect()
    snapshot = await page.snapshot_storage()
    c = OpenProxyClient()
    tools_before = await tools(c)
    try:
        print("\n== no user rules: a scenario turns Map Local on ==")
        await set_user_rules(page, [], False)
        await c.call("AGENT_SET_TOOLS", {"map_local": False, "map_remote": False})
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-test 1", "map_local": MOCKS})
        check("enabled_tools names map_local", r.get("enabled_tools") == ["map_local"], str(r.get("enabled_tools")))
        await asyncio.sleep(0.5)
        check("Map Local pill is yellow", (await page.toolbar())["mapLocal"] == "YELLOW")
        check("mock fires", await hit(c) == (418, True))

        print("\n== a reload mid-scenario keeps Map Local on ==")
        await page.reload()
        check("backend Map Local still on", (await tools(c))["map_local"] is True)
        check("Map Local pill still yellow", (await page.toolbar())["mapLocal"] == "YELLOW")
        check("mock still fires", await hit(c) == (418, True))

        print("\n== the user switching it off sticks ==")
        await page.h("""
          pill('Map Local').click(); await new Promise(r => setTimeout(r, 500));
          const row = $$('*').find(e => e.children.length <= 3 && /^Enable Map Local/.test(e.textContent.trim()) && e.querySelector('.toggle'));
          row.querySelector('.toggle').click();
          document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
          return 1;""")
        await asyncio.sleep(0.5)
        other = OpenProxyClient()
        await other.call("AGENT_STATUS")   # its HELLO sends the UI a fresh AGENT_STATE
        await asyncio.sleep(1)
        await other.close()
        await asyncio.sleep(0.5)
        check("backend Map Local stays off", (await tools(c))["map_local"] is False)
        check("Map Local pill plain", (await page.toolbar())["mapLocal"] == "plain")
        check("mock no longer fires", (await hit(c))[1] is False)

        print("\n== an active user rule: scenario warns, switch untouched ==")
        await set_user_rules(page, [{**USER_RULE, "active": True}], False)
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-test 4", "map_local": MOCKS})
        check("scenario warns", "map_local" in (r.get("warning") or ""), str(r.get("warning"))[:60])
        check("no enabled_tools", not r.get("enabled_tools"))
        await page.reload()
        check("a reload leaves it off", (await tools(c))["map_local"] is False)
        await c.call("AGENT_CLEAR_SCENARIO")
        await c.call("AGENT_SET_TOOLS", {"map_local": True})
        await asyncio.sleep(0.5)
        check("active user rule + switch on, no agent → blue", (await page.toolbar())["mapLocal"] == "BLUE")

        print("\n== only an inactive user rule ==")
        await set_user_rules(page, [{**USER_RULE, "active": False}], True)
        check("inactive-only rule, switch on, no agent → plain", (await page.toolbar())["mapLocal"] == "plain")
        await set_user_rules(page, [{**USER_RULE, "active": False}], False)
        await c.call("AGENT_SET_TOOLS", {"map_local": False})
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-test 5", "map_local": MOCKS})
        check("scenario turns Map Local on", r.get("enabled_tools") == ["map_local"], str(r.get("enabled_tools")))
        await page.reload()
        check("a reload keeps it on", (await tools(c))["map_local"] is True)
        check("Map Local pill yellow", (await page.toolbar())["mapLocal"] == "YELLOW")
        check("mock fires", await hit(c) == (418, True))
        await c.call("AGENT_CLEAR_SCENARIO")

        print("\n== a rewrite-only scenario ==")
        await c.call("AGENT_SET_TOOLS", {"map_remote": False})
        r = await c.call("AGENT_RUN_SCENARIO", {"name": "ui-test 6", "map_remote": [
            {"active": True, "pattern": r"rewrite\.openproxy\.test", "target": "example.com"}]})
        check("enabled_tools names map_remote", r.get("enabled_tools") == ["map_remote"], str(r.get("enabled_tools")))
        await asyncio.sleep(0.5)
        tb = await page.toolbar()
        check("Map Remote pill yellow", tb["mapRemote"] == "YELLOW")
        check("banner reads 'redirecting 1 endpoint'", "redirecting 1 endpoint" in tb["banner"], tb["banner"][:70])
        agents = 1 + tb["banner"].startswith(tuple(f"{n} agents" for n in range(2, 10)))
        check("banner verb agrees with the agent count",
              (" are redirecting" if agents > 1 else " is redirecting") in tb["banner"], tb["banner"][:50])
        # example.com's own latency varies by seconds; give it room.
        flow, _ = await send(c, "http://rewrite.openproxy.test/", timeout=30)
        check("rewritten request reaches example.com", flow.get("status") == 200,
              str(flow.get("status") or flow.get("error")))

        print("\n== set_proxy_tools is reflected live ==")
        await c.call("AGENT_SET_TOOLS", {"no_cache": False, "throttle": "Fast 3G"})
        await asyncio.sleep(0.5)
        check("throttle pill shows Fast 3G", (await page.toolbar())["throttle"] == "Fast 3G")
        check("UI saved No Cache off", await page.get_storage("openproxy_disableCache") == "false")

        print("\n== a disconnect restores what an agent turned off ==")
        other = OpenProxyClient()
        await other.call("AGENT_SET_TOOLS", {"recording": False})
        await asyncio.sleep(0.5)
        check("UI shows recording paused", (await page.toolbar())["recording"] == "Start Intercepting")
        await other.close()
        await asyncio.sleep(1.5)
        check("UI shows recording resumed after disconnect",
              (await page.toolbar())["recording"] == "Pause Intercepting")

        print("\n== a reload while an agent has recording paused ==")
        other = OpenProxyClient()
        await other.call("AGENT_SET_TOOLS", {"recording": False})
        await page.reload()
        check("after reload the UI shows recording paused",
              (await page.toolbar())["recording"] == "Start Intercepting")

        print("\n== the user re-toggles before the agent leaves ==")
        click_record = "document.querySelector('[title*=Intercepting]').click(); return 1;"
        await page.h(click_record)          # user: on
        await asyncio.sleep(0.3)
        await page.h(click_record)          # user: off again, on purpose
        await asyncio.sleep(0.3)
        await other.close()
        await asyncio.sleep(1.5)
        check("the user's own off survives the agent leaving",
              (await tools(c))["recording"] is False
              and (await page.toolbar())["recording"] == "Start Intercepting")
        await page.h(click_record)          # user resumes
        await asyncio.sleep(0.3)
        check("the user can resume", (await tools(c))["recording"] is True)
    finally:
        await restore(page, c, snapshot, tools_before)
        await page.close()
    return report("agent-switch UI")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
