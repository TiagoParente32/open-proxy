<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'

import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'

const requests = ref([])
const connectionStatus = ref('Connecting...')
const selectedRequest = ref(null)

const activeReqTab = ref('Header')
const activeResTab = ref('Body')

// Proxy State
const isRecording = ref(true)
const proxyHost = ref('127.0.0.1:8080')

// Map Local State
const showMapModal = ref(false)
const mapLocalRules = ref([])
const selectedRuleId = ref(null)
let wsConnection = null;
const contextMenu = ref({ show: false, x: 0, y: 0, request: null })

const formatUrl = (fullUrl) => {
  try { const u = new URL(fullUrl); return { host: u.hostname, path: u.pathname + u.search } } 
  catch (e) { return { host: fullUrl, path: '' } }
}

// --- FOCUS MODE & SOURCES LOGIC ---
const isFocusMode = ref(false)
const pinnedSources = ref([])
const newPinnedSource = ref('')
const activeFilter = ref({ type: 'all', value: null }) 

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
  if (activeFilter.value.value === source) {
    activeFilter.value = { type: 'all', value: null }
  }
}

const pinFromContextMenu = () => {
  if (contextMenu.value.request) {
    const host = formatUrl(contextMenu.value.request.url).host;
    addPinnedSource(host);
  }
  closeContextMenu();
}

// Calculate which domains we have discovered that ARE NOT pinned
const unpinnedDomains = computed(() => {
  const domains = new Set()
  requests.value.forEach(req => {
    const host = formatUrl(req.url).host
    if (host) {
      // Check if it matches any of our pinned sources
      const isPinned = pinnedSources.value.some(p => host.toLowerCase().includes(p.toLowerCase()))
      if (!isPinned) domains.add(host)
    }
  })
  return Array.from(domains).sort()
})

const filteredRequests = computed(() => {
  let baseList = requests.value;

  // 1. If Focus Mode is ON, strictly filter to ONLY show pinned sources
  if (isFocusMode.value) {
    if (pinnedSources.value.length === 0) return []; // Nothing pinned = nothing shown
    
    baseList = baseList.filter(req => {
      const urlLower = req.url.toLowerCase();
      return pinnedSources.value.some(pinned => urlLower.includes(pinned.toLowerCase()));
    });
  }

  // 2. Apply the specific item clicked in the sidebar
  if (activeFilter.value.type === 'all') return baseList;

  if (activeFilter.value.type === 'pinned' || activeFilter.value.type === 'unpinned') {
    const pattern = activeFilter.value.value.toLowerCase();
    return baseList.filter(req => req.url.toLowerCase().includes(pattern));
  }

  return baseList;
})
// ------------------------------------------------

onMounted(() => {
  wsConnection = new WebSocket("ws://127.0.0.1:8765")
  wsConnection.onopen = () => { connectionStatus.value = '🟢 Intercepting Traffic' }
  wsConnection.onmessage = (event) => {
    const payload = JSON.parse(event.data)
    if (payload.type === "NEW_REQUEST") {
      requests.value.unshift(payload.data)
      if (requests.value.length > 2000) requests.value.pop()
    } else if (payload.type === "UPDATE_REQUEST") {
      const reqIndex = requests.value.findIndex(r => r.id === payload.data.id)
      if (reqIndex !== -1) Object.assign(requests.value[reqIndex], payload.data)
    }
  }
  wsConnection.onclose = () => { connectionStatus.value = '🔴 Disconnected' }
  document.addEventListener('click', closeContextMenu)
})

onUnmounted(() => { document.removeEventListener('click', closeContextMenu) })

const toggleRecording = () => {
  isRecording.value = !isRecording.value
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    wsConnection.send(JSON.stringify({ type: "TOGGLE_PROXY", is_recording: isRecording.value }))
  }
}

const openContextMenu = (e, req) => {
  selectedRequest.value = req; 
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, request: req }
}
const closeContextMenu = () => { contextMenu.value.show = false }

const activeRule = computed(() => mapLocalRules.value.find(r => r.id === selectedRuleId.value))
const extensions = [json(), oneDark, EditorView.lineWrapping] 

