<script setup>
import { ref, computed, nextTick } from 'vue'
import { isFocusMode, activeFilter, deviceTrafficTree, pinnedSources, proxyIgnoreHosts, proxyAllowHosts, proxyHostFilterMode, showIgnoreHostsModal, pinSource, unpinSource, isPinnedSource, deviceNicknames, addDeviceHighlightRule } from '../store.js'

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
  isFocusMode.value = false
  activeFilter.value = { type: 'device', ip: ip }
}

const selectDomain = (ip, domain) => {
  isFocusMode.value = false
  activeFilter.value = { type: 'device_domain', ip: ip, domain: domain }
}

// --- DEVICE CONTEXT MENU ---
const deviceMenu = ref({ show: false, x: 0, y: 0, ip: null, label: null })

const openDeviceMenu = (e, node) => {
  e.preventDefault()
  e.stopPropagation()
  deviceMenu.value = { show: true, x: e.clientX, y: e.clientY, ip: node.ip, label: node.label }
}

const closeDeviceMenu = () => { deviceMenu.value.show = false }

const renameDevice = () => {
  const ip = deviceMenu.value.ip
  closeDeviceMenu()
  editingIp.value = ip
  editingValue.value = deviceNicknames.value[ip] || ''
  nextTick(() => renameInput.value?.[0]?.focus())
}

const highlightDevice = () => {
  const { ip, label } = deviceMenu.value
  closeDeviceMenu()
  addDeviceHighlightRule(ip, label)
}

// --- INLINE RENAME ---
const editingIp = ref(null)
const editingValue = ref('')
const renameInput = ref(null)

const commitRename = (ip) => {
  const val = editingValue.value.trim()
  if (val) {
    deviceNicknames.value = { ...deviceNicknames.value, [ip]: val }
  } else {
    const n = { ...deviceNicknames.value }
    delete n[ip]
    deviceNicknames.value = n
  }
  editingIp.value = null
}

// Host filter display
const hostFilterLabel = computed(() => {
  if (proxyHostFilterMode.value === 'allow') {
    const count = proxyAllowHosts.value.length
    return count ? `Intercept ${count} host${count !== 1 ? 's' : ''}` : 'No hosts (nothing intercepted)'
  }
  const count = proxyIgnoreHosts.value.length
  return count ? `Ignoring ${count} host${count !== 1 ? 's' : ''}` : 'All traffic'
})

// --- PINNED LOGIC ---
const newPinnedSource = ref('')

const addPinnedSource = (sourceToAdd = null) => {
  const val = (sourceToAdd || newPinnedSource.value).trim()
  if (val) {
    pinSource(val)
    newPinnedSource.value = ''
  }
}

const removePinnedSource = (source, event) => {
  event.stopPropagation()
  unpinSource(source)
}

const togglePinnedDomain = (domain, event) => {
  event.stopPropagation()
  if (isPinnedSource(domain)) {
    unpinSource(domain)
    return
  }
  pinSource(domain)
}
</script>

