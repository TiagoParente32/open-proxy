<script setup>
import { activeChips } from '../store.js'

const protocols = ['All', 'HTTP', 'HTTPS', 'WS']
const types = ['All', 'JSON', 'Form', 'XML', 'JS', 'CSS', 'GraphQL', 'Document', 'Media']
const statuses = ['All', '1xx', '2xx', '3xx', '4xx', '5xx']
const colors = ['All', 'red', 'orange', 'yellow', 'green', 'blue', 'purple']

const setChip = (category, value) => {
  activeChips.value[category] = value;
}

</script>

<template>
  <div class="filter-bar">
    <div class="chip-group">
      <button 
        class="chip" :class="{ active: activeChips.starred }"
        @click="activeChips.starred = !activeChips.starred"
        style="color: var(--method-put);"
      >
        {{ activeChips.starred ? '⭐ Starred Only' : '⭐ Starred' }}
      </button>
    </div>

    <div class="divider"></div>
    
    <div class="chip-group">
      <button 
        v-for="p in protocols" :key="p" 
        class="chip" :class="{ active: activeChips.protocol === p }"
        @click="setChip('protocol', p)"
      >
        {{ p }}
      </button>
    </div>

    <div class="divider"></div>

    <div class="chip-group">
      <button 
        v-for="t in types" :key="t" 
        class="chip" :class="{ active: activeChips.type === t }"
        @click="setChip('type', t)"
      >
        {{ t }}
      </button>
    </div>

    <div class="divider"></div>

    <div class="chip-group">
      <button 
        v-for="s in statuses" :key="s" 
        class="chip" :class="{ active: activeChips.status === s }"
        @click="setChip('status', s)"
      >
        {{ s }}
      </button>
    </div>

    <div class="divider"></div>

    <div class="chip-group">
      <button 
        v-for="c in colors" :key="c" 
        class="chip" :class="{ active: activeChips.color === c }"
        @click="setChip('color', c)"
        :title="c === 'All' ? 'All Colors' : c.charAt(0).toUpperCase() + c.slice(1)"
      >
        <span v-if="c === 'All'">All Colors</span>
        <span v-else class="color-indicator" :class="c"></span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* --- Ultra Compact Bar --- */
.filter-bar {
  display: flex;
  align-items: center;
  padding: 4px 16px;
  background-color: var(--bg-main);
  border-bottom: 1px solid var(--border);
  gap: 12px;
  overflow-x: auto;
  user-select: none;
}

/* Hide scrollbar for a cleaner look */
.filter-bar::-webkit-scrollbar { display: none; }

.chip-group {
  display: flex;
  align-items: center;
  gap: 2px; /* Very tight spacing between chips */
}

/* --- The Chips --- */
.chip {
  background: transparent;
  border: 1px solid transparent;
  color: var(--fg-muted);
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  outline: none;
}

.chip:hover {
  color: var(--fg-secondary);
  background: var(--surface-hover);
}

.chip.active {
  background: var(--accent-muted);
  color: var(--accent);
  border-color: var(--accent-border);
  font-weight: 600;
}

.divider {
  width: 1px;
  height: 14px;
  background: var(--border);
  flex-shrink: 0;
}

/* --- Tiny Color Indicators inside the buttons --- */
.color-indicator {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
/* Color-only chips are icon-only, so reduce padding */
.chip:has(.color-indicator) { padding: 2px 6px; }
.color-indicator.red    { background: #ef4444; }
.color-indicator.orange { background: #f97316; }
.color-indicator.yellow { background: #f59e0b; }
.color-indicator.green  { background: #10b981; }
.color-indicator.blue   { background: #3b82f6; }
.color-indicator.purple { background: #8b5cf6; }
</style>