const openMapLocalModal = (fromContextMenu = false) => {
  closeContextMenu();
  if (fromContextMenu && contextMenu.value.request) {
    const req = contextMenu.value.request;
    const realStatus = req.status !== '...' ? Number(req.status) : 200;
    const realHeaders = req.res_headers && Object.keys(req.res_headers).length > 0 ? JSON.stringify(req.res_headers, null, 2) : '{\n  "Content-Type": "application/json"\n}';
    let realBody = req.res_body || '';
    try { if (realBody) realBody = JSON.stringify(JSON.parse(realBody), null, 2); } catch (e) {}

    const newRule = { id: Date.now(), active: true, pattern: req.url.split('?')[0], status: realStatus, headers: realHeaders, body: realBody };
    mapLocalRules.value.unshift(newRule);
    selectedRuleId.value = newRule.id;
  } else if (mapLocalRules.value.length > 0 && !selectedRuleId.value) {
    selectedRuleId.value = mapLocalRules.value[0].id;
  }
  showMapModal.value = true;
}

const addNewRule = () => {
  const newRule = { id: Date.now(), active: true, pattern: 'api.example.com/*', status: 200, headers: '{\n  "Content-Type": "application/json"\n}', body: '' }
  mapLocalRules.value.unshift(newRule)
  selectedRuleId.value = newRule.id
}
const deleteRule = (id) => {
  mapLocalRules.value = mapLocalRules.value.filter(r => r.id !== id)
  if (selectedRuleId.value === id) selectedRuleId.value = mapLocalRules.value.length ? mapLocalRules.value[0].id : null
}
const saveAndApplyRules = () => {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) { wsConnection.send(JSON.stringify({ type: "UPDATE_MAP_LOCAL_RULES", rules: mapLocalRules.value })) }
  showMapModal.value = false
}
const getMethodColor = (method) => {
  const colors = { GET: '#3b82f6', POST: '#10b981', PUT: '#f59e0b', DELETE: '#ef4444', OPTIONS: '#8b5cf6' }
  return colors[method] || '#8b949e'
}
const formatJson = (str) => {
  if (!str) return '// No body data'
  try { return JSON.stringify(JSON.parse(str), null, 2) } catch (e) { return str }
}
</script>

