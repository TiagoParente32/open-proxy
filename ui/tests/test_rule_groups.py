#!/usr/bin/env python3
"""UI checks for rule groups in the Map Local window against the running dev
app: rendering, collapse, the right-click menu that creates and fills groups,
the editor's group picker, the group on/off switch, drag and drop, and an
agent's group edits showing up live.

    npm run start:debug                              # in one terminal
    venv/bin/python ui/tests/test_rule_groups.py     # in another

See cdp.py for what the harness needs and how settings are restored.
"""
import json
import asyncio

from cdp import OpenProxyClient, Page, check, isolate, report, restore, tools


def mock(i, label, **extra):
    return {"id": i, "active": True, "label": label, "method": "GET",
            "pattern": f"*/ui-groups/{label}*", "status": 200, "headers": "", "body": "",
            "body_source": "inline", "file_path": "", **extra}


RULES = [mock(1, "alpha", group_id=500), mock(2, "beta", group_id=500), mock(3, "gamma"), mock(4, "delta")]
GROUPS = [{"id": 500, "name": "Staging", "color": "blue", "collapsed": False}]

# What the sidebar shows, top to bottom: group headers as "G:<name>:<count>",
# rules as their label, grouped ones prefixed with "  ".
SIDEBAR = """
  return $$('.pm-rule-list .rg-list > *').filter(vis).map(e => {
    if (e.classList.contains('rg-header')) return 'G:' + e.querySelector('.rg-name').textContent.trim() + ':' + e.querySelector('.rg-count').textContent.trim();
    if (e.classList.contains('rg-item')) return (e.classList.contains('rg-item--grouped') ? '  ' : '') + e.querySelector('.pm-rule-pattern').textContent.trim();
    if (e.classList.contains('rg-empty-group')) return '  (empty)';
    return null;
  }).filter(Boolean);"""


async def sidebar(page):
    return await page.h(SIDEBAR)


async def groups_in_storage(page):
    return json.loads(await page.get_storage("openproxy_mapLocalGroups") or "[]")


async def rules_in_storage(page):
    return json.loads(await page.get_storage("openproxy_mapLocalRules") or "[]")


async def pick_group(page, option):
    """Choose an entry in the editor's group dropdown by its text."""
    await page.h("document.querySelector('.rgp-trigger').click(); return 1;")
    await asyncio.sleep(0.2)
    # The menu is position: fixed, so it has no offsetParent — find it by text alone.
    await page.h(f"$$('.rgp-option').find(e => e.textContent.trim() === {json.dumps(option)}).click(); return 1;")
    await asyncio.sleep(0.3)


async def right_click(page, label):
    await page.h(f"""
      const row = $$('.rg-item').find(e => vis(e) && e.textContent.includes({json.dumps(label)}));
      const r = row.getBoundingClientRect();
      row.dispatchEvent(new MouseEvent('contextmenu', {{bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 10}}));
      return 1;""")
    await asyncio.sleep(0.25)


async def menu_items(page):
    return await page.h("return $$('.rg-menu > .rg-menu-item').map(e => (e.querySelector('.rg-menu-sub-label') || e).textContent.trim().replace(/\s+/g, ' '));")


async def open_map_local(page):
    await page.h("pill('Map Local').click(); return 1;")
    await asyncio.sleep(0.4)


