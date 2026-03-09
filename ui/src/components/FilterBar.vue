<script setup>
import { activeChips } from '../store.js'

const protocols = ['All', 'HTTP', 'HTTPS', 'WS']
const types = ['All', 'JSON', 'Form', 'XML', 'JS', 'CSS', 'GraphQL', 'Document', 'Media']
const statuses = ['All', '1xx', '2xx', '3xx', '4xx', '5xx']

const setChip = (category, value) => {
  activeChips.value[category] = value;
}
</script>

<template>
  <div class="filter-bar">
    
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

  </div>
</template>

<style scoped>
/* --- Ultra Compact Bar --- */
.filter-bar {
  display: flex;
  align-items: center;
  padding: 4px 16px;
  background-color: #1e1e1f; /* Slightly darker than toolbar to create depth */
  border-bottom: 1px solid var(--border);
  gap: 12px;
  overflow-x: auto; /* Allows scrolling if window gets too small */
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
  color: #8b949e;
  padding: 2px 8px; /* Extremely compact */
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  outline: none;
}

.chip:hover {
  color: #ccc;
  background: rgba(255, 255, 255, 0.05);
}

/* The Active State (Proxyman Blue) */
.chip.active {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border-color: rgba(59, 130, 246, 0.3);
  font-weight: 600;
}

.divider {
  width: 1px;
  height: 14px;
  background: #333;
  flex-shrink: 0;
}
</style>