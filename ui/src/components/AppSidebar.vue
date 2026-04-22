<script setup>
import { ref } from 'vue'
import { isFocusMode, activeFilter, deviceTrafficTree, pinnedSources } from '../store.js'

// --- FOLDER LOGIC ---
const expandedFolders = ref(new Set())

const toggleFolder = (ip) => {
  if (expandedFolders.value.has(ip)) {
    expandedFolders.value.delete(ip)
  } else {
    expandedFolders.value.add(ip)
  }
}

const selectDevice = (ip) => {
  activeFilter.value = { type: 'device', ip: ip }
}

const selectDomain = (ip, domain) => {
  activeFilter.value = { type: 'device_domain', ip: ip, domain: domain }
}

// --- PINNED LOGIC ---
const newPinnedSource = ref('')

const addPinnedSource = (sourceToAdd = null) => {
  const val = (sourceToAdd || newPinnedSource.value).trim()
  if (val && !pinnedSources.value.includes(val)) {
    pinnedSources.value.push(val)
    activeFilter.value = { type: 'pinned', domain: val }
    newPinnedSource.value = ''
  }
}

const removePinnedSource = (source, event) => {
  event.stopPropagation()
  pinnedSources.value = pinnedSources.value.filter(s => s !== source)
  if (activeFilter.value.type === 'pinned' && activeFilter.value.domain === source) {
    activeFilter.value = { type: 'all' }
  }
}
</script>

<template>
  <div class="sidebar">
    <div class="focus-mode-wrapper" @click="isFocusMode = !isFocusMode" :class="{ 'focus-on': isFocusMode }">
      <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3"></circle>
      </svg>
      <span class="focus-label">Focus Mode</span>
      <div class="toggle-switch" :class="{ 'on': isFocusMode }"></div>
    </div>

    <div class="tree-container">
      
      <div class="tree-item main-item" :class="{ 'active': activeFilter.type === 'all' }" @click="activeFilter = { type: 'all' }">
        <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
        </svg>
        <span class="truncate">All {{ isFocusMode ? 'Pinned ' : '' }}Traffic</span>
      </div>

      <div class="sidebar-subheader">Pinned Sources</div>
      
      <div class="pin-input-group">
        <input v-model="newPinnedSource" @keyup.enter="addPinnedSource()" type="text" placeholder="Add domain..." class="filter-input-small" />
        <button class="action-btn" @click="addPinnedSource()">
          <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
        </button>
      </div>
      
      <div v-for="source in pinnedSources" :key="source" 
           class="tree-item pin-item" 
           :class="{ 'active': activeFilter.type === 'pinned' && activeFilter.domain === source }" 
           @click="activeFilter = { type: 'pinned', domain: source }">
        <svg class="ui-icon outline-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle>
        </svg>
        <span class="truncate" :title="source">{{ source }}</span>
        <span class="delete-icon" @click="removePinnedSource(source, $event)">
          <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </span>
      </div>

      <div class="sidebar-subheader">Connected Devices</div>
      
      <div v-if="deviceTrafficTree.length === 0" class="empty-state">
        No devices connected yet
      </div>

      <div v-for="node in deviceTrafficTree" :key="node.ip" class="folder-group">
        <div class="tree-item folder-header" 
             @click="toggleFolder(node.ip); selectDevice(node.ip)"
             :class="{ 'active': activeFilter.type === 'device' && activeFilter.ip === node.ip }">
          <svg class="chevron-icon" :class="{ 'rotated': expandedFolders.has(node.ip) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
          <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line>
          </svg>
          <span class="truncate folder-label">{{ node.label }}</span>
        </div>

        <div v-show="expandedFolders.has(node.ip)" class="folder-contents">
          <div v-for="domain in node.domains" :key="domain" 
               class="tree-item sub-item"
               @click="selectDomain(node.ip, domain)"
               :class="{ 'active': activeFilter.type === 'device_domain' && activeFilter.ip === node.ip && activeFilter.domain === domain }">
            <div class="tree-line"></div>
            <svg class="ui-icon child-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline>
            </svg>
            <span class="truncate">{{ domain }}</span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.sidebar { 
  background-color: var(--bg-sidebar); 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  overflow: hidden; 
  text-align: left;
  user-select: none;
}

