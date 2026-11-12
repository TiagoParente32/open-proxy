<script setup>
/**
 * The user's rules as a draggable list with Chrome-style groups.
 *
 * Owns the structure — group headers, collapse state, drag and drop between
 * and into groups — and leaves each row's content to the parent through the
 * `row` slot, so Map Local, Map Remote and Breakpoints keep their own row
 * design and editor while sharing one grouping behaviour.
 *
 * Drag targets, in the vocabulary of useRuleGroups.applyDrop:
 *   - top / bottom half of a row        → before / after that rule (joins its group)
 *   - a group header                    → appended to that group; its top edge → above the group
 *   - the strip under the last row      → end of the list, ungrouped
 * A group header can be dragged too, which carries all of its rules along.
 *
 * Groups are made the way browser tab groups are: right-click a rule and
 * choose "Add to new group" — the rule goes in and the naming card opens.
 */
import { ref, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { buildBlocks, groupHex } from '../composables/useRuleGroups'
import GroupEditorPopover from './GroupEditorPopover.vue'

const props = defineProps({
  ctl: { type: Object, required: true },              // useRuleGroups() controller
  selectedId: { default: null },
  filter: { type: Function, default: () => true },    // search predicate
  searching: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'deleted', 'delete-rule'])

const sid = (v) => (v == null ? null : String(v))

const blocks = computed(() =>
  buildBlocks(props.ctl.rules.value, props.ctl.groups.value, {
    filter: props.filter, searching: props.searching,
  })
)

const rowsOf = (b) => (props.searching ? b.visible : b.rules)
const isOpen = (b) => props.searching || !b.group.collapsed

// ---- drag & drop -----------------------------------------------------------

const listEl = ref(null)
const drag = ref(null)    // { type: 'rule' | 'group', id }
const hover = ref(null)   // an applyDrop target

const startDrag = (e, what) => {
  drag.value = what
  e.dataTransfer.effectAllowed = 'move'
  // Chromium needs some payload for the drag to start at all.
  try { e.dataTransfer.setData('text/plain', `${what.type}:${what.id}`) } catch {}
}

const endDrag = () => { drag.value = null; hover.value = null }

const hoverRow = (e, rule) => {
  if (!drag.value) return
  const d = drag.value
  if (d.type === 'rule' && sid(rule.id) === sid(d.id)) { hover.value = null; return }
  if (d.type === 'group' && sid(rule.group_id) === sid(d.id)) { hover.value = null; return }
  const rect = e.currentTarget.getBoundingClientRect()
  const before = e.clientY < rect.top + rect.height / 2
  hover.value = { kind: before ? 'before' : 'after', ruleId: rule.id }
  e.dataTransfer.dropEffect = 'move'
}

const hoverHeader = (e, b) => {
  if (!drag.value) return
  const d = drag.value
  const gid = b.group.id
  if (d.type === 'group' && sid(gid) === sid(d.id)) { hover.value = null; return }
  const rect = e.currentTarget.getBoundingClientRect()
  if (d.type === 'group') {
    const before = e.clientY < rect.top + rect.height / 2
    hover.value = { kind: before ? 'before-group' : 'after-group', groupId: gid }
  } else {
    const above = e.clientY < rect.top + rect.height * 0.25
    hover.value = above ? { kind: 'before-group', groupId: gid } : { kind: 'into', groupId: gid }
  }
  e.dataTransfer.dropEffect = 'move'
}

const hoverEnd = (e) => {
  if (!drag.value) return
  hover.value = { kind: 'end' }
  e.dataTransfer.dropEffect = 'move'
}

const finishDrop = () => {
  if (drag.value && hover.value) props.ctl.drop(drag.value, hover.value)
  endDrag()
}

const rowClass = (rule) => {
  const h = hover.value
  return {
    'rg-dragging': drag.value?.type === 'rule' && sid(drag.value.id) === sid(rule.id),
    'rg-drop-before': h?.kind === 'before' && sid(h.ruleId) === sid(rule.id),
    'rg-drop-after': h?.kind === 'after' && sid(h.ruleId) === sid(rule.id),
  }
}

const headerClass = (b) => {
  const h = hover.value
  const same = h && sid(h.groupId) === sid(b.group.id)
  return {
    'rg-collapsed': !isOpen(b),
    'rg-dragging': drag.value?.type === 'group' && sid(drag.value.id) === sid(b.group.id),
    'rg-drop-into': same && h.kind === 'into',
    'rg-drop-before': same && h.kind === 'before-group',
    'rg-drop-after': same && h.kind === 'after-group',
  }
}

// ---- group editor ----------------------------------------------------------

const editor = ref(null)   // { group, anchor }

const openEditor = (group, el) => {
  editor.value = { group, anchor: el?.getBoundingClientRect?.() || null }
}

const headerEl = (groupId) => listEl.value?.querySelector(`[data-group="${groupId}"]`)

const onDeleted = (ids) => emit('deleted', ids)

// ---- rule context menu -----------------------------------------------------

const MENU_W = 220
const menu = ref(null)   // { rule, x, y, sub }

const SUBMENU_W = 200

const openMenu = (e, rule) => {
  emit('select', rule.id)
  const x = Math.min(e.clientX, window.innerWidth - MENU_W - 8)
  const y = Math.min(e.clientY, window.innerHeight - 200)
  // The submenu hangs off the right edge unless that would run off-screen.
  const subLeft = x + MENU_W + SUBMENU_W + 8 > window.innerWidth
  menu.value = { rule, x, y, sub: false, subLeft }
}
const closeMenu = () => { menu.value = null }

const menuGroup = computed(() => (menu.value ? props.ctl.findGroup(menu.value.rule.group_id) : null))
const otherGroups = computed(() =>
  props.ctl.groups.value.filter(g => sid(g.id) !== sid(menuGroup.value?.id))
)

/** "Add to new group": the rule goes in and the card opens to name it. */
const newGroupWith = async (rule) => {
  closeMenu()
  const group = props.ctl.createGroup({ ruleIds: [rule.id] })
  await nextTick()
  openEditor(group, headerEl(group.id))
}

const addToGroup = (rule, group) => { closeMenu(); props.ctl.assign(rule.id, group.id) }
const removeFromGroup = (rule) => { closeMenu(); props.ctl.assign(rule.id, null) }
const deleteRule = (rule) => { closeMenu(); emit('delete-rule', rule.id) }

// Escape closes the menu without also closing the window behind it.
const onKey = (e) => {
  if (e.key === 'Escape' && menu.value) { e.stopPropagation(); closeMenu() }
}
watch(menu, (m) => {
  if (m) window.addEventListener('keydown', onKey, true)
  else window.removeEventListener('keydown', onKey, true)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <div ref="listEl" class="rg-list" :class="{ 'rg-is-dragging': !!drag }">
    <template v-for="b in blocks" :key="b.type === 'group' ? `g${b.group.id}` : `r${b.rule.id}`">

      <template v-if="b.type === 'group'">
        <div class="rg-header" :class="headerClass(b)" :style="{ '--g': groupHex(b.group.color) }"
             :data-group="b.group.id" draggable="true" :title="b.group.name || 'Untitled group'"
             @dragstart="startDrag($event, { type: 'group', id: b.group.id })" @dragend="endDrag"
             @dragover.prevent="hoverHeader($event, b)" @drop.prevent="finishDrop"
             @click="ctl.toggleCollapsed(b.group.id)"
             @contextmenu.prevent="openEditor(b.group, $event.currentTarget)">
          <svg class="rg-chevron" :class="{ open: isOpen(b) }" width="10" height="10" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 6 15 12 9 18"/>
          </svg>

          <label class="rg-check" :title="ctl.activeState(b.group.id) === 'all' ? 'Switch the whole group off' : 'Switch the whole group on'"
                 @click.stop>
            <input type="checkbox" :checked="ctl.activeState(b.group.id) === 'all'"
                   :indeterminate="ctl.activeState(b.group.id) === 'some'"
                   :disabled="!b.rules.length" @change="ctl.toggleActive(b.group.id)" />
            <span class="rg-checkmark"></span>
          </label>

          <span class="rg-name" :class="{ 'rg-name--untitled': !b.group.name }">
            {{ b.group.name || 'Untitled group' }}
          </span>
          <span class="rg-count" :title="`${b.rules.length} rule${b.rules.length === 1 ? '' : 's'}`">{{ b.rules.length }}</span>

          <button type="button" class="rg-edit" title="Rename, recolour or remove this group"
                  @click.stop="openEditor(b.group, $event.currentTarget.parentElement)">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
            </svg>
          </button>
        </div>

        <template v-if="isOpen(b)">
          <div v-for="rule in rowsOf(b)" :key="rule.id"
               class="rg-item rg-item--grouped" :class="rowClass(rule)" :style="{ '--g': groupHex(b.group.color) }"
               draggable="true"
               @dragstart.stop="startDrag($event, { type: 'rule', id: rule.id })" @dragend="endDrag"
               @dragover.prevent="hoverRow($event, rule)" @drop.prevent.stop="finishDrop"
               @contextmenu.prevent="openMenu($event, rule)">
            <slot name="row" :rule="rule" :group="b.group" />
          </div>
        </template>
      </template>

      <div v-else-if="b.visible" class="rg-item" :class="rowClass(b.rule)" draggable="true"
           @dragstart.stop="startDrag($event, { type: 'rule', id: b.rule.id })" @dragend="endDrag"
           @dragover.prevent="hoverRow($event, b.rule)" @drop.prevent.stop="finishDrop"
           @contextmenu.prevent="openMenu($event, b.rule)">
        <slot name="row" :rule="b.rule" :group="null" />
      </div>
    </template>

    <!-- Landing strip for "take it out of its group and put it last". Only
         tall enough to hit while something is being dragged. -->
    <div class="rg-end" :class="{ 'rg-drop-end': hover?.kind === 'end' }"
         @dragover.prevent="hoverEnd" @drop.prevent="finishDrop">
      <span v-if="drag">Drop here to move to the end{{ ctl.groups.value.length ? ', outside any group' : '' }}</span>
    </div>
  </div>

  <GroupEditorPopover v-if="editor" :group="editor.group" :anchor="editor.anchor" :ctl="ctl"
                      @close="editor = null" @deleted="onDeleted" />

  <!-- Right-click menu on a rule, modelled on a browser's tab menu. -->
  <Teleport to="body">
    <template v-if="menu">
      <div class="rg-menu-backdrop" @mousedown="closeMenu" @contextmenu.prevent="closeMenu"></div>
      <div class="rg-menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" role="menu">
        <button type="button" class="rg-menu-item" role="menuitem" @click="newGroupWith(menu.rule)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add to new group
        </button>

        <div v-if="otherGroups.length" class="rg-menu-item rg-menu-item--sub" role="menuitem" aria-haspopup="true"
             @mouseenter="menu.sub = true" @mouseleave="menu.sub = false" @click="menu.sub = !menu.sub">
          <span class="rg-menu-sub-label">{{ menuGroup ? 'Move to group' : 'Add to group' }}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 6 15 12 9 18"/>
          </svg>
          <div v-show="menu.sub" class="rg-submenu" :class="{ 'rg-submenu--left': menu.subLeft }" role="menu">
            <button v-for="g in otherGroups" :key="g.id" type="button" class="rg-menu-item" role="menuitem"
                    @click.stop="addToGroup(menu.rule, g)">
              <span class="rg-menu-dot" :style="{ background: groupHex(g.color) }"></span>
              <span class="rg-menu-text">{{ g.name || 'Untitled group' }}</span>
            </button>
          </div>
        </div>

        <button v-if="menuGroup" type="button" class="rg-menu-item" role="menuitem" @click="removeFromGroup(menu.rule)">
          <span class="rg-menu-dot" :style="{ background: groupHex(menuGroup.color) }"></span>
          Remove from “{{ menuGroup.name || 'Untitled group' }}”
        </button>

        <div class="rg-menu-sep"></div>
        <button type="button" class="rg-menu-item rg-menu-item--danger" role="menuitem" @click="deleteRule(menu.rule)">
          Delete rule
        </button>
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
.rg-list { display: flex; flex-direction: column; }

/* ---- group header ------------------------------------------------------ */
.rg-header {
  display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px 0 8px;
  box-sizing: border-box; cursor: pointer; user-select: none;
  background: color-mix(in srgb, var(--g) 14%, transparent);
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: inset 3px 0 0 var(--g);
  transition: background 0.12s;
}
.rg-header:hover { background: color-mix(in srgb, var(--g) 22%, transparent); }
.rg-chevron { color: var(--fg-muted); flex-shrink: 0; transition: transform 0.15s; }
.rg-chevron.open { transform: rotate(90deg); }
.rg-name {
  flex: 1; min-width: 0; font-size: 11px; font-weight: 700; color: var(--fg-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; letter-spacing: 0.2px;
}
.rg-name--untitled { font-weight: 500; color: var(--fg-muted); font-style: italic; }
.rg-count {
  font-size: 9px; font-weight: 700; min-width: 16px; height: 16px; padding: 0 5px;
  border-radius: 8px; display: inline-flex; align-items: center; justify-content: center;
  background: var(--g); color: #fff; flex-shrink: 0;
}
.rg-edit {
  display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px;
  border-radius: 4px; border: none; background: transparent; color: var(--fg-muted);
  cursor: pointer; opacity: 0; transition: opacity 0.12s, background 0.12s; flex-shrink: 0; padding: 0;
}
.rg-header:hover .rg-edit, .rg-edit:focus-visible { opacity: 1; }
.rg-edit:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

/* Group on/off switch, in the same style as the rows' own checkbox. */
.rg-check { position: relative; width: 14px; height: 14px; flex-shrink: 0; cursor: pointer; display: block; }
.rg-check input { position: absolute; opacity: 0; width: 0; height: 0; }
.rg-checkmark {
  position: absolute; inset: 0; border-radius: 3px; box-sizing: border-box;
  background: var(--bg-deepest); border: 1px solid var(--fg-muted);
  transition: border-color 0.2s, background-color 0.2s;
}
.rg-check:hover input:not(:disabled) ~ .rg-checkmark { border-color: var(--g); }
.rg-check input:checked ~ .rg-checkmark,
.rg-check input:indeterminate ~ .rg-checkmark { background: var(--g); border-color: var(--g); }
.rg-checkmark::after { content: ''; position: absolute; display: none; }
.rg-check input:checked ~ .rg-checkmark::after {
  display: block; left: 50%; top: 45%; width: 3px; height: 7px;
  border: solid #fff; border-width: 0 2px 2px 0; transform: translate(-50%, -50%) rotate(45deg);
}
.rg-check input:indeterminate ~ .rg-checkmark::after {
  display: block; left: 3px; right: 3px; top: 50%; height: 2px; background: #fff; transform: translateY(-50%);
}
.rg-check input:disabled ~ .rg-checkmark { opacity: 0.4; }

/* ---- rows --------------------------------------------------------------- */
.rg-item { position: relative; }
.rg-item--grouped {
  padding-left: 10px; box-shadow: inset 3px 0 0 var(--g);
  background: color-mix(in srgb, var(--g) 6%, transparent);
}

/* ---- drag feedback ------------------------------------------------------ */
.rg-dragging { opacity: 0.35; }
.rg-is-dragging .rg-item > * { pointer-events: none; }   /* rows are targets, not their buttons */
.rg-drop-before { box-shadow: inset 0 2px 0 var(--accent) !important; }
.rg-drop-after  { box-shadow: inset 0 -2px 0 var(--accent) !important; }
.rg-item--grouped.rg-drop-before { box-shadow: inset 3px 0 0 var(--g), inset 0 2px 0 var(--accent) !important; }
.rg-item--grouped.rg-drop-after  { box-shadow: inset 3px 0 0 var(--g), inset 0 -2px 0 var(--accent) !important; }
.rg-header.rg-drop-before { box-shadow: inset 3px 0 0 var(--g), inset 0 2px 0 var(--accent); }
.rg-header.rg-drop-after  { box-shadow: inset 3px 0 0 var(--g), inset 0 -2px 0 var(--accent); }
.rg-header.rg-drop-into   { outline: 2px dashed var(--g); outline-offset: -3px; background: color-mix(in srgb, var(--g) 28%, transparent); }

.rg-end {
  min-height: 6px; display: flex; align-items: center; justify-content: center;
  font-size: 10px; color: var(--fg-muted); transition: min-height 0.12s;
}
.rg-is-dragging .rg-end { min-height: 34px; border: 1px dashed var(--border); margin: 6px 10px; border-radius: 6px; }
.rg-end.rg-drop-end { border-color: var(--accent); color: var(--accent); background: var(--accent-muted); }

/* ---- context menu ------------------------------------------------------- */
.rg-menu-backdrop { position: fixed; inset: 0; z-index: 100000; }
.rg-menu {
  position: fixed; z-index: 100001; width: 220px; box-sizing: border-box; padding: 4px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: var(--shadow-lg); display: flex; flex-direction: column;
}
.rg-menu-item {
  position: relative; display: flex; align-items: center; gap: 8px; width: 100%;
  text-align: left; background: transparent; border: none; color: var(--fg-secondary);
  font-size: 12px; font-family: inherit; padding: 7px 10px; border-radius: 5px; cursor: pointer;
  box-sizing: border-box; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rg-menu-item:hover, .rg-menu-item--sub:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.rg-menu-item--danger { color: var(--error); }
.rg-menu-item--danger:hover { background: var(--error-muted); color: var(--error); }
/* The flyout is positioned off this row, so the row must not clip it. */
.rg-menu-item--sub { user-select: none; overflow: visible; }
.rg-menu-sub-label { flex: 1; }
.rg-menu-sep { height: 1px; background: var(--border-subtle); margin: 4px 6px; }
.rg-menu-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.rg-menu-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.rg-submenu {
  position: absolute; left: calc(100% - 4px); top: -5px; width: 200px; padding: 4px; z-index: 1;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: var(--shadow-lg); display: flex; flex-direction: column; max-height: 260px; overflow-y: auto;
}
.rg-submenu--left { left: auto; right: calc(100% - 4px); }
</style>