<template>
  <div class="app-wrapper">
    <header class="toolbar">
      <div class="actions">
        <button class="action-btn icon-btn" :class="isRecording ? 'btn-pause' : 'btn-record'" @click="toggleRecording" :title="isRecording ? 'Pause Intercepting' : 'Resume Intercepting'">
          <svg v-if="isRecording" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
        </button>
      </div>

      <div class="title" style="display: flex; align-items: center; gap: 8px;">
        <span class="status-indicator" :class="isRecording ? 'active' : 'inactive'"></span>
        OpenProxy running on {{ proxyHost }}
      </div>

      <div class="actions" style="display: flex; gap: 10px;">
        <button class="action-btn" @click="openMapLocalModal(false)">⚡️ Map Local</button>
        <button class="action-btn" @click="requests = []">🚫 Clear</button>
      </div>
    </header>

    <splitpanes class="default-theme custom-theme" style="flex: 1; overflow: hidden;">
      
      <pane min-size="15" size="20">
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
      </pane>

      <pane size="80">
        <splitpanes horizontal class="custom-theme">
          <pane min-size="20" size="45">
            <div class="table-container">
              <table class="traffic-table">
                <thead><tr><th style="width: 60px;">ID</th><th style="width: 70px;">Method</th><th style="width: 60px;">Status</th><th style="width: 200px;">Host</th><th>Path</th></tr></thead>
                <tbody>
                  <tr v-for="req in filteredRequests" :key="req.id" @click="selectedRequest = req" @contextmenu.prevent="openContextMenu($event, req)" :class="{ selected: selectedRequest?.id === req.id }">
                    <td class="text-muted text-id">{{ req.id.substring(0, 5) }}</td>
                    <td><span class="method-badge" :style="{ backgroundColor: getMethodColor(req.method) + '20', color: getMethodColor(req.method) }">{{ req.method }}</span></td>
                    <td><span v-if="req.status === '...'" class="text-muted">...</span><span v-else class="status-badge" :class="{'text-green': req.status < 400, 'text-red': req.status >= 400}">{{ req.status }}</span></td>
                    <td class="font-semibold truncate">{{ formatUrl(req.url).host }}</td><td class="text-muted truncate">{{ formatUrl(req.url).path }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-if="filteredRequests.length === 0" class="global-empty">
                <span v-if="isFocusMode && pinnedSources.length === 0">Add a Pinned Source to see traffic.</span>
                <span v-else>Waiting for traffic...</span>
              </div>
            </div>
          </pane>

          <pane size="55">
            <div class="detail-container">
              <div v-if="selectedRequest" style="height: 100%;">
                <splitpanes class="custom-theme">
                  <pane size="50">
                    <div class="inspector-panel">
                      <div class="inspector-toolbar">
                        <span class="panel-title">Request</span>
                        <div class="panel-tabs"><span v-for="tab in ['Header', 'Body']" :key="tab" @click="activeReqTab = tab" class="panel-tab" :class="{ active: activeReqTab === tab }">{{ tab }}</span></div>
                      </div>
                      <div class="inspector-content">
                        <table v-if="activeReqTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.req_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
                        <div v-if="activeReqTab === 'Body'" style="height: 100%;"><codemirror :model-value="formatJson(selectedRequest.req_body)" :style="{ height: '100%' }" :extensions="extensions" :disabled="true" /></div>
                      </div>
                    </div>
                  </pane>
                  <pane size="50">
                    <div class="inspector-panel">
                      <div class="inspector-toolbar">
                        <span class="panel-title" :class="{'text-green': selectedRequest.status < 400, 'text-red': selectedRequest.status >= 400}">Response {{ selectedRequest.status !== '...' ? `(${selectedRequest.status})` : '' }}</span>
                        <div class="panel-tabs"><span v-for="tab in ['Header', 'Body']" :key="tab" @click="activeResTab = tab" class="panel-tab" :class="{ active: activeResTab === tab }">{{ tab }}</span></div>
                      </div>
                      <div class="inspector-content">
                        <table v-if="activeResTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.res_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
                        <div v-if="activeResTab === 'Body'" style="height: 100%;"><codemirror :model-value="formatJson(selectedRequest.res_body)" :style="{ height: '100%' }" :extensions="extensions" :disabled="true" /></div>
                      </div>
                    </div>
                  </pane>
                </splitpanes>
              </div>
              <div v-else class="global-empty">Select a request to view details.</div>
            </div>
          </pane>
        </splitpanes>
      </pane>
    </splitpanes>

    <div v-if="contextMenu.show" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }">
      <div class="context-menu-item" @click="pinFromContextMenu">📌 Pin Domain</div>
      <div class="context-menu-item" @click="openMapLocalModal(true)">⚡️ Map Local</div>
    </div>

    <div v-if="showMapModal" class="modal-overlay" @mousedown.self="showMapModal = false"><div class="modal-content large"><div class="modal-sidebar"><div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;"><strong style="color: white; font-size: 13px;">Map Local Rules</strong><button class="action-btn" @click="addNewRule">+ Add</button></div><div class="rule-list"><div v-for="rule in mapLocalRules" :key="rule.id" class="rule-item" :class="{ active: selectedRuleId === rule.id }" @click="selectedRuleId = rule.id"><input type="checkbox" v-model="rule.active" @click.stop /><span class="truncate" style="flex: 1; font-family: monospace; font-size: 11px;">{{ rule.pattern || 'New Rule' }}</span><span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold;" @click.stop="deleteRule(rule.id)">×</span></div><div v-if="mapLocalRules.length === 0" class="empty-state" style="padding: 20px;">No rules yet.</div></div></div><div class="modal-editor"><div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;"><div style="padding: 20px 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px;"><div class="form-group"><label class="modal-label">URL Pattern (Regex)</label><input type="text" v-model="activeRule.pattern" class="modal-input" placeholder="api.example.com/*" /></div><div class="form-group" style="max-width: 150px;"><label class="modal-label">Status Code</label><input type="number" v-model="activeRule.status" class="modal-input" /></div><div class="form-group"><label class="modal-label">Response Headers (JSON)</label><div class="code-editor-wrapper" style="height: 140px; flex-shrink: 0;"><codemirror v-model="activeRule.headers" placeholder="Enter headers as JSON..." :style="{ height: '100%' }" :indent-with-tab="true" :tab-size="2" :extensions="extensions" /></div></div><div class="form-group" style="flex: 1; display: flex; flex-direction: column;"><label class="modal-label">Response Body</label><div class="code-editor-wrapper"><codemirror v-model="activeRule.body" placeholder="Enter JSON response..." :style="{ height: '100%' }" :autofocus="true" :indent-with-tab="true" :tab-size="2" :extensions="extensions" /></div></div></div><div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar);"><button class="action-btn" @click="showMapModal = false">Cancel</button><button class="action-btn" style="background: #3b82f6; color: white; border-color: #3b82f6; padding: 6px 16px;" @click="saveAndApplyRules">Save & Apply</button></div></div><div v-else class="global-empty">Select or create a rule to edit.</div></div></div></div>
  </div>
</template>

<style>
/* ... BASE STYLES ... */
:root { background-color: #1a1a1b; color: #cccccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; --bg-main: #1e1e1f; --bg-sidebar: #222223; --bg-active: #2a2d2e; --border: #333333; }
body { margin: 0; padding: 0; }
.app-wrapper { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.splitpanes.custom-theme .splitpanes__pane { background-color: var(--bg-main); }
.splitpanes.custom-theme .splitpanes__splitter { background-color: var(--border); transition: background-color 0.2s; }
.splitpanes.custom-theme .splitpanes__splitter:hover { background-color: #555; }
.splitpanes.custom-theme.splitpanes--vertical > .splitpanes__splitter { width: 3px; border-left: 1px solid #111; }
.splitpanes.custom-theme.splitpanes--horizontal > .splitpanes__splitter { height: 3px; border-top: 1px solid #111; }
.sidebar, .table-container, .detail-container { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.toolbar { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background-color: var(--bg-sidebar); border-bottom: 1px solid var(--border); font-size: 13px; }
.toolbar .title { font-weight: 600; color: #ffffff; }

.action-btn { background: transparent; border: 1px solid #444; color: #ccc; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.2s; outline: none !important; }
.action-btn:focus { outline: none !important; box-shadow: none !important; }
.action-btn:hover { background: #333; color: white; }
.icon-btn { display: flex; align-items: center; justify-content: center; padding: 4px 8px; height: 26px; width: 32px; }
.btn-pause { color: #ef4444; border-color: rgba(239, 68, 68, 0.4); }
.btn-pause:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }
.btn-record { color: #10b981; border-color: rgba(16, 185, 129, 0.4); }
.btn-record:hover { background: rgba(16, 185, 129, 0.1); border-color: #10b981; }

.status-indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; }
.status-indicator.active { background-color: #10b981; box-shadow: 0 0 8px #10b981; }
.status-indicator.inactive { background-color: #ef4444; box-shadow: 0 0 8px #ef4444; }

/* FOCUS MODE CSS */
.sidebar { background-color: var(--bg-sidebar); }
.focus-mode-wrapper { padding: 12px 16px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.2s; }
.focus-mode-wrapper:hover { background: #2a2d2e; }
.focus-mode-wrapper.focus-on { background: rgba(59, 130, 246, 0.1); border-bottom: 1px solid rgba(59, 130, 246, 0.3); }
.toggle-switch { width: 32px; height: 18px; background: #444; border-radius: 20px; position: relative; transition: background 0.3s; }
.toggle-switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; background: white; border-radius: 50%; transition: transform 0.3s; }
.toggle-switch.on { background: #3b82f6; }
.toggle-switch.on::after { transform: translateX(14px); }

.sidebar-subheader { padding: 4px 16px; margin-top: 12px; margin-bottom: 4px; font-size: 10px; color: #777; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.filter-input-small { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 4px 8px; border-radius: 4px; font-size: 11px; outline: none; transition: border-color 0.2s; }
.filter-input-small:focus { border-color: #3b82f6; }
.delete-icon { margin-left: auto; color: #ef4444; font-weight: bold; font-size: 14px; opacity: 0; transition: opacity 0.2s; }
.tree-item:hover .delete-icon { opacity: 1; }

.tree-container { padding: 0 8px; overflow-y: auto; flex: 1; }
.tree-item { padding: 6px 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; border-radius: 4px; margin-bottom: 2px; font-size: 12px; color: #ccc; transition: background 0.1s; }
.tree-item:hover { background: #2a2d2e; color: #fff; }
.tree-item.active { background: #3b82f6; color: #fff; }
.tree-item.active .text-icon { color: #fff; }
.text-icon { font-size: 12px; color: #888; }

.table-container { overflow-y: auto; }
.traffic-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
.traffic-table th { text-align: left; padding: 6px 10px; background-color: var(--bg-sidebar); color: #888; font-weight: 500; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 1; }
.traffic-table td { padding: 4px 10px; border-bottom: 1px solid #282829; white-space: nowrap; }
.traffic-table tbody tr:hover { background-color: var(--bg-active); cursor: pointer; }
.traffic-table tbody tr.selected { background-color: #1e3a5f; color: #fff; }

.inspector-panel { display: flex; flex-direction: column; height: 100%; background: var(--bg-main); }
.inspector-toolbar { display: flex; align-items: center; gap: 16px; padding: 0 12px; background-color: var(--bg-sidebar); border-bottom: 1px solid var(--border); height: 32px; flex-shrink: 0; }
.panel-title { font-size: 12px; font-weight: 700; color: #ccc; }
.panel-tabs { display: flex; gap: 12px; font-size: 11px; font-weight: 500; color: #888; height: 100%; }
.panel-tab { cursor: pointer; display: flex; align-items: center; border-bottom: 2px solid transparent; transition: color 0.2s; }
.panel-tab:hover { color: #ccc; }
.panel-tab.active { color: #3b82f6; border-bottom-color: #3b82f6; }

.inspector-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.kv-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
.kv-table tr { border-bottom: 1px solid #222; }
.kv-table td { padding: 8px 16px !important; vertical-align: top; word-wrap: break-word; }
.kv-key { width: 30%; color: #8b949e; font-weight: 500; text-align: left; border-right: 1px solid var(--border); }
.kv-value { width: 70%; color: #e1e4e8; font-family: 'Consolas', monospace; text-align: left; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.text-muted { color: #8b949e; }
.text-id { font-family: monospace; font-size: 11px; }
.font-semibold { font-weight: 600; color: #e1e4e8; }
.text-green { color: #10b981 !important; }
.text-red { color: #ef4444 !important; }
.method-badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }
.status-badge { padding: 2px 6px; border-radius: 4px; background: #333; font-size: 10px; font-weight: bold; border: 1px solid #444; }
.global-empty { display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px; }

.context-menu { position: fixed; background: #252526; border: 1px solid #444; box-shadow: 0 4px 12px rgba(0,0,0,0.5); border-radius: 6px; padding: 4px; z-index: 9999; min-width: 150px; }
.context-menu-item { padding: 6px 12px; font-size: 12px; color: #ccc; cursor: pointer; border-radius: 4px; display: flex; align-items: center; }
.context-menu-item:hover { background: #3b82f6; color: white; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 100; display: flex; justify-content: center; align-items: center; }
.modal-content.large { display: flex; background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; width: 1100px; height: 750px; min-width: 800px; min-height: 500px; max-width: 95vw; max-height: 95vh; box-shadow: 0 10px 40px rgba(0,0,0,0.6); resize: both; overflow: hidden; }
.modal-sidebar { width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.rule-list { flex: 1; overflow-y: auto; }
.rule-item { padding: 10px 16px; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 10px; cursor: pointer; transition: background 0.2s; }
.rule-item:hover { background: #2a2d2e; }
.rule-item.active { background: #1e3a5f; }
.modal-editor { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #3b82f6; }
.code-editor-wrapper { flex: 1; border: 1px solid #444; border-radius: 6px; overflow: hidden; font-size: 13px; min-width: 0; max-width: 100%; }

.cm-editor { height: 100% !important; outline: none !important; text-align: left !important; }
.cm-scroller { align-items: flex-start !important; justify-content: flex-start !important; }
.cm-content { padding: 12px 0 !important; }

.traffic-table, 
.inspector-content, 
.modal-editor, 
.cm-editor,
.cm-content {
  -webkit-user-select: text !important;
  user-select: text !important;
  cursor: text;
}

/* 2. Keep structural UI elements unselectable so they feel native */
.toolbar, 
.sidebar, 
.action-btn, 
.panel-tabs,
.sidebar-header,
.splitpanes__splitter {
  -webkit-user-select: none !important;
  user-select: none !important;
}
</style>