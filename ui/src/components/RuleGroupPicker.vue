<script setup>
/**
 * "Which group is this rule in?" — the editor-side way to group a rule, for
 * people who'd rather pick from a list than drag. "New group…" creates one
 * with this rule already in it and opens the naming card.
 */
import { ref, computed, nextTick } from 'vue'
import { groupHex } from '../composables/useRuleGroups'
import GroupEditorPopover from './GroupEditorPopover.vue'

const props = defineProps({
  rule: { type: Object, required: true },
  ctl: { type: Object, required: true },
})

const selectEl = ref(null)
const editor = ref(null)

const sid = (v) => (v == null ? '' : String(v))
const current = computed(() => props.ctl.findGroup(props.rule.group_id))
const value = computed(() => (current.value ? sid(current.value.id) : ''))

const onChange = async (e) => {
  const v = e.target.value
  if (v === '__new') {
    const group = props.ctl.createGroup({ ruleIds: [props.rule.id] })
    await nextTick()
    editor.value = { group, anchor: selectEl.value?.getBoundingClientRect() || null }
    return
  }
  props.ctl.assign(props.rule.id, v === '' ? null : v)
}

const editCurrent = () => {
  if (!current.value) return
  editor.value = { group: current.value, anchor: selectEl.value?.getBoundingClientRect() || null }
}
</script>

<template>
  <div class="rgp">
    <span v-if="current" class="rgp-dot" :style="{ background: groupHex(current.color) }"></span>
    <select ref="selectEl" class="rgp-select" :value="value" @change="onChange" title="Group">
      <option value="">No group</option>
      <option v-for="g in ctl.groups.value" :key="g.id" :value="sid(g.id)">{{ g.name || 'Untitled group' }}</option>
      <option value="__new">New group…</option>
    </select>
    <button v-if="current" type="button" class="rgp-edit" title="Rename or recolour this group" @click="editCurrent">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
      </svg>
    </button>
  </div>

  <GroupEditorPopover v-if="editor" :group="editor.group" :anchor="editor.anchor" :ctl="ctl"
                      @close="editor = null" />
</template>

<style scoped>
.rgp { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.rgp-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.rgp-select {
  background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-secondary);
  padding: 5px 8px; border-radius: 5px; font-size: 11px; outline: none; max-width: 180px;
  cursor: pointer;
}
.rgp-select:focus { border-color: var(--accent); }
.rgp-edit {
  display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border-radius: 4px; border: 1px solid transparent; background: transparent; color: var(--fg-muted);
  cursor: pointer; padding: 0;
}
.rgp-edit:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
</style>