async def main():
    page = Page()
    await page.connect()
    snapshot = await page.snapshot_storage()
    c = OpenProxyClient()
    tools_before = await tools(c)
    try:
        await isolate(page)
        await page.set_storage({"openproxy_mapLocalRules": json.dumps(RULES),
                                "openproxy_mapLocalGroups": json.dumps(GROUPS),
                                "openproxy_enableMapLocal": "false"})
        await page.reload()
        await open_map_local(page)

        print("\n== grouped rules render under their header ==")
        check("sidebar shows the group block then the loose rules",
              await sidebar(page) == ["G:Staging:2", "  alpha", "  beta", "gamma", "delta"], str(await sidebar(page)))
        listed = await c.call("AGENT_LIST_RULES")
        check("backend received the groups with the rules",
              [g["name"] for g in listed["map_local_groups"]] == ["Staging"], str(listed["map_local_groups"]))

        print("\n== collapse / expand ==")
        await page.h("$$('.rg-header').find(vis).click(); return 1;")
        await asyncio.sleep(0.2)
        check("collapsed group hides its rules", await sidebar(page) == ["G:Staging:2", "gamma", "delta"], str(await sidebar(page)))
        check("collapsed state is persisted", (await groups_in_storage(page))[0]["collapsed"] is True)
        await page.h("$$('.rg-header').find(vis).click(); return 1;")
        await asyncio.sleep(0.2)
        check("expanded again", len(await sidebar(page)) == 5)

        print("\n== right-click → Add to new group ==")
        check("no + Group button any more", not await page.h("return !!byText('button', '+ Group');"))
        await right_click(page, "gamma")
        check("menu offers new group, existing groups and delete (rule is loose, so no remove)",
              await menu_items(page) == ["Add to new group", "Add to group", "Delete rule"], str(await menu_items(page)))
        check("right-click also selects the rule",
              await page.h("return document.querySelector('.pm-routing-input').value === 'gamma';"))
        await page.h("byText('.rg-menu-item', 'Add to new group').click(); return 1;")
        await asyncio.sleep(0.3)
        check("the rule is in a fresh group, which sits where the rule was",
              await sidebar(page) == ["G:Staging:2", "  alpha", "  beta", "G:Untitled group:1", "  gamma", "delta"], str(await sidebar(page)))
        # The card is position: fixed, so it has no offsetParent — check its box instead.
        check("naming card is open with the name field focused",
              await page.h("return document.querySelector('.rg-popover')?.getClientRects().length > 0 && document.activeElement === document.querySelector('.rg-name-input');"))
        await page.h("""
          setVal(document.querySelector('.rg-name-input'), 'Errors');
          $$('.rg-swatch')[2].click();
          document.querySelector('.rg-name-input').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
          return 1;""")
        await asyncio.sleep(0.3)
        stored = await groups_in_storage(page)
        check("card closed on Enter", not await page.h("return !!document.querySelector('.rg-popover');"))
        check("name and colour saved", [(g["name"], g["color"]) for g in stored] == [("Staging", "blue"), ("Errors", "red")], str(stored))
        errors_id = stored[1]["id"]
        check("header shows the new name", (await sidebar(page))[3] == "G:Errors:1")
        check("flat list carries the group id in the shown order",
              [(r["label"], r.get("group_id")) for r in await rules_in_storage(page)]
              == [("alpha", 500), ("beta", 500), ("gamma", errors_id), ("delta", None)], str(await rules_in_storage(page)))

        print("\n== right-click → Add to group / Remove from group ==")
        await right_click(page, "delta")
        await page.h("byText('.rg-menu-sub-label', 'Add to group').parentElement.click(); return 1;")
        await asyncio.sleep(0.2)
        check("submenu opens and lists the existing groups",
              await page.h("return document.querySelector('.rg-submenu')?.getClientRects().length > 0;")
              and await page.h("return $$('.rg-submenu .rg-menu-item').filter(e => e.getClientRects().length).map(e => e.textContent.trim());") == ["Staging", "Errors"])
        await page.h("byText('.rg-menu-sub-label', 'Add to group').parentElement.dispatchEvent(new MouseEvent('mouseleave')); return 1;")
        await asyncio.sleep(0.2)
        check("submenu closes when the pointer leaves",
              not await page.h("return document.querySelector('.rg-submenu')?.getClientRects().length > 0;"))
        await page.h("byText('.rg-menu-sub-label', 'Add to group').parentElement.dispatchEvent(new MouseEvent('mouseenter')); return 1;")
        await asyncio.sleep(0.2)
        check("hovering opens it", await page.h("return document.querySelector('.rg-submenu')?.getClientRects().length > 0;"))
        await page.h("$$('.rg-submenu .rg-menu-item').find(e => e.textContent.includes('Staging')).click(); return 1;")
        await asyncio.sleep(0.3)
        check("rule is appended to the chosen group",
              await sidebar(page) == ["G:Staging:3", "  alpha", "  beta", "  delta", "G:Errors:1", "  gamma"], str(await sidebar(page)))
        await right_click(page, "delta")
        check("a grouped rule's menu offers to move it or take it out",
              await menu_items(page) == ["Add to new group", "Move to group", "Remove from “Staging”", "Delete rule"], str(await menu_items(page)))
        await page.h("$$('.rg-menu-item').find(e => e.textContent.includes('Remove from')).click(); return 1;")
        await asyncio.sleep(0.3)
        check("removed rule stays where it was, ungrouped",
              await sidebar(page) == ["G:Staging:2", "  alpha", "  beta", "delta", "G:Errors:1", "  gamma"], str(await sidebar(page)))
        await right_click(page, "delta")
        await page.h("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1;")
        await asyncio.sleep(0.2)
        check("Escape closes the menu but not the window",
              not await page.h("return !!document.querySelector('.rg-menu');") and await page.h("return modalOpen();"))

        print("\n== the editor's group picker ==")
        await page.h("$$('.rg-item').find(e => vis(e) && e.textContent.includes('gamma')).querySelector('.pm-rule-item').click(); return 1;")
        await asyncio.sleep(0.2)
        await page.h("document.querySelector('.rgp-trigger').click(); return 1;")
        await asyncio.sleep(0.2)
        check("the picker is a themed dropdown listing every group with its colour",
              await page.h("return $$('.rgp-option').map(e => e.textContent.trim());") == ["No group", "Staging", "Errors", "New group…"]
              and await page.h("return $$('.rgp-menu .rgp-dot').length === 3;"),
              str(await page.h("return $$('.rgp-option').map(e => e.textContent.trim());")))
        await page.h("document.querySelector('.rgp-overlay').click(); return 1;")
        await asyncio.sleep(0.2)
        check("clicking outside closes it", not await page.h("return !!document.querySelector('.rgp-menu');"))
        await pick_group(page, "No group")
        check("'No group' takes it out; the now-empty group is pinned to the top",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "G:Staging:2", "  alpha", "  beta", "delta", "gamma"], str(await sidebar(page)))
        await pick_group(page, "Errors")
        check("picking a group files the rule under it, where the rule is",
              await sidebar(page) == ["G:Staging:2", "  alpha", "  beta", "delta", "G:Errors:1", "  gamma"], str(await sidebar(page)))
        await pick_group(page, "New group…")
        check("'New group…' makes a group with this rule in it and opens the card",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "G:Staging:2", "  alpha", "  beta", "delta", "G:Untitled group:1", "  gamma"]
              and await page.h("return document.querySelector('.rg-popover')?.getClientRects().length > 0;"), str(await sidebar(page)))
        await page.h("""
          setVal(document.querySelector('.rg-name-input'), 'Temp');
          document.querySelector('.rg-name-input').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
          return 1;""")
        await asyncio.sleep(0.3)
        check("picker shows the group and its colour dot",
              await page.h("return document.querySelector('.rgp-value').textContent.trim() === 'Temp' && !!document.querySelector('.rgp-trigger .rgp-dot:not(.rgp-dot--none)');"))
        await page.h("document.querySelector('.rgp-edit').click(); return 1;")
        await asyncio.sleep(0.3)
        await page.h("byText('.rg-action', 'Ungroup').click(); return 1;")
        await asyncio.sleep(0.3)
        check("ungrouping from the picker's card drops the group",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "G:Staging:2", "  alpha", "  beta", "delta", "gamma"]
              and [g["name"] for g in await groups_in_storage(page)] == ["Staging", "Errors"], str(await sidebar(page)))

        print("\n== the group switch toggles every rule in it ==")
        await page.h("$$('.rg-header').find(e => vis(e) && e.textContent.includes('Staging')).querySelector('.rg-check input').click(); return 1;")
        await asyncio.sleep(0.3)
        rules = await rules_in_storage(page)
        check("all of Staging switched off", [r["active"] for r in rules if r.get("group_id") == 500] == [False, False], str(rules))
        await page.h("$$('.rg-item--grouped').find(e => vis(e) && e.textContent.includes('alpha')).querySelector('.pm-checkbox-container input').click(); return 1;")
        await asyncio.sleep(0.3)
        check("one rule back on shows the group as partly on",
              await page.h("return $$('.rg-header').find(e => vis(e) && e.textContent.includes('Staging')).querySelector('.rg-check input').indeterminate;"))
        await page.h("$$('.rg-header').find(e => vis(e) && e.textContent.includes('Staging')).querySelector('.rg-check input').click(); return 1;")
        await asyncio.sleep(0.3)
        check("partly on → one click switches the whole group on",
              [r["active"] for r in await rules_in_storage(page) if r.get("group_id") == 500] == [True, True])

        print("\n== drag and drop ==")
        # Synthetic drag events go through the same handlers a real drag does.
        await page.h("""
          const rowOf = t => $$('.rg-item').find(e => vis(e) && e.textContent.includes(t));
          const dt = new DataTransfer();
          const fire = (el, type, y) => el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}));
          const src = rowOf('delta'), dst = rowOf('beta');
          const r = dst.getBoundingClientRect();
          fire(src, 'dragstart', 0);
          fire(dst, 'dragover', r.bottom - 2);
          fire(dst, 'drop', r.bottom - 2);
          fire(src, 'dragend', 0);
          return 1;""")
        await asyncio.sleep(0.3)
        check("dropping below the last grouped row joins the group",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "G:Staging:3", "  alpha", "  beta", "  delta", "gamma"], str(await sidebar(page)))
        await page.h("""
          const hdr = $$('.rg-header').find(e => vis(e) && e.textContent.includes('Staging'));
          const dt = new DataTransfer();
          const fire = (el, type, y) => el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}));
          const end = document.querySelector('.rg-end');
          fire(hdr, 'dragstart', 0);
          fire(end, 'dragover', 0);
          fire(end, 'drop', 0);
          fire(hdr, 'dragend', 0);
          return 1;""")
        await asyncio.sleep(0.3)
        check("a group header dragged to the end carries its rules along",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "gamma", "G:Staging:3", "  alpha", "  beta", "  delta"], str(await sidebar(page)))
        await page.h("""
          const rowOf = t => $$('.rg-item').find(e => vis(e) && e.textContent.includes(t));
          const dt = new DataTransfer();
          const fire = (el, type, y) => el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}));
          const src = rowOf('alpha'), dst = rowOf('gamma');
          const r = dst.getBoundingClientRect();
          fire(src, 'dragstart', 0);
          fire(dst, 'dragover', r.top + 2);
          fire(dst, 'drop', r.top + 2);
          fire(src, 'dragend', 0);
          return 1;""")
        await asyncio.sleep(0.3)
        check("dropping above a loose rule leaves the group",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "alpha", "gamma", "G:Staging:2", "  beta", "  delta"], str(await sidebar(page)))
        check("backend sees the new order",
              [r["label"] for r in (await c.call("AGENT_LIST_RULES"))["map_local"]] == ["alpha", "gamma", "beta", "delta"])

        print("\n== an agent's group edits show up live ==")
        res = await c.call("AGENT_EDIT_RULES", {"kind": "map_local", "operations": [
            {"op": "add_group", "group": {"name": "Agent made", "color": "green"}, "rule_ids": [1]},
            {"op": "update_group", "id": 500, "fields": {"name": "Stage"}},
        ]})
        await asyncio.sleep(0.6)
        check("new group and rename are in the sidebar",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "G:Agent made:1", "  alpha", "gamma", "G:Stage:2", "  beta", "  delta"], str(await sidebar(page)))
        stored = await groups_in_storage(page)
        check("groups persisted with collapsed kept for the ones we had",
              [(g["name"], g["collapsed"]) for g in stored] == [("Stage", False), ("Errors", False), ("Agent made", False)], str(stored))

        print("\n== search keeps collapsed groups readable ==")
        await page.h("$$('.rg-header').find(e => vis(e) && e.textContent.includes('Stage')).click(); return 1;")
        await asyncio.sleep(0.2)
        await page.h("setVal(document.querySelector('.pm-search-input'), 'delta'); return 1;")
        await asyncio.sleep(0.3)
        check("only the matching rule, inside its (collapsed) group, is shown",
              await sidebar(page) == ["G:Stage:2", "  delta"], str(await sidebar(page)))
        await page.h("setVal(document.querySelector('.pm-search-input'), ''); return 1;")
        await asyncio.sleep(0.3)
        check("search cleared → collapsed group is collapsed again", "  delta" not in await sidebar(page))

        print("\n== ungroup and delete from the card ==")
        await page.h("$$('.rg-header').find(e => vis(e) && e.textContent.includes('Agent made')).querySelector('.rg-edit').click(); return 1;")
        await asyncio.sleep(0.3)
        await page.h("byText('.rg-action', 'Ungroup').click(); return 1;")
        await asyncio.sleep(0.3)
        check("ungroup keeps the rule, drops the group",
              "alpha" in await sidebar(page) and not any(s.startswith("G:Agent") for s in await sidebar(page)), str(await sidebar(page)))
        await page.h("$$('.rg-header').find(e => vis(e) && e.textContent.includes('Stage')).querySelector('.rg-edit').click(); return 1;")
        await asyncio.sleep(0.3)
        await page.h("$$('.rg-action').find(b => b.textContent.includes('Delete group')).click(); return 1;")
        await asyncio.sleep(0.4)
        check("delete removes the group and its rules",
              await sidebar(page) == ["G:Errors:0", "  (empty)", "alpha", "gamma"], str(await sidebar(page)))
        check("the editor is still on a live rule", await page.h("return vis(document.querySelector('.pm-omnibar'));"))
        listed = await c.call("AGENT_LIST_RULES")
        check("backend matches", [r["label"] for r in listed["map_local"]] == ["alpha", "gamma"]
              and [g["name"] for g in listed["map_local_groups"]] == ["Errors"])
        await right_click(page, "gamma")
        await page.h("byText('.rg-menu-item', 'Delete rule').click(); return 1;")
        await asyncio.sleep(0.3)
        check("Delete rule from the menu removes it", await sidebar(page) == ["G:Errors:0", "  (empty)", "alpha"], str(await sidebar(page)))

        print("\n== import merges rules and groups ==")
        # Drive the file input's handler with an in-memory file: an export of
        # one grouped rule, naming a group we already have by id and a new one.
        await page.h(f"""
          const payload = {{ rules: [{json.dumps(mock(77, "imported", group_id=9001))}, {json.dumps(mock(78, "also", group_id=errors_id))}],
                            groups: [{{ id: 9001, name: 'From file', color: 'cyan' }}, {{ id: {errors_id}, name: 'Errors renamed', color: 'red' }}] }};
          const input = $$('input[type=file]').find(i => i.accept === '.json');
          const file = new File([JSON.stringify(payload)], 'rules.json', {{ type: 'application/json' }});
          const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
          input.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return 1;""")
        await asyncio.sleep(0.6)
        check("imported rules land in their groups; a known group id is updated in place",
              await sidebar(page) == ["alpha", "G:From file:1", "  imported", "G:Errors renamed:1", "  also"], str(await sidebar(page)))

        await page.h("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1;")
        check("no console errors or exceptions", not page.errors, "; ".join(page.errors)[:300])
    finally:
        await restore(page, c, snapshot, tools_before)
        await page.close()
    return report("rule groups")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