<template>
  <div class="sidebar">
    <div class="focus-mode-wrapper" @click="isFocusMode = !isFocusMode; if (isFocusMode) activeFilter = { type: 'all' }" :class="{ 'focus-on': isFocusMode }">
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
           @click="isFocusMode = false; activeFilter = { type: 'pinned', domain: source }">
        <svg class="pin-icon" viewBox="0 0 24 24" style="width:16px;height:16px;min-width:16px;opacity:1" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="9" r="5.5"/>
          <line x1="12" y1="14.5" x2="12" y2="21" stroke-width="2.5"/>
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
             @contextmenu="openDeviceMenu($event, node)"
             :class="{ 'active': activeFilter.type === 'device' && activeFilter.ip === node.ip }">
          <svg class="chevron-icon" :class="{ 'rotated': expandedFolders.has(node.ip) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
          <!-- Local System (Mac/laptop) -->
          <svg v-if="node.type === 'local'" class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="4" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="18" x2="12" y2="21"/>
          </svg>
          <!-- VPN device -->
          <svg v-else-if="node.type === 'vpn'" class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <!-- Wi-Fi / physical device -->
          <svg v-else class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01"/>
          </svg>
          <input
            v-if="editingIp === node.ip"
            ref="renameInput"
            v-model="editingValue"
            class="rename-input"
            @blur="commitRename(node.ip)"
            @keyup.enter="commitRename(node.ip)"
            @keyup.escape="editingIp = null"
            @click.stop
          />
          <span v-else class="truncate folder-label">{{ node.label }}</span>
          <span v-if="node.label !== node.ip && editingIp !== node.ip" class="device-ip-badge">{{ node.ip }}</span>
        </div>

        <div v-show="expandedFolders.has(node.ip)" class="folder-contents">
          <div v-for="domain in node.domains" :key="domain" 
               class="tree-item sub-item"
               @click="selectDomain(node.ip, domain)"
               :class="{ 'active': activeFilter.type === 'device_domain' && activeFilter.ip === node.ip && activeFilter.domain === domain }">
            <svg class="child-icon" viewBox="0 0 24 24" style="width:16px;height:16px;min-width:16px;opacity:0.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline>
            </svg>
            <span class="truncate">{{ domain }}</span>
            <button
              class="pin-toggle"
              :class="{ pinned: isPinnedSource(domain) }"
              :title="isPinnedSource(domain) ? 'Unpin endpoint' : 'Pin endpoint'"
              @click="togglePinnedDomain(domain, $event)"
            >
              <svg viewBox="0 0 24 24" style="width:16px;height:16px;flex-shrink:0"
                fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="9" r="5.5"/>
                <line x1="12" y1="14.5" x2="12" y2="21" stroke-width="2.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

    </div>

    <!-- Host Filter footer -->
    <div class="host-filter-section">
      <div class="host-filter-row">
        <span class="host-filter-label">Host Filter</span>
        <button class="host-filter-edit" @click="showIgnoreHostsModal = true" title="Edit host filter">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Edit
        </button>
      </div>
      <div class="host-filter-status" @click="showIgnoreHostsModal = true">
        <span class="host-filter-dot" :class="proxyHostFilterMode === 'allow' ? 'dot-allow' : (proxyIgnoreHosts.length ? 'dot-ignore' : 'dot-all')"></span>
        <span class="host-filter-desc">{{ hostFilterLabel }}</span>
      </div>
    </div>

  </div>

  <!-- Device context menu -->
  <Teleport to="body">
    <div v-if="deviceMenu.show" class="device-ctx-overlay" @mousedown="closeDeviceMenu">
      <div class="device-ctx-menu" :style="{ top: deviceMenu.y + 'px', left: deviceMenu.x + 'px' }" @mousedown.stop>
        <button class="ctx-item" @click="renameDevice">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Rename device
        </button>
        <button class="ctx-item" @click="highlightDevice">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M8 12l2 2 4-4"/>
          </svg>
          Highlight traffic
        </button>
      </div>
    </div>
  </Teleport>
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
.focus-mode-wrapper:hover { background: var(--surface-hover); }
.focus-mode-wrapper.focus-on { background: rgba(59, 130, 246, 0.1); border-bottom-color: rgba(59, 130, 246, 0.3); }
.focus-mode-wrapper.focus-on .ui-icon { color: #3b82f6; opacity: 1; }

.focus-label { flex: 1; font-weight: 600; font-size: 13px; color: var(--fg-secondary); }

.toggle-switch { width: 32px; height: 18px; background: var(--border); border-radius: 20px; position: relative; transition: background 0.3s; margin-left: auto; border: 1px solid var(--border); }
.toggle-switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: var(--fg-muted); border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle-switch.on { background: var(--accent); border-color: var(--accent); }
.toggle-switch.on::after { transform: translateX(14px); background: #fff; }

/* Subheaders */
.sidebar-subheader { 
  padding: 0 8px; 
  margin-top: 24px; 
  margin-bottom: 8px; 
  font-size: 11px; 
  color: var(--fg-muted); 
  font-weight: 600; 
  letter-spacing: 0.5px; 
}

.empty-state { padding: 0 8px; font-size: 12px; color: var(--fg-placeholder); font-style: italic; }

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
  color: var(--fg-muted); 
  transition: all 0.1s; 
}
.tree-item:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.tree-item.active { background: var(--accent); color: #fff; font-weight: 500; }
.tree-item.active .ui-icon, .tree-item.active .chevron-icon { opacity: 1; }
.tree-item.active .folder-label, .tree-item.active .truncate { color: #fff; }

.main-item { margin-bottom: 8px; font-weight: 500; color: var(--fg-secondary); }

/* Pin Input & Items */
.pin-input-group { padding: 0 8px; margin-bottom: 8px; display: flex; gap: 6px; }
.filter-input-small { 
  flex: 1; background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-secondary); 
  padding: 6px 8px; border-radius: 4px; font-size: 11px; outline: none; transition: border-color 0.2s; 
}
.filter-input-small:focus { border-color: var(--accent); }

.action-btn { 
  background: var(--surface-hover); border: 1px solid var(--border); color: var(--fg-muted); 
  border-radius: 4px; padding: 0 8px; cursor: pointer; transition: all 0.2s; 
  display: flex; align-items: center; justify-content: center;
}
.action-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

.delete-icon { margin-left: auto; color: var(--error); opacity: 0; transition: opacity 0.2s; display: flex; align-items: center; padding: 2px; border-radius: 4px; }
.delete-icon:hover { background: var(--error-muted); }
.tree-item:hover .delete-icon { opacity: 1; }

.pin-toggle {
  margin-left: auto;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--fg-placeholder);
  opacity: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: opacity 0.2s, color 0.2s, background 0.2s;
}

.sub-item:hover .pin-toggle,
.pin-toggle.pinned {
  opacity: 1;
}

.pin-toggle:hover {
  background: var(--surface-hover-strong);
}

.pin-toggle.pinned {
  color: var(--accent);
  opacity: 1;
}

.tree-item.active .pin-toggle {
  color: var(--fg-placeholder);
  opacity: 1;
}

.tree-item.active .pin-toggle.pinned {
  color: #fff;
}

/* Folders (IDE Style) */
.folder-group { margin-bottom: 4px; }
.folder-header { gap: 6px; }
.folder-label { font-weight: 500; color: var(--fg-secondary); }
.device-ip-badge {
  font-size: 10px;
  color: var(--fg-muted);
  opacity: 0.7;
  margin-left: auto;
  flex-shrink: 0;
  font-family: monospace;
}
.tree-item.active .device-ip-badge { color: #fff; opacity: 0.6; }

.folder-contents { display: flex; flex-direction: column; position: relative; margin-left: 22px; padding-left: 12px; border-left: 1px solid var(--border); }
.sub-item { position: relative; font-size: 12px; color: var(--fg-muted); }
.child-icon { opacity: 0.5; width: 16px !important; height: 16px !important; min-width: 16px !important; }
.pin-icon { color: var(--accent); }
.tree-item.active .pin-icon { color: #fff; }

/* Device context menu */
.device-ctx-overlay { position: fixed; inset: 0; z-index: 9999; }
.device-ctx-menu {
  position: fixed;
  background: var(--bg-elevated, var(--bg-sidebar));
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px;
  min-width: 160px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  z-index: 10000;
}
.ctx-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 7px 10px;
  background: none; border: none; border-radius: 5px;
  color: var(--fg-secondary); font-size: 12.5px;
  cursor: pointer; text-align: left;
  transition: background 0.1s, color 0.1s;
}
.ctx-item:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

/* Inline rename input */
.rename-input {
  flex: 1; min-width: 0;
  background: var(--bg-deepest);
  border: 1px solid var(--accent);
  border-radius: 4px;
  color: var(--fg-primary);
  font-size: 12.5px;
  padding: 1px 5px;
  outline: none;
}
.tree-item.active .rename-input {
  border-color: #fff;
  color: #fff;
  background: rgba(255,255,255,0.1);
}

/* Host Filter footer */
.host-filter-section {
  border-top: 1px solid var(--border);
  padding: 10px 16px;
  display: flex; flex-direction: column; gap: 5px;
  background: var(--bg-sidebar);
}
.host-filter-row {
  display: flex; align-items: center; justify-content: space-between;
}
.host-filter-label {
  font-size: 10px; font-weight: 600; color: var(--fg-muted);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.host-filter-edit {
  display: flex; align-items: center; gap: 4px;
  font-size: 10px; color: var(--fg-muted); background: none; border: none;
  cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all 0.15s;
}
.host-filter-edit:hover { color: var(--accent); background: var(--accent-muted, rgba(88,166,255,0.1)); }
.host-filter-status {
  display: flex; align-items: center; gap: 7px;
  cursor: pointer; padding: 4px 2px; border-radius: 5px; transition: background 0.15s;
}
.host-filter-status:hover { background: rgba(255,255,255,0.05); }
.host-filter-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.dot-all    { background: #10b981; }
.dot-ignore { background: #f59e0b; }
.dot-allow  { background: #3b82f6; }
.host-filter-desc { font-size: 11px; color: var(--fg-secondary); }
</style>