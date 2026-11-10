/**
 * Chrome-style groups for the rule lists (Map Local, Map Remote, Breakpoints).
 *
 * A group is `{ id, name, color, collapsed }` and lives in its own list; a rule
 * joins one by carrying `group_id`. The flat rule list stays the single source
 * of truth for match order — the backend never sees a group, only rules in
 * order — so grouping is a view over that list with one invariant: a group's
 * rules sit next to each other, like grouped tabs do. Every operation here
 * re-establishes that invariant (`normalizeRules`) so what the sidebar shows is
 * exactly the order the proxy matches in.
 *
 * The palette and the group-op semantics are mirrored in
 * server/bridge/agent_api.py so an MCP agent can work with the same groups.
 */

export const GROUP_COLORS = [
  { id: 'grey',   hex: '#8b949e' },
  { id: 'blue',   hex: '#3b82f6' },
  { id: 'red',    hex: '#ef4444' },
  { id: 'yellow', hex: '#eab308' },
  { id: 'green',  hex: '#10b981' },
  { id: 'pink',   hex: '#ec4899' },
  { id: 'purple', hex: '#a855f7' },
  { id: 'cyan',   hex: '#06b6d4' },
  { id: 'orange', hex: '#f97316' },
]

export const groupHex = (color) =>
  (GROUP_COLORS.find(c => c.id === color) || GROUP_COLORS[0]).hex

const sid = (v) => (v == null ? null : String(v))

const groupIndex = (groups) => new Map(groups.map(g => [sid(g.id), g]))

/** The group a rule belongs to, or null if it has none or it no longer exists. */
const groupOf = (rule, byId) =>
  rule.group_id != null ? (byId.get(sid(rule.group_id)) || null) : null

/**
 * The sidebar's display order: a list of blocks, each either
 *   { type: 'rule', rule, visible }                      — an ungrouped rule
 *   { type: 'group', group, rules, visible }             — a group with its rules
 *
 * Groups appear where their first rule does. Empty groups have nothing to
 * anchor them, so they sit at the top until something is dragged in. With
 * `searching`, hidden rules and groups with no match are dropped and
 * collapsed groups are shown open — a search that hides its own hits is no
 * search at all.
 */
export function buildBlocks(rules, groups, { filter = () => true, searching = false } = {}) {
  const byId = groupIndex(groups)
  const blocks = []
  const open = new Map()

  const used = new Set(rules.map(r => sid(r.group_id)))
  for (const g of groups) {
    if (used.has(sid(g.id))) continue
    const b = { type: 'group', group: g, rules: [], visible: [] }
    blocks.push(b)
    open.set(sid(g.id), b)
  }

  for (const r of rules) {
    const g = groupOf(r, byId)
    if (!g) {
      blocks.push({ type: 'rule', rule: r, visible: filter(r) })
      continue
    }
    let b = open.get(sid(g.id))
    if (!b) {
      b = { type: 'group', group: g, rules: [], visible: [] }
      open.set(sid(g.id), b)
      blocks.push(b)
    }
    b.rules.push(r)
    if (filter(r)) b.visible.push(r)
  }

  if (searching) return blocks.filter(b => (b.type === 'rule' ? b.visible : b.visible.length > 0))
  return blocks
}

/**
 * The flat list reordered so it matches `buildBlocks` — every group's rules
 * contiguous — with references to deleted groups dropped. Mutates `group_id`
 * on the rules it cleans; returns a new array.
 */
export function normalizeRules(rules, groups) {
  const byId = groupIndex(groups)
  const out = []
  for (const b of buildBlocks(rules, groups)) {
    if (b.type === 'rule') out.push(b.rule)
    else out.push(...b.rules)
  }
  for (const r of out) {
    if (r.group_id != null && !byId.has(sid(r.group_id))) delete r.group_id
  }
  return out
}

/**
 * Where a drag ended. `drag` is { type: 'rule' | 'group', id }; `target` one of
 *   { kind: 'before' | 'after', ruleId }        — relative to a visible row
 *   { kind: 'into', groupId }                   — appended to a group
 *   { kind: 'before-group' | 'after-group', groupId }
 *   { kind: 'end' }                             — bottom of the list, ungrouped
 *
 * Dropping next to a grouped row joins that group; dropping a whole group
 * never lands inside another one — it snaps to that group's edge instead.
 * Returns the new flat list, or null when the drop changes nothing.
 */
