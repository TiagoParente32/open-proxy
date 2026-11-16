<script setup>
/**
 * "Which group is this rule in?" — the editor-side way to group a rule, for
 * people who'd rather pick from a list than drag. "New group…" creates one
 * with this rule already in it and opens the naming card.
 *
 * A custom dropdown rather than a native <select>, like the method picker in
 * the Map Local omnibar, so it takes the app's theme and can show each
 * group's colour. `size="field"` matches the editors' text inputs; the
 * default is the compact row used next to a "GROUP" label.
 */
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { groupHex } from '../composables/useRuleGroups'
import GroupEditorPopover from './GroupEditorPopover.vue'

const props = defineProps({
  rule: { type: Object, required: true },
  ctl: { type: Object, required: true },
  size: { type: String, default: 'compact' },   // 'compact' | 'field'
})

const triggerEl = ref(null)
const menuEl = ref(null)
const open = ref(false)
const menuStyle = ref({})
const editor = ref(null)

const sid = (v) => (v == null ? '' : String(v))
const current = computed(() => props.ctl.findGroup(props.rule.group_id))
const isCurrent = (g) => !!current.value && sid(current.value.id) === sid(g.id)
const label = (g) => g.name || 'Untitled group'

// The menu is position: fixed and hung off the trigger's box, so it isn't
// clipped by a scrolling editor area. Flipped above when it wouldn't fit.
const place = async () => {
  await nextTick()
  const a = triggerEl.value?.getBoundingClientRect()
  if (!a) return
  const h = menuEl.value?.offsetHeight || 0
  const below = a.bottom + 4
  const top = below + h > window.innerHeight - 8 ? Math.max(8, a.top - h - 4) : below
  menuStyle.value = { left: `${a.left}px`, top: `${top}px`, minWidth: `${Math.max(a.width, 160)}px` }
}

const toggle = async () => {
  open.value = !open.value
  if (open.value) await place()
}
const close = () => { open.value = false }

const choose = (groupId) => {
  props.ctl.assign(props.rule.id, groupId)
  close()
}

const newGroup = async () => {
  const anchor = triggerEl.value?.getBoundingClientRect() || null
  close()
  const group = props.ctl.createGroup({ ruleIds: [props.rule.id] })
  await nextTick()
  editor.value = { group, anchor }
}

const editCurrent = () => {
  if (!current.value) return
  editor.value = { group: current.value, anchor: triggerEl.value?.getBoundingClientRect() || null }
}

const onKey = (e) => { if (e.key === 'Escape' && open.value) { e.stopPropagation(); close() } }
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="rgp" :class="`rgp--${size}`">
    <button ref="triggerEl" type="button" class="rgp-trigger" :class="{ open }" title="Group"
            aria-haspopup="listbox" :aria-expanded="open" @click="toggle">
      <span class="rgp-dot" :class="{ 'rgp-dot--none': !current }"
            :style="current ? { background: groupHex(current.color) } : null"></span>
      <span class="rgp-value">{{ current ? label(current) : 'No group' }}</span>
      <svg class="rgp-chevron" viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
        <path d="M7 10l5 5 5-5z" fill="currentColor"/>
      </svg>
    </button>
    <button v-if="current" type="button" class="rgp-edit" title="Rename or recolour this group" @click="editCurrent">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
      </svg>
    </button>
  </div>

  <Teleport to="body">
    <div v-if="open" class="rgp-overlay" @click.stop="close"></div>
    <div v-if="open" ref="menuEl" class="rgp-menu" :style="menuStyle" role="listbox" aria-label="Group">
      <div class="rgp-option" :class="{ selected: !current }" role="option" :aria-selected="!current" @click="choose(null)">
        <span class="rgp-dot rgp-dot--none"></span>No group
      </div>
      <div v-for="g in ctl.groups.value" :key="g.id" class="rgp-option" :class="{ selected: isCurrent(g) }"
           role="option" :aria-selected="isCurrent(g)" @click="choose(g.id)">
        <span class="rgp-dot" :style="{ background: groupHex(g.color) }"></span>{{ label(g) }}
      </div>
      <div class="rgp-sep"></div>
      <div class="rgp-option rgp-option--new" role="option" @click="newGroup">
        <span class="rgp-plus" aria-hidden="true">+</span>New group…
      </div>
    </div>
  </Teleport>

  <GroupEditorPopover v-if="editor" :group="editor.group" :anchor="editor.anchor" :ctl="ctl"
                      @close="editor = null" />
</template>

<style>
/* Unscoped: the menu is teleported to <body>, outside this component's root.
   The z-indices sit above the modal (99999), like the other group popovers. */
.rgp-overlay { position: fixed; inset: 0; z-index: 100000; cursor: default; }
.rgp-menu {
  position: fixed; z-index: 100001; padding: 4px 0; max-height: 280px; overflow-y: auto;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px;
  box-shadow: var(--shadow-lg);
}
.rgp-option {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px; font-size: 12px;
  color: var(--fg-secondary); cursor: pointer; white-space: nowrap; transition: background 0.1s;
}
.rgp-option:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.rgp-option.selected { color: var(--fg-primary); font-weight: 600; }
.rgp-option--new { color: var(--accent); }
.rgp-plus { width: 9px; text-align: center; font-weight: 700; }
.rgp-sep { height: 1px; background: var(--border); margin: 4px 0; }
.rgp-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.rgp-dot--none { background: transparent; border: 1px solid var(--fg-muted); box-sizing: border-box; }
</style>

<style scoped>
.rgp { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.rgp-trigger {
  display: inline-flex; align-items: center; gap: 7px; max-width: 220px;
  background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-secondary);
  padding: 5px 8px; border-radius: 5px; font-size: 11px; cursor: pointer; outline: none;
  transition: border-color 0.2s; text-align: left; font-family: inherit;
}
.rgp-trigger:hover { color: var(--fg-primary); }
.rgp-trigger:focus-visible, .rgp-trigger.open { border-color: var(--accent); }
.rgp-value { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rgp-chevron { flex-shrink: 0; color: var(--fg-muted); }
/* Same box as the editors' .pm-routing-input, so a row of fields lines up. */
.rgp--field .rgp-trigger {
  height: 38px; box-sizing: border-box; padding: 0 12px; border-radius: 6px; font-size: 13px;
  min-width: 160px; color: var(--fg-primary);
}
.rgp-edit {
  display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border-radius: 4px; border: 1px solid transparent; background: transparent; color: var(--fg-muted);
  cursor: pointer; padding: 0;
}
.rgp-edit:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
</style>
