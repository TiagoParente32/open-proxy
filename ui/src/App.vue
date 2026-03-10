<script setup>
import { onMounted, onUnmounted } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'

// Import our new components!
import AppToolbar from './components/AppToolbar.vue'
import AppSidebar from './components/AppSidebar.vue'
import TrafficTable from './components/TrafficTable.vue'
import InspectorPane from './components/InspectorPane.vue'
import MapLocalModal from './components/MapLocalModal.vue'
import BreakpointHit from './components/BreakpointHit.vue'
import BreakpointsModal from './components/BreakpointsModal.vue'
import ComposeModal from './components/ComposeModal.vue'
import MapRemoteModal from './components/MapRemoteModal.vue'
import FilterBar from './components/FilterBar.vue'
import HighlightModal from './components/HighlightModal.vue'
import DeviceSetupModal from './components/DeviceSetupModal.vue'
// Import just the logic needed for the top-level app overlay (WebSockets & Context Menu)
import { 
  initWebSocket, 
  closeContextMenu, 
  contextMenu, 
  formatUrl, 
  pinnedSources, 
  activeFilter, 
  showMapModal, 
  mapLocalRules, 
  selectedRuleId,
  showBreakpointModal,
  breakpointRules,
  selectedBreakpointId,
  repeatRequest,
  openComposeModal,
  showMapRemoteModal,
  mapRemoteRules,
  selectedMapRemoteId
} from './store.js'

onMounted(() => {
  initWebSocket()
  document.addEventListener('click', closeContextMenu)
})

onUnmounted(() => {
  document.removeEventListener('click', closeContextMenu)
})

const handleEditAndRepeatFromContext = () => {
  if (contextMenu.value.request) {
    openComposeModal(contextMenu.value.request);
  }
  closeContextMenu();
}

const handleRepeatFromContext = () => {
  repeatRequest();
  closeContextMenu();
}


// --- COLOR & STAR LOGIC ---
const toggleStar = () => {
  if (contextMenu.value.request) {
    // Flip the boolean
    contextMenu.value.request.starred = !contextMenu.value.request.starred;
  }
  closeContextMenu();
}

const setRowColor = (colorClass) => {
  if (contextMenu.value.request) {
    // Assign a color string (e.g., 'red', 'blue', or null to clear)
    contextMenu.value.request.color = colorClass;
  }
  closeContextMenu();
}

// --- Context Menu Actions ---
const pinFromContextMenu = () => {
  if (contextMenu.value.request) {
    const host = formatUrl(contextMenu.value.request.url).host;
    if (host && !pinnedSources.value.includes(host)) {
      pinnedSources.value.push(host);
      activeFilter.value = { type: 'pinned', value: host };
    }
  }
  closeContextMenu();
}

const openMapRemoteModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    
    // Strip query params and escape dots for a safe regex pattern
    let defaultPattern = req.url.split('?')[0].replace(/\./g, '\\.');

    const newRule = { 
      id: Date.now(), 
      active: true, 
      pattern: defaultPattern, 
      target: 'http://localhost:8080' // Default target for dev servers
    };
    
    mapRemoteRules.value.unshift(newRule);
    selectedMapRemoteId.value = newRule.id;
  } else if (mapRemoteRules.value.length > 0 && !selectedMapRemoteId.value) {
    selectedMapRemoteId.value = mapRemoteRules.value[0].id;
  }
  
  showMapRemoteModal.value = true;
}

const openMapLocalModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
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

const openBreakpointModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    
    // Pro-tip: Strip the query parameters (everything after '?') so the regex is cleaner
    // and escape the dots so 'google.com' doesn't accidentally match 'google-com'
    let defaultPattern = req.url.split('?')[0].replace(/\./g, '\\.');

    const newRule = { 
      id: Date.now(), 
      active: true, 
      pattern: defaultPattern, 
      is_request: true, 
      is_response: false 
    };
    
    breakpointRules.value.unshift(newRule);
    selectedBreakpointId.value = newRule.id;
  } else if (breakpointRules.value.length > 0 && !selectedBreakpointId.value) {
    selectedBreakpointId.value = breakpointRules.value[0].id;
  }
  
  showBreakpointModal.value = true;
}
</script>