export function applyDrop(rules, groups, drag, target) {
  if (!drag || !target) return null
  const byId = groupIndex(groups)
  const list = normalizeRules(rules, groups)

  const moving = drag.type === 'rule'
    ? list.filter(r => sid(r.id) === sid(drag.id))
    : list.filter(r => sid(r.group_id) === sid(drag.id))
  if (!moving.length) return null
  const movingSet = new Set(moving)
  const rest = list.filter(r => !movingSet.has(r))

  const members = (gid) =>
    rest.map((r, i) => (sid(groupOf(r, byId)?.id) === sid(gid) ? i : -1)).filter(i => i >= 0)

  let index
  let group = null
  switch (target.kind) {
    case 'end':
      index = rest.length
      break
    case 'into': {
      group = byId.get(sid(target.groupId)) || null
      const m = members(target.groupId)
      index = m.length ? m[m.length - 1] + 1 : 0
      break
    }
    case 'before-group':
    case 'after-group': {
      const m = members(target.groupId)
      if (!m.length) index = 0
      else index = target.kind === 'before-group' ? m[0] : m[m.length - 1] + 1
      break
    }
    case 'before':
    case 'after': {
      const i = rest.findIndex(r => sid(r.id) === sid(target.ruleId))
      if (i < 0) return null
      group = groupOf(rest[i], byId)
      index = target.kind === 'before' ? i : i + 1
      break
    }
    default:
      return null
  }

  if (drag.type === 'group') {
    // A group block keeps its own membership and can't be nested.
    if (group) {
      const m = members(group.id)
      index = target.kind === 'before' ? m[0] : m[m.length - 1] + 1
    }
  } else if (group) {
    moving[0].group_id = group.id
  } else {
    delete moving[0].group_id
  }

  rest.splice(index, 0, ...moving)
  return rest
}

/**
 * Bind the helpers above to a rules ref and a groups ref. Every method writes
 * straight to the refs, so the store's watchers persist and sync the result
 * the same way a hand edit in the editor would.
 */
export function useRuleGroups(rulesRef, groupsRef) {
  const rules = () => rulesRef.value
  const groups = () => groupsRef.value

  const findGroup = (id) => groups().find(g => sid(g.id) === sid(id)) || null
  const membersOf = (id) => rules().filter(r => sid(r.group_id) === sid(id))

  const nextColor = () => {
    const used = new Set(groups().map(g => g.color))
    const free = GROUP_COLORS.find(c => !used.has(c.id))
    return (free || GROUP_COLORS[groups().length % GROUP_COLORS.length]).id
  }

  /** Create a group, optionally with some rules already in it. Returns the reactive group. */
  const createGroup = ({ name = '', color = null, ruleIds = [] } = {}) => {
    const group = { id: Date.now(), name, color: color || nextColor(), collapsed: false }
    groupsRef.value = [...groups(), group]
    if (ruleIds.length) {
      const wanted = new Set(ruleIds.map(sid))
      for (const r of rules()) if (wanted.has(sid(r.id))) r.group_id = group.id
      rulesRef.value = normalizeRules(rules(), groups())
    }
    return findGroup(group.id)
  }

  /** Put one rule in a group (or none, with null), keeping the list contiguous. */
  const assign = (ruleId, groupId) => {
    const rule = rules().find(r => sid(r.id) === sid(ruleId))
    if (!rule) return
    const group = groupId != null ? findGroup(groupId) : null
    if (group) rule.group_id = group.id
    else delete rule.group_id
    rulesRef.value = normalizeRules(rules(), groups())
  }

  const drop = (drag, target) => {
    const next = applyDrop(rules(), groups(), drag, target)
    if (next) rulesRef.value = next
    return !!next
  }

  /** Dissolve a group; its rules stay where they are, just ungrouped. */
  const ungroup = (groupId) => {
    for (const r of membersOf(groupId)) delete r.group_id
    groupsRef.value = groups().filter(g => sid(g.id) !== sid(groupId))
  }

  /** Delete a group and every rule in it. Returns the ids of the rules removed. */
  const deleteGroup = (groupId) => {
    const gone = membersOf(groupId).map(r => r.id)
    const goneSet = new Set(gone.map(sid))
    rulesRef.value = rules().filter(r => !goneSet.has(sid(r.id)))
    groupsRef.value = groups().filter(g => sid(g.id) !== sid(groupId))
    return gone
  }

  /** 'all' | 'some' | 'none' of the group's rules are switched on. */
  const activeState = (groupId) => {
    const m = membersOf(groupId)
    const on = m.filter(r => r.active !== false).length
    return on === 0 ? 'none' : on === m.length ? 'all' : 'some'
  }

  /** One click switches the whole group on, unless it's already all on. */
  const toggleActive = (groupId) => {
    const on = activeState(groupId) !== 'all'
    for (const r of membersOf(groupId)) r.active = on
  }

  const toggleCollapsed = (groupId) => {
    const g = findGroup(groupId)
    if (g) g.collapsed = !g.collapsed
  }

  return {
    rules: rulesRef, groups: groupsRef,
    findGroup, membersOf, createGroup, assign, drop, ungroup, deleteGroup,
    activeState, toggleActive, toggleCollapsed,
  }
}