/* Global SVG Styling */
.ui-icon { width: 14px; height: 14px; min-width: 14px; opacity: 0.8; }
.outline-icon { opacity: 0.5; }
.chevron-icon { width: 12px; height: 12px; min-width: 12px; opacity: 0.5; transition: transform 0.2s ease; }
.chevron-icon.rotated { transform: rotate(90deg); }

/* Focus Mode */
.focus-mode-wrapper { 
  padding: 14px 16px; 
  display: flex; 
  align-items: center; 
  gap: 10px; 
  border-bottom: 1px solid var(--border); 
  cursor: pointer; 
  transition: all 0.2s; 
}
.focus-mode-wrapper:hover { background: rgba(255, 255, 255, 0.03); }
.focus-mode-wrapper.focus-on { background: rgba(59, 130, 246, 0.1); border-bottom-color: rgba(59, 130, 246, 0.3); }
.focus-mode-wrapper.focus-on .ui-icon { color: #3b82f6; opacity: 1; }

.focus-label { flex: 1; font-weight: 600; font-size: 13px; color: #eee; }

.toggle-switch { width: 32px; height: 18px; background: #333; border-radius: 20px; position: relative; transition: background 0.3s; margin-left: auto; border: 1px solid #444; }
.toggle-switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle-switch.on { background: #3b82f6; border-color: #3b82f6; }
.toggle-switch.on::after { transform: translateX(14px); background: #fff; }

/* Subheaders */
.sidebar-subheader { 
  padding: 0 16px; 
  margin-top: 24px; 
  margin-bottom: 8px; 
  font-size: 11px; 
  color: #666; 
  font-weight: 600; 
  letter-spacing: 0.5px; 
}

.empty-state { padding: 0 16px; font-size: 12px; color: #555; font-style: italic; }

/* Tree Layout */
.tree-container { padding: 8px; overflow-y: auto; flex: 1; }

.tree-item { 
  padding: 6px 8px; 
  cursor: pointer; 
  display: flex; 
  align-items: center; 
  gap: 8px; 
  border-radius: 6px; 
  margin-bottom: 2px; 
  font-size: 12.5px; 
  color: #bbb; 
  transition: all 0.1s; 
}
.tree-item:hover { background: rgba(255, 255, 255, 0.05); color: #fff; }
.tree-item.active { background: #3b82f6; color: #fff; font-weight: 500; }
.tree-item.active .ui-icon, .tree-item.active .chevron-icon { opacity: 1; }

.main-item { margin-bottom: 8px; font-weight: 500; color: #ddd; }

/* Pin Input & Items */
.pin-input-group { padding: 0 8px; margin-bottom: 8px; display: flex; gap: 6px; }
.filter-input-small { 
  flex: 1; background: rgba(0, 0, 0, 0.2); border: 1px solid #333; color: #eee; 
  padding: 6px 8px; border-radius: 4px; font-size: 11px; outline: none; transition: border-color 0.2s; 
}
.filter-input-small:focus { border-color: #3b82f6; }

.action-btn { 
  background: rgba(255, 255, 255, 0.05); border: 1px solid #333; color: #aaa; 
  border-radius: 4px; padding: 0 8px; cursor: pointer; transition: all 0.2s; 
  display: flex; align-items: center; justify-content: center;
}
.action-btn:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }

.delete-icon { margin-left: auto; color: #ef4444; opacity: 0; transition: opacity 0.2s; display: flex; align-items: center; padding: 2px; border-radius: 4px; }
.delete-icon:hover { background: rgba(239, 68, 68, 0.2); }
.tree-item:hover .delete-icon { opacity: 1; }

/* Folders (IDE Style) */
.folder-group { margin-bottom: 4px; }
.folder-header { gap: 6px; }
.folder-label { font-weight: 500; color: #ddd; }

.folder-contents { display: flex; flex-direction: column; position: relative; margin-left: 14px; padding-left: 10px; }
.tree-line {
  position: absolute; left: 0; top: 0; bottom: 8px; width: 1px;
  background: #333; /* The vertical line connecting children */
}

.sub-item { position: relative; font-size: 12px; color: #999; }
.child-icon { opacity: 0.4; width: 12px; height: 12px; }
</style>