<template>
  <div class="app-wrapper">
    <AppToolbar />
    <FilterBar />
    <splitpanes class="default-theme custom-theme" style="flex: 1; overflow: hidden;">
      
      <pane min-size="15" size="20">
        <AppSidebar />
      </pane>

      <pane size="80">
        <splitpanes horizontal class="custom-theme">
          
          <pane min-size="20" size="45">
            <TrafficTable />
          </pane>

          <pane size="55">
            <InspectorPane />
          </pane>

        </splitpanes>
      </pane>

    </splitpanes>

   <div v-if="contextMenu.show" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }">
      <div class="context-menu-item" @click="handleRepeatFromContext">🔄 Repeat Request</div>
      <div class="context-menu-item" @click="handleEditAndRepeatFromContext">✏️ Edit & Repeat</div>
      
      <div class="context-menu-divider"></div>
      
      <div class="context-menu-item" @click="toggleStar">
        {{ contextMenu.request?.starred ? '⭐ Unstar Request' : '⭐ Star Request' }}
      </div>
      
      <div class="context-menu-colors">
        <div class="color-dot red" @click="setRowColor('red')" title="Red"></div>
        <div class="color-dot yellow" @click="setRowColor('yellow')" title="Yellow"></div>
        <div class="color-dot green" @click="setRowColor('green')" title="Green"></div>
        <div class="color-dot blue" @click="setRowColor('blue')" title="Blue"></div>
        <div class="color-dot clear" @click="setRowColor(null)" title="Clear Color">🚫</div>
      </div>
      
      <div class="context-menu-divider"></div>
      
      <div class="context-menu-item" @click="pinFromContextMenu">📌 Pin Domain</div>
      <div class="context-menu-item" @click="openMapLocalModalFromContext">⚡️ Map Local</div>
      <div class="context-menu-item" @click="openMapRemoteModalFromContext">🔀 Map Remote</div>
      <div class="context-menu-item" @click="openBreakpointModalFromContext">🛑 Add Breakpoint</div>
    </div>

    <MapLocalModal />
    <MapRemoteModal />
    <BreakpointHit />
    <BreakpointsModal />
    <ComposeModal />
    <HighlightModal />
    <DeviceSetupModal />
  </div>
</template>

<style>
:root { background-color: #1a1a1b; color: #cccccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; --bg-main: #1e1e1f; --bg-sidebar: #222223; --bg-active: #2a2d2e; --border: #333333; }
body { margin: 0; padding: 0; }
.app-wrapper { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* --- SPLITPANES THEME OVERRIDES --- */
.splitpanes.custom-theme .splitpanes__pane { background-color: var(--bg-main); }
.splitpanes.custom-theme .splitpanes__splitter { background-color: var(--border); transition: background-color 0.2s; }
.splitpanes.custom-theme .splitpanes__splitter:hover { background-color: #555; }
.splitpanes.custom-theme.splitpanes--vertical > .splitpanes__splitter { width: 3px; border-left: 1px solid #111; }
.splitpanes.custom-theme.splitpanes--horizontal > .splitpanes__splitter { height: 3px; border-top: 1px solid #111; }

/* --- SHARED UTILITIES --- */
.action-btn { background: transparent; border: 1px solid #444; color: #ccc; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.2s; outline: none !important; }
.action-btn:focus { outline: none !important; box-shadow: none !important; }
.action-btn:hover { background: #333; color: white; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.text-muted { color: #8b949e; }
.font-semibold { font-weight: 600; color: #e1e4e8; }
.text-green { color: #10b981 !important; }
.text-red { color: #ef4444 !important; }
.global-empty { display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px; }
.text-icon { font-size: 12px; color: #888; }

/* --- GLOBAL CONTEXT MENU --- */
.context-menu { position: fixed; background: #252526; border: 1px solid #444; box-shadow: 0 4px 12px rgba(0,0,0,0.5); border-radius: 6px; padding: 4px; z-index: 9999; min-width: 150px; }
.context-menu-item { padding: 6px 12px; font-size: 12px; color: #ccc; cursor: pointer; border-radius: 4px; display: flex; align-items: center; }
.context-menu-item:hover { background: #3b82f6; color: white; }

/* --- CODEMIRROR GLOBAL FIXES --- */
.cm-editor { height: 100% !important; outline: none !important; text-align: left !important; }
.cm-scroller { align-items: flex-start !important; justify-content: flex-start !important; }
.cm-content { padding: 12px 0 !important; }

/* --- TEXT SELECTION FIXES --- */
.traffic-table, .inspector-content, .modal-editor, .cm-editor, .cm-content { -webkit-user-select: text !important; user-select: text !important; cursor: text; }
.toolbar, .sidebar, .action-btn, .panel-tabs, .sidebar-header, .splitpanes__splitter { -webkit-user-select: none !important; user-select: none !important; }

.context-menu-divider { height: 1px; background: #333; margin: 4px 0; }

.context-menu-colors {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  gap: 8px;
}

.color-dot {
  width: 16px; height: 16px; border-radius: 50%; cursor: pointer;
  transition: transform 0.1s; border: 1px solid #444;
  display: flex; align-items: center; justify-content: center; font-size: 10px;
}
.color-dot:hover { transform: scale(1.2); }
.color-dot.red { background: #ef4444; }
.color-dot.yellow { background: #f59e0b; }
.color-dot.green { background: #10b981; }
.color-dot.blue { background: #3b82f6; }
.color-dot.clear { background: transparent; border: none; font-size: 12px; }
</style>