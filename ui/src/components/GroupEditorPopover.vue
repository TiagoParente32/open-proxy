<script setup>
/**
 * The small card that names and colours a group — the same one Chrome shows
 * when you create a tab group. Anchored under whatever opened it (a group
 * header, or the editor's group picker) and closed by a click anywhere else.
 */
import { ref, computed, onMounted, nextTick } from 'vue'
import { GROUP_COLORS, groupHex } from '../composables/useRuleGroups'

const props = defineProps({
  group: { type: Object, required: true },
  anchor: { type: Object, default: null },   // DOMRect of the element to hang under
  ctl: { type: Object, required: true },     // useRuleGroups() controller
})
const emit = defineEmits(['close', 'deleted'])

const W = 236
const nameInput = ref(null)

const style = computed(() => {
  const a = props.anchor
  if (!a) return { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
  const left = Math.max(8, Math.min(a.left, window.innerWidth - W - 8))
  const below = a.bottom + 6
  // Flip above the anchor if the card wouldn't fit underneath it.
  const top = below + 190 > window.innerHeight ? Math.max(8, a.top - 196) : below
  return { left: `${left}px`, top: `${top}px` }
})

const count = computed(() => props.ctl.membersOf(props.group.id).length)

onMounted(async () => {
  await nextTick()
  nameInput.value?.focus()
  nameInput.value?.select()
})

const ungroup = () => {
  props.ctl.ungroup(props.group.id)
  emit('close')
}

const deleteGroup = () => {
  const n = count.value
  if (n && !window.confirm(`Delete this group and the ${n} rule${n === 1 ? '' : 's'} in it?`)) return
  const gone = props.ctl.deleteGroup(props.group.id)
  emit('deleted', gone)
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div class="rg-backdrop" @mousedown="emit('close')" @contextmenu.prevent="emit('close')"></div>
    <div class="rg-popover" :style="style" role="dialog" aria-label="Edit group"
         @keydown.esc.stop="emit('close')">
      <input ref="nameInput" v-model="group.name" class="rg-name-input" type="text"
             placeholder="Name this group" maxlength="60"
             @keydown.enter.prevent="emit('close')" />

      <div class="rg-swatches" role="radiogroup" aria-label="Group colour">
        <button v-for="c in GROUP_COLORS" :key="c.id" type="button"
                class="rg-swatch" :class="{ active: (group.color || 'grey') === c.id }"
                :style="{ '--g': c.hex }" :title="c.id" role="radio"
                :aria-checked="(group.color || 'grey') === c.id"
                @click="group.color = c.id"></button>
      </div>

      <div class="rg-actions">
        <button type="button" class="rg-action" @click="ctl.toggleCollapsed(group.id); emit('close')">
          {{ group.collapsed ? 'Expand group' : 'Collapse group' }}
        </button>
        <button type="button" class="rg-action" @click="ungroup">Ungroup</button>
        <button type="button" class="rg-action rg-action--danger" @click="deleteGroup">
          Delete group{{ count ? ` and ${count} rule${count === 1 ? '' : 's'}` : '' }}
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rg-backdrop { position: fixed; inset: 0; z-index: 100000; }
.rg-popover {
  position: fixed; z-index: 100001; width: 236px; box-sizing: border-box;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: var(--shadow-lg); padding: 10px; display: flex; flex-direction: column; gap: 10px;
}
.rg-name-input {
  width: 100%; box-sizing: border-box; background: var(--bg-deepest);
  border: 1px solid var(--border); color: var(--fg-primary); padding: 7px 9px;
  border-radius: 6px; font-size: 12px; outline: none;
}
.rg-name-input:focus { border-color: var(--accent); box-shadow: var(--focus-ring); }

.rg-swatches { display: flex; gap: 6px; justify-content: space-between; padding: 0 2px; }
.rg-swatch {
  width: 18px; height: 18px; border-radius: 50%; border: 2px solid transparent;
  background: var(--g); cursor: pointer; padding: 0; box-sizing: border-box;
  transition: transform 0.1s, box-shadow 0.1s;
}
.rg-swatch:hover { transform: scale(1.12); }
.rg-swatch.active { border-color: var(--bg-card); box-shadow: 0 0 0 2px var(--g); }
.rg-swatch:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--fg-primary); }

.rg-actions { display: flex; flex-direction: column; border-top: 1px solid var(--border-subtle); padding-top: 6px; }
.rg-action {
  text-align: left; background: transparent; border: none; color: var(--fg-secondary);
  font-size: 12px; font-family: inherit; padding: 6px 8px; border-radius: 5px; cursor: pointer;
}
.rg-action:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.rg-action--danger { color: var(--error); }
.rg-action--danger:hover { background: var(--error-muted); color: var(--error); }
</style>
