<script setup>
import { ref } from 'vue'
import { isFocusMode, activeFilter, pinnedSources, unpinnedDomains } from '../store.js'

const newPinnedSource = ref('')

const addPinnedSource = (sourceToAdd = null) => {
  const val = (sourceToAdd || newPinnedSource.value).trim()
  if (val && !pinnedSources.value.includes(val)) {
    pinnedSources.value.push(val)
    activeFilter.value = { type: 'pinned', value: val }
    newPinnedSource.value = ''
  }
}

const removePinnedSource = (source, event) => {
  event.stopPropagation()
  pinnedSources.value = pinnedSources.value.filter(s => s !== source)
  if (activeFilter.value.value === source) activeFilter.value = { type: 'all', value: null }
}
</script>

<template>
  <div class="sidebar">
    <div class="focus-mode-wrapper" @click="isFocusMode = !isFocusMode" :class="{ 'focus-on': isFocusMode }">
      <span class="text-icon">🎯</span>
      <span style="flex: 1; font-weight: 600; font-size: 13px; color: white;">Focus Mode</span>
      <div class="toggle-switch" :class="{ 'on': isFocusMode }"></div>
    </div>

    <div class="tree-container">
      <div class="tree-item" :class="{ 'active': activeFilter.type === 'all' }" @click="activeFilter = { type: 'all', value: null }">
        <span class="text-icon">🌐</span> <span class="truncate">All {{ isFocusMode ? 'Pinned ' : '' }}Traffic</span>
      </div>
      
      <div class="sidebar-subheader">📌 Pinned Sources</div>
      <div style="padding: 0 8px; margin-bottom: 8px; display: flex; gap: 4px;">
        <input v-model="newPinnedSource" @keyup.enter="addPinnedSource()" type="text" placeholder="Add domain..." class="filter-input-small" />
        <button class="action-btn" style="padding: 2px 8px; font-weight: bold;" @click="addPinnedSource()">+</button>
      </div>
      
      <div v-for="source in pinnedSources" :key="source" class="tree-item" :class="{ 'active': activeFilter.value === source }" @click="activeFilter = { type: 'pinned', value: source }">
        <span class="text-icon">⚡️</span> <span class="truncate" :title="source">{{ source }}</span>
        <span class="delete-icon" @click="removePinnedSource(source, $event)">×</span>
      </div>

      <div v-if="!isFocusMode">
        <div class="sidebar-subheader" style="margin-top: 16px;">🌍 Other Traffic</div>
        <div v-for="domain in unpinnedDomains" :key="domain" class="tree-item" :class="{ 'active': activeFilter.value === domain }" @click="activeFilter = { type: 'unpinned', value: domain }">
          <span class="text-icon">📄</span> <span class="truncate" :title="domain">{{ domain }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.sidebar { background-color: var(--bg-sidebar); display: flex; flex-direction: column; height: 100%; overflow: hidden; }

/* Focus Mode Toggle */
.focus-mode-wrapper { padding: 12px 16px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.2s; }
.focus-mode-wrapper:hover { background: #2a2d2e; }
.focus-mode-wrapper.focus-on { background: rgba(59, 130, 246, 0.1); border-bottom: 1px solid rgba(59, 130, 246, 0.3); }
.toggle-switch { width: 32px; height: 18px; background: #444; border-radius: 20px; position: relative; transition: background 0.3s; }
.toggle-switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; background: white; border-radius: 50%; transition: transform 0.3s; }
.toggle-switch.on { background: #3b82f6; }
.toggle-switch.on::after { transform: translateX(14px); }

/* Tree & Inputs */
.sidebar-subheader { padding: 4px 16px; margin-top: 12px; margin-bottom: 4px; font-size: 10px; color: #777; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.filter-input-small { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 4px 8px; border-radius: 4px; font-size: 11px; outline: none; transition: border-color 0.2s; }
.filter-input-small:focus { border-color: #3b82f6; }
.delete-icon { margin-left: auto; color: #ef4444; font-weight: bold; font-size: 14px; opacity: 0; transition: opacity 0.2s; }

.tree-container { padding: 0 8px; overflow-y: auto; flex: 1; }
.tree-item { padding: 6px 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; border-radius: 4px; margin-bottom: 2px; font-size: 12px; color: #ccc; transition: background 0.1s; }
.tree-item:hover { background: #2a2d2e; color: #fff; }
.tree-item:hover .delete-icon { opacity: 1; }
.tree-item.active { background: #3b82f6; color: #fff; }
.tree-item.active .text-icon { color: #fff; }
</